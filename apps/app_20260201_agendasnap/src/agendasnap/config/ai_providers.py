"""Provider and cost-profile resolution helpers for AI integrations."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

COST_PROFILES = {"standard", "low_cost"}

TEXT_PROVIDERS = {
    "openai",
    "dashscope",
    "baidu",
    "zhipu",
    "custom",
}

STT_PROVIDERS = {
    "openai_realtime",
    "openai_compatible_realtime",
    "dashscope_realtime",
    "baidu_realtime",
    "zhipu_realtime",
    "custom_realtime",
}


@dataclass(frozen=True)
class TextProviderDefaults:
    api_key_service: str
    base_url: str | None
    translation_model: str
    translation_low_cost_model: str
    minutes_model: str
    minutes_low_cost_model: str
    minutes_final_model: str
    minutes_low_cost_final_model: str


TEXT_PROVIDER_DEFAULTS: dict[str, TextProviderDefaults] = {
    "openai": TextProviderDefaults(
        api_key_service="openai",
        base_url="https://api.openai.com/v1/responses",
        translation_model="gpt-4o-mini",
        translation_low_cost_model="gpt-4o-mini",
        minutes_model="gpt-5.2",
        minutes_low_cost_model="gpt-4o-mini",
        minutes_final_model="gpt-5.2",
        minutes_low_cost_final_model="gpt-4o-mini",
    ),
    "dashscope": TextProviderDefaults(
        api_key_service="dashscope",
        base_url=None,
        translation_model="qwen-plus",
        translation_low_cost_model="qwen-turbo",
        minutes_model="qwen-plus",
        minutes_low_cost_model="qwen-turbo",
        minutes_final_model="qwen-plus",
        minutes_low_cost_final_model="qwen-turbo",
    ),
    "baidu": TextProviderDefaults(
        api_key_service="baidu",
        base_url=None,
        translation_model="ernie-4.0-8k",
        translation_low_cost_model="ernie-speed-128k",
        minutes_model="ernie-4.0-8k",
        minutes_low_cost_model="ernie-speed-128k",
        minutes_final_model="ernie-4.0-8k",
        minutes_low_cost_final_model="ernie-speed-128k",
    ),
    "zhipu": TextProviderDefaults(
        api_key_service="zhipu",
        base_url=None,
        translation_model="glm-4-plus",
        translation_low_cost_model="glm-4-air",
        minutes_model="glm-4-plus",
        minutes_low_cost_model="glm-4-air",
        minutes_final_model="glm-4-plus",
        minutes_low_cost_final_model="glm-4-air",
    ),
    "custom": TextProviderDefaults(
        api_key_service="custom",
        base_url=None,
        translation_model="",
        translation_low_cost_model="",
        minutes_model="",
        minutes_low_cost_model="",
        minutes_final_model="",
        minutes_low_cost_final_model="",
    ),
}


STT_PROVIDER_DEFAULTS: dict[str, dict[str, str | None]] = {
    "openai_realtime": {
        "api_key_service": "openai",
        "url": "wss://api.openai.com/v1/realtime?model=gpt-realtime",
    },
    "openai_compatible_realtime": {
        "api_key_service": "custom",
        "url": None,
    },
    "dashscope_realtime": {
        "api_key_service": "dashscope",
        "url": None,
    },
    "baidu_realtime": {
        "api_key_service": "baidu",
        "url": None,
    },
    "zhipu_realtime": {
        "api_key_service": "zhipu",
        "url": None,
    },
    "custom_realtime": {
        "api_key_service": "custom",
        "url": None,
    },
}


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _inject_model_query(url: str, model: str) -> str:
    if not url or not model:
        return url
    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["model"] = model
    return urlunparse(parsed._replace(query=urlencode(query)))


def normalize_cost_profile(value: Any, *, default: str = "standard") -> str:
    text = _as_text(value).lower() or default
    return text if text in COST_PROFILES else default


def normalize_provider(value: Any, *, allowed: set[str], default: str) -> str:
    text = _as_text(value).lower() or default
    return text if text in allowed else default


def normalize_api_key_priority(value: Any, *, fallback: Sequence[str] | None = None) -> list[str]:
    if isinstance(value, list):
        out = [str(x).strip() for x in value if str(x).strip()]
        if out:
            return out
    elif isinstance(value, str):
        text = value.strip()
        if text:
            return [text]

    out = [str(x).strip() for x in (fallback or []) if str(x).strip()]
    if out:
        return out
    return ["env"]


def select_model_for_cost_profile(
    *,
    standard_model: Any,
    low_cost_model: Any,
    cost_profile: Any,
    default_standard: str = "",
    default_low_cost: str = "",
) -> str:
    standard = _as_text(standard_model) or default_standard
    low_cost = _as_text(low_cost_model) or default_low_cost or standard
    if normalize_cost_profile(cost_profile) == "low_cost":
        return low_cost
    return standard


def resolve_stt_runtime(stt_cfg: Mapping[str, Any], *, fallback_priority: Sequence[str] | None = None) -> dict[str, Any]:
    provider = normalize_provider(stt_cfg.get("provider"), allowed=STT_PROVIDERS, default="openai_realtime")
    defaults = STT_PROVIDER_DEFAULTS.get(provider, STT_PROVIDER_DEFAULTS["openai_realtime"])

    cost_profile = normalize_cost_profile(stt_cfg.get("cost_profile"), default="standard")
    api_key_priority = normalize_api_key_priority(
        stt_cfg.get("api_key_priority") if "api_key_priority" in stt_cfg else stt_cfg.get("api_key_source"),
        fallback=fallback_priority,
    )

    runtime = {
        "provider": provider,
        "cost_profile": cost_profile,
        "api_key_priority": api_key_priority,
        "api_key_service": _as_text(stt_cfg.get("api_key_service")) or str(defaults.get("api_key_service") or "openai"),
        "url": _as_text(stt_cfg.get("url")) or _as_text(defaults.get("url")),
        "model": select_model_for_cost_profile(
            standard_model=stt_cfg.get("model"),
            low_cost_model=stt_cfg.get("low_cost_model"),
            cost_profile=cost_profile,
        ),
        "transcription_model": select_model_for_cost_profile(
            standard_model=stt_cfg.get("transcription_model"),
            low_cost_model=stt_cfg.get("low_cost_transcription_model"),
            cost_profile=cost_profile,
        ),
        "language": _as_text(stt_cfg.get("language")) or "ja",
        "request_timeout_seconds": float(stt_cfg.get("request_timeout_seconds", 30.0)),
    }
    if runtime["provider"] == "openai_realtime" and runtime.get("url") and runtime.get("model"):
        runtime["url"] = _inject_model_query(str(runtime["url"]), str(runtime["model"]))
    return runtime


def resolve_text_runtime(
    feature_cfg: Mapping[str, Any],
    *,
    fallback_priority: Sequence[str] | None = None,
    purpose: str,
) -> dict[str, Any]:
    provider = normalize_provider(feature_cfg.get("provider"), allowed=TEXT_PROVIDERS, default="openai")
    defaults = TEXT_PROVIDER_DEFAULTS.get(provider, TEXT_PROVIDER_DEFAULTS["openai"])

    cost_profile = normalize_cost_profile(feature_cfg.get("cost_profile"), default="standard")
    api_key_priority = normalize_api_key_priority(feature_cfg.get("api_key_priority"), fallback=fallback_priority)
    base_url = _as_text(feature_cfg.get("base_url")) or (defaults.base_url or "")
    api_key_service = _as_text(feature_cfg.get("api_key_service")) or defaults.api_key_service

    model = ""
    final_model = ""
    if purpose == "translation":
        model = select_model_for_cost_profile(
            standard_model=feature_cfg.get("model"),
            low_cost_model=feature_cfg.get("low_cost_model"),
            cost_profile=cost_profile,
            default_standard=defaults.translation_model,
            default_low_cost=defaults.translation_low_cost_model,
        )
    elif purpose == "minutes":
        model = select_model_for_cost_profile(
            standard_model=feature_cfg.get("model"),
            low_cost_model=feature_cfg.get("low_cost_model"),
            cost_profile=cost_profile,
            default_standard=defaults.minutes_model,
            default_low_cost=defaults.minutes_low_cost_model,
        )
        final_model = select_model_for_cost_profile(
            standard_model=feature_cfg.get("final_model"),
            low_cost_model=feature_cfg.get("low_cost_final_model"),
            cost_profile=cost_profile,
            default_standard=defaults.minutes_final_model,
            default_low_cost=defaults.minutes_low_cost_final_model,
        )
    else:
        raise ValueError(f"unknown text runtime purpose: {purpose}")

    return {
        "provider": provider,
        "cost_profile": cost_profile,
        "api_key_priority": api_key_priority,
        "api_key_service": api_key_service,
        "base_url": base_url,
        "model": model,
        "final_model": final_model,
    }
