#!/usr/bin/env python3
"""
Shared static config helpers for the KaroSpace portal.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


DEFAULT_VIEWER_HOST = "https://viewers.karospace.se"
DEFAULT_SITE_CONFIG_PATH = "site/config.json"


def normalize_public_base(public_host: str) -> str:
    cleaned = str(public_host or "").strip().rstrip("/")
    if not cleaned:
        return DEFAULT_VIEWER_HOST
    if cleaned.startswith("http://") or cleaned.startswith("https://"):
        return cleaned
    return f"https://{cleaned}"


def resolve_site_config_path(path: str | Path | None = None) -> Path:
    raw = path or DEFAULT_SITE_CONFIG_PATH
    return Path(raw).expanduser().resolve()


def load_site_config(path: str | Path | None = None) -> dict[str, Any]:
    config_path = resolve_site_config_path(path)
    if not config_path.exists():
        return {"viewer_host": DEFAULT_VIEWER_HOST, "config_path": str(config_path)}

    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid JSON in site config {config_path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise RuntimeError(f"Site config {config_path} must contain a JSON object.")

    viewer_host = normalize_public_base(raw.get("viewer_host", DEFAULT_VIEWER_HOST))
    return {
        **raw,
        "viewer_host": viewer_host,
        "config_path": str(config_path),
    }


def resolve_viewer_host(
    cli_value: str | None = None,
    env_value: str | None = None,
    *,
    config_path: str | Path | None = None,
) -> str:
    if cli_value:
        return normalize_public_base(cli_value)
    if env_value:
        return normalize_public_base(env_value)
    return load_site_config(config_path).get("viewer_host", DEFAULT_VIEWER_HOST)
