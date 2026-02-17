#!/usr/bin/env python3
"""
Externalize embedded KaroSpace payloads from a single self-contained HTML file.

Supported embedded patterns:
1) <script type="application/json" id="..."> ... </script>
2) JS assignment with JSON literal:
   - const DATA = {...};
   - let DATA = {...};
   - var DATA = {...};
   - window.__DATA__ = {...};
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCRIPT_TAG_RE = re.compile(
    r"(?is)<script\b(?P<attrs>[^>]*)>(?P<body>.*?)</script>"
)

ASSIGNMENT_START_RE = re.compile(
    r"""
    (?P<lhs>
        (?:(?P<decl_kind>const|let|var)\s+(?P<decl_name>[A-Za-z_$][\w$]*)\s*=\s*)
        |
        (?:window\.(?P<window_name>[A-Za-z_$][\w$]*)\s*=\s*)
    )
    """,
    re.VERBOSE,
)


JSON_DECODER = json.JSONDecoder()


@dataclass
class BlobCandidate:
    detector: str
    start: int
    end: int
    payload_bytes: int
    raw_json: str
    value: Any
    script_attrs: str | None = None
    script_id: str | None = None
    script_had_id: bool = False
    assignment_style: str | None = None
    decl_kind: str | None = None
    variable_name: str | None = None


@dataclass
class Replacement:
    start: int
    end: int
    text: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Externalize embedded KaroSpace data payloads from HTML."
    )
    parser.add_argument("--input", required=True, help="Input KaroSpace HTML file.")
    parser.add_argument("--outdir", required=True, help="Output root directory.")
    parser.add_argument("--slug", required=True, help="Viewer slug (e.g. RRMap).")
    parser.add_argument(
        "--mode",
        choices=["auto", "single", "directory"],
        default="auto",
        help="auto: threshold-based decision, single: always copy, directory: always externalize",
    )
    parser.add_argument(
        "--threshold-mb",
        type=float,
        default=80.0,
        help="If auto and embedded payload <= threshold, keep as single HTML.",
    )
    parser.add_argument(
        "--chunk-mb",
        type=float,
        default=50.0,
        help="Target chunk size for externalized data files.",
    )
    return parser.parse_args()


def validate_slug(slug: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9._-]+", slug):
        raise ValueError(
            f"Invalid slug '{slug}'. Use only letters, numbers, dot, underscore, hyphen."
        )


def extract_attr(attrs: str, name: str) -> str | None:
    pattern = re.compile(
        rf"""\b{re.escape(name)}\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'=<>`]+))""",
        re.IGNORECASE,
    )
    match = pattern.search(attrs)
    if not match:
        return None
    return next((value for value in match.groups() if value is not None), None)


def skip_whitespace(text: str, pos: int) -> int:
    length = len(text)
    while pos < length and text[pos].isspace():
        pos += 1
    return pos


def detect_assignment_candidates(script_body: str, base_offset: int) -> list[BlobCandidate]:
    candidates: list[BlobCandidate] = []
    scan_pos = 0
    consumed_until = 0

    while True:
        match = ASSIGNMENT_START_RE.search(script_body, scan_pos)
        if not match:
            break

        if match.start() < consumed_until:
            scan_pos = consumed_until
            continue

        value_start = skip_whitespace(script_body, match.end())
        if value_start >= len(script_body) or script_body[value_start] not in "[{":
            scan_pos = match.end()
            continue

        try:
            value, rel_end = JSON_DECODER.raw_decode(script_body[value_start:])
        except json.JSONDecodeError:
            scan_pos = match.end()
            continue

        value_end = value_start + rel_end
        stmt_end = skip_whitespace(script_body, value_end)
        if stmt_end < len(script_body) and script_body[stmt_end] == ";":
            stmt_end += 1

        raw_json = script_body[value_start:value_end]
        payload_bytes = len(raw_json.encode("utf-8"))
        assignment_style = "window" if match.group("window_name") else "declaration"
        variable_name = match.group("window_name") or match.group("decl_name")

        candidates.append(
            BlobCandidate(
                detector="js_assignment",
                start=base_offset + match.start(),
                end=base_offset + stmt_end,
                payload_bytes=payload_bytes,
                raw_json=raw_json,
                value=value,
                assignment_style=assignment_style,
                decl_kind=match.group("decl_kind"),
                variable_name=variable_name,
            )
        )

        consumed_until = stmt_end
        scan_pos = stmt_end

    return candidates


