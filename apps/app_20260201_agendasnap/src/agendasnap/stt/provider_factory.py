"""STT provider factory for realtime engines."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from agendasnap.config.ai_providers import resolve_stt_runtime
from agendasnap.stt.base import ISttEngine
from agendasnap.stt.openai_realtime import OpenAIRealtime


@dataclass(frozen=True)
class SttRuntimeConfig:
    provider: str
    url: str
    model: str
    transcription_model: str
    language: str
    api_key_priority: list[str]
    api_key_service: str
    request_timeout_seconds: float
    source: str
    noise_reduction: Any | None
    transcription_prompt: str | None
    prompt_metadata: Mapping[str, Any] | None


def resolve_runtime_for_source(
    *,
    source: str,
    stt_cfg: Mapping[str, Any],
    fallback_priority: Sequence[str] | None = None,
) -> SttRuntimeConfig:
    runtime = resolve_stt_runtime(stt_cfg, fallback_priority=fallback_priority)

    noise_reduction = stt_cfg.get("noise_reduction_sys") if source == "sys" else stt_cfg.get("noise_reduction_mic")
    cfg = SttRuntimeConfig(
        provider=str(runtime["provider"]),
        url=str(runtime.get("url") or ""),
        model=str(runtime.get("model") or ""),
        transcription_model=str(runtime.get("transcription_model") or ""),
        language=str(runtime.get("language") or "ja"),
        api_key_priority=list(runtime.get("api_key_priority") or ["env"]),
        api_key_service=str(runtime.get("api_key_service") or "openai"),
        request_timeout_seconds=float(runtime.get("request_timeout_seconds", 30.0)),
        source=source,
        noise_reduction=noise_reduction,
        transcription_prompt=str(stt_cfg.get("transcription_prompt") or "").strip() or None,
        prompt_metadata=stt_cfg.get("rolling_context_metadata")
        if isinstance(stt_cfg.get("rolling_context_metadata"), Mapping)
        else None,
    )
    if not cfg.url:
        raise RuntimeError(
            f"STT provider '{cfg.provider}' requires stt.url to be configured for realtime access."
        )
    if not cfg.transcription_model:
        raise RuntimeError("stt.transcription_model is required")
    return cfg


def build_realtime_engine(
    *,
    source: str,
    stt_cfg: Mapping[str, Any],
    fallback_priority: Sequence[str] | None = None,
) -> tuple[ISttEngine, SttRuntimeConfig]:
    runtime = resolve_runtime_for_source(
        source=source,
        stt_cfg=stt_cfg,
        fallback_priority=fallback_priority,
    )

    # Providers currently share the OpenAI-compatible realtime protocol path.
    engine: ISttEngine = OpenAIRealtime(
        url=runtime.url,
        api_key_priority=runtime.api_key_priority,
        api_key_service=runtime.api_key_service,
        language=runtime.language,
        transcription_model=runtime.transcription_model,
        source=runtime.source,
        noise_reduction=runtime.noise_reduction,
        transcription_prompt=runtime.transcription_prompt,
        prompt_metadata=runtime.prompt_metadata,
        request_timeout_seconds=runtime.request_timeout_seconds,
    )
    return engine, runtime
