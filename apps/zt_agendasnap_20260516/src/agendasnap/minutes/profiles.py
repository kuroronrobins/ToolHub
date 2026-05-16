"""Minutes cost-profile definitions and effective config resolution."""
from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class MinutesCostProfileDefinition:
    profile_id: str
    label: str
    description: str
    incremental_mode: str
    incremental_model: str | None = None
    final_model: str | None = None
    update_interval_seconds: int | None = None
    min_interval_seconds: int | None = None
    min_new_segments: int | None = None
    max_segments_per_call: int | None = None
    incremental_max_output_tokens: int | None = None
    final_max_output_tokens: int | None = None


MINUTES_PROFILE_CURRENT = "current_baseline"

MINUTES_COST_PROFILE_DEFINITIONS: dict[str, MinutesCostProfileDefinition] = {
    "current_baseline": MinutesCostProfileDefinition(
        profile_id="current_baseline",
        label="現行品質優先",
        description="Keep the existing minutes LLM model, cadence, and token caps.",
        incremental_mode="llm",
    ),
    "low_cost_incremental": MinutesCostProfileDefinition(
        profile_id="low_cost_incremental",
        label="低コスト増分 + 高品質final",
        description="Use the test-default low-cost realtime draft model and a high-quality final model.",
        incremental_mode="llm",
        incremental_model="gpt-5.4-nano",
        final_model="gpt-5.4",
        update_interval_seconds=180,
        min_interval_seconds=180,
        min_new_segments=12,
        max_segments_per_call=24,
        incremental_max_output_tokens=2500,
    ),
    "balanced_incremental": MinutesCostProfileDefinition(
        profile_id="balanced_incremental",
        label="バランス増分 + 高品質final",
        description="Use a medium-cost realtime draft model and keep the configured high-quality final model.",
        incremental_mode="llm",
        incremental_model="gpt-5-mini",
        update_interval_seconds=180,
        min_interval_seconds=180,
        min_new_segments=12,
        max_segments_per_call=24,
        incremental_max_output_tokens=3000,
    ),
    "final_quality_only": MinutesCostProfileDefinition(
        profile_id="final_quality_only",
        label="final品質優先",
        description="Skip LLM realtime draft calls; use local draft minutes and the configured final model.",
        incremental_mode="disabled",
        update_interval_seconds=300,
        min_interval_seconds=300,
        min_new_segments=999999,
        max_segments_per_call=1,
        incremental_max_output_tokens=0,
    ),
    "hybrid_extract_then_final": MinutesCostProfileDefinition(
        profile_id="hybrid_extract_then_final",
        label="実験: extractive + final",
        description="Use local extractive realtime notes and the configured final model.",
        incremental_mode="extractive",
        update_interval_seconds=180,
        min_interval_seconds=180,
        min_new_segments=12,
        max_segments_per_call=24,
        incremental_max_output_tokens=0,
    ),
    "high_quality_final_modern": MinutesCostProfileDefinition(
        profile_id="high_quality_final_modern",
        label="実験: modern high-quality final",
        description="Use cheap realtime draft notes while allowing the final model to be overridden.",
        incremental_mode="llm",
        incremental_model="gpt-4o-mini",
        update_interval_seconds=180,
        min_interval_seconds=180,
        min_new_segments=12,
        max_segments_per_call=24,
        incremental_max_output_tokens=2500,
    ),
}

MINUTES_PROFILE_IDS = tuple(MINUTES_COST_PROFILE_DEFINITIONS.keys())
MINUTES_PROFILE_LABELS = {
    profile_id: definition.label
    for profile_id, definition in MINUTES_COST_PROFILE_DEFINITIONS.items()
}

_INT_OVERRIDE_FIELDS = {
    "update_interval_seconds",
    "min_interval_seconds",
    "min_new_segments",
    "max_segments_per_call",
    "incremental_max_output_tokens",
    "final_max_output_tokens",
}
_STR_OVERRIDE_FIELDS = {"incremental_model", "final_model", "incremental_mode"}