def detect_candidates(html: str) -> list[BlobCandidate]:
    candidates: list[BlobCandidate] = []
    generated_script_counter = 0

    for script_match in SCRIPT_TAG_RE.finditer(html):
        attrs = script_match.group("attrs") or ""
        body = script_match.group("body") or ""
        body_start = script_match.start("body")
        script_type = (extract_attr(attrs, "type") or "").lower().strip()

        if script_type == "application/json":
            raw_body = body.strip()
            if not raw_body:
                continue

            try:
                parsed = json.loads(raw_body)
            except json.JSONDecodeError:
                continue

            existing_id = extract_attr(attrs, "id")
            script_id = existing_id or f"karospace_data_{generated_script_counter:03d}"
            if existing_id is None:
                generated_script_counter += 1

            candidates.append(
                BlobCandidate(
                    detector="script_json",
                    start=script_match.start(),
                    end=script_match.end(),
                    payload_bytes=len(raw_body.encode("utf-8")),
                    raw_json=raw_body,
                    value=parsed,
                    script_attrs=attrs,
                    script_id=script_id,
                    script_had_id=existing_id is not None,
                )
            )
            continue

        candidates.extend(detect_assignment_candidates(body, base_offset=body_start))

    candidates.sort(key=lambda c: c.start)
    return candidates


def split_utf8_text_by_bytes(text: str, max_bytes: int) -> list[str]:
    if max_bytes <= 0:
        raise ValueError("max_bytes must be > 0")

    payload = text.encode("utf-8")
    total = len(payload)
    if total == 0:
        return [""]

    chunks: list[str] = []
    idx = 0
    while idx < total:
        end = min(idx + max_bytes, total)
        while end < total and (payload[end] & 0b1100_0000) == 0b1000_0000:
            end -= 1
        if end <= idx:
            end = min(idx + max_bytes, total)
        chunks.append(payload[idx:end].decode("utf-8"))
        idx = end

    return chunks


def split_array_for_target_bytes(items: list[Any], target_bytes: int) -> list[list[Any]]:
    if target_bytes <= 0:
        raise ValueError("target_bytes must be > 0")

    if not items:
        return [[]]

    chunks: list[list[Any]] = []
    current: list[Any] = []
    current_bytes = 2  # []

    for item in items:
        item_json = json.dumps(item, ensure_ascii=False, separators=(",", ":"))
        item_bytes = len(item_json.encode("utf-8"))
        extra_comma = 1 if current else 0
        projected = current_bytes + extra_comma + item_bytes

        if current and projected > target_bytes:
            chunks.append(current)
            current = [item]
            current_bytes = 2 + item_bytes
            continue

        if current:
            current_bytes += 1
        current.append(item)
        current_bytes += item_bytes

    if current:
        chunks.append(current)

    return chunks


def write_array_chunks(
    value: list[Any], data_dir: Path, chunk_target_bytes: int, chunk_counter: int
) -> tuple[list[dict[str, Any]], int, str]:
    entries: list[dict[str, Any]] = []
    array_slices = split_array_for_target_bytes(value, chunk_target_bytes)

    for arr in array_slices:
        filename = f"chunk_{chunk_counter:03d}.json"
        chunk_path = data_dir / filename
        json_text = json.dumps(arr, ensure_ascii=False, separators=(",", ":"))
        chunk_path.write_text(json_text, encoding="utf-8")
        entries.append(
            {
                "path": f"data/{filename}",
                "bytes": len(json_text.encode("utf-8")),
                "items": len(arr),
                "format": "json_array",
            }
        )
        chunk_counter += 1

    return entries, chunk_counter, "array_slices"


def write_text_chunks(
    value: Any, data_dir: Path, chunk_target_bytes: int, chunk_counter: int
) -> tuple[list[dict[str, Any]], int, str]:
    entries: list[dict[str, Any]] = []
    json_text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    parts = split_utf8_text_by_bytes(json_text, chunk_target_bytes)

    for part in parts:
        filename = f"chunk_{chunk_counter:03d}.txt"
        chunk_path = data_dir / filename
        chunk_path.write_text(part, encoding="utf-8")
        entries.append(
            {
                "path": f"data/{filename}",
                "bytes": len(part.encode("utf-8")),
                "format": "json_text_piece",
            }
        )
        chunk_counter += 1

    return entries, chunk_counter, "text_concat"


