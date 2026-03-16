#!/usr/bin/env python3
"""
Validation helpers for datasets, viewer artifacts, and published viewer URLs.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen


VALID_DATASET_TYPES = {"single", "directory"}
SLUG_RE = re.compile(r"[A-Za-z0-9._-]+")
REMOTE_METHODS = ("HEAD", "GET")
GENE_AUX_URL_RE = re.compile(r'"gene_aux_url"\s*:\s*"((?:[^"\\]|\\.)*)"')
GENE_SIDECAR_FORMAT = "karospace-gene-sidecar-manifest-v2"


@dataclass
class ValidationReport:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def add_error(self, message: str) -> None:
        self.errors.append(message)

    def add_warning(self, message: str) -> None:
        self.warnings.append(message)


def format_report(report: ValidationReport) -> str:
    lines: list[str] = []
    if report.errors:
        lines.append("Errors:")
        lines.extend(f"- {message}" for message in report.errors)
    if report.warnings:
        if lines:
            lines.append("")
        lines.append("Warnings:")
        lines.extend(f"- {message}" for message in report.warnings)
    if not lines:
        lines.append("No validation issues found.")
    return "\n".join(lines)


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid JSON in {path}: {exc}") from exc


def _is_remote_like(path: str) -> bool:
    value = str(path or "").strip()
    return (
        value.startswith("http://")
        or value.startswith("https://")
        or value.startswith("data:")
        or value.startswith("/")
    )


def _resolve_relative(base_dir: Path, relative_path: str) -> Path:
    raw = str(relative_path or "").strip()
    target = (base_dir / raw).resolve()
    try:
        target.relative_to(base_dir.resolve())
    except ValueError as exc:
        raise RuntimeError(f"Path escapes base directory {base_dir}: {relative_path}") from exc
    return target


def _extract_gene_aux_url(html_path: Path) -> str | None:
    try:
        text = html_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(f"Unable to read HTML viewer {html_path}: {exc}") from exc

    match = GENE_AUX_URL_RE.search(text)
    if not match:
        return None
    return json.loads(f'"{match.group(1)}"')


def _validate_gene_sidecar(html_path: Path, context: str, report: ValidationReport) -> None:
    try:
        aux_relative = _extract_gene_aux_url(html_path)
    except RuntimeError as exc:
        report.add_error(f"{context}: {exc}")
        return

    if not aux_relative:
        return

    try:
        aux_path = _resolve_relative(html_path.parent, aux_relative)
    except RuntimeError as exc:
        report.add_error(f"{context}: {exc}")
        return

    if not aux_path.exists():
        report.add_error(f"{context}: missing gene sidecar manifest {aux_path}")
        return
    if not aux_path.is_file():
        report.add_error(f"{context}: gene sidecar manifest is not a file {aux_path}")
        return

    try:
        manifest = _load_json(aux_path)
    except RuntimeError as exc:
        report.add_error(f"{context}: {exc}")
        return

    if not isinstance(manifest, dict):
        report.add_error(f"{context}: gene sidecar manifest must contain a JSON object")
        return
    if manifest.get("format") != GENE_SIDECAR_FORMAT:
        report.add_error(
            f"{context}: unsupported gene sidecar format "
            f"'{manifest.get('format')}' in {aux_path}"
        )

    shards = manifest.get("shards")
    if not isinstance(shards, dict) or not shards:
        report.add_error(f"{context}: gene sidecar manifest must contain a non-empty 'shards' object")
        return

    seen_shards: set[str] = set()
    for shard_relative, genes in shards.items():
        if not isinstance(shard_relative, str) or not shard_relative.strip():
            report.add_error(f"{context}: gene sidecar shard path must be a non-empty string")
            continue
        if shard_relative in seen_shards:
            report.add_error(f"{context}: duplicate gene sidecar shard '{shard_relative}'")
            continue
        seen_shards.add(shard_relative)

        if not isinstance(genes, list) or not all(isinstance(gene, str) and gene.strip() for gene in genes):
            report.add_error(f"{context}: shard '{shard_relative}' must map to a list of non-empty gene names")

        try:
            shard_path = _resolve_relative(html_path.parent, shard_relative)
        except RuntimeError as exc:
            report.add_error(f"{context}: {exc}")
            continue

        if not shard_path.exists():
            report.add_error(f"{context}: missing gene shard {shard_path}")
            continue
        if not shard_path.is_file():
            report.add_error(f"{context}: gene shard is not a file {shard_path}")
            continue

        try:
            _load_json(shard_path)
        except RuntimeError as exc:
            report.add_error(f"{context}: {exc}")


def _collect_sidecar_entry_names(root: Path) -> set[str]:
    recognized: set[str] = set()
    for html_path in sorted(root.glob("*.html")):
        try:
            aux_relative = _extract_gene_aux_url(html_path)
        except RuntimeError:
            continue
        if not aux_relative:
            continue

        aux_name = Path(aux_relative).name
        if aux_name:
            recognized.add(aux_name)

        sidecar_dir_name = Path(aux_relative).stem
        if sidecar_dir_name:
            recognized.add(sidecar_dir_name)

        try:
            aux_path = _resolve_relative(html_path.parent, aux_relative)
        except RuntimeError:
            continue
        if not aux_path.exists() or not aux_path.is_file():
            continue

        try:
            manifest = _load_json(aux_path)
        except RuntimeError:
            continue
        shards = manifest.get("shards") if isinstance(manifest, dict) else None
        if not isinstance(shards, dict):
            continue
        for shard_relative in shards:
            if not isinstance(shard_relative, str) or not shard_relative.strip():
                continue
            try:
                shard_path = _resolve_relative(html_path.parent, shard_relative)
                relative_parts = shard_path.relative_to(root).parts
            except (RuntimeError, ValueError):
                continue
            if relative_parts:
                recognized.add(relative_parts[0])

    return recognized


def _validate_manifest(viewer_dir: Path, manifest_path: Path, context: str, report: ValidationReport) -> None:
    if not manifest_path.exists():
        report.add_error(f"{context}: missing manifest.json at {manifest_path}")
        return
    if not manifest_path.is_file():
        report.add_error(f"{context}: manifest.json is not a file at {manifest_path}")
        return

    try:
        manifest = _load_json(manifest_path)
    except RuntimeError as exc:
        report.add_error(f"{context}: {exc}")
        return

    if not isinstance(manifest, dict):
        report.add_error(f"{context}: manifest.json must contain a JSON object")
        return

    blobs = manifest.get("blobs")
    if not isinstance(blobs, list):
        report.add_error(f"{context}: manifest.json must contain a 'blobs' array")
        return

    blob_keys: set[str] = set()
    for blob_index, blob in enumerate(blobs):
        blob_context = f"{context}: manifest blob {blob_index}"
        if not isinstance(blob, dict):
            report.add_error(f"{blob_context}: entry must be an object")
            continue

        blob_key = blob.get("key")
        if not isinstance(blob_key, str) or not blob_key.strip():
            report.add_error(f"{blob_context}: missing non-empty 'key'")
        elif blob_key in blob_keys:
            report.add_error(f"{blob_context}: duplicate blob key '{blob_key}'")
        else:
            blob_keys.add(blob_key)

        chunks = blob.get("chunks")
        if not isinstance(chunks, list) or not chunks:
            report.add_error(f"{blob_context}: missing non-empty 'chunks' array")
            continue

        seen_chunk_paths: set[str] = set()
        for chunk_index, chunk in enumerate(chunks):
            chunk_context = f"{blob_context}: chunk {chunk_index}"
            if not isinstance(chunk, dict):
                report.add_error(f"{chunk_context}: entry must be an object")
                continue

            relative_path = chunk.get("path")
            if not isinstance(relative_path, str) or not relative_path.strip():
                report.add_error(f"{chunk_context}: missing non-empty 'path'")
                continue
            if relative_path in seen_chunk_paths:
                report.add_error(f"{chunk_context}: duplicate chunk path '{relative_path}'")
                continue
            seen_chunk_paths.add(relative_path)

            try:
                chunk_path = _resolve_relative(viewer_dir, relative_path)
            except RuntimeError as exc:
                report.add_error(f"{chunk_context}: {exc}")
                continue

            if not chunk_path.exists():
                report.add_error(f"{chunk_context}: missing file {chunk_path}")
            elif not chunk_path.is_file():
                report.add_error(f"{chunk_context}: target is not a file {chunk_path}")


def validate_viewer_entry(r2_path: str, dataset_type: str, viewers_root: Path, context: str) -> ValidationReport:
    report = ValidationReport()
    relative_path = str(r2_path or "").lstrip("/")
    if not relative_path:
        report.add_error(f"{context}: missing r2_path")
        return report

    try:
        target_path = _resolve_relative(viewers_root.parent, relative_path)
    except RuntimeError as exc:
        report.add_error(f"{context}: {exc}")
        return report

    if not target_path.exists():
        report.add_error(f"{context}: missing local target {target_path}")
        return report

    if dataset_type == "single":
        if target_path.suffix.lower() != ".html":
            report.add_error(f"{context}: single viewer r2_path must point to an .html file")
        if not target_path.is_file():
            report.add_error(f"{context}: single viewer target is not a file {target_path}")
            return report
        _validate_gene_sidecar(target_path, context, report)
        return report

    if dataset_type == "directory":
        if target_path.name != "index.html":
            report.add_error(f"{context}: directory viewer r2_path must point to index.html")
            return report
        if not target_path.is_file():
            report.add_error(f"{context}: directory viewer index is not a file {target_path}")
            return report
        viewer_dir = target_path.parent
        manifest_path = viewer_dir / "manifest.json"
        _validate_manifest(viewer_dir, manifest_path, context, report)
        return report

    report.add_error(f"{context}: unsupported dataset type '{dataset_type}'")
    return report


def validate_viewers_tree(viewers_dir: Path) -> ValidationReport:
    report = ValidationReport()
    root = viewers_dir.expanduser().resolve()
    if not root.exists():
        report.add_error(f"Viewers directory does not exist: {root}")
        return report
    if not root.is_dir():
        report.add_error(f"Viewers path is not a directory: {root}")
        return report

    sidecar_entries = _collect_sidecar_entry_names(root)
    entries = [
        path for path in sorted(root.iterdir())
        if (
            not path.name.startswith(".")
            and path.name != "_backups"
            and path.name not in sidecar_entries
        )
    ]
    if not entries:
        report.add_error(f"No viewer artifacts found in {root}")
        return report

    for entry in entries:
        context = f"viewer '{entry.name}'"
        if entry.is_file():
            if entry.suffix.lower() != ".html":
                report.add_warning(f"{context}: unexpected top-level file {entry.name}")
                continue
            _validate_gene_sidecar(entry, context, report)
            continue
        if entry.is_dir():
            index_path = entry / "index.html"
            if not index_path.exists():
                report.add_error(f"{context}: missing index.html at {index_path}")
                continue
            manifest_path = entry / "manifest.json"
            _validate_manifest(entry, manifest_path, context, report)
            continue
        report.add_warning(f"{context}: unsupported filesystem entry type")

    return report


def _validate_dataset_record(
    dataset: dict[str, Any],
    dataset_index: int,
    site_dir: Path,
    viewers_root: Path,
    seen_slugs: set[str],
    seen_paths: set[str],
) -> ValidationReport:
    report = ValidationReport()
    context = f"dataset[{dataset_index}]"

    required_string_fields = ("title", "description", "slug", "type", "r2_path")
    for field_name in required_string_fields:
        value = dataset.get(field_name)
        if not isinstance(value, str) or not value.strip():
            report.add_error(f"{context}: missing non-empty '{field_name}'")

    tags = dataset.get("tags")
    if not isinstance(tags, list) or not all(isinstance(tag, str) and tag.strip() for tag in tags):
        report.add_error(f"{context}: 'tags' must be a list of non-empty strings")

    citation = dataset.get("citation")
    if citation is not None and not isinstance(citation, str):
        report.add_error(f"{context}: 'citation' must be a string when provided")

    slug = dataset.get("slug")
    if isinstance(slug, str) and slug.strip():
        if not SLUG_RE.fullmatch(slug):
            report.add_error(f"{context}: invalid slug '{slug}'")
        elif slug in seen_slugs:
            report.add_error(f"{context}: duplicate slug '{slug}'")
        else:
            seen_slugs.add(slug)

    dataset_type = dataset.get("type")
    if isinstance(dataset_type, str) and dataset_type not in VALID_DATASET_TYPES:
        report.add_error(f"{context}: invalid dataset type '{dataset_type}'")

    r2_path = dataset.get("r2_path")
    if isinstance(r2_path, str) and r2_path.strip():
        normalized_r2 = r2_path.lstrip("/")
        if normalized_r2 in seen_paths:
            report.add_warning(f"{context}: duplicate r2_path '{r2_path}'")
        else:
            seen_paths.add(normalized_r2)

        if isinstance(dataset_type, str) and dataset_type in VALID_DATASET_TYPES:
            entry_report = validate_viewer_entry(
                r2_path=r2_path,
                dataset_type=dataset_type,
                viewers_root=viewers_root,
                context=context,
            )
            report.errors.extend(entry_report.errors)
            report.warnings.extend(entry_report.warnings)

    thumbnail = dataset.get("thumbnail")
    if thumbnail is None:
        report.add_warning(f"{context}: missing thumbnail field")
    elif not isinstance(thumbnail, str) or not thumbnail.strip():
        report.add_error(f"{context}: thumbnail must be a non-empty string when provided")
    elif not _is_remote_like(thumbnail):
        try:
            thumb_path = _resolve_relative(site_dir, thumbnail)
        except RuntimeError as exc:
            report.add_error(f"{context}: {exc}")
        else:
            if not thumb_path.exists():
                report.add_error(f"{context}: missing thumbnail file {thumb_path}")
            elif not thumb_path.is_file():
                report.add_error(f"{context}: thumbnail target is not a file {thumb_path}")

    return report


def validate_datasets(
    datasets_path: Path,
    *,
    site_dir: Path | None = None,
    viewers_dir: Path | None = None,
) -> ValidationReport:
    report = ValidationReport()
    resolved_datasets = datasets_path.expanduser().resolve()
    if not resolved_datasets.exists():
        report.add_error(f"Datasets file not found: {resolved_datasets}")
        return report

    try:
        raw = _load_json(resolved_datasets)
    except RuntimeError as exc:
        report.add_error(str(exc))
        return report

    if not isinstance(raw, list):
        report.add_error(f"{resolved_datasets} must contain a JSON array")
        return report

    resolved_site_dir = (site_dir or resolved_datasets.parent).expanduser().resolve()
    resolved_viewers_dir = (viewers_dir or (resolved_datasets.parent.parent / "viewers")).expanduser().resolve()
    seen_slugs: set[str] = set()
    seen_paths: set[str] = set()

    for dataset_index, dataset in enumerate(raw):
        if not isinstance(dataset, dict):
            report.add_error(f"dataset[{dataset_index}]: entry must be a JSON object")
            continue
        item_report = _validate_dataset_record(
            dataset=dataset,
            dataset_index=dataset_index,
            site_dir=resolved_site_dir,
            viewers_root=resolved_viewers_dir,
            seen_slugs=seen_slugs,
            seen_paths=seen_paths,
        )
        report.errors.extend(item_report.errors)
        report.warnings.extend(item_report.warnings)

    return report


def iter_remote_dataset_urls(datasets_path: Path, viewer_host: str) -> Iterable[tuple[str, str]]:
    raw = _load_json(datasets_path.expanduser().resolve())
    if not isinstance(raw, list):
        raise RuntimeError(f"{datasets_path} must contain a JSON array")

    for dataset in raw:
        if not isinstance(dataset, dict):
            continue
        slug = str(dataset.get("slug", "")).strip() or "<missing-slug>"
        r2_path = str(dataset.get("r2_path", "")).lstrip("/")
        if not r2_path:
            continue
        yield slug, urljoin(f"{viewer_host.rstrip('/')}/", r2_path)


def _check_remote_url(url: str, timeout_sec: float) -> str | None:
    headers = {"User-Agent": "KaroSpaceSE validator/1.0"}
    for method in REMOTE_METHODS:
        request = Request(url, headers=headers, method=method)
        try:
            with urlopen(request, timeout=timeout_sec) as response:
                status = getattr(response, "status", response.getcode())
                if 200 <= status < 400:
                    return None
                return f"HTTP {status}"
        except HTTPError as exc:
            if method == "HEAD" and exc.code in {403, 405, 501}:
                continue
            return f"HTTP {exc.code}"
        except URLError as exc:
            return str(exc.reason)
    return "request failed"


def validate_remote_urls(
    datasets_path: Path,
    viewer_host: str,
    *,
    timeout_sec: float = 15.0,
) -> ValidationReport:
    report = ValidationReport()
    for slug, url in iter_remote_dataset_urls(datasets_path, viewer_host):
        error = _check_remote_url(url, timeout_sec)
        if error:
            report.add_error(f"remote '{slug}': {error} for {url}")
    return report
