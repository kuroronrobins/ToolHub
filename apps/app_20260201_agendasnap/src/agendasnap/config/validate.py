"""Config validation for AgendaSnap.

Philosophy:
- Fail fast on misconfiguration.
- Report *all* detected issues at once.
- Avoid silent fallback/guessing.
"""
from __future__ import annotations

from typing import Any, Dict, List, Sequence

from agendasnap.config.ai_providers import COST_PROFILES, STT_PROVIDERS, TEXT_PROVIDERS
from agendasnap.config.glossary import (
    GLOSSARY_CATEGORIES,
    ROLLING_CONTEXT_GUARD_STYLES,
    ROLLING_CONTEXT_UPDATE_POLICIES,
)
from agendasnap.minutes.profiles import MINUTES_PROFILE_IDS

def _is_num(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def validate_config(cfg: Dict[str, Any]) -> None:
    errors: List[str] = []

    def req_map(root: Dict[str, Any], key: str, ctx: str) -> Dict[str, Any]:
        v = root.get(key)
        if not isinstance(v, dict):
            errors.append(f"{ctx}.{key}: required mapping")
            return {}
        return v

    def req(root: Dict[str, Any], key: str, ctx: str, typ, pred=None) -> Any:
        if key not in root:
            errors.append(f"{ctx}.{key}: missing")
            return None
        v = root.get(key)
        if typ == "num":
            if not _is_num(v):
                errors.append(f"{ctx}.{key}: expected number, got {type(v).__name__}")
                return None
        elif typ == "bool":
            if not isinstance(v, bool):
                errors.append(f"{ctx}.{key}: expected bool, got {type(v).__name__}")
                return None
        elif typ == "int":
            if not isinstance(v, int) or isinstance(v, bool):
                errors.append(f"{ctx}.{key}: expected int, got {type(v).__name__}")
                return None
        elif typ == "str":
            if not isinstance(v, str) or not v.strip():
                errors.append(f"{ctx}.{key}: expected non-empty string")
                return None
        elif typ == "list_str":
            if not isinstance(v, list) or not v or not all(isinstance(x, str) and x for x in v):
                errors.append(f"{ctx}.{key}: expected non-empty list[str]")
                return None
        else:
            raise ValueError(f"unknown typ {typ}")

        if pred and v is not None:
            try:
                if not pred(v):
                    errors.append(f"{ctx}.{key}: invalid value: {v!r}")
            except Exception:
                errors.append(f"{ctx}.{key}: invalid value: {v!r}")
        return v

    def opt(root: Dict[str, Any], key: str, ctx: str, typ, pred=None) -> Any:
        if key not in root:
            return None
        return req(root, key, ctx, typ, pred)

    audio = req_map(cfg, "audio", "cfg")
    stt = req_map(cfg, "stt", "cfg")
    minutes = req_map(cfg, "minutes", "cfg")
    secrets = req_map(cfg, "secrets", "cfg")
    translation = cfg.get("translation")
    resilience = cfg.get("resilience")
    ui = cfg.get("ui")

    # audio
    req(audio, "capture_rate", "audio", "int", lambda v: v > 0)
    tr = req(audio, "target_rate", "audio", "int", lambda v: v > 0)
    if tr is not None and tr != 24000:
        errors.append(f"audio.target_rate: must be 24000 for Realtime (got {tr})")

    req(audio, "channels_system", "audio", "int", lambda v: v > 0)
    req(audio, "channels_mic", "audio", "int", lambda v: v > 0)
    req(audio, "frames_per_buffer", "audio", "int", lambda v: v > 0)
    req(audio, "chunk_ms", "audio", "int", lambda v: v > 0)

    # required thresholds (no fallback)
    req(audio, "energy_threshold_sys", "audio", "num", lambda v: v >= 0)
    req(audio, "energy_threshold_mic", "audio", "num", lambda v: v >= 0)

    req(audio, "queue_max_chunks", "audio", "int", lambda v: v > 0)
    req(audio, "session_root", "audio", "str")
    if "system_device_follow_default" in audio:
        req(audio, "system_device_follow_default", "audio", "bool")
    if "system_device_prompt" in audio:
        req(audio, "system_device_prompt", "audio", "bool")
    if "system_device_index" in audio and audio.get("system_device_index") is not None:
        req(audio, "system_device_index", "audio", "int", lambda v: int(v) >= 0)
    if "mic_device_index" in audio and audio.get("mic_device_index") is not None:
        req(audio, "mic_device_index", "audio", "int", lambda v: int(v) >= 0)
    if "metrics_interval_seconds" in audio:
        req(audio, "metrics_interval_seconds", "audio", "num", lambda v: v >= 0)
    if "level_interval_seconds" in audio:
        req(audio, "level_interval_seconds", "audio", "num", lambda v: 0.02 <= v <= 1.0)
    if "enable_system" in audio:
        req(audio, "enable_system", "audio", "bool")
    if "enable_mic" in audio:
        req(audio, "enable_mic", "audio", "bool")
    recording = audio.get("recording")
    if isinstance(recording, dict):
        req(recording, "system", "audio.recording", "bool")
        req(recording, "mic", "audio.recording", "bool")
        fmt = req(recording, "format", "audio.recording", "str")
        if fmt and fmt.lower() not in ("wav", "flac"):
            errors.append(f"audio.recording.format: invalid value: {fmt!r}")
        req(recording, "rotate_seconds", "audio.recording", "num", lambda v: v >= 0)
        if "rotate_mb" in recording:
            req(recording, "rotate_mb", "audio.recording", "num", lambda v: v >= 0)
        if "rotate_bytes" in recording:
            req(recording, "rotate_bytes", "audio.recording", "int", lambda v: v >= 0)
        dir_val = recording.get("directory")
        if not isinstance(dir_val, str):
            errors.append("audio.recording.directory: expected string")
        # legacy keys are optional but validated if present
        opt(audio, "save_wav_system", "audio", "bool")
        opt(audio, "save_wav_mic", "audio", "bool")
    else:
        req(audio, "save_wav_system", "audio", "bool")
        req(audio, "save_wav_mic", "audio", "bool")

    # optional calibration
    calibration = audio.get("calibration")
    if isinstance(calibration, dict):
        req(calibration, "enable", "audio.calibration", "bool")
        req(calibration, "seconds", "audio.calibration", "num", lambda v: v >= 0)
        req(calibration, "percentile", "audio.calibration", "num", lambda v: 0 <= v <= 100)
        req(calibration, "multiplier", "audio.calibration", "num", lambda v: v > 0)
        if "min_threshold_sys" in calibration:
            req(calibration, "min_threshold_sys", "audio.calibration", "num", lambda v: v >= 0)
        if "min_threshold_mic" in calibration:
            req(calibration, "min_threshold_mic", "audio.calibration", "num", lambda v: v >= 0)
        if "max_threshold_sys" in calibration:
            req(calibration, "max_threshold_sys", "audio.calibration", "num", lambda v: v >= 0)
        if "max_threshold_mic" in calibration:
            req(calibration, "max_threshold_mic", "audio.calibration", "num", lambda v: v >= 0)
        if "recalibration_interval_seconds" in calibration:
            req(calibration, "recalibration_interval_seconds", "audio.calibration", "num", lambda v: v >= 0)
        if "recalibration_window_seconds" in calibration:
            req(calibration, "recalibration_window_seconds", "audio.calibration", "num", lambda v: v >= 0)
        if "recalibration_min_samples" in calibration:
            req(calibration, "recalibration_min_samples", "audio.calibration", "int", lambda v: v >= 0)
        if "recalibration_min_change_ratio" in calibration:
            req(calibration, "recalibration_min_change_ratio", "audio.calibration", "num", lambda v: v >= 0)

    vad = audio.get("vad")
    if isinstance(vad, dict):
        req(vad, "enable_hysteresis", "audio.vad", "bool")
        if "start_threshold_sys" in vad:
            req(vad, "start_threshold_sys", "audio.vad", "num", lambda v: v >= 0)
        if "stop_threshold_sys" in vad:
            req(vad, "stop_threshold_sys", "audio.vad", "num", lambda v: v >= 0)
        if "start_threshold_mic" in vad:
            req(vad, "start_threshold_mic", "audio.vad", "num", lambda v: v >= 0)
        if "stop_threshold_mic" in vad:
            req(vad, "stop_threshold_mic", "audio.vad", "num", lambda v: v >= 0)
        if "start_ratio_sys" in vad:
            req(vad, "start_ratio_sys", "audio.vad", "num", lambda v: v >= 0)
        if "stop_ratio_sys" in vad:
            req(vad, "stop_ratio_sys", "audio.vad", "num", lambda v: v >= 0)
        if "start_ratio_mic" in vad:
            req(vad, "start_ratio_mic", "audio.vad", "num", lambda v: v >= 0)
        if "stop_ratio_mic" in vad:
            req(vad, "stop_ratio_mic", "audio.vad", "num", lambda v: v >= 0)
        if "min_voice_chunks_sys" in vad:
            req(vad, "min_voice_chunks_sys", "audio.vad", "int", lambda v: v >= 1)
        if "min_voice_chunks_mic" in vad:
            req(vad, "min_voice_chunks_mic", "audio.vad", "int", lambda v: v >= 1)

        st = vad.get("start_threshold_sys")
        sp = vad.get("stop_threshold_sys")
        if st is not None and sp is not None and st < sp:
            errors.append("audio.vad: start_threshold_sys should be >= stop_threshold_sys")

        st = vad.get("start_threshold_mic")
        sp = vad.get("stop_threshold_mic")
        if st is not None and sp is not None and st < sp:
            errors.append("audio.vad: start_threshold_mic should be >= stop_threshold_mic")

        guard_mic = vad.get("guard_mic")
        if isinstance(guard_mic, dict):
            if "enable" in guard_mic:
                req(guard_mic, "enable", "audio.vad.guard_mic", "bool")
            if "frame_ms" in guard_mic:
                req(guard_mic, "frame_ms", "audio.vad.guard_mic", "int", lambda v: v > 0)
            if "min_voiced_ms" in guard_mic:
                req(guard_mic, "min_voiced_ms", "audio.vad.guard_mic", "num", lambda v: v >= 0)
            if "min_rms_std_ratio" in guard_mic:
                req(guard_mic, "min_rms_std_ratio", "audio.vad.guard_mic", "num", lambda v: v >= 0)
            if "strong_rms_ratio" in guard_mic:
                req(guard_mic, "strong_rms_ratio", "audio.vad.guard_mic", "num", lambda v: v >= 0)
            if "prebuffer_chunks" in guard_mic:
                req(guard_mic, "prebuffer_chunks", "audio.vad.guard_mic", "int", lambda v: v >= 0)

        adaptive = vad.get("adaptive")
        if isinstance(adaptive, dict):
            if "enable" in adaptive:
                req(adaptive, "enable", "audio.vad.adaptive", "bool")
            if "update_interval_seconds" in adaptive:
                req(adaptive, "update_interval_seconds", "audio.vad.adaptive", "num", lambda v: v > 0)
            if "target_drop_rate" in adaptive:
                req(adaptive, "target_drop_rate", "audio.vad.adaptive", "num", lambda v: 0 <= v <= 1)
            if "deadband" in adaptive:
                req(adaptive, "deadband", "audio.vad.adaptive", "num", lambda v: 0 <= v <= 1)
            if "max_step_ratio" in adaptive:
                req(adaptive, "max_step_ratio", "audio.vad.adaptive", "num", lambda v: 0 <= v <= 1)
            if "smoothing" in adaptive:
                req(adaptive, "smoothing", "audio.vad.adaptive", "num", lambda v: 0 <= v <= 0.95)
            if "min_samples" in adaptive:
                req(adaptive, "min_samples", "audio.vad.adaptive", "int", lambda v: v >= 0)
            if "min_change_ratio" in adaptive:
                req(adaptive, "min_change_ratio", "audio.vad.adaptive", "num", lambda v: v >= 0)
            if "min_threshold_sys" in adaptive:
                req(adaptive, "min_threshold_sys", "audio.vad.adaptive", "num", lambda v: v >= 0)
            if "max_threshold_sys" in adaptive:
                req(adaptive, "max_threshold_sys", "audio.vad.adaptive", "num", lambda v: v >= 0)
            if "min_threshold_mic" in adaptive:
                req(adaptive, "min_threshold_mic", "audio.vad.adaptive", "num", lambda v: v >= 0)
            if "max_threshold_mic" in adaptive:
                req(adaptive, "max_threshold_mic", "audio.vad.adaptive", "num", lambda v: v >= 0)

    # stt
    req(stt, "enable", "stt", "bool")
    if "provider" in stt:
        req(stt, "provider", "stt", "str", lambda v: str(v).strip().lower() in STT_PROVIDERS)
    if "cost_profile" in stt:
        req(stt, "cost_profile", "stt", "str", lambda v: str(v).strip().lower() in COST_PROFILES)
    req(stt, "url", "stt", "str")
    req(stt, "model", "stt", "str")
    req(stt, "language", "stt", "str")
    req(stt, "transcription_model", "stt", "str")
    if "low_cost_model" in stt:
        req(stt, "low_cost_model", "stt", "str")
    if "low_cost_transcription_model" in stt:
        req(stt, "low_cost_transcription_model", "stt", "str")
    if "api_key_service" in stt:
        req(stt, "api_key_service", "stt", "str")
    if "api_key_priority" in stt:
        req(stt, "api_key_priority", "stt", "list_str")
    req(stt, "segment_max_seconds", "stt", "num", lambda v: v > 0)
    req(stt, "segment_gap_ms", "stt", "num", lambda v: v >= 0)
    if "noise_reduction_sys" in stt:
        req(stt, "noise_reduction_sys", "stt", "str")
    if "noise_reduction_mic" in stt:
        req(stt, "noise_reduction_mic", "stt", "str")
    if "transcription_prompt" in stt and not isinstance(stt.get("transcription_prompt"), str):
        errors.append("stt.transcription_prompt: expected string")
    rolling_context = stt.get("rolling_context")
    if rolling_context is not None:
        if not isinstance(rolling_context, dict):
            errors.append("stt.rolling_context: expected mapping")
        else:
            for key in (
                "enable",
                "use_recent_final_transcript",
                "use_topic",
                "use_glossary",
                "use_summary",
                "include_partial",
                "include_low_confidence",
                "repetition_guard",
            ):
                if key in rolling_context:
                    req(rolling_context, key, "stt.rolling_context", "bool")
            for key in (
                "max_recent_segments",
                "max_recent_chars",
                "max_glossary_terms",
                "max_prompt_chars",
            ):
                if key in rolling_context:
                    req(rolling_context, key, "stt.rolling_context", "int", lambda v: v >= 0)
            if "max_prompt_chars" in rolling_context and isinstance(
                rolling_context.get("max_prompt_chars"), int
            ) and rolling_context.get("max_prompt_chars") < 200:
                errors.append("stt.rolling_context.max_prompt_chars: should be >= 200")
            if rolling_context.get("include_partial") is True:
                errors.append("stt.rolling_context.include_partial: must remain false")
            if "update_policy" in rolling_context:
                req(
                    rolling_context,
                    "update_policy",
                    "stt.rolling_context",
                    "str",
                    lambda v: str(v).strip() in ROLLING_CONTEXT_UPDATE_POLICIES,
                )
            if "guard_style" in rolling_context:
                req(
                    rolling_context,
                    "guard_style",
                    "stt.rolling_context",
                    "str",
                    lambda v: str(v).strip() in ROLLING_CONTEXT_GUARD_STYLES,
                )
    if "include_logprobs" in stt:
        req(stt, "include_logprobs", "stt", "bool")
    if "low_confidence_marking" in stt:
        req(stt, "low_confidence_marking", "stt", "bool")

    meeting = cfg.get("meeting")
    if isinstance(meeting, dict):
        if "topic" in meeting and not isinstance(meeting.get("topic"), str):
            errors.append("meeting.topic: expected string")
        if "glossary" in meeting:
            glossary = meeting.get("glossary")
            if not isinstance(glossary, list):
                errors.append("meeting.glossary: expected list[str|dict]")
            else:
                for idx, item in enumerate(glossary):
                    ctx = f"meeting.glossary[{idx}]"
                    if isinstance(item, str):
                        continue
                    if not isinstance(item, dict):
                        errors.append(f"{ctx}: expected string or mapping")
                        continue
                    surface = item.get("surface")
                    if not isinstance(surface, str) or not surface.strip():
                        errors.append(f"{ctx}.surface: expected non-empty string")
                    if "readings" in item:
                        readings = item.get("readings")
                        if not isinstance(readings, list) or not all(isinstance(x, str) for x in readings):
                            errors.append(f"{ctx}.readings: expected list[str]")
                    if "aliases" in item:
                        aliases = item.get("aliases")
                        if not isinstance(aliases, list) or not all(isinstance(x, str) for x in aliases):
                            errors.append(f"{ctx}.aliases: expected list[str]")
                    if "category" in item:
                        category = str(item.get("category") or "").strip().lower()
                        if category and category not in GLOSSARY_CATEGORIES:
                            errors.append(f"{ctx}.category: invalid value: {item.get('category')!r}")
                    if "note" in item and not isinstance(item.get("note"), str):
                        errors.append(f"{ctx}.note: expected string")
                    if "enabled" in item and not isinstance(item.get("enabled"), bool):
                        errors.append(f"{ctx}.enabled: expected bool")

    if ui is not None and not isinstance(ui, dict):
        errors.append("ui: expected map")
    if isinstance(ui, dict):
        caption = ui.get("caption")
        if isinstance(caption, dict):
            if "font_size" in caption:
                req(caption, "font_size", "ui.caption", "num", lambda v: v > 0)
            if "min_font_size" in caption:
                req(caption, "min_font_size", "ui.caption", "num", lambda v: v > 0)
            if "max_font_size" in caption:
                req(caption, "max_font_size", "ui.caption", "num", lambda v: v > 0)
            min_size = caption.get("min_font_size")
            max_size = caption.get("max_font_size")
            if _is_num(min_size) and _is_num(max_size) and float(min_size) > float(max_size):
                errors.append("ui.caption: min_font_size must be <= max_font_size")

    # optional: request timeout, rolling minutes
    if "request_timeout_seconds" in stt:
        req(stt, "request_timeout_seconds", "stt", "num", lambda v: v > 0)
    if "rolling_session_minutes" in stt:
        req(stt, "rolling_session_minutes", "stt", "int", lambda v: v > 0)
    if "rolling_overlap_seconds" in stt:
        req(stt, "rolling_overlap_seconds", "stt", "num", lambda v: v >= 0)
    if "min_turn_seconds" in stt:
        req(stt, "min_turn_seconds", "stt", "num", lambda v: v >= 0)
    if "max_consecutive_failures" in stt:
        req(stt, "max_consecutive_failures", "stt", "int", lambda v: v > 0)
    if "reconnect_enable" in stt:
        req(stt, "reconnect_enable", "stt", "bool")
    if "reconnect_backoff_seconds" in stt:
        req(stt, "reconnect_backoff_seconds", "stt", "num", lambda v: v > 0)
    if "reconnect_max_backoff_seconds" in stt:
        req(stt, "reconnect_max_backoff_seconds", "stt", "num", lambda v: v > 0)

    # secrets
    req(secrets, "priority", "secrets", "list_str")

    if isinstance(translation, dict):
        if "provider" in translation:
            req(
                translation,
                "provider",
                "translation",
                "str",
                lambda v: str(v).strip().lower() in TEXT_PROVIDERS,
            )
        if "cost_profile" in translation:
            req(
                translation,
                "cost_profile",
                "translation",
                "str",
                lambda v: str(v).strip().lower() in COST_PROFILES,
            )
        if "enable" in translation:
            req(translation, "enable", "translation", "bool")
        if "target_language" in translation:
            req(translation, "target_language", "translation", "str")
        if "target_language_mic" in translation:
            req(translation, "target_language_mic", "translation", "str")
        if "target_language_sys" in translation:
            req(translation, "target_language_sys", "translation", "str")
        if "model" in translation:
            req(translation, "model", "translation", "str")
        if "low_cost_model" in translation:
            req(translation, "low_cost_model", "translation", "str")
        if "base_url" in translation:
            req(translation, "base_url", "translation", "str")
        if "api_key_service" in translation:
            req(translation, "api_key_service", "translation", "str")
        if "api_key_priority" in translation:
            req(translation, "api_key_priority", "translation", "list_str")
        if "batch_wait_ms" in translation:
            req(translation, "batch_wait_ms", "translation", "int", lambda v: v >= 0)
        if "batch_lines" in translation:
            req(translation, "batch_lines", "translation", "int", lambda v: v >= 1)
        if "batch_chars" in translation:
            req(translation, "batch_chars", "translation", "int", lambda v: v >= 1)
        if "request_timeout_seconds" in translation:
            req(translation, "request_timeout_seconds", "translation", "num", lambda v: v > 0)
        if "max_output_tokens" in translation:
            req(translation, "max_output_tokens", "translation", "int", lambda v: v > 0)
        if "backfill_lines" in translation:
            req(translation, "backfill_lines", "translation", "int", lambda v: v >= 0)

    # minutes
    if "profile" in minutes:
        req(
            minutes,
            "profile",
            "minutes",
            "str",
            lambda v: str(v).strip() in MINUTES_PROFILE_IDS,
        )
    req(minutes, "update_interval_seconds", "minutes", "int", lambda v: v > 0)
    if "merge_enable" in minutes:
        req(minutes, "merge_enable", "minutes", "bool")
    if "merge_min_seconds" in minutes:
        req(minutes, "merge_min_seconds", "minutes", "num", lambda v: v >= 0)
    if "merge_max_seconds" in minutes:
        req(minutes, "merge_max_seconds", "minutes", "num", lambda v: v >= 0)
    if "merge_gap_seconds" in minutes:
        req(minutes, "merge_gap_seconds", "minutes", "num", lambda v: v >= 0)
    if "merge_by_source" in minutes:
        req(minutes, "merge_by_source", "minutes", "bool")
    if "dedupe_enable" in minutes:
        req(minutes, "dedupe_enable", "minutes", "bool")
    if "dedupe_window_seconds" in minutes:
        req(minutes, "dedupe_window_seconds", "minutes", "num", lambda v: v >= 0)
    if "dedupe_similarity" in minutes:
        req(minutes, "dedupe_similarity", "minutes", "num", lambda v: 0 <= v <= 1)

    filt = minutes.get("filter")
    if isinstance(filt, dict):
        if "enable" in filt:
            req(filt, "enable", "minutes.filter", "bool")
        if "min_chars" in filt:
            req(filt, "min_chars", "minutes.filter", "int", lambda v: v >= 0)
        if "allowlist" in filt:
            allow = filt.get("allowlist")
            if not isinstance(allow, list) or not all(isinstance(x, str) and x for x in allow):
                errors.append("minutes.filter.allowlist: expected list[str] (empty allowed)")

    llm = minutes.get("llm")
    if isinstance(llm, dict):
        if "provider" in llm:
            req(
                llm,
                "provider",
                "minutes.llm",
                "str",
                lambda v: str(v).strip().lower() in TEXT_PROVIDERS,
            )
        if "cost_profile" in llm:
            req(
                llm,
                "cost_profile",
                "minutes.llm",
                "str",
                lambda v: str(v).strip().lower() in COST_PROFILES,
            )
        req(llm, "enable", "minutes.llm", "bool")
        if "model" in llm:
            req(llm, "model", "minutes.llm", "str")
        if "low_cost_model" in llm:
            req(llm, "low_cost_model", "minutes.llm", "str")
        if "final_model" in llm:
            req(llm, "final_model", "minutes.llm", "str")
        if "low_cost_final_model" in llm:
            req(llm, "low_cost_final_model", "minutes.llm", "str")
        if "base_url" in llm:
            req(llm, "base_url", "minutes.llm", "str")
        if "api_key_service" in llm:
            req(llm, "api_key_service", "minutes.llm", "str")
        if "api_key_priority" in llm:
            req(llm, "api_key_priority", "minutes.llm", "list_str")
        if "temperature" in llm:
            req(llm, "temperature", "minutes.llm", "num", lambda v: v >= 0)
        if "max_output_tokens" in llm:
            req(llm, "max_output_tokens", "minutes.llm", "int", lambda v: v > 0)
        if "incremental_enable" in llm:
            req(llm, "incremental_enable", "minutes.llm", "bool")
        if "incremental_mode" in llm:
            req(
                llm,
                "incremental_mode",
                "minutes.llm",
                "str",
                lambda v: str(v).strip().lower() in {"llm", "disabled", "extractive"},
            )
        if "incremental_max_output_tokens" in llm:
            req(llm, "incremental_max_output_tokens", "minutes.llm", "int", lambda v: v >= 0)
        if "final_max_output_tokens" in llm:
            req(llm, "final_max_output_tokens", "minutes.llm", "int", lambda v: v > 0)
        if "reasoning_effort" in llm:
            req(
                llm,
                "reasoning_effort",
                "minutes.llm",
                "str",
                lambda v: str(v).strip().lower() in {"none", "low", "medium", "high"},
            )
        if "store" in llm:
            req(llm, "store", "minutes.llm", "bool")
        if "structured_output" in llm:
            req(llm, "structured_output", "minutes.llm", "bool")
        if "min_interval_seconds" in llm:
            req(llm, "min_interval_seconds", "minutes.llm", "num", lambda v: v >= 0)
        if "min_new_segments" in llm:
            req(llm, "min_new_segments", "minutes.llm", "int", lambda v: v >= 0)
        if "max_segments_per_call" in llm:
            req(llm, "max_segments_per_call", "minutes.llm", "int", lambda v: v > 0)
        if "request_timeout_seconds" in llm:
            req(llm, "request_timeout_seconds", "minutes.llm", "num", lambda v: v > 0)
        if "confidence_threshold" in llm:
            req(llm, "confidence_threshold", "minutes.llm", "num", lambda v: 0 <= v <= 1)
        if "dedupe_similarity" in llm:
            req(llm, "dedupe_similarity", "minutes.llm", "num", lambda v: 0 <= v <= 1)
        if "prompt_version" in llm:
            req(llm, "prompt_version", "minutes.llm", "str")
        if "language" in llm:
            req(llm, "language", "minutes.llm", "str")
        cost_tracking = llm.get("cost_tracking")
        if isinstance(cost_tracking, dict):
            if "enable" in cost_tracking:
                req(cost_tracking, "enable", "minutes.llm.cost_tracking", "bool")
            if "filename" in cost_tracking:
                filename = req(cost_tracking, "filename", "minutes.llm.cost_tracking", "str")
                if filename and ("/" in filename or "\\" in filename):
                    errors.append("minutes.llm.cost_tracking.filename: must be a filename, not a path")

    profile_overrides = minutes.get("profile_overrides")
    if profile_overrides is not None:
        if not isinstance(profile_overrides, dict):
            errors.append("minutes.profile_overrides: expected mapping")
        else:
            for profile_id, override in profile_overrides.items():
                ctx = f"minutes.profile_overrides.{profile_id}"
                if str(profile_id) not in MINUTES_PROFILE_IDS:
                    errors.append(f"{ctx}: unknown profile")
                    continue
                if not isinstance(override, dict):
                    errors.append(f"{ctx}: expected mapping")
                    continue
                for key in ("incremental_model", "final_model"):
                    if key in override:
                        req(override, key, ctx, "str")
                if "incremental_mode" in override:
                    req(
                        override,
                        "incremental_mode",
                        ctx,
                        "str",
                        lambda v: str(v).strip().lower() in {"llm", "disabled", "extractive"},
                    )
                for key in (
                    "update_interval_seconds",
                    "min_interval_seconds",
                    "min_new_segments",
                    "incremental_max_output_tokens",
                ):
                    if key in override:
                        req(override, key, ctx, "int", lambda v: v >= 0)
                if "max_segments_per_call" in override:
                    req(override, "max_segments_per_call", ctx, "int", lambda v: v > 0)
                if "final_max_output_tokens" in override:
                    req(override, "final_max_output_tokens", ctx, "int", lambda v: v > 0)

    finalize = minutes.get("finalize")
    if isinstance(finalize, dict):
        if "request_timeout_seconds" in finalize:
            req(finalize, "request_timeout_seconds", "minutes.finalize", "num", lambda v: v > 0)
        if "retries" in finalize:
            req(finalize, "retries", "minutes.finalize", "int", lambda v: v >= 0)
        if "retry_backoff_seconds" in finalize:
            req(finalize, "retry_backoff_seconds", "minutes.finalize", "num", lambda v: v > 0)
        if "fallback_model" in finalize:
            req(finalize, "fallback_model", "minutes.finalize", "str")
        if "low_cost_fallback_model" in finalize:
            req(finalize, "low_cost_fallback_model", "minutes.finalize", "str")
        if "fallback_request_timeout_seconds" in finalize:
            req(
                finalize,
                "fallback_request_timeout_seconds",
                "minutes.finalize",
                "num",
                lambda v: v > 0,
            )
        chunking = finalize.get("chunking")
        if isinstance(chunking, dict):
            if "mode" in chunking:
                req(
                    chunking,
                    "mode",
                    "minutes.finalize.chunking",
                    "str",
                    lambda v: str(v).strip().lower() in {"auto", "always", "off"},
                )
            if "min_chars" in chunking:
                req(chunking, "min_chars", "minutes.finalize.chunking", "int", lambda v: v >= 0)
            if "max_chars" in chunking:
                req(chunking, "max_chars", "minutes.finalize.chunking", "int", lambda v: v > 0)
            if "overlap_chars" in chunking:
                req(chunking, "overlap_chars", "minutes.finalize.chunking", "int", lambda v: v >= 0)
            if "max_segments" in chunking:
                req(chunking, "max_segments", "minutes.finalize.chunking", "int", lambda v: v > 0)

    if isinstance(resilience, dict):
        req(resilience, "enable", "resilience", "bool")
        if "status_interval_seconds" in resilience:
            req(resilience, "status_interval_seconds", "resilience", "num", lambda v: v >= 0)

        delay_mode = resilience.get("delay_mode")
        if isinstance(delay_mode, dict):
            if "queue_ratio" in delay_mode:
                req(delay_mode, "queue_ratio", "resilience.delay_mode", "num", lambda v: v >= 0)
            if "delay_seconds" in delay_mode:
                req(delay_mode, "delay_seconds", "resilience.delay_mode", "num", lambda v: v >= 0)
            if "drop_rate" in delay_mode:
                req(delay_mode, "drop_rate", "resilience.delay_mode", "num", lambda v: 0 <= v <= 1)
            if "recover_queue_ratio" in delay_mode:
                req(delay_mode, "recover_queue_ratio", "resilience.delay_mode", "num", lambda v: v >= 0)
            if "recover_delay_seconds" in delay_mode:
                req(delay_mode, "recover_delay_seconds", "resilience.delay_mode", "num", lambda v: v >= 0)
            if "recover_drop_rate" in delay_mode:
                req(delay_mode, "recover_drop_rate", "resilience.delay_mode", "num", lambda v: 0 <= v <= 1)

        actions = resilience.get("actions")
        if isinstance(actions, dict):
            if "segment_max_seconds_boost" in actions:
                req(actions, "segment_max_seconds_boost", "resilience.actions", "num", lambda v: v >= 0)
            if "minutes_interval_boost" in actions:
                req(actions, "minutes_interval_boost", "resilience.actions", "num", lambda v: v >= 0)

        catch_up = resilience.get("catch_up")
        if isinstance(catch_up, dict):
            if "enable" in catch_up:
                req(catch_up, "enable", "resilience.catch_up", "bool")
            if "only_when_delay" in catch_up:
                req(catch_up, "only_when_delay", "resilience.catch_up", "bool")
            if "overwrite_transcript" in catch_up:
                req(catch_up, "overwrite_transcript", "resilience.catch_up", "bool")
            if "keep_realtime_artifacts" in catch_up:
                req(catch_up, "keep_realtime_artifacts", "resilience.catch_up", "bool")

    if errors:
        msg = "Invalid configuration:\n" + "\n".join(f"- {e}" for e in errors)
        raise ValueError(msg)