def normalize_minutes_profile(value: Any) -> str:
    text = str(value or MINUTES_PROFILE_CURRENT).strip()
    return text if text in MINUTES_COST_PROFILE_DEFINITIONS else MINUTES_PROFILE_CURRENT


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _positive_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except Exception:
        return None
    return parsed if parsed >= 0 else None


def _profile_overrides(minutes_cfg: Mapping[str, Any], profile_id: str) -> dict[str, Any]:
    overrides = _as_mapping(minutes_cfg.get("profile_overrides"))
    profile_overrides = _as_mapping(overrides.get(profile_id))
    return dict(profile_overrides)


def describe_minutes_profile(minutes_cfg: Mapping[str, Any]) -> dict[str, Any]:
    """Return safe metadata about the active minutes profile."""
    profile_id = normalize_minutes_profile(minutes_cfg.get("profile"))
    definition = MINUTES_COST_PROFILE_DEFINITIONS[profile_id]
    effective = apply_minutes_profile(minutes_cfg)
    llm = _as_mapping(effective.get("llm"))
    return {
        "profile": profile_id,
        "label": definition.label,
        "description": definition.description,
        "incremental_mode": str(llm.get("incremental_mode", definition.incremental_mode)),
        "incremental_model": str(llm.get("model", "")),
        "final_model": str(llm.get("final_model", "")),
        "update_interval_seconds": effective.get("update_interval_seconds"),
        "min_interval_seconds": llm.get("min_interval_seconds"),
        "min_new_segments": llm.get("min_new_segments"),
        "max_segments_per_call": llm.get("max_segments_per_call"),
        "incremental_max_output_tokens": llm.get("incremental_max_output_tokens", llm.get("max_output_tokens")),
        "final_max_output_tokens": llm.get("final_max_output_tokens", llm.get("max_output_tokens")),
    }


def apply_minutes_profile(minutes_cfg: Mapping[str, Any] | None) -> dict[str, Any]:
    """Return an effective minutes config with a cost profile applied.

    The source config is never mutated. ``current_baseline`` is intentionally a
    no-op so existing default.yaml behavior stays unchanged.
    """
    source = _as_mapping(minutes_cfg)
    effective = copy.deepcopy(dict(source))
    profile_id = normalize_minutes_profile(effective.get("profile"))
    effective["profile"] = profile_id

    if profile_id == MINUTES_PROFILE_CURRENT:
        return effective

    definition = MINUTES_COST_PROFILE_DEFINITIONS[profile_id]
    llm = effective.get("llm")
    if not isinstance(llm, dict):
        llm = {}
        effective["llm"] = llm

    def set_int(target: dict[str, Any], key: str, value: int | None) -> None:
        if value is not None:
            target[key] = int(value)

    set_int(effective, "update_interval_seconds", definition.update_interval_seconds)
    set_int(llm, "min_interval_seconds", definition.min_interval_seconds)
    set_int(llm, "min_new_segments", definition.min_new_segments)
    set_int(llm, "max_segments_per_call", definition.max_segments_per_call)
    set_int(llm, "incremental_max_output_tokens", definition.incremental_max_output_tokens)
    set_int(llm, "final_max_output_tokens", definition.final_max_output_tokens)

    llm["incremental_mode"] = definition.incremental_mode
    llm["incremental_enable"] = definition.incremental_mode == "llm"
    if definition.incremental_model:
        llm["model"] = definition.incremental_model
    if definition.final_model:
        llm["final_model"] = definition.final_model

    for key, value in _profile_overrides(source, profile_id).items():
        if key in _STR_OVERRIDE_FIELDS and value is not None:
            text = str(value).strip()
            if text:
                if key == "incremental_model":
                    llm["model"] = text
                else:
                    llm[key] = text
                if key == "incremental_mode":
                    llm["incremental_enable"] = text == "llm"
        elif key in _INT_OVERRIDE_FIELDS:
            parsed = _positive_int(value)
            if parsed is not None:
                if key == "update_interval_seconds":
                    effective[key] = parsed
                else:
                    llm[key] = parsed

    return effective
