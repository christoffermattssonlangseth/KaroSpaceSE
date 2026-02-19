#!/usr/bin/env python3
"""
Upload local viewers output to Cloudflare R2 using the S3-compatible API.

Required environment variables:
- R2_ACCESS_KEY_ID
- R2_SECRET_ACCESS_KEY
- R2_ACCOUNT_ID
- R2_BUCKET
- R2_PUBLIC_HOST

Optional:
- R2_PREFIX (default: "viewers")
"""

from __future__ import annotations

import argparse
import mimetypes
import os
import sys
from pathlib import Path
from typing import Iterable


EXTENSION_CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".svg": "image/svg+xml",
    ".txt": "text/plain; charset=utf-8",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync ./viewers content to Cloudflare R2.")
    parser.add_argument(
        "--viewers-dir",
        default="./viewers",
        help="Local viewers directory to upload.",
    )
    parser.add_argument(
        "--prefix",
        default=None,
        help="R2 key prefix. Defaults to env R2_PREFIX or 'viewers'.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show planned uploads without sending data.",
    )
    return parser.parse_args()


def require_env(name: str) -> str:
    value = os.environ.get(name)
    if value:
        return value
    raise RuntimeError(f"Missing required environment variable: {name}")


def normalize_public_base(public_host: str) -> str:
    cleaned = public_host.strip().rstrip("/")
    if cleaned.startswith("http://") or cleaned.startswith("https://"):
        return cleaned
    return f"https://{cleaned}"


def iter_upload_files(viewers_dir: Path) -> Iterable[Path]:
    for root, dirs, files in os.walk(viewers_dir):
        dirs[:] = [
            d for d in dirs if not d.startswith(".") and d != "_backups"
        ]
        for filename in sorted(files):
            if filename.startswith("."):
                continue
            yield Path(root) / filename


def content_type_for(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in EXTENSION_CONTENT_TYPES:
        return EXTENSION_CONTENT_TYPES[ext]
    guessed, _ = mimetypes.guess_type(path.name)
    return guessed or "application/octet-stream"


def cache_control_for(path: Path) -> str:
    ext = path.suffix.lower()
    if ext == ".html":
        return "public, max-age=300, stale-while-revalidate=86400"
    if ext in {".json", ".txt", ".js", ".css", ".png", ".jpg", ".jpeg", ".svg"}:
        return "public, max-age=31536000, immutable"
    return "public, max-age=86400"


def build_key(prefix: str, viewers_dir: Path, file_path: Path) -> str:
    relative = file_path.relative_to(viewers_dir).as_posix()
    cleaned_prefix = prefix.strip("/ ")
    if not cleaned_prefix:
        return relative
    return f"{cleaned_prefix}/{relative}"


def build_s3_client(access_key: str, secret_key: str, account_id: str):
    try:
        import boto3
        from botocore.config import Config
    except ImportError as exc:
        raise RuntimeError(
            "boto3 and botocore are required. Install with: pip install boto3"
        ) from exc

    endpoint = f"https://{account_id}.r2.cloudflarestorage.com"
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        config=Config(signature_version="s3v4"),
        region_name="auto",
    )


def run() -> int:
    args = parse_args()

    access_key = require_env("R2_ACCESS_KEY_ID")
    secret_key = require_env("R2_SECRET_ACCESS_KEY")
    account_id = require_env("R2_ACCOUNT_ID")
    bucket = require_env("R2_BUCKET")
    public_host = require_env("R2_PUBLIC_HOST")
    prefix = args.prefix or os.environ.get("R2_PREFIX", "viewers")

    viewers_dir = Path(args.viewers_dir).expanduser().resolve()
    if not viewers_dir.exists():
        raise FileNotFoundError(f"Viewers directory does not exist: {viewers_dir}")
    if not viewers_dir.is_dir():
        raise ValueError(f"--viewers-dir is not a directory: {viewers_dir}")

    files = sorted(iter_upload_files(viewers_dir))
    if not files:
        raise RuntimeError(f"No files found to upload in {viewers_dir}")

    public_base = normalize_public_base(public_host)
    uploaded_urls: list[str] = []

    if args.dry_run:
        print("Dry run enabled. No files will be uploaded.")
        for file_path in files:
            key = build_key(prefix, viewers_dir, file_path)
            ctype = content_type_for(file_path)
            ccache = cache_control_for(file_path)
            print(
                f"DRY RUN upload: {file_path} -> s3://{bucket}/{key} "
                f"({ctype}, Cache-Control={ccache})"
            )
            uploaded_urls.append(f"{public_base}/{key}")
    else:
        s3_client = build_s3_client(access_key, secret_key, account_id)
        for file_path in files:
            key = build_key(prefix, viewers_dir, file_path)
            ctype = content_type_for(file_path)
            ccache = cache_control_for(file_path)
            s3_client.upload_file(
                str(file_path),
                bucket,
                key,
                ExtraArgs={"ContentType": ctype, "CacheControl": ccache},
            )
            print(
                f"Uploaded: {file_path} -> s3://{bucket}/{key} "
                f"({ctype}, Cache-Control={ccache})"
            )
            uploaded_urls.append(f"{public_base}/{key}")

    print("")
    print("Public URLs:")
    for url in uploaded_urls:
        print(url)

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