def ensure_loader_runtime(html: str) -> str:
    runtime_marker = "KAROSPACE_LOADER_RUNTIME"
    if runtime_marker in html:
        return html

    loader_script = """
<script>
/* KAROSPACE_LOADER_RUNTIME */
(function () {
  if (window.__KAROSPACE_DATA_LOADER__) {
    return;
  }

  function getTextSync(path) {
    var req = new XMLHttpRequest();
    req.open("GET", path, false);
    req.send(null);
    if (req.status < 200 || req.status >= 300) {
      throw new Error("Failed to load " + path + " (status " + req.status + ")");
    }
    return req.responseText;
  }

  function buildIndex(manifest) {
    var index = {};
    var blobs = manifest.blobs || [];
    for (var i = 0; i < blobs.length; i += 1) {
      index[blobs[i].key] = blobs[i];
    }
    return index;
  }

  function reconstruct(blob, chunkTexts) {
    if (blob.strategy === "array_slices") {
      var merged = [];
      for (var i = 0; i < chunkTexts.length; i += 1) {
        var arr = JSON.parse(chunkTexts[i]);
        if (!Array.isArray(arr)) {
          throw new Error("Expected array chunk for " + blob.key);
        }
        merged = merged.concat(arr);
      }
      return merged;
    }
    if (blob.strategy === "text_concat") {
      return JSON.parse(chunkTexts.join(""));
    }
    throw new Error("Unsupported chunk strategy: " + blob.strategy);
  }

  var loader = {
    _manifest: null,
    _manifestIndex: null,
    _manifestPromise: null,
    _cache: {},
    _blobPromises: {},

    getManifestSync: function () {
      if (!this._manifest) {
        this._manifest = JSON.parse(getTextSync("./manifest.json"));
        this._manifestIndex = buildIndex(this._manifest);
      }
      return this._manifest;
    },

    getManifestAsync: function () {
      if (this._manifest) {
        return Promise.resolve(this._manifest);
      }
      if (this._manifestPromise) {
        return this._manifestPromise;
      }

      var self = this;
      this._manifestPromise = fetch("./manifest.json")
        .then(function (response) {
          if (!response.ok) {
            throw new Error("Failed to load manifest.json (" + response.status + ")");
          }
          return response.json();
        })
        .then(function (manifest) {
          self._manifest = manifest;
          self._manifestIndex = buildIndex(manifest);
          return manifest;
        });
      return this._manifestPromise;
    },

    getSync: function (key) {
      if (Object.prototype.hasOwnProperty.call(this._cache, key)) {
        return this._cache[key];
      }

      this.getManifestSync();
      var blob = this._manifestIndex[key];
      if (!blob) {
        throw new Error("Blob not found in manifest: " + key);
      }

      var chunks = blob.chunks || [];
      var texts = [];
      for (var i = 0; i < chunks.length; i += 1) {
        texts.push(getTextSync("./" + chunks[i].path));
      }

      var value = reconstruct(blob, texts);
      this._cache[key] = value;
      window.__KAROSPACE_DATA__ = window.__KAROSPACE_DATA__ || {};
      window.__KAROSPACE_DATA__[key] = value;
      return value;
    },

    getAsync: function (key) {
      if (Object.prototype.hasOwnProperty.call(this._cache, key)) {
        return Promise.resolve(this._cache[key]);
      }
      if (this._blobPromises[key]) {
        return this._blobPromises[key];
      }

      var self = this;
      this._blobPromises[key] = this.getManifestAsync().then(function () {
        var blob = self._manifestIndex[key];
        if (!blob) {
          throw new Error("Blob not found in manifest: " + key);
        }
        var chunks = blob.chunks || [];
        return Promise.all(
          chunks.map(function (chunk) {
            return fetch("./" + chunk.path).then(function (response) {
              if (!response.ok) {
                throw new Error("Failed to load " + chunk.path + " (" + response.status + ")");
              }
              return response.text();
            });
          })
        ).then(function (chunkTexts) {
          var value = reconstruct(blob, chunkTexts);
          self._cache[key] = value;
          window.__KAROSPACE_DATA__ = window.__KAROSPACE_DATA__ || {};
          window.__KAROSPACE_DATA__[key] = value;
          return value;
        });
      });
      return this._blobPromises[key];
    }
  };

  window.__KAROSPACE_DATA__ = window.__KAROSPACE_DATA__ || {};
  window.__KAROSPACE_DATA_LOADER__ = loader;

  if (typeof fetch === "function") {
    loader.getManifestAsync().catch(function () {});
  }
})();
</script>
""".strip()

    head_match = re.search(r"(?is)<head\b[^>]*>", html)
    if head_match:
        idx = head_match.end()
        return html[:idx] + "\n" + loader_script + "\n" + html[idx:]

    html_match = re.search(r"(?is)<html\b[^>]*>", html)
    if html_match:
        idx = html_match.end()
        return html[:idx] + "\n" + loader_script + "\n" + html[idx:]

    return loader_script + "\n" + html


