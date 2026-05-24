"""Atomic file write helpers with fallback for Windows file locks."""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def write_text_atomic(path: Path, text: str, *, encoding: str = "utf-8") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp.write_text(text, encoding=encoding)
        tmp.replace(path)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Atomic write failed for %s: %s (fallback to direct write)", path, exc)
        try:
            path.write_text(text, encoding=encoding)
        finally:
            try:
                if tmp.exists():
                    tmp.unlink()
            except Exception:
                pass
