#!/usr/bin/env python3
"""
Generate small dataset thumbnail screenshots from published viewer URLs.

This script reads site/datasets.json, opens each viewer URL in a headless browser,
captures a screenshot, and writes a thumbnail path back into each dataset entry.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlparse


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate thumbnail screenshots for datasets."
    )
    parser.add_argument(
        "--datasets",
        default="site/datasets.json",
        help="Path to datasets JSON file.",
    )
    parser.add_argument(
        "--output-dir",
        default="site/thumbs",
        help="Directory where thumbnails are saved.",
    )
    parser.add_argument(
        "--viewer-host",
        default="https://viewers.karospace.se",
        help="Viewer host used with each dataset r2_path.",
    )
    parser.add_argument(
        "--host-ip",
        default="",
        help="Optional IP for viewer host DNS override (useful for stale local DNS).",
    )
    parser.add_argument(
        "--ignore-https-errors",
        action="store_true",
        help="Ignore HTTPS certificate errors (use only when debugging).",
    )
    parser.add_argument(
        "--width",
        type=int,
        default=960,
        help="Screenshot viewport width.",
    )
    parser.add_argument(
        "--height",
        type=int,
        default=540,
        help="Screenshot viewport height.",
    )
    parser.add_argument(
        "--wait-ms",
        type=int,
        default=2500,
        help="Extra wait after page load before capture.",
    )
    parser.add_argument(
        "--timeout-ms",
        type=int,
        default=120000,
        help="Navigation timeout per dataset.",
    )
    parser.add_argument(
        "--quality",
        type=int,
        default=82,
        help="JPEG quality (0-100).",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing thumbnail files.",
    )
    parser.add_argument(
        "--slugs",
        nargs="*",
        default=[],
        help="Optional subset of dataset slugs to process.",
    )
    parser.add_argument(
        "--no-update-datasets",
        action="store_true",
        help="Do not update datasets.json thumbnail fields.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned actions without opening browser or writing files.",
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Run browser in headed mode for debugging.",
    )
    parser.add_argument(
        "--theme",
        choices=["auto", "light", "dark"],
        default="auto",
        help="Force viewer theme during capture (default: auto).",
    )
    return parser.parse_args()


def normalize_host(value: str) -> str:
    host = value.strip().rstrip("/")
    if not host:
        raise ValueError("--viewer-host cannot be empty.")
    if not host.startswith(("http://", "https://")):
        host = f"https://{host}"
    return host


def sanitize_slug(slug: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9._-]+", "_", slug).strip("._")
    return clean or "dataset"


def build_url(host: str, r2_path: str) -> str:
    path = str(r2_path or "").lstrip("/")
    if not path:
        raise ValueError("Missing r2_path.")
    return f"{host}/{path}"


def load_datasets(path: Path) -> list[dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(data, list):
        raise RuntimeError(f"{path} must contain a JSON array.")
    return data


def save_datasets(path: Path, datasets: list[dict]) -> None:
    path.write_text(
        json.dumps(datasets, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def run() -> int:
    args = parse_args()
    viewer_host = normalize_host(args.viewer_host)

    if args.width <= 0 or args.height <= 0:
        raise ValueError("--width and --height must be > 0.")
    if args.wait_ms < 0:
        raise ValueError("--wait-ms must be >= 0.")
    if args.timeout_ms <= 0:
        raise ValueError("--timeout-ms must be > 0.")
    if not (0 <= args.quality <= 100):
        raise ValueError("--quality must be between 0 and 100.")

    datasets_path = Path(args.datasets).expanduser().resolve()
    if not datasets_path.exists():
        raise FileNotFoundError(f"datasets file not found: {datasets_path}")

    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    datasets = load_datasets(datasets_path)
    selected_slugs = set(args.slugs)

    targets: list[tuple[dict, str, str, Path, str]] = []
    for dataset in datasets:
        slug = str(dataset.get("slug", "")).strip()
        if not slug:
            print("Skipping entry with missing slug.", file=sys.stderr)
            continue
        if selected_slugs and slug not in selected_slugs:
            continue

        url = build_url(viewer_host, dataset.get("r2_path", ""))
        filename = f"{sanitize_slug(slug)}.jpg"
        thumb_path = output_dir / filename
        thumb_rel = os.path.relpath(thumb_path, datasets_path.parent).replace("\\", "/")
        targets.append((dataset, slug, url, thumb_path, thumb_rel))

    if not targets:
        raise RuntimeError("No datasets selected. Check --slugs or datasets.json content.")

    print(f"Datasets selected: {len(targets)}")
    print(f"Output directory: {output_dir}")
    print(f"Viewer host: {viewer_host}")
    if args.theme != "auto":
        print(f"Capture theme: {args.theme}")

    if args.dry_run:
        for _, slug, url, thumb_path, thumb_rel in targets:
            print(f"DRY RUN {slug}: {url} -> {thumb_path} (thumbnail={thumb_rel})")
        return 0

    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "Playwright is required.\n"
            "Install with:\n"
            "  pip install playwright\n"
            "  python -m playwright install chromium"
        ) from exc

    updated = False
    created = 0
    skipped = 0
    failures = 0

    with sync_playwright() as playwright:
        launch_args: list[str] = []
        host_name = urlparse(viewer_host).hostname or ""
        if args.host_ip:
            launch_args.append(f"--host-resolver-rules=MAP {host_name} {args.host_ip}")
            print(f"Host override: {host_name} -> {args.host_ip}")

        browser = playwright.chromium.launch(
            headless=not args.headed,
            args=launch_args,
        )
        context_kwargs: dict = {
            "viewport": {"width": args.width, "height": args.height},
            "ignore_https_errors": args.ignore_https_errors,
        }
        if args.theme in {"light", "dark"}:
            context_kwargs["color_scheme"] = args.theme

        context = browser.new_context(**context_kwargs)

        if args.theme in {"light", "dark"}:
            forced_theme = json.dumps(args.theme)
            context.add_init_script(
                f"""
