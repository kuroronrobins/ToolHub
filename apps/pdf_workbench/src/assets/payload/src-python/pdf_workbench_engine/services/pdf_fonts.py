from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .pdf_document import _import_fitz


PDF_WORKBENCH_FONT = "pdf-workbench-gothic"
PDF_WORKBENCH_FALLBACK_FONT = "japan"

_FONT_CANDIDATES = [
    os.environ.get("PDF_WORKBENCH_FONT_FILE"),
    r"C:\Windows\Fonts\BIZ-UDGothicB.ttc",
    r"C:\Windows\Fonts\BIZ-UDGothicR.ttc",
    r"C:\Windows\Fonts\YuGothB.ttc",
    r"C:\Windows\Fonts\YuGothM.ttc",
    r"C:\Windows\Fonts\meiryob.ttc",
    r"C:\Windows\Fonts\meiryo.ttc",
]


def preferred_font_file() -> Path | None:
    for candidate in _FONT_CANDIDATES:
        if not candidate:
            continue
        path = Path(candidate)
        if path.exists() and path.is_file():
            return path
    return None


def text_insert_kwargs() -> dict[str, Any]:
    font_file = preferred_font_file()
    if font_file:
        return {"fontname": PDF_WORKBENCH_FONT, "fontfile": str(font_file)}
    return {"fontname": PDF_WORKBENCH_FALLBACK_FONT}


def text_width(text: str, font_size: float) -> float:
    fitz = _import_fitz()
    font_file = preferred_font_file()
    if font_file:
        try:
            font = fitz.Font(fontfile=str(font_file))
            return float(font.text_length(text, fontsize=font_size))
        except Exception:
            pass

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
