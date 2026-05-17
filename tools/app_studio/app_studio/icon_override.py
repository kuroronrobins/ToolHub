from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

from .default_icon import DEFAULT_ICON_SOURCE
from .icon_compat import is_legacy_fallback_icon_source, legacy_fallback_icon_warning


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def load_icon_override(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise FileNotFoundError(f"icon override file was not found: {path}") from exc
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"icon override JSON is invalid: line {exc.lineno}, column {exc.colno}") from exc
    if not isinstance(data, dict):
        raise ValueError("icon override JSON root must be an object")
    return data


def load_uploaded_png_override(path: Path) -> dict[str, Any]:
    try:
        png = path.read_bytes()
    except OSError as exc:
        raise FileNotFoundError(f"uploaded icon PNG was not found: {path}") from exc
    if not png.startswith(PNG_SIGNATURE):
        raise ValueError(f"uploaded icon file was not a PNG: {path}")
    return {
        "selected_icon_source": "uploaded_png",
        "png_base64": base64.b64encode(png).decode("ascii"),
    }


def apply_icon_override(default_png: bytes, override: dict[str, Any] | None) -> tuple[bytes, str, list[str]]:
    if not override:
        return default_png, DEFAULT_ICON_SOURCE, []

    warnings: list[str] = []
    source = str(override.get("selected_icon_source") or "").strip()
    if source in {"", "default_icon"}:
        return default_png, DEFAULT_ICON_SOURCE, warnings
    if is_legacy_fallback_icon_source(source):
        warnings.append(legacy_fallback_icon_warning(source))
        return default_png, DEFAULT_ICON_SOURCE, warnings
    if source not in {"candidate_png", "final_png", "ai_candidate_png", "uploaded_png"}:
        warnings.append("Ignored icon override: unsupported selected_icon_source.")
        return default_png, DEFAULT_ICON_SOURCE, warnings

    raw_png = str(override.get("png_base64") or "").strip()
    if not raw_png:
        warnings.append("Ignored icon override: png_base64 was empty.")
        return default_png, DEFAULT_ICON_SOURCE, warnings
    try:
        png = decode_png_base64(raw_png)
    except ValueError as exc:
        warnings.append(f"Ignored icon override: {exc}")
        return default_png, DEFAULT_ICON_SOURCE, warnings
    return png, source, warnings


def decode_png_base64(value: str) -> bytes:
    if value.startswith("data:image/png;base64,"):
        value = value.split(",", 1)[1]
    try:
        png = base64.b64decode(value, validate=True)
    except Exception as exc:
        raise ValueError("png_base64 could not be decoded.") from exc
    if not png.startswith(PNG_SIGNATURE):
        raise ValueError("decoded data was not a PNG.")
    return png