def replacement_for_candidate(candidate: BlobCandidate, blob_key: str) -> str:
    if candidate.detector == "script_json":
        attrs = candidate.script_attrs or ""
        if not candidate.script_had_id and candidate.script_id:
            attrs = f"{attrs} id=\"{candidate.script_id}\""
        if not candidate.script_id:
            raise ValueError("script_json candidate missing script_id")

        return (
            f"<script{attrs}></script>\n"
            "<script>\n"
            "(function () {\n"
            f"  var __kData = window.__KAROSPACE_DATA_LOADER__.getSync({json.dumps(blob_key)});\n"
            f"  var __kNode = document.getElementById({json.dumps(candidate.script_id)});\n"
            "  if (__kNode) {\n"
            "    __kNode.textContent = JSON.stringify(__kData);\n"
            "  }\n"
            "})();\n"
            "</script>"
        )

    if candidate.detector == "js_assignment":
        if candidate.assignment_style == "window":
            return (
                f"window.{candidate.variable_name} = "
                f"window.__KAROSPACE_DATA_LOADER__.getSync({json.dumps(blob_key)});"
            )
        return (
            f"{candidate.decl_kind} {candidate.variable_name} = "
            f"window.__KAROSPACE_DATA_LOADER__.getSync({json.dumps(blob_key)});"
        )

    raise ValueError(f"Unsupported candidate detector '{candidate.detector}'")


def apply_replacements(html: str, replacements: list[Replacement]) -> str:
    updated = html
    for repl in sorted(replacements, key=lambda r: r.start, reverse=True):
        updated = updated[: repl.start] + repl.text + updated[repl.end :]
    return updated


def make_backup_copy(input_path: Path, outdir: Path, slug: str) -> Path:
    backup_dir = outdir / "_backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / f"{slug}.original.html"
    shutil.copy2(input_path, backup_path)
    return backup_path


def copy_single(input_path: Path, outdir: Path, slug: str) -> Path:
    outdir.mkdir(parents=True, exist_ok=True)
    target = outdir / f"{slug}.html"

    if input_path.resolve() == target.resolve():
        raise ValueError("Input and output are the same file path.")

    shutil.copy2(input_path, target)
    return target


def bytes_to_mb(num_bytes: int) -> float:
    return num_bytes / (1024 * 1024)