(() => {{
  const theme = {forced_theme};
  try {{
    localStorage.setItem("spatial-viewer-theme", theme);
    localStorage.setItem("karospace-theme", theme);
  }} catch (_err) {{}}
  try {{
    document.documentElement.classList.remove("light", "dark");
    document.documentElement.classList.add(theme);
    document.documentElement.setAttribute("data-theme", theme);
  }} catch (_err) {{}}
}})();
"""
            )

        for dataset, slug, url, thumb_path, thumb_rel in targets:
            if thumb_path.exists() and not args.overwrite:
                print(f"SKIP {slug}: {thumb_path} exists (use --overwrite to replace)")
                skipped += 1
                if not args.no_update_datasets and dataset.get("thumbnail") != thumb_rel:
                    dataset["thumbnail"] = thumb_rel
                    updated = True
                continue

            page = context.new_page()
            try:
                print(f"CAPTURE {slug}: {url}")
                page.goto(url, wait_until="domcontentloaded", timeout=args.timeout_ms)
                page.wait_for_load_state("networkidle", timeout=args.timeout_ms)
                if args.wait_ms:
                    page.wait_for_timeout(args.wait_ms)
                page.screenshot(
                    path=str(thumb_path),
                    type="jpeg",
                    quality=args.quality,
                    full_page=False,
                )
                created += 1
                if not args.no_update_datasets:
                    dataset["thumbnail"] = thumb_rel
                    updated = True
            except PlaywrightTimeoutError:
                failures += 1
                print(f"ERROR {slug}: timed out loading {url}", file=sys.stderr)
            except PlaywrightError as exc:
                failures += 1
                print(f"ERROR {slug}: {exc}", file=sys.stderr)
            finally:
                page.close()

        context.close()
        browser.close()

    if updated:
        save_datasets(datasets_path, datasets)
        print(f"Updated datasets file: {datasets_path}")

    print(
        f"Done. created={created}, skipped={skipped}, failures={failures}, "
        f"updated_datasets={'yes' if updated else 'no'}"
    )
    return 1 if failures else 0


def main() -> None:
    try:
        sys.exit(run())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
