from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


STRING_KEYS = {"short_description", "description", "change_summary"}
LIST_KEYS = {
    "categories",
    "keywords",
    "examples",
    "use_cases",
    "inputs",
    "outputs",
    "notes",
    "release_notes",
}
ALLOWED_KEYS = STRING_KEYS | LIST_KEYS
SECRET_VALUE_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_-]{8,}"),
    re.compile(r"(?i)\b(?:openai_api_key|api[_-]?key|password|token|secret|client_secret|credentials)\b\s*[:=]\s*\S+"),
]


def load_metadata_override(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise FileNotFoundError(f"metadata override file was not found: {path}") from exc
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"metadata override JSON is invalid: line {exc.lineno}, column {exc.colno}") from exc
    if not isinstance(data, dict):
        raise ValueError("metadata override JSON root must be an object")
    return data


def apply_metadata_override(
    metadata: dict[str, Any],
    override: dict[str, Any],
) -> tuple[dict[str, Any], list[str], list[str]]:
    result = dict(metadata)
    applied: list[str] = []
    warnings: list[str] = []

    for key in sorted(override):
        if key not in ALLOWED_KEYS:
            warnings.append(f"Ignored unsupported metadata override key: {key}")

    for key in sorted(STRING_KEYS):
        if key not in override:
            continue
        value = override[key]
        if not isinstance(value, str):
            warnings.append(f"Ignored metadata override {key}: expected string")
            continue
        cleaned = value.strip()
        if not cleaned:
            continue
        if contains_secret_like_value(cleaned):
            warnings.append(f"Ignored metadata override {key}: value looked secret-like")
            continue
        result[key] = cleaned
        applied.append(key)

    for key in sorted(LIST_KEYS):
        if key not in override:
            continue
        value = override[key]
        if not isinstance(value, list):
            warnings.append(f"Ignored metadata override {key}: expected list")
            continue
        cleaned = clean_string_list(value)
        if not cleaned:
            continue
        secret_items = [item for item in cleaned if contains_secret_like_value(item)]
        if secret_items:
            warnings.append(f"Ignored metadata override {key}: one or more values looked secret-like")
            continue
        result[key] = cleaned
        applied.append(key)

    return result, applied, warnings


def clean_string_list(value: list[Any]) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = str(item).strip()
        if not text or text in seen:
            continue
        cleaned.append(text)
        seen.add(text)
    return cleaned


def contains_secret_like_value(value: str) -> bool:
    return any(pattern.search(value) for pattern in SECRET_VALUE_PATTERNS)