def externalize_to_directory(
    html: str,
    candidates: list[BlobCandidate],
    outdir: Path,
    slug: str,
    chunk_mb: float,
) -> dict[str, Any]:
    if not candidates:
        raise RuntimeError("No externalizable payload candidates were found.")

    chunk_target_bytes = int(chunk_mb * 1024 * 1024)
    if chunk_target_bytes <= 0:
        raise ValueError("--chunk-mb must be greater than zero.")

    viewer_dir = outdir / slug
    data_dir = viewer_dir / "data"
    viewer_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)

    manifest: dict[str, Any] = {
        "version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "slug": slug,
        "chunk_target_mb": chunk_mb,
        "blobs": [],
    }

    replacements: list[Replacement] = []
    chunk_counter = 0

    for idx, candidate in enumerate(candidates):
        blob_key = f"blob_{idx:03d}"
        if isinstance(candidate.value, list):
            chunk_entries, chunk_counter, strategy = write_array_chunks(
                candidate.value, data_dir, chunk_target_bytes, chunk_counter
            )
        else:
            chunk_entries, chunk_counter, strategy = write_text_chunks(
                candidate.value, data_dir, chunk_target_bytes, chunk_counter
            )

        manifest["blobs"].append(
            {
                "key": blob_key,
                "detector": candidate.detector,
                "payload_bytes": candidate.payload_bytes,
                "strategy": strategy,
                "chunks": chunk_entries,
                "script_id": candidate.script_id,
                "assignment_style": candidate.assignment_style,
                "variable_name": candidate.variable_name,
                "decl_kind": candidate.decl_kind,
            }
        )

        replacements.append(
            Replacement(
                start=candidate.start,
                end=candidate.end,
                text=replacement_for_candidate(candidate, blob_key),
            )
        )

    index_html = apply_replacements(html, replacements)
    index_html = ensure_loader_runtime(index_html)

    manifest_path = viewer_dir / "manifest.json"
    index_path = viewer_dir / "index.html"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    index_path.write_text(index_html, encoding="utf-8")

    return {
        "viewer_dir": viewer_dir,
        "index_path": index_path,
        "manifest_path": manifest_path,
        "chunks_written": chunk_counter,
    }


def run() -> int:
    args = parse_args()
    validate_slug(args.slug)

    input_path = Path(args.input).expanduser().resolve()
    if not input_path.exists():
        raise FileNotFoundError(f"Input file does not exist: {input_path}")
    if not input_path.is_file():
        raise ValueError(f"Input path is not a file: {input_path}")

    outdir = Path(args.outdir).expanduser().resolve()
    outdir.mkdir(parents=True, exist_ok=True)

    html = input_path.read_text(encoding="utf-8")
    backup_path = make_backup_copy(input_path, outdir, args.slug)

    if args.mode == "single":
        output_file = copy_single(input_path, outdir, args.slug)
        print(f"Mode: single")
        print(f"Input copied to: {output_file}")
        print(f"Backup copy: {backup_path}")
        print(f"Viewer URL path: viewers/{args.slug}.html")
        return 0

    candidates = detect_candidates(html)
    if not candidates:
        raise RuntimeError(
            "Could not detect embedded payload patterns in the input HTML.\n"
            "Supported patterns: <script type=\"application/json\"> blocks and JSON JS assignments."
        )

    total_payload_bytes = sum(candidate.payload_bytes for candidate in candidates)
    threshold_bytes = int(args.threshold_mb * 1024 * 1024)

    print(f"Detected {len(candidates)} embedded JSON blob(s).")
    print(
        f"Estimated embedded payload size: {bytes_to_mb(total_payload_bytes):.2f} MB "
        f"({total_payload_bytes} bytes)"
    )

    if args.mode == "auto" and total_payload_bytes <= threshold_bytes:
        output_file = copy_single(input_path, outdir, args.slug)
        print(
            f"Mode: auto -> single (payload <= threshold {args.threshold_mb:.2f} MB)"
        )
        print(f"Input copied to: {output_file}")
        print(f"Backup copy: {backup_path}")
        print(f"Viewer URL path: viewers/{args.slug}.html")
        return 0

    result = externalize_to_directory(
        html=html,
        candidates=candidates,
        outdir=outdir,
        slug=args.slug,
        chunk_mb=args.chunk_mb,
    )
    print(
        f"Mode: {args.mode} -> directory "
        f"(threshold {args.threshold_mb:.2f} MB, chunk target {args.chunk_mb:.2f} MB)"
    )
    print(f"Output directory: {result['viewer_dir']}")
    print(f"index.html: {result['index_path']}")
    print(f"manifest.json: {result['manifest_path']}")
    print(f"Chunk files written: {result['chunks_written']}")
    print(f"Backup copy: {backup_path}")
    print(f"Viewer URL path: viewers/{args.slug}/")
    print(f"Viewer URL path: viewers/{args.slug}/index.html")
    return 0


def main() -> None:
    try:
        code = run()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
    sys.exit(code)


if __name__ == "__main__":
    main()
