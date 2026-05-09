from __future__ import annotations

from typing import Any


LEGACY_FALLBACK_ICON_SOURCES = {"fallback_png", "provisional_fallback_png"}
LEGACY_IMAGE_EVALUATION_STATUS_ALIASES = {
    "fallback_rule_based": "deterministic_png_check",
}
LEGACY_SCORE_BASIS_ALIASES = {
    "prompt_concept_only": "rule_based_prompt_and_manifest",
}


def is_legacy_fallback_icon_source(source: str | None) -> bool:
    return (source or "").strip() in LEGACY_FALLBACK_ICON_SOURCES


def legacy_fallback_icon_warning(source: str | None) -> str:
    value = (source or "").strip() or "legacy fallback source"
    return f"Legacy {value} icon override was treated as default_icon."


def manifest_entry_is_legacy_fallback(entry: dict[str, Any]) -> bool:
    source = str(entry.get("source") or "")
    return bool(entry.get("fallback")) or "fallback" in source


def normalize_image_evaluation_status(statuses: set[str]) -> str:
    normalized = {LEGACY_IMAGE_EVALUATION_STATUS_ALIASES.get(status, status) for status in statuses if status}
    if "deterministic_png_check" in normalized:
        return "deterministic_png_check"
    if normalized:
        return sorted(normalized)[0]
    return "not_run"


def normalize_score_basis(value: str | None) -> str:
    text = (value or "").strip()
    return LEGACY_SCORE_BASIS_ALIASES.get(text, text)
