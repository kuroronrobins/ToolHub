from __future__ import annotations

from pathlib import Path


DEFAULT_ICON_SOURCE = "default_icon"
DEFAULT_ICON_STATUS = "default_icon"
DEFAULT_ICON_REASON = (
    "No uploaded icon or adopted AI image candidate was selected, so ToolHub uses the common default app icon."
)

ASSET_DIR = Path(__file__).resolve().parents[1] / "assets"
DEFAULT_ICON_PNG = ASSET_DIR / "default_app_icon.png"
DEFAULT_ICON_SVG = ASSET_DIR / "default_app_icon.svg"


def default_icon_png() -> bytes:
    try:
        data = DEFAULT_ICON_PNG.read_bytes()
    except OSError as exc:
        raise FileNotFoundError(f"ToolHub default app icon PNG was not found: {DEFAULT_ICON_PNG}") from exc
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError(f"ToolHub default app icon is not a PNG: {DEFAULT_ICON_PNG}")
    return data


def default_icon_svg() -> str:
    try:
        return DEFAULT_ICON_SVG.read_text(encoding="utf-8")
    except OSError as exc:
        raise FileNotFoundError(f"ToolHub default app icon SVG was not found: {DEFAULT_ICON_SVG}") from exc
