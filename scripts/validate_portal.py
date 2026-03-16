#!/usr/bin/env python3
"""
Validate local portal metadata and viewer artifacts.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from portal_config import DEFAULT_SITE_CONFIG_PATH, load_site_config, resolve_viewer_host
from portal_validation import format_report, validate_datasets, validate_remote_urls, validate_viewers_tree


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate datasets.json, thumbnails, and viewer artifacts."
    )
    parser.add_argument(
        "--datasets",
        default="site/datasets.json",
        help="Path to datasets JSON file.",
    )
    parser.add_argument(
        "--site-dir",
        default="site",
        help="Path to the site directory.",
    )
    parser.add_argument(
        "--viewers-dir",
        default="viewers",
        help="Path to the viewers directory.",
    )
    parser.add_argument(
        "--config",
        default=DEFAULT_SITE_CONFIG_PATH,
        help="Path to static site config JSON.",
    )
    parser.add_argument(
        "--check-remote",
        action="store_true",
        help="Verify that published viewer URLs resolve on the configured viewer host.",
    )
    parser.add_argument(
        "--viewer-host",
        default=None,
        help="Override the viewer host used for --check-remote.",
    )
    parser.add_argument(
        "--timeout-sec",
        type=float,
        default=15.0,
        help="Timeout for remote URL verification.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    datasets_path = Path(args.datasets).expanduser().resolve()
    site_dir = Path(args.site_dir).expanduser().resolve()
    viewers_dir = Path(args.viewers_dir).expanduser().resolve()

    config = load_site_config(args.config)
    viewer_host = resolve_viewer_host(args.viewer_host, None, config_path=args.config)

    datasets_report = validate_datasets(
        datasets_path,
        site_dir=site_dir,
        viewers_dir=viewers_dir,
    )
    viewers_report = validate_viewers_tree(viewers_dir)

    print(f"Datasets file: {datasets_path}")
    print(f"Site dir: {site_dir}")
    print(f"Viewers dir: {viewers_dir}")
    print(f"Viewer host: {viewer_host}")
    print(f"Site config: {config.get('config_path')}")
    print("")
    print("Datasets validation")
    print(format_report(datasets_report))
    print("")
    print("Viewer artifact validation")
    print(format_report(viewers_report))

    exit_code = 0
    if datasets_report.errors or viewers_report.errors:
        exit_code = 1

    if args.check_remote:
        remote_report = validate_remote_urls(
            datasets_path,
            viewer_host,
            timeout_sec=args.timeout_sec,
        )
        print("")
        print("Remote URL validation")
        print(format_report(remote_report))
        if remote_report.errors:
            exit_code = 1

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
