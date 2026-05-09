from __future__ import annotations

from pathlib import Path
from typing import Any

from .icon_compat import manifest_entry_is_legacy_fallback
from .models import IconCandidateAsset
from .openai_client import decode_base64_image


def select_icon_manifest_candidate(entries: list[Any], candidate_id: str | None) -> dict[str, Any] | None:
    candidates = [entry for entry in entries if isinstance(entry, dict)]
    requested = (candidate_id or "").strip()
    if requested:
        for candidate in candidates:
            if str(candidate.get("candidate_id") or candidate.get("id") or "") == requested:
                return candidate
    return candidates[0] if candidates else None

def selected_candidate_image_path(icon_work: Path, candidate: dict[str, Any] | None) -> Path | None:
    if not candidate:
        legacy = icon_work / "icon_candidate_1.png"
        return legacy if legacy.is_file() else None
    file_name = str(candidate.get("file_name") or "").strip()
    if file_name:
        path = icon_work / file_name
        if path.is_file():
            return path
    legacy = icon_work / "icon_candidate_1.png"
    return legacy if legacy.is_file() else None

def manifest_entry_is_fallback(entry: dict[str, Any]) -> bool:
    return manifest_entry_is_legacy_fallback(entry)

def image_candidate_from_result(image_result, candidate_number: int = 1) -> tuple[bytes | None, str, str]:
    if image_result is None or not image_result.ok or not image_result.content:
        reason = image_result.fallback_reason if image_result else "AI image generation was skipped."
        return None, "", f"No API image candidate was saved for icon_candidate_{candidate_number}. reason={reason or 'none'}"
    content = image_result.content.strip()
    if content.startswith("http://") or content.startswith("https://"):
        return None, content, f"API returned an image URL. It will be saved as icon_candidate_{candidate_number}.url.txt."
    try:
        return decode_base64_image(content), "", f"API returned b64 image data. It will be saved as icon_candidate_{candidate_number}.png."
    except Exception:
        return None, "", f"API image data could not be decoded for icon_candidate_{candidate_number}; ToolHub default icon remains available."

def saved_candidate_name(png_bytes: bytes | None, image_url: str) -> str:
    if png_bytes:
        return "icon_candidate_1.png"
    if image_url:
        return "icon_candidate_1.url.txt"
    return "none"

def is_api_candidate(candidate: IconCandidateAsset) -> bool:
    return not candidate.is_fallback and candidate.source.startswith("api")
