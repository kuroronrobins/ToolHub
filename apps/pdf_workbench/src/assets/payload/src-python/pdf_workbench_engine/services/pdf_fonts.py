from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from .pdf_document import _import_fitz


PDF_WORKBENCH_FONT = "pdf-workbench-gothic"
PDF_WORKBENCH_FALLBACK_FONT = "japan"
PDF_WORKBENCH_ASCII_FONT = "helv"

_FONT_CANDIDATES = [
    os.environ.get("PDF_WORKBENCH_FONT_FILE"),
    r"C:\Windows\Fonts\BIZ-UDGothicB.ttc",
    r"C:\Windows\Fonts\BIZ-UDGothicR.ttc",
    r"C:\Windows\Fonts\YuGothB.ttc",
    r"C:\Windows\Fonts\YuGothM.ttc",
    r"C:\Windows\Fonts\meiryob.ttc",
    r"C:\Windows\Fonts\meiryo.ttc",
]


@lru_cache(maxsize=1)
def preferred_font_file() -> Path | None:
    for candidate in _FONT_CANDIDATES:
        if not candidate:
            continue
        path = Path(candidate)
        if path.exists() and path.is_file():
            return path
    return None


@lru_cache(maxsize=1)
def _font_file_insert_kwargs() -> dict[str, Any]:
    font_file = preferred_font_file()
    if font_file:
        return {"fontname": PDF_WORKBENCH_FONT, "fontfile": str(font_file)}
    return {"fontname": PDF_WORKBENCH_FALLBACK_FONT}


def _can_use_builtin_ascii_font(text: str) -> bool:
    return text.isascii()


def text_insert_kwargs(text: str = "") -> dict[str, Any]:
    if text and _can_use_builtin_ascii_font(text):
        return {"fontname": PDF_WORKBENCH_ASCII_FONT}
    if text:
        return {"fontname": PDF_WORKBENCH_FALLBACK_FONT}
    return _font_file_insert_kwargs()


@lru_cache(maxsize=1)
def _preferred_fitz_font() -> Any | None:
    font_file = preferred_font_file()
    if not font_file:
        return None
    fitz = _import_fitz()
    try:
        return fitz.Font(fontfile=str(font_file))
    except Exception:
        return None


@lru_cache(maxsize=4096)
def text_width(text: str, font_size: float) -> float:
    fitz = _import_fitz()
    if text and _can_use_builtin_ascii_font(text):
        return float(
            fitz.get_text_length(
                text,
                fontsize=font_size,
                fontname=PDF_WORKBENCH_ASCII_FONT,
            )
        )
    if text:
        try:
            return float(
                fitz.get_text_length(
                    text,
                    fontsize=font_size,
                    fontname=PDF_WORKBENCH_FALLBACK_FONT,
                )
            )
        except Exception:
            pass

    font = _preferred_fitz_font()
    if font is not None:
        return float(font.text_length(text, fontsize=font_size))

    try:
        return float(
            fitz.get_text_length(
                text,
                fontsize=font_size,
                fontname=PDF_WORKBENCH_FALLBACK_FONT,
            )
        )
    except Exception:
        return float(fitz.get_text_length(text, fontsize=font_size))
