"""Continuous capture -> STT -> minutes pipeline for long sessions."""
from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import queue
import threading
import time
from collections import deque
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable, Optional

import numpy as np
import pyaudiowpatch as pyaudio
import shutil

from agendasnap.audio.adaptive_vad import AdaptiveVadConfig, AdaptiveVadController
from agendasnap.audio.capture_mic import open_mic_stream
from agendasnap.audio.capture_wasapi import open_loopback_stream
from agendasnap.audio.devices import build_capture_device_info
from agendasnap.audio.calibration import build_source_calibration, compute_threshold_from_rms, resolve_calibration_config
from agendasnap.audio.diagnostics import AudioDecisionEvent
from agendasnap.audio.levels import LiveAudioLevel, compute_pcm16_level, inactive_level
from agendasnap.audio.recording import AudioRecorder, resolve_recording_config
from agendasnap.audio.resample import resample_pcm16
from agendasnap.bus.events import AudioChunk
from agendasnap.config.glossary import (
    build_rolling_transcription_prompt,
    build_transcription_prompt,
    enabled_glossary_terms,
    normalize_rolling_context_settings,
    rolling_transcription_prompt_metadata,
)
from agendasnap.minutes.generator import generate_minutes
from agendasnap.minutes.llm_summarizer import LlmMinutesUpdater
from agendasnap.minutes.profiles import apply_minutes_profile
from agendasnap.minutes.render_md import render as render_minutes
from agendasnap.minutes.ssot import save_minutes_json_atomic
from agendasnap.resilience.controller import ResilienceController
from agendasnap.store.atomic import write_text_atomic
from agendasnap.store.session_fs import write_device_info
from agendasnap.store.transcript_repo import TranscriptRepo
from agendasnap.stt.errors import (
    PERMANENT,
    PermanentSttError,
    SttErrorInfo,
    classify_stt_error,
    stt_error_safe_category,
)
from agendasnap.stt.offline import build_turns_from_recordings, run_stt_once
from agendasnap.stt.provider_factory import build_realtime_engine

logger = logging.getLogger(__name__)


def _read_status_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _write_pipeline_status(
    status_path: Path,
    *,
    phase: str | None = None,
    pipeline_fields: Optional[dict] = None,
    minutes_finalize: Optional[dict] = None,
) -> None:
    payload = _read_status_json(status_path)
    now = time.time()

    if phase is not None:
        pipeline = payload.get("pipeline")
        if not isinstance(pipeline, dict):
            pipeline = {}
            payload["pipeline"] = pipeline
        pipeline["phase"] = phase
        pipeline["updated_at"] = now

    if pipeline_fields:
        pipeline = payload.get("pipeline")
        if not isinstance(pipeline, dict):
            pipeline = {}
            payload["pipeline"] = pipeline
        pipeline.update(pipeline_fields)
        pipeline["updated_at"] = now

    if minutes_finalize is not None:
        finalize = payload.get("minutes_finalize")
        if not isinstance(finalize, dict):
            finalize = {}
            payload["minutes_finalize"] = finalize
        finalize.update(minutes_finalize)
        finalize["updated_at"] = now
        state = str(finalize.get("state", "")).strip().lower()
        if "started_at" not in finalize and state in {
            "running",
            "provisional_finalize",
            "catch_up_stt",
            "catch_up_finalize",
        }:
            finalize["started_at"] = now

    payload["timestamp"] = now
    write_text_atomic(
        status_path,
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _coerce_bool(value: object, default: bool = True) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "no", "off", "disabled"}
    return bool(value)


def _build_effective_stt_prompt_cfg(
    stt_cfg: dict,
    *,
    recent_segments: list[Any],
    source: str,
) -> dict:
    """Return a per-session STT config with a bounded transcription prompt."""
    effective = dict(stt_cfg)
    rolling_settings = normalize_rolling_context_settings(
        stt_cfg.get("rolling_context") if isinstance(stt_cfg.get("rolling_context"), dict) else None
    )
    base_prompt = stt_cfg.get("base_transcription_prompt")
    if base_prompt is None:
        base_prompt = stt_cfg.get("transcription_prompt")
    topic = stt_cfg.get("meeting_topic", "")
    glossary = stt_cfg.get("meeting_glossary", [])

    try:
        metadata: dict[str, Any] | None = None
        if rolling_settings["enable"] and rolling_settings["update_policy"] != "manual_only":
            prompt = build_rolling_transcription_prompt(
                base_prompt,
                topic,
                glossary,
                recent_segments,
                rolling_summary=stt_cfg.get("rolling_summary", ""),
                settings=rolling_settings,
            )
            max_prompt_chars = int(rolling_settings["max_prompt_chars"])
            if max_prompt_chars and len(prompt) >= int(max_prompt_chars * 0.9):
                logger.warning(
                    "%s Rolling STT prompt length is high: %d/%d chars",
                    source,
                    len(prompt),
                    max_prompt_chars,
                )
            try:
                metadata = rolling_transcription_prompt_metadata(
                    base_prompt,
                    topic,
                    glossary,
                    recent_segments,
                    rolling_summary=stt_cfg.get("rolling_summary", ""),
                    settings=rolling_settings,
                )
            except Exception as exc:  # noqa: BLE001
                logger.debug("%s Rolling STT metadata build failed: %s", source, exc)
            else:
                logger.debug("%s Rolling STT Context metadata: %s", source, metadata)
        else:
            prompt = build_transcription_prompt(base_prompt, topic, glossary)
            metadata = {
                "rolling_context_enabled": False,
                "update_policy": str(rolling_settings.get("update_policy") or ""),
                "prompt_chars": len(prompt),
                "recent_segments_count": 0,
                "recent_chars": 0,
                "glossary_terms_count": len(enabled_glossary_terms(glossary)[:80]),
                "topic_used": bool(str(topic or "").strip()),
                "summary_used": False,
                "include_partial": False,
                "include_low_confidence": False,
            }
        effective["transcription_prompt"] = prompt
        if metadata is not None:
            effective["rolling_context_metadata"] = metadata
    except Exception as exc:  # noqa: BLE001
        logger.warning("%s Rolling STT prompt build failed; using existing prompt: %s", source, exc)
    return effective


def _set_engine_prompt_if_supported(
    engine: Any,
    prompt: str | None,
    *,
    source: str,
    prompt_metadata: dict[str, Any] | None = None,
) -> None:
    setter = getattr(engine, "set_transcription_prompt", None)
    if not callable(setter):
        return
    try:
        setter(prompt)
    except Exception as exc:  # noqa: BLE001
        logger.warning("%s Rolling STT prompt update failed; continuing: %s", source, exc)
    metadata_setter = getattr(engine, "set_transcription_prompt_metadata", None)
    if callable(metadata_setter):
        try:
            metadata_setter(prompt_metadata)
        except Exception as exc:  # noqa: BLE001
            logger.warning("%s Rolling STT prompt metadata update failed; continuing: %s", source, exc)


def _resolve_hysteresis_cfg(vad_cfg: dict, *, source: str, base_threshold: float) -> dict:
    if not isinstance(vad_cfg, dict):
        return {"enable": False}

    enable = bool(vad_cfg.get("enable_hysteresis", False))
    start = vad_cfg.get(f"start_threshold_{source}")
    stop = vad_cfg.get(f"stop_threshold_{source}")
    start_ratio = vad_cfg.get(f"start_ratio_{source}")
    stop_ratio = vad_cfg.get(f"stop_ratio_{source}")

    if not enable and start is None and stop is None and start_ratio is None and stop_ratio is None:
        return {"enable": False}

    return {
        "enable": True,
        "start_threshold": float(start) if start is not None else None,
        "stop_threshold": float(stop) if stop is not None else None,
        "start_ratio": float(start_ratio) if start_ratio is not None else None,
        "stop_ratio": float(stop_ratio) if stop_ratio is not None else None,
        "base_threshold": float(base_threshold),
    }


def _chunk_rms(pcm: bytes) -> float:
    if not pcm:
        return 0.0
    arr = np.frombuffer(pcm, dtype=np.int16)
    if arr.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(arr.astype(np.float64) ** 2)))


def _frame_rms_values(pcm: bytes, *, sample_rate: int, frame_ms: int) -> list[float]:
    if not pcm or sample_rate <= 0:
        return []
    arr = np.frombuffer(pcm, dtype=np.int16)
    if arr.size == 0:
        return []
    frame_len = max(1, int(sample_rate * frame_ms / 1000))
    rms_values: list[float] = []
    for i in range(0, arr.size, frame_len):
        frame = arr[i : i + frame_len]
        if frame.size == 0:
            break
        rms = float(np.sqrt(np.mean(frame.astype(np.float32) ** 2)))
        rms_values.append(rms)
    return rms_values


class ProducerStats:
    def __init__(self, *, energy_threshold: float) -> None:
        self._lock = threading.Lock()
        self.produced = 0
        self.dropped_energy = 0
        self.dropped_full = 0
        self.last_rms = 0.0
        self.last_chunk_t1: float | None = None
        self.noise_rms: float | None = None
        self.energy_threshold = float(energy_threshold)

    def update(
        self,
        *,
        produced: int | None = None,
        dropped_energy: int | None = None,
        dropped_full: int | None = None,
        last_rms: float | None = None,
        last_chunk_t1: float | None = None,
        noise_rms: float | None = None,
        energy_threshold: float | None = None,
    ) -> None:
        with self._lock:
            if produced is not None:
                self.produced = produced
            if dropped_energy is not None:
                self.dropped_energy = dropped_energy
            if dropped_full is not None:
                self.dropped_full = dropped_full
            if last_rms is not None:
                self.last_rms = last_rms
            if last_chunk_t1 is not None:
                self.last_chunk_t1 = last_chunk_t1
            if noise_rms is not None:
                self.noise_rms = noise_rms
            if energy_threshold is not None:
                self.energy_threshold = float(energy_threshold)

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "produced": self.produced,
                "dropped_energy": self.dropped_energy,
                "dropped_full": self.dropped_full,
                "last_rms": self.last_rms,
                "last_chunk_t1": self.last_chunk_t1,
                "noise_rms": self.noise_rms,
                "energy_threshold": self.energy_threshold,
            }


@dataclass(frozen=True)
class InputSourceUpdate:
    source: str  # "sys" or "mic"
    enabled: bool
    device_index: int | None = None
    follow_default: bool | None = None


@dataclass
class SourceRuntime:
    name: str
    enabled: bool
    device_index: int | None
    follow_default: bool
    stream: Any | None
    producer_thread: threading.Thread | None
    queue: queue.Queue
    stt_task: asyncio.Task | None
    stop_source: threading.Event
    stt_stop: asyncio.Event
    recorder: AudioRecorder | None
    stats: ProducerStats
    adaptive: AdaptiveVadController | None
    calibration: dict | None
    rate_used: int | None
    channels_used: int | None
    actual_device_index: int | None
    device_info: dict | None = None
    latest_error: str | None = None


def apply_input_update_to_audio_config(audio_cfg: dict, update: InputSourceUpdate) -> dict:
    """Apply a source update to an audio config mapping without touching session state."""
    source = str(update.source).strip().lower()
    if source == "system":
        source = "sys"
    if source not in {"sys", "mic"}:
        raise ValueError(f"unknown input source: {update.source!r}")

    out = dict(audio_cfg)
    if source == "mic":
        out["enable_mic"] = bool(update.enabled)
        out.pop("mic_device_index", None)
        if update.enabled and update.device_index is not None:
            out["mic_device_index"] = int(update.device_index)
        return out

    out["enable_system"] = bool(update.enabled)
    follow_default = (
        bool(update.follow_default)
        if update.follow_default is not None
        else update.device_index is None
    )
    out["system_device_follow_default"] = True if not update.enabled else follow_default
    out.pop("system_device_index", None)
    if update.enabled and not follow_default and update.device_index is not None:
        out["system_device_index"] = int(update.device_index)
    return out


def _producer_thread(
    *,
    stream: pyaudio.Stream,
    source: str,
    capture_rate: int,
    capture_channels: int,
    target_rate: int,
    chunk_ms: int,
    energy_threshold: float,
    frames_per_buffer: int,
    out_queue: queue.Queue,
    stop_all: threading.Event,
    stop_source: threading.Event,
    recorder: Optional[AudioRecorder] = None,
    calibration: Optional[dict] = None,
    timeline_base: float | None = None,
    stats: Optional[ProducerStats] = None,
    adaptive: Optional[AdaptiveVadController] = None,
    guard_cfg: Optional[dict] = None,
    level_callback: Callable[[LiveAudioLevel], None] | None = None,
    diagnostic_event_callback: Callable[[AudioDecisionEvent], None] | None = None,
    level_interval_seconds: float = 0.08,
    device_index: int | None = None,
    device_name: str | None = None,
) -> None:
    """Read from PyAudio stream, resample to target_rate/mono, chunk by chunk_ms, push AudioChunk.

    Behavior:
    - Drops low-energy chunks (light VAD gate).
    - Queue is bounded; if full, drops the oldest chunk (bounded memory).
    """
    bytes_per_sample = 2
    bytes_per_chunk = int(capture_channels * capture_rate * bytes_per_sample * (chunk_ms / 1000))
    buf = bytearray()
    sample_count = 0  # in target_rate samples
    produced = 0
    dropped_energy = 0
    dropped_full = 0
    last_rms = 0.0
    offset_seconds = 0.0
    first_time: float | None = None
    last_level_emit = 0.0
    level_interval_seconds = max(0.02, float(level_interval_seconds or 0.08))

    logger.info(
        "%s producer start: chunk_ms=%s energy_threshold=%.1f queue_max=%s",
        source,
        chunk_ms,
        energy_threshold,
        getattr(out_queue, "maxsize", None),
    )

    calibration = calibration or {}
    calib_enabled = bool(calibration.get("enable", False))
    calib_seconds = float(calibration.get("seconds", 0.0))
    calib_target_samples = int(calib_seconds * target_rate) if calib_seconds > 0 else 0
    calib_percentile = float(calibration.get("percentile", 20.0))
    calib_multiplier = float(calibration.get("multiplier", 2.5))
    calib_min = float(calibration.get("min_threshold", 0.0))
    calib_max = float(calibration.get("max_threshold", 0.0))
    recalib_interval = float(calibration.get("recalibration_interval_seconds", 0.0) or 0.0)
    recalib_window = float(calibration.get("recalibration_window_seconds", 0.0) or 0.0)
    recalib_min_samples = int(calibration.get("recalibration_min_samples", 0) or 0)
    recalib_min_change_ratio = float(calibration.get("recalibration_min_change_ratio", 0.0) or 0.0)
    recalib_samples: list[tuple[float, float]] = []
    next_recalib = (time.monotonic() + recalib_interval) if recalib_interval > 0 else None
    calib_rms: list[float] = []
    calib_samples = 0
    calib_done = not calib_enabled or calib_target_samples <= 0

    hysteresis = calibration.get("hysteresis") if isinstance(calibration, dict) else None
    hyst_enabled = bool(hysteresis and hysteresis.get("enable", False))
    start_thr = None
    stop_thr = None
    start_ratio = None
    stop_ratio = None
    min_voice_chunks = 1
    guard_cfg = guard_cfg or {}
    guard_enable = source == "mic" and bool(guard_cfg.get("enable", False))
    guard_frame_ms = int(guard_cfg.get("frame_ms", 30) or 30)
    guard_min_voiced_ms = float(guard_cfg.get("min_voiced_ms", 0.0) or 0.0)
    guard_min_rms_std_ratio = float(guard_cfg.get("min_rms_std_ratio", 0.0) or 0.0)
    guard_strong_rms_ratio = float(guard_cfg.get("strong_rms_ratio", 0.0) or 0.0)
    prebuffer_chunks = int(guard_cfg.get("prebuffer_chunks", 0) or 0)
    prebuffer: deque[AudioChunk] = deque(maxlen=max(0, prebuffer_chunks))
    start_from_calib = False
    stop_from_calib = False
    start_from_ratio = False
    stop_from_ratio = False
    if hyst_enabled:
        start_thr = hysteresis.get("start_threshold")
        stop_thr = hysteresis.get("stop_threshold")
        start_ratio = hysteresis.get("start_ratio")
        stop_ratio = hysteresis.get("stop_ratio")
        min_voice_chunks = int(hysteresis.get("min_voice_chunks") or 1)
        base_thr = float(hysteresis.get("base_threshold", energy_threshold))
        if start_thr is None and start_ratio is not None:
            start_thr = base_thr * float(start_ratio)
            start_from_ratio = True
        elif start_thr is None:
            start_thr = base_thr
            start_from_calib = True
        if stop_thr is None and stop_ratio is not None:
            stop_thr = base_thr * float(stop_ratio)
            stop_from_ratio = True
        elif stop_thr is None:
            stop_thr = base_thr
            stop_from_calib = True
        start_thr = float(start_thr)
        stop_thr = float(stop_thr)
    in_voice = False
    voiced_streak = 0

    if adaptive is not None:
        adaptive.set_threshold(
            threshold=energy_threshold,
            start_threshold=start_thr if hyst_enabled else None,
            stop_threshold=stop_thr if hyst_enabled else None,
            reset_timer=True,
        )
        if stats is not None:
            stats.update(energy_threshold=adaptive.current_thresholds()[0])

    def _buffer_silence(chunk: AudioChunk) -> None:
        if guard_enable and prebuffer_chunks > 0:
            prebuffer.append(chunk)

    def _flush_prebuffer() -> None:
        if not prebuffer:
            return
        while prebuffer:
            _enqueue(prebuffer.popleft(), last_rms_value=None)

    def _with_producer_stats(level: LiveAudioLevel) -> LiveAudioLevel:
        if stats is None:
            return level
        snap = stats.snapshot()
        queue_max = getattr(out_queue, "maxsize", None)
        return replace(
            level,
            noise_rms=snap.get("noise_rms"),
            energy_threshold=float(snap.get("energy_threshold", energy_threshold) or energy_threshold),
            produced=int(snap.get("produced", 0) or 0),
            dropped_energy=int(snap.get("dropped_energy", 0) or 0),
            dropped_full=int(snap.get("dropped_full", 0) or 0),
            queue_size=out_queue.qsize(),
            queue_max=int(queue_max) if isinstance(queue_max, int) and queue_max >= 0 else None,
        )

    def _emit_decision_event(
        *,
        chunk: AudioChunk,
        decision: str,
        reason: str,
        level: LiveAudioLevel,
    ) -> None:
        if diagnostic_event_callback is None:
            return
        snap = stats.snapshot() if stats is not None else {}
        queue_max = getattr(out_queue, "maxsize", None)
        start_value = float(start_thr) if hyst_enabled and start_thr is not None else float(energy_threshold)
        stop_value = float(stop_thr) if hyst_enabled and stop_thr is not None else float(energy_threshold)
        with contextlib.suppress(Exception):
            diagnostic_event_callback(
                AudioDecisionEvent(
                    source=source,
                    t0=float(chunk.t0 or 0.0),
                    t1=float(chunk.t1 or chunk.t0 or 0.0),
                    rms=float(level.rms),
                    peak=float(level.peak),
                    dbfs=float(level.dbfs),
                    threshold=float(energy_threshold),
                    start_threshold=start_value,
                    stop_threshold=stop_value,
                    noise_rms=snap.get("noise_rms"),
                    clipped=bool(level.clipped),
                    decision="clipped" if level.clipped else decision,
                    reason="clipped" if level.clipped else reason,
                    produced_count=int(snap.get("produced", produced) or 0),
                    dropped_energy_count=int(snap.get("dropped_energy", dropped_energy) or 0),
                    dropped_full_count=int(snap.get("dropped_full", dropped_full) or 0),
                    queue_size=out_queue.qsize(),
                    queue_max=int(queue_max) if isinstance(queue_max, int) and queue_max >= 0 else None,
                    estimated=False,
                )
            )

    def _enqueue(chunk: AudioChunk, *, last_rms_value: float | None) -> None:
        nonlocal produced, dropped_full, produced_this
        queued = False
        queue_full_hit = False
        try:
            out_queue.put(chunk, timeout=1.0)
            produced += 1
            produced_this = True
            queued = True
        except queue.Full:
            # Drop oldest to keep bounded memory.
            dropped_full += 1
            queue_full_hit = True
            with contextlib.suppress(Exception):
                _ = out_queue.get_nowait()
            with contextlib.suppress(Exception):
                out_queue.put_nowait(chunk)
                queued = True
        if stats is not None and last_rms_value is not None:
            stats.update(
                produced=produced,
                dropped_energy=dropped_energy,
                dropped_full=dropped_full,
                last_rms=last_rms_value,
                last_chunk_t1=chunk.t1 if produced_this else None,
            )
        if last_rms_value is not None:
            level = compute_pcm16_level(
                chunk.pcm,
                source=source,
                threshold=energy_threshold,
                enabled=True,
                timestamp=time.time(),
                device_index=device_index,
                device_name=device_name,
            )
            if queue_full_hit:
                _emit_decision_event(chunk=chunk, decision="queue_dropped", reason="queue_full", level=level)
            elif queued and produced_this:
                _emit_decision_event(chunk=chunk, decision="stt_candidate", reason="enqueued", level=level)

    try:
        if recorder is not None:
            recorder.start()
        while (not stop_all.is_set()) and (not stop_source.is_set()):
            try:
                data = stream.read(frames_per_buffer, exception_on_overflow=False)
            except Exception as exc:  # noqa: BLE001
                logger.warning("%s producer stopped (read error): %s", source, exc)
                if level_callback is not None:
                    with contextlib.suppress(Exception):
                        level_callback(
                            _with_producer_stats(
                                inactive_level(
                                    source=source,
                                    threshold=energy_threshold,
                                    error=str(exc),
                                    device_index=device_index,
                                    device_name=device_name,
                                )
                            )
                        )
                break
            if level_callback is not None:
                now_level = time.monotonic()
                if (now_level - last_level_emit) >= level_interval_seconds:
                    last_level_emit = now_level
                    with contextlib.suppress(Exception):
                        level_callback(
                            _with_producer_stats(
                                compute_pcm16_level(
                                    data,
                                    source=source,
                                    threshold=energy_threshold,
                                    enabled=True,
                                    device_index=device_index,
                                    device_name=device_name,
                                )
                            )
                        )
            if timeline_base is not None and first_time is None:
                first_time = time.monotonic()
                offset_seconds = max(0.0, float(first_time - timeline_base))

            if recorder is not None:
                recorder.write(data)

            buf.extend(data)

            produced_this = False
            while len(buf) >= bytes_per_chunk:
                raw = bytes(buf[:bytes_per_chunk])
                del buf[:bytes_per_chunk]

                resampled, frames_cnt, used_rate, used_ch = resample_pcm16(
                    raw,
                    src_rate=capture_rate,
                    dst_rate=target_rate,
                    src_channels=capture_channels,
                    target_channels=1,
                )
                if not resampled:
                    continue

                duration = frames_cnt / used_rate if used_rate else 0.0
                base_t0 = sample_count / used_rate if used_rate else 0.0
                t0 = offset_seconds + base_t0
                t1 = t0 + duration
                sample_count += frames_cnt
                last_rms = _chunk_rms(resampled)
                chunk_level = compute_pcm16_level(
                    resampled,
                    source=source,
                    threshold=energy_threshold,
                    enabled=True,
                    timestamp=time.time(),
                    device_index=device_index,
                    device_name=device_name,
                )
                chunk = AudioChunk(
                    pcm=resampled,
                    sample_rate=used_rate,
                    channels=used_ch,
                    source=source,
                    t0=t0,
                    t1=t1,
                )
                if calib_enabled and not calib_done:
                    calib_samples += frames_cnt
                    calib_rms.append(last_rms)
                    if calib_samples >= calib_target_samples:
                        new_threshold, noise_rms = compute_threshold_from_rms(
                            calib_rms,
                            percentile=calib_percentile,
                            multiplier=calib_multiplier,
                            min_threshold=calib_min,
                            max_threshold=calib_max,
                        )
                        if new_threshold is not None:
                            energy_threshold = new_threshold
                            if hyst_enabled:
                                if start_from_ratio and start_ratio is not None:
                                    start_thr = float(new_threshold) * float(start_ratio)
                                elif start_from_calib:
                                    start_thr = float(new_threshold)
                                if stop_from_ratio and stop_ratio is not None:
                                    stop_thr = float(new_threshold) * float(stop_ratio)
                                elif stop_from_calib:
                                    stop_thr = float(new_threshold)
                            logger.info(
                                "%s calibration done: noise_rms=%.1f threshold=%.1f",
                                source,
                                noise_rms or 0.0,
                                energy_threshold,
                            )
                            if stats is not None:
                                stats.update(
                                    energy_threshold=energy_threshold,
                                    noise_rms=noise_rms if noise_rms is not None else None,
                                )
                            if adaptive is not None:
                                adaptive.set_threshold(
                                    threshold=energy_threshold,
                                    start_threshold=start_thr if hyst_enabled else None,
                                    stop_threshold=stop_thr if hyst_enabled else None,
                                    reset_timer=True,
                                )
                                if stats is not None:
                                    stats.update(energy_threshold=adaptive.current_thresholds()[0])
                        calib_done = True
                if recalib_interval > 0 and calib_done and calib_enabled:
                    now = time.monotonic()
                    silence_thr = stop_thr if (hyst_enabled and stop_thr is not None) else energy_threshold
                    if last_rms < float(silence_thr):
                        recalib_samples.append((now, last_rms))
                    if recalib_window > 0:
                        cutoff = now - recalib_window
                        recalib_samples = [(t, v) for t, v in recalib_samples if t >= cutoff]
                    if next_recalib is not None and now >= next_recalib:
                        if recalib_samples and len(recalib_samples) >= max(1, recalib_min_samples):
                            vals = [v for _, v in recalib_samples]
                            new_threshold, noise_rms = compute_threshold_from_rms(
                                vals,
                                percentile=calib_percentile,
                                multiplier=calib_multiplier,
                                min_threshold=calib_min,
                                max_threshold=calib_max,
                            )
                            if new_threshold is not None:
                                denom = max(float(energy_threshold), 1.0)
                                change_ratio = abs(float(new_threshold) - float(energy_threshold)) / denom
                                if change_ratio >= recalib_min_change_ratio:
                                    energy_threshold = float(new_threshold)
                                    if hyst_enabled:
                                        if start_from_ratio and start_ratio is not None:
                                            start_thr = energy_threshold * float(start_ratio)
                                        elif start_from_calib:
                                            start_thr = energy_threshold
                                        if stop_from_ratio and stop_ratio is not None:
                                            stop_thr = energy_threshold * float(stop_ratio)
                                        elif stop_from_calib:
                                            stop_thr = energy_threshold
                                    if stats is not None:
                                        stats.update(
                                            energy_threshold=energy_threshold,
                                            noise_rms=noise_rms if noise_rms is not None else None,
                                        )
                                    if adaptive is not None:
                                        adaptive.set_threshold(
                                            threshold=energy_threshold,
                                            start_threshold=start_thr if hyst_enabled else None,
                                            stop_threshold=stop_thr if hyst_enabled else None,
                                            reset_timer=True,
                                        )
                                        if stats is not None:
                                            stats.update(energy_threshold=adaptive.current_thresholds()[0])
                                    logger.info(
                                        "%s recalibration: noise_rms=%.1f threshold=%.1f",
                                        source,
                                        noise_rms or 0.0,
                                        energy_threshold,
                                    )
                        next_recalib = now + recalib_interval
                        if recalib_window <= 0:
                            recalib_samples.clear()
                if adaptive is not None:
                    energy_threshold, adaptive_start, adaptive_stop = adaptive.current_thresholds()
                    if hyst_enabled:
                        if adaptive_start is not None:
                            start_thr = adaptive_start
                        if adaptive_stop is not None:
                            stop_thr = adaptive_stop
                if guard_enable and not in_voice:
                    voice_thr = float(start_thr) if (hyst_enabled and start_thr is not None) else float(energy_threshold)
                    rms_values = _frame_rms_values(
                        resampled,
                        sample_rate=int(used_rate) if used_rate else 0,
                        frame_ms=int(guard_frame_ms),
                    )
                    if rms_values:
                        arr = np.asarray(rms_values, dtype=np.float32)
                        mean = float(arr.mean()) if arr.size else 0.0
                        std = float(arr.std()) if arr.size else 0.0
                        rms_std_ratio = (std / mean) if mean > 0 else 0.0
                        voiced_frames = int((arr >= voice_thr).sum())
                        voiced_ms = float(voiced_frames * guard_frame_ms)
                    else:
                        rms_std_ratio = 0.0
                        voiced_ms = 0.0
                    voiced_ok = (guard_min_voiced_ms <= 0) or (voiced_ms >= guard_min_voiced_ms)
                    strong_ok = (
                        guard_strong_rms_ratio > 0
                        and energy_threshold > 0
                        and last_rms >= (float(energy_threshold) * guard_strong_rms_ratio)
                    )
                    var_ok = (guard_min_rms_std_ratio <= 0) or (rms_std_ratio >= guard_min_rms_std_ratio)
                    if (not voiced_ok) or (not strong_ok and not var_ok):
                        voiced_streak = 0
                        in_voice = False
                        dropped_energy += 1
                        _buffer_silence(chunk)
                        if stats is not None:
                            stats.update(
                                produced=produced,
                                dropped_energy=dropped_energy,
                                dropped_full=dropped_full,
                                last_rms=last_rms,
                            )
                        _emit_decision_event(chunk=chunk, decision="vad_discarded", reason="mic_guard", level=chunk_level)
                        continue
                if hyst_enabled:
                    just_started_voice = False
                    if not in_voice:
                        if last_rms < float(start_thr):
                            voiced_streak = 0
                            dropped_energy += 1
                            _buffer_silence(chunk)
                            if stats is not None:
                                stats.update(
                                    produced=produced,
                                    dropped_energy=dropped_energy,
                                    dropped_full=dropped_full,
                                    last_rms=last_rms,
                                )
                            _emit_decision_event(
                                chunk=chunk,
                                decision="vad_discarded",
                                reason="below_start_threshold",
                                level=chunk_level,
                            )
                            continue
                        voiced_streak += 1
                        if voiced_streak < max(1, int(min_voice_chunks)):
                            dropped_energy += 1
                            _buffer_silence(chunk)
                            if stats is not None:
                                stats.update(
                                    produced=produced,
                                    dropped_energy=dropped_energy,
                                    dropped_full=dropped_full,
                                    last_rms=last_rms,
                            )
                            _emit_decision_event(
                                chunk=chunk,
                                decision="vad_discarded",
                                reason="min_voice_chunks",
                                level=chunk_level,
                            )
                            continue
                        in_voice = True
                        voiced_streak = 0
                        just_started_voice = True
                    else:
                        if last_rms < float(stop_thr):
                            dropped_energy += 1
                            in_voice = False
                            voiced_streak = 0
                            _buffer_silence(chunk)
                            if stats is not None:
                                stats.update(
                                    produced=produced,
                                    dropped_energy=dropped_energy,
                                    dropped_full=dropped_full,
                                    last_rms=last_rms,
                                )
                            _emit_decision_event(
                                chunk=chunk,
                                decision="vad_discarded",
                                reason="below_stop_threshold",
                                level=chunk_level,
                            )
                            continue
                else:
                    just_started_voice = False
                    if last_rms < energy_threshold:
                        voiced_streak = 0
                        in_voice = False
                        dropped_energy += 1
                        _buffer_silence(chunk)
                        if stats is not None:
                            stats.update(
                                produced=produced,
                                dropped_energy=dropped_energy,
                                dropped_full=dropped_full,
                                last_rms=last_rms,
                            )
                        _emit_decision_event(
                            chunk=chunk,
                            decision="vad_discarded",
                            reason="below_start_threshold",
                            level=chunk_level,
                        )
                        continue
                    voiced_streak += 1
                    if voiced_streak < max(1, int(min_voice_chunks)):
                        dropped_energy += 1
                        _buffer_silence(chunk)
                        if stats is not None:
                            stats.update(
                                produced=produced,
                                dropped_energy=dropped_energy,
                                dropped_full=dropped_full,
                                last_rms=last_rms,
                            )
                        _emit_decision_event(
                            chunk=chunk,
                            decision="vad_discarded",
                            reason="min_voice_chunks",
                            level=chunk_level,
                        )
                        continue
                    if not in_voice:
                        just_started_voice = True
                    in_voice = True
                    voiced_streak = 0

                if guard_enable and prebuffer_chunks > 0 and just_started_voice:
                    _flush_prebuffer()
                _enqueue(chunk, last_rms_value=last_rms)

            if produced_this and produced % 40 == 0:
                logger.info(
                    "%s producer stats: produced=%d dropped_energy=%d dropped_full=%d last_rms=%.1f",
                    source,
                    produced,
                    dropped_energy,
                    dropped_full,
                    last_rms,
                )
    finally:
        with contextlib.suppress(Exception):
            stream.stop_stream()
        if recorder is not None:
            recorder.close()
        if level_callback is not None:
            with contextlib.suppress(Exception):
                level_callback(
                    _with_producer_stats(
                        inactive_level(
                            source=source,
                            threshold=energy_threshold,
                            device_index=device_index,
                            device_name=device_name,
                        )
                    )
                )

        logger.info(
            "%s producer stop: produced=%d dropped_energy=%d dropped_full=%d",
            source,
            produced,
            dropped_energy,
            dropped_full,
        )


async def _write_minutes_rule_based(repo: TranscriptRepo, session_dir: Path, minutes_cfg: dict) -> None:
    minutes_doc = generate_minutes(repo.memory, minutes_cfg)
    save_minutes_json_atomic(session_dir / "minutes.json", minutes_doc)
    minutes_md = render_minutes(minutes_doc)
    write_text_atomic(session_dir / "minutes.md", minutes_md, encoding="utf-8")


async def _minutes_updater(
    repo: TranscriptRepo,
    session_dir: Path,
    interval: float,
    minutes_cfg: dict,
    stop_event: asyncio.Event,
    llm_updater: LlmMinutesUpdater,
    controller: ResilienceController,
) -> None:
    """Regenerate minutes.md only when transcript changes."""
    last_version = -1
    use_llm_incremental = (
        bool(llm_updater.llm_cfg.enable)
        and bool(llm_updater.llm_cfg.incremental_enable)
        and llm_updater.llm_cfg.incremental_mode == "llm"
    )
    # Ensure file exists quickly (even if transcript empty).
    if use_llm_incremental:
        # initialize minutes.json so UI can pick it up
        save_minutes_json_atomic(session_dir / "minutes.json", llm_updater.doc)
        minutes_md = render_minutes(llm_updater.doc)
        write_text_atomic(session_dir / "minutes.md", minutes_md, encoding="utf-8")
    else:
        await _write_minutes_rule_based(repo, session_dir, minutes_cfg)
    last_version = repo.version

    while not stop_event.is_set():
        if repo.version != last_version:
            if use_llm_incremental:
                await llm_updater.update_incremental(repo.memory)
            else:
                await _write_minutes_rule_based(repo, session_dir, minutes_cfg)
            last_version = repo.version

        try:
            timeout = controller.current_minutes_interval() if controller.cfg.enable else float(interval)
            await asyncio.wait_for(stop_event.wait(), timeout=float(timeout))
        except asyncio.TimeoutError:
            continue


def _compute_drop_rate(stats: dict) -> float:
    """Queue-full drop rate (%). VAD-dropped chunks are excluded."""
    produced = int(stats.get("produced", 0))
    dropped_full = int(stats.get("dropped_full", 0))
    total = produced + dropped_full
    if total <= 0:
        return 0.0
    return (dropped_full / total) * 100.0


def _compute_vad_drop_rate(stats: dict) -> float:
    produced = int(stats.get("produced", 0))
    dropped_energy = int(stats.get("dropped_energy", 0))
    total = produced + dropped_energy
    if total <= 0:
        return 0.0
    return dropped_energy / total


def _compute_delay(now: float, *, timeline_base: float | None, last_t1: float | None) -> float | None:
    if timeline_base is None or last_t1 is None:
        return None
    return max(0.0, now - (timeline_base + last_t1))


def _backup_with_suffix(path: Path, suffix: str) -> Optional[Path]:
    if not path.exists():
        return None
    candidate = path.with_name(f"{path.stem}{suffix}{path.suffix}")
    counter = 1
    while candidate.exists():
        candidate = path.with_name(f"{path.stem}{suffix}.{counter}{path.suffix}")
        counter += 1
    path.replace(candidate)
    return candidate


def _restore_backups(backups: dict[Path, Optional[Path]]) -> None:
    for original, backup in backups.items():
        if not backup or not backup.exists():
            continue
        if original.exists():
            continue
        backup.replace(original)


def _normalize_source_set(sources: dict[str, str] | set[str] | list[str] | tuple[str, ...] | None) -> set[str]:
    if not sources:
        return set()
    if isinstance(sources, dict):
        values = sources.keys()
    else:
        values = sources
    return {str(source).strip().lower() for source in values if str(source).strip().lower() in {"sys", "mic"}}


def _filter_catch_up_turns_for_permanent_errors(
    turns_by_source: dict[str, list[AudioChunk]],
    permanent_errors: dict[str, str] | set[str] | list[str] | tuple[str, ...] | None,
) -> dict[str, list[AudioChunk]]:
    """Remove sources that already failed permanently during realtime STT."""
    skipped = _normalize_source_set(permanent_errors)
    if not skipped:
        return dict(turns_by_source)
    return {source: turns for source, turns in turns_by_source.items() if source not in skipped}


async def _run_catch_up(
    *,
    session_dir: Path,
    status_path: Path,
    audio_cfg: dict,
    stt_cfg: dict,
    minutes_cfg: dict,
    recording_cfg: dict,
    catch_cfg: dict,
    controller: ResilienceController,
    permanent_stt_errors: dict[str, str] | None = None,
) -> None:
    if not catch_cfg.get("enable", False):
        logger.info("Catch-up disabled.")
        return

    only_when_delay = bool(catch_cfg.get("only_when_delay", True))
    if only_when_delay and not controller.delay_mode_triggered:
        logger.info("Catch-up skipped: no delay detected.")
        return

    if not recording_cfg.get("system") and not recording_cfg.get("mic"):
        logger.warning("Catch-up skipped: audio recording disabled.")
        return

    record_dir = session_dir / recording_cfg["directory"] if recording_cfg["directory"] else session_dir
    if not record_dir.exists():
        logger.warning("Catch-up skipped: recording directory not found (%s).", record_dir)
        return

    turns_by_source: dict[str, list[AudioChunk]] = {}
    if recording_cfg.get("system"):
        turns_by_source["sys"] = build_turns_from_recordings(
            record_dir=record_dir,
            basename="system",
            fmt=recording_cfg.get("format", "wav"),
            source="sys",
            audio_cfg=audio_cfg,
            stt_cfg=stt_cfg,
            log=logger,
        )
    if recording_cfg.get("mic"):
        turns_by_source["mic"] = build_turns_from_recordings(
            record_dir=record_dir,
            basename="mic",
            fmt=recording_cfg.get("format", "wav"),
            source="mic",
            audio_cfg=audio_cfg,
            stt_cfg=stt_cfg,
            log=logger,
        )

    skipped_sources = _normalize_source_set(permanent_stt_errors)
    catch_up_skip_fields: dict[str, Any] = {}
    if skipped_sources:
        for source in sorted(skipped_sources):
            logger.warning(
                "Catch-up skipped for %s due to permanent realtime STT error: %s",
                source,
                (permanent_stt_errors or {}).get(source, "permanent STT error"),
            )
        catch_up_skip_fields = {
            "catch_up_skipped_sources": sorted(skipped_sources),
            "catch_up_skip_reason": "permanent_stt_error",
        }
        turns_by_source = _filter_catch_up_turns_for_permanent_errors(turns_by_source, skipped_sources)

    total_turns = sum(len(v) for v in turns_by_source.values())
    if total_turns == 0:
        if skipped_sources:
            message = "Catch-up skipped because realtime STT had permanent errors."
        else:
            message = "No catch-up turns; using provisional final minutes."
        logger.warning("Catch-up skipped: no turns generated from recordings.")
        _write_pipeline_status(
            status_path,
            phase="completed",
            minutes_finalize={
                "state": "completed",
                "message": message,
                "progress_current": 0,
                "progress_total": 0,
                "progress_ratio": 1.0,
                "eta_seconds": 0.0,
                "completed_at": time.time(),
                **catch_up_skip_fields,
            },
        )
        return

    logger.info(
        "Catch-up starting: turns=%d (sys=%d, mic=%d)",
        total_turns,
        len(turns_by_source.get("sys", [])),
        len(turns_by_source.get("mic", [])),
    )

    overwrite_transcript = bool(catch_cfg.get("overwrite_transcript", True))
    keep_realtime = bool(catch_cfg.get("keep_realtime_artifacts", True))

    backups: dict[Path, Optional[Path]] = {}
    if overwrite_transcript:
        backups[session_dir / "transcript.jsonl"] = _backup_with_suffix(
            session_dir / "transcript.jsonl", "_realtime"
        )
        if keep_realtime:
            backups[session_dir / "minutes.json"] = _backup_with_suffix(
                session_dir / "minutes.json", "_realtime"
            )
            backups[session_dir / "minutes.md"] = _backup_with_suffix(
                session_dir / "minutes.md", "_realtime"
            )

    catch_started = time.time()
    _write_pipeline_status(
        status_path,
        phase="catch_up_stt",
        minutes_finalize={
            "state": "catch_up_stt",
            "message": "Re-transcribing recorded audio for catch-up.",
            "progress_current": 0,
            "progress_total": int(total_turns),
            "progress_ratio": 0.0,
            "eta_seconds": None,
            "error": None,
            "started_at": catch_started,
            **catch_up_skip_fields,
        },
    )

    def _on_catch_up_progress(payload: dict) -> None:
        phase = str(payload.get("phase", "")).strip().lower()
        if phase == "stt":
            done = int(payload.get("processed_turns", 0) or 0)
            total = int(payload.get("total_turns", 0) or 0)
            ratio = float(done / total) if total > 0 else 0.0
            eta_seconds: float | None = None
            elapsed = max(0.0, time.time() - catch_started)
            if done > 0 and total > done:
                eta_seconds = max(0.0, elapsed * (total - done) / done)
            _write_pipeline_status(
                status_path,
                phase="catch_up_stt",
                minutes_finalize={
                    "state": "catch_up_stt",
                    "message": "Re-transcribing recorded audio for catch-up.",
                    "progress_current": done,
                    "progress_total": total,
                    "progress_ratio": ratio,
                    "eta_seconds": eta_seconds,
                },
            )
            return
        if phase == "finalize":
            _write_pipeline_status(
                status_path,
                phase="catch_up_finalize",
                minutes_finalize={
                    "state": "catch_up_finalize",
                    "message": "Generating final minutes from catch-up transcript.",
                    "progress_current": int(payload.get("processed_turns", 0) or 0),
                    "progress_total": int(payload.get("total_turns", 0) or 0),
                    "progress_ratio": 1.0,
                    "eta_seconds": None,
                },
            )
            return
        if phase == "failed":
            _write_pipeline_status(
                status_path,
                phase="failed",
                minutes_finalize={
                    "state": "failed",
                    "message": "Catch-up failed during STT/finalization.",
                    "error": str(payload.get("error", "unknown error")),
                    "eta_seconds": None,
                },
            )

    try:
        await run_stt_once(
            stt_cfg=stt_cfg,
            turns_by_source=turns_by_source,
            session_dir=session_dir,
            minutes_cfg=minutes_cfg,
            progress_callback=_on_catch_up_progress,
        )
        logger.info("Catch-up completed.")
        _write_pipeline_status(
            status_path,
            phase="completed",
            minutes_finalize={
                "state": "completed",
                "message": "Final minutes are ready.",
                "progress_current": int(total_turns),
                "progress_total": int(total_turns),
                "progress_ratio": 1.0,
                "eta_seconds": 0.0,
                "completed_at": time.time(),
                "error": None,
            },
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Catch-up failed: %s", exc)
        _write_pipeline_status(
            status_path,
            phase="failed",
            minutes_finalize={
                "state": "failed",
                "message": "Catch-up failed.",
                "error": str(exc),
                "eta_seconds": None,
            },
        )
        _restore_backups(backups)


async def _metrics_logger(
    *,
    sys_queue: queue.Queue,
    mic_queue: queue.Queue,
    sys_stats: ProducerStats,
    mic_stats: ProducerStats,
    timeline_base: float | None,
    interval: float,
    stop_event: asyncio.Event,
    controller: ResilienceController,
    status_path: Path,
    enable_sys: bool,
    enable_mic: bool,
    adaptive_sys: Optional[AdaptiveVadController] = None,
    adaptive_mic: Optional[AdaptiveVadController] = None,
) -> None:
    while not stop_event.is_set():
        now = time.monotonic()
        sys_snap = sys_stats.snapshot()
        mic_snap = mic_stats.snapshot()

        sys_delay = (
            _compute_delay(now, timeline_base=timeline_base, last_t1=sys_snap.get("last_chunk_t1"))
            if enable_sys
            else None
        )
        mic_delay = (
            _compute_delay(now, timeline_base=timeline_base, last_t1=mic_snap.get("last_chunk_t1"))
            if enable_mic
            else None
        )

        sys_delay_s = "off" if not enable_sys else (f"{sys_delay:.2f}s" if sys_delay is not None else "na")
        mic_delay_s = "off" if not enable_mic else (f"{mic_delay:.2f}s" if mic_delay is not None else "na")

        sys_noise = sys_snap.get("noise_rms")
        mic_noise = mic_snap.get("noise_rms")
        sys_noise_s = f"{float(sys_noise):.1f}" if sys_noise is not None else "na"
        mic_noise_s = f"{float(mic_noise):.1f}" if mic_noise is not None else "na"

        sys_drop = _compute_drop_rate(sys_snap) if enable_sys else 0.0
        mic_drop = _compute_drop_rate(mic_snap) if enable_mic else 0.0
        sys_vad_drop = _compute_vad_drop_rate(sys_snap) if enable_sys else 0.0
        mic_vad_drop = _compute_vad_drop_rate(mic_snap) if enable_mic else 0.0

        if adaptive_sys is not None and enable_sys:
            change = adaptive_sys.maybe_update(
                drop_rate=sys_vad_drop,
                sample_count=int(sys_snap.get("produced", 0)) + int(sys_snap.get("dropped_energy", 0)),
                now=now,
            )
            if change:
                old, new = change
                logger.info("sys adaptive VAD: drop=%.2f threshold %.1f -> %.1f", sys_vad_drop, old, new)
                sys_stats.update(energy_threshold=new)

        if adaptive_mic is not None and enable_mic:
            change = adaptive_mic.maybe_update(
                drop_rate=mic_vad_drop,
                sample_count=int(mic_snap.get("produced", 0)) + int(mic_snap.get("dropped_energy", 0)),
                now=now,
            )
            if change:
                old, new = change
                logger.info("mic adaptive VAD: drop=%.2f threshold %.1f -> %.1f", mic_vad_drop, old, new)
                mic_stats.update(energy_threshold=new)

        if enable_sys:
            controller.update_metrics(
                "sys",
                queue_size=sys_queue.qsize(),
                delay_seconds=sys_delay,
                drop_rate=sys_drop / 100.0,
            )
        else:
            controller.update_metrics("sys", queue_size=0, delay_seconds=None, drop_rate=0.0)
        if enable_mic:
            controller.update_metrics(
                "mic",
                queue_size=mic_queue.qsize(),
                delay_seconds=mic_delay,
                drop_rate=mic_drop / 100.0,
            )
        else:
            controller.update_metrics("mic", queue_size=0, delay_seconds=None, drop_rate=0.0)
        mode_changed = controller.evaluate_mode()

        logger.info(
            "metrics: mode=%s sys q=%d delay=%s dropQ=%.1f%% rms=%.1f thr=%.1f noise=%s | mic q=%d delay=%s dropQ=%.1f%% rms=%.1f thr=%.1f noise=%s",
            controller.mode,
            sys_queue.qsize(),
            sys_delay_s,
            sys_drop,
            float(sys_snap.get("last_rms", 0.0)),
            float(sys_snap.get("energy_threshold", 0.0)),
            sys_noise_s,
            mic_queue.qsize(),
            mic_delay_s,
            mic_drop,
            float(mic_snap.get("last_rms", 0.0)),
            float(mic_snap.get("energy_threshold", 0.0)),
            mic_noise_s,
        )
        if mode_changed:
            logger.warning("Resilience mode changed: %s", controller.mode)

        try:
            existing_status = _read_status_json(status_path)
            status_payload = controller.status_payload()
            status_payload["timestamp"] = time.time()
            status_payload["audio"] = {
                "sys": {
                    "rms": float(sys_snap.get("last_rms", 0.0)),
                    "threshold": float(sys_snap.get("energy_threshold", 0.0)),
                    "noise_rms": sys_snap.get("noise_rms"),
                    "enabled": bool(enable_sys),
                },
                "mic": {
                    "rms": float(mic_snap.get("last_rms", 0.0)),
                    "threshold": float(mic_snap.get("energy_threshold", 0.0)),
                    "noise_rms": mic_snap.get("noise_rms"),
                    "enabled": bool(enable_mic),
                },
            }
            for key in ("pipeline", "minutes_finalize"):
                value = existing_status.get(key)
                if isinstance(value, dict):
                    status_payload[key] = value
            write_text_atomic(
                status_path, json.dumps(status_payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("Failed to write status.json: %s", exc)

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=float(interval))
        except asyncio.TimeoutError:
            continue


async def _stt_worker(
    *,
    name: str,
    cfg: dict,
    chunk_queue: queue.Queue,
    repo: TranscriptRepo,
    stop_global: asyncio.Event,
    stop_source_async: asyncio.Event | None = None,
    stop_source_thread: threading.Event = None,
    dead_flags: dict | None = None,
    controller: ResilienceController | None = None,
    stop_on_all_dead: bool = False,
    permanent_error_callback: Callable[[str, SttErrorInfo], None] | None = None,
) -> None:
    """Consume AudioChunks, build turns, send to Realtime STT, append transcripts.

    This worker runs independently per source. On failures it can reconnect
    with backoff while the other source keeps running.
    """
    # stt cfg may carry feature-specific priorities and provider settings.
    min_turn_seconds = float(cfg.get("min_turn_seconds", 0.0) or 0.0)
    api_key_priority = cfg.get("api_key_priority") or [cfg.get("api_key_source", "env")]

    base_seg_max_s = float(cfg.get("segment_max_seconds", 12.0))
    seg_gap_ms = float(cfg.get("segment_gap_ms", 800.0))
    rolling_seconds = int(cfg.get("rolling_session_minutes", 60)) * 60
    overlap_seconds = float(cfg.get("rolling_overlap_seconds", 0.0))
    max_failures = int(cfg.get("max_consecutive_failures", 5))
    reconnect_enable = bool(cfg.get("reconnect_enable", True))
    reconnect_backoff = float(cfg.get("reconnect_backoff_seconds", 1.0))
    reconnect_max_backoff = float(cfg.get("reconnect_max_backoff_seconds", 30.0))
    rolling_context_settings = normalize_rolling_context_settings(
        cfg.get("rolling_context") if isinstance(cfg.get("rolling_context"), dict) else None
    )
    rolling_context_policy = str(rolling_context_settings.get("update_policy") or "rolling_session")
    initial_context_segments = repo.memory
    if rolling_context_policy == "session_update_experimental":
        logger.warning(
            "%s requested session_update_experimental; dynamic session.update is not implemented. "
            "Rolling STT Context will apply on the next Realtime session start.",
            name,
        )

    def _record_error(info: SttErrorInfo) -> None:
        if controller is None:
            return
        if info.classification == PERMANENT:
            controller.record_stt_permanent_error(name, info.safe_message)
        else:
            controller.record_stt_error(name, info.safe_message)

    def _record_permanent(info: SttErrorInfo) -> None:
        _record_error(info)
        if permanent_error_callback is not None:
            with contextlib.suppress(Exception):
                permanent_error_callback(name, info)

    def _recent_segments_for_next_session() -> list[Any]:
        if not rolling_context_settings.get("enable", True):
            return []
        if rolling_context_policy == "manual_only":
            return []
        if rolling_context_policy == "session_start":
            return list(initial_context_segments)
        return repo.memory

    def _make_client():
        effective_cfg = _build_effective_stt_prompt_cfg(
            cfg,
            recent_segments=_recent_segments_for_next_session(),
            source=name,
        )
        client, runtime = build_realtime_engine(
            source=name,
            stt_cfg=effective_cfg,
            fallback_priority=api_key_priority,
        )
        return client, runtime

    async def _run_connected(client) -> None:
        # current buffered turn
        buf: list[AudioChunk] = []
        buf_start = 0.0
        buf_end = 0.0
        consecutive_failures = 0
        recent_chunks: deque[AudioChunk] = deque()

        async def flush_turn() -> None:
            nonlocal buf, buf_start, buf_end, consecutive_failures
            if not buf:
                return
            duration = max(0.0, float(buf_end) - float(buf_start))
            if min_turn_seconds and duration < min_turn_seconds:
                logger.info(
                    "%s drop short turn: %.2fs (<%.2fs)",
                    name,
                    duration,
                    float(min_turn_seconds),
                )
                buf = []
                buf_start = 0.0
                buf_end = 0.0
                return
            try:
                segments = await client.push_audio(buf)
                if segments:
                    for seg in segments:
                        seg.source = name
                    repo.append(segments)
                consecutive_failures = 0
            except Exception as exc:  # noqa: BLE001
                info = classify_stt_error(exc)
                if info.classification == PERMANENT:
                    logger.error(
                        "%s STT permanent error t0=%.3f t1=%.3f err=%s",
                        name,
                        buf_start,
                        buf_end,
                        info.safe_message,
                    )
                    _record_permanent(info)
                    raise PermanentSttError(info) from exc
                consecutive_failures += 1
                logger.error(
                    "%s STT failed (consecutive_failures=%d/%d) t0=%.3f t1=%.3f err=%s",
                    name,
                    consecutive_failures,
                    max_failures,
                    buf_start,
                    buf_end,
                    info.safe_message,
                )
                _record_error(info)
                if consecutive_failures >= max_failures:
                    raise RuntimeError(f"too many STT failures: {consecutive_failures}") from exc
            finally:
                buf = []
                buf_start = 0.0
                buf_end = 0.0

        def _push_overlap() -> None:
            nonlocal buf, buf_start, buf_end
            if not overlap_seconds or not recent_chunks:
                return
            buf = list(recent_chunks)
            buf_start = float(buf[0].t0 or 0.0)
            buf_end = float(buf[-1].t1 or buf_start)
            logger.info("%s rolling overlap: buffered %.2fs", name, buf_end - buf_start)

        session_started = time.monotonic()

        while not stop_global.is_set() and not (
            stop_source_async is not None and stop_source_async.is_set()
        ):
            # Rolling session restart
            if rolling_seconds and (time.monotonic() - session_started) > rolling_seconds:
                logger.info("%s rolling session restart", name)
                try:
                    await client.stop()
                    effective_cfg = _build_effective_stt_prompt_cfg(
                        cfg,
                        recent_segments=_recent_segments_for_next_session(),
                        source=name,
                    )
                    _set_engine_prompt_if_supported(
                        client,
                        effective_cfg.get("transcription_prompt"),
                        source=name,
                        prompt_metadata=effective_cfg.get("rolling_context_metadata")
                        if isinstance(effective_cfg.get("rolling_context_metadata"), dict)
                        else None,
                    )
                    await client.start()
                    session_started = time.monotonic()
                    _push_overlap()
                except Exception as exc:  # noqa: BLE001
                    raise RuntimeError("rolling session restart failed") from exc

            try:
                chunk = await asyncio.to_thread(chunk_queue.get, True, 1.0)
            except queue.Empty:
                if buf:
                    await flush_turn()
                continue

            if not chunk or not getattr(chunk, "pcm", None):
                continue

            c0 = float(chunk.t0 or 0.0)
            c1 = float(chunk.t1 or c0)
            if overlap_seconds > 0:
                recent_chunks.append(chunk)
                # trim to overlap window
                while recent_chunks and (c1 - float(recent_chunks[0].t0 or 0.0)) > overlap_seconds:
                    recent_chunks.popleft()

            if not buf:
                buf = [chunk]
                buf_start = c0
                buf_end = c1
                continue

            gap_ms = max(0.0, (c0 - buf_end) * 1000.0)
            would_len = max(0.0, c1 - buf_start)

            seg_max_s = controller.current_segment_max_seconds()
            if gap_ms >= seg_gap_ms or would_len > seg_max_s:
                await flush_turn()
                buf = [chunk]
                buf_start = c0
                buf_end = c1
            else:
                buf.append(chunk)
                buf_end = max(buf_end, c1)

        # stop requested; flush remaining
        if buf:
            with contextlib.suppress(Exception):
                await flush_turn()

    backoff = reconnect_backoff
    recovering = False
    try:
        while not stop_global.is_set() and not (
            stop_source_async is not None and stop_source_async.is_set()
        ):
            client, runtime = _make_client()
            try:
                await client.start()
            except Exception as exc:  # noqa: BLE001
                info = classify_stt_error(exc)
                if info.classification == PERMANENT:
                    logger.error("%s STT permanent connect error: %s", name, info.safe_message)
                    _record_permanent(info)
                    break
                logger.error("%s STT connect failed: %s", name, info.safe_message)
                _record_error(info)
                recovering = True
                if not reconnect_enable:
                    break
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, reconnect_max_backoff)
                continue

            logger.info(
                "%s STT worker started (provider=%s realtime_model=%s transcription_model=%s)",
                name,
                runtime.provider,
                runtime.model,
                runtime.transcription_model,
            )
            if recovering:
                logger.info("%s STT recovered (片側復帰)", name)
                controller.record_stt_reconnect(name)
                recovering = False
            backoff = reconnect_backoff

            try:
                await _run_connected(client)
            except Exception as exc:  # noqa: BLE001
                info = classify_stt_error(exc)
                if info.classification == PERMANENT:
                    logger.error("%s STT permanent worker error: %s", name, info.safe_message)
                    _record_permanent(info)
                    break
                logger.error("%s STT worker error: %s", name, info.safe_message)
                _record_error(info)
                recovering = True
                if not reconnect_enable:
                    break
            finally:
                with contextlib.suppress(Exception):
                    await client.stop()

            if (
                not reconnect_enable
                or stop_global.is_set()
                or (stop_source_async is not None and stop_source_async.is_set())
            ):
                break

            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, reconnect_max_backoff)

    finally:
        # Stop this source producer when worker is done (to avoid queue growth).
        if stop_source_thread is not None:
            stop_source_thread.set()

        if dead_flags is not None:
            dead_flags[name] = True
        if stop_on_all_dead and dead_flags is not None and all(dead_flags.values()):
            stop_global.set()

        logger.info("%s STT worker stopped", name)


async def _run_streaming_legacy(
    cfg: dict,
    stt_cfg: dict,
    minutes_cfg: dict,
    session_dir: Path,
    recording_cfg: Optional[dict] = None,
    max_seconds: Optional[float] = None,
    resilience_cfg: Optional[dict] = None,
    stop_event: Optional[threading.Event] = None,
) -> None:
    """Start continuous capture (sys+mic) and stream to STT until Ctrl+C or max_seconds."""
    if not stt_cfg.get("enable", True):
        logger.warning("STT is disabled in config; streaming will not run.")
        return

    # Required (no fallback): caller validates config.
    capture_rate = int(cfg["capture_rate"])
    target_rate = int(cfg["target_rate"])
    frames_per_buffer = int(cfg["frames_per_buffer"])
    chunk_ms = int(cfg["chunk_ms"])
    queue_max = int(cfg["queue_max_chunks"])
    energy_threshold_sys = float(cfg["energy_threshold_sys"])
    energy_threshold_mic = float(cfg["energy_threshold_mic"])
    ch_sys = int(cfg["channels_system"])
    ch_mic = int(cfg["channels_mic"])
    enable_sys = _coerce_bool(cfg.get("enable_system", True))
    enable_mic = _coerce_bool(cfg.get("enable_mic", True))
    metrics_interval = float(cfg.get("metrics_interval_seconds", 10.0))
    resilience_cfg = resilience_cfg or {}
    status_interval = float(resilience_cfg.get("status_interval_seconds", metrics_interval))
    catch_up_cfg = resilience_cfg.get("catch_up", {}) if isinstance(resilience_cfg, dict) else {}
    vad_cfg = cfg.get("vad") if isinstance(cfg.get("vad"), dict) else {}
    adaptive_cfg = vad_cfg.get("adaptive") if isinstance(vad_cfg, dict) else {}
    guard_mic_cfg = vad_cfg.get("guard_mic") if isinstance(vad_cfg.get("guard_mic"), dict) else None

    recording_cfg = recording_cfg or resolve_recording_config(cfg)
    calibration_cfg = resolve_calibration_config(cfg)

    stop_all = threading.Event()
    stop_sys = threading.Event()
    stop_mic = threading.Event()
    status_path = session_dir / "status.json"

    sys_queue: queue.Queue[AudioChunk] = queue.Queue(maxsize=queue_max)
    mic_queue: queue.Queue[AudioChunk] = queue.Queue(maxsize=queue_max)

    sys_stream = mic_stream = None
    producer_threads: list[threading.Thread] = []

    stop_global = asyncio.Event()
    minutes_stop = asyncio.Event()
    metrics_stop = asyncio.Event()

    dead_flags = {"sys": (not enable_sys), "mic": (not enable_mic)}

    repo = TranscriptRepo(session_dir / "transcript.jsonl")
    minutes_task: Optional[asyncio.Task] = None
    effective_minutes_cfg = apply_minutes_profile(minutes_cfg)
    llm_updater = LlmMinutesUpdater(
        session_dir=session_dir,
        minutes_cfg=effective_minutes_cfg,
        api_key_priority=stt_cfg.get("api_key_priority") or [],
    )
    controller = ResilienceController(
        cfg=resilience_cfg,
        base_segment_max_seconds=float(stt_cfg.get("segment_max_seconds", 12.0)),
        base_minutes_interval=float(effective_minutes_cfg.get("update_interval_seconds", 60)),
        queue_max=queue_max,
    )
    permanent_stt_errors: dict[str, str] = {}

    def _record_permanent_stt_error(source: str, info: SttErrorInfo) -> None:
        permanent_stt_errors[source] = info.safe_message
        enabled_sources = {name for name, enabled in {"sys": enable_sys, "mic": enable_mic}.items() if enabled}
        if enabled_sources and enabled_sources.issubset(permanent_stt_errors):
            logger.error("All enabled STT sources failed permanently; stopping streaming.")
            stop_global.set()

    _write_pipeline_status(
        status_path,
        phase="running",
        minutes_finalize={
            "state": "idle",
            "message": "Realtime minutes are updating.",
            "progress_current": 0,
            "progress_total": 0,
            "progress_ratio": 0.0,
            "eta_seconds": None,
            "error": None,
        },
    )
    metrics_task: Optional[asyncio.Task] = None
    sys_stats = ProducerStats(energy_threshold=energy_threshold_sys)
    mic_stats = ProducerStats(energy_threshold=energy_threshold_mic)

    if not enable_sys and not enable_mic:
        logger.warning("Both system and mic inputs are disabled; entering idle mode.")

        async def _wait_for_stop() -> None:
            wait_tasks = []
            if stop_event is not None:
                wait_tasks.append(asyncio.create_task(asyncio.to_thread(stop_event.wait)))
            if max_seconds:
                wait_tasks.append(asyncio.create_task(asyncio.sleep(float(max_seconds))))
            if not wait_tasks:
                await asyncio.Event().wait()
                return
            await asyncio.wait(wait_tasks, return_when=asyncio.FIRST_COMPLETED)

        if status_interval > 0:
            metrics_task = asyncio.create_task(
                _metrics_logger(
                    sys_queue=sys_queue,
                    mic_queue=mic_queue,
                    sys_stats=sys_stats,
                    mic_stats=mic_stats,
                    timeline_base=None,
                    interval=status_interval,
                    stop_event=metrics_stop,
                    controller=controller,
                    status_path=status_path,
                    enable_sys=False,
                    enable_mic=False,
                    adaptive_sys=None,
                    adaptive_mic=None,
                )
            )

        try:
            await _wait_for_stop()
        finally:
            metrics_stop.set()
            if metrics_task is not None:
                with contextlib.suppress(Exception):
                    await metrics_task
        return

    pa = pyaudio.PyAudio()

    try:
        sys_device = mic_device = None
        sys_rate_used = sys_ch_used = None
        mic_rate_used = mic_ch_used = None

        if enable_sys:
            sys_stream, sys_device, sys_rate_used, sys_ch_used = open_loopback_stream(
                pa,
                capture_rate,
                ch_sys,
                frames_per_buffer,
                follow_default=bool(cfg.get("system_device_follow_default", True)),
                select_each_time=bool(cfg.get("system_device_prompt", False)),
                device_index=cfg.get("system_device_index"),
            )
        if enable_mic:
            mic_stream, mic_device, mic_rate_used, mic_ch_used = open_mic_stream(
                pa,
                capture_rate,
                ch_mic,
                frames_per_buffer,
                device_index=cfg.get("mic_device_index"),
            )

        logger.info(
            "Streaming capture start (system device=%s, mic device=%s) stt_model=%s stt_url=%s",
            sys_device if enable_sys else "off",
            mic_device if enable_mic else "off",
            stt_cfg.get("model"),
            stt_cfg.get("url"),
        )

        try:
            device_info = {}
            if enable_sys and sys_device is not None:
                device_info["system"] = build_capture_device_info(
                    pa,
                    sys_device,
                    capture_rate=sys_rate_used,
                    channels=sys_ch_used,
                    frames_per_buffer=frames_per_buffer,
                )
            if enable_mic and mic_device is not None:
                device_info["mic"] = build_capture_device_info(
                    pa,
                    mic_device,
                    capture_rate=mic_rate_used,
                    channels=mic_ch_used,
                    frames_per_buffer=frames_per_buffer,
                )
            if device_info:
                write_device_info(session_dir, device_info)
        except Exception:  # noqa: BLE001
            logger.exception("Failed to write device info.")

        sys_calibration = None
        mic_calibration = None
        if enable_sys:
            sys_calibration = build_source_calibration(
                calibration_cfg,
                source="sys",
                fallback_threshold=energy_threshold_sys,
            )
            sys_calibration["hysteresis"] = _resolve_hysteresis_cfg(
                vad_cfg,
                source="sys",
                base_threshold=energy_threshold_sys,
            )
            if isinstance(sys_calibration.get("hysteresis"), dict):
                sys_calibration["hysteresis"]["min_voice_chunks"] = int(
                    vad_cfg.get("min_voice_chunks_sys", 1)
                )
        if enable_mic:
            mic_calibration = build_source_calibration(
                calibration_cfg,
                source="mic",
                fallback_threshold=energy_threshold_mic,
            )
            mic_calibration["hysteresis"] = _resolve_hysteresis_cfg(
                vad_cfg,
                source="mic",
                base_threshold=energy_threshold_mic,
            )
            if isinstance(mic_calibration.get("hysteresis"), dict):
                mic_calibration["hysteresis"]["min_voice_chunks"] = int(
                    vad_cfg.get("min_voice_chunks_mic", 1)
                )

        def _build_adaptive(source: str, base_threshold: float) -> Optional[AdaptiveVadController]:
            if not isinstance(adaptive_cfg, dict) or not adaptive_cfg:
                return None
            if not bool(adaptive_cfg.get("enable", False)):
                return None

            min_thr = adaptive_cfg.get(f"min_threshold_{source}")
            max_thr = adaptive_cfg.get(f"max_threshold_{source}")
            if min_thr is None:
                min_thr = calibration_cfg.get(f"min_threshold_{source}")
            if max_thr is None:
                max_thr = calibration_cfg.get(f"max_threshold_{source}")

            cfg_obj = AdaptiveVadConfig(
                enable=True,
                update_interval_seconds=float(adaptive_cfg.get("update_interval_seconds", 30.0)),
                target_drop_rate=float(adaptive_cfg.get("target_drop_rate", 0.4)),
                deadband=float(adaptive_cfg.get("deadband", 0.1)),
                max_step_ratio=float(adaptive_cfg.get("max_step_ratio", 0.15)),
                smoothing=float(adaptive_cfg.get("smoothing", 0.7)),
                min_samples=int(adaptive_cfg.get("min_samples", 40)),
                min_change_ratio=float(adaptive_cfg.get("min_change_ratio", 0.03)),
                min_threshold=float(min_thr) if min_thr is not None else None,
                max_threshold=float(max_thr) if max_thr is not None else None,
            )
            return AdaptiveVadController(
                base_threshold=float(base_threshold),
                start_threshold=None,
                stop_threshold=None,
                cfg=cfg_obj,
            )

        adaptive_sys = _build_adaptive("sys", energy_threshold_sys) if enable_sys else None
        adaptive_mic = _build_adaptive("mic", energy_threshold_mic) if enable_mic else None

        record_dir = session_dir / recording_cfg["directory"] if recording_cfg["directory"] else session_dir
        sample_width = 2  # PCM16 (paInt16)
        sys_recorder = None
        mic_recorder = None

        if enable_sys and recording_cfg["system"] and sys_rate_used is not None and sys_ch_used is not None:
            sys_recorder = AudioRecorder(
                base_dir=record_dir,
                basename="system",
                sample_rate=sys_rate_used,
                channels=sys_ch_used,
                sample_width=sample_width,
                fmt=recording_cfg["format"],
                rotate_seconds=recording_cfg["rotate_seconds"],
                rotate_bytes=recording_cfg["rotate_bytes"],
                always_index=True,
            )

        if enable_mic and recording_cfg["mic"] and mic_rate_used is not None and mic_ch_used is not None:
            mic_recorder = AudioRecorder(
                base_dir=record_dir,
                basename="mic",
                sample_rate=mic_rate_used,
                channels=mic_ch_used,
                sample_width=sample_width,
                fmt=recording_cfg["format"],
                rotate_seconds=recording_cfg["rotate_seconds"],
                rotate_bytes=recording_cfg["rotate_bytes"],
                always_index=True,
            )
        # Start minutes updater after successful capture device open.
        minutes_task = asyncio.create_task(
            _minutes_updater(
                repo,
                session_dir,
                float(effective_minutes_cfg.get("update_interval_seconds", 60)),
                effective_minutes_cfg,
                minutes_stop,
                llm_updater,
                controller,
            )
        )

        timeline_base = time.monotonic()

        producer_threads = []
        if enable_sys and sys_stream is not None and sys_rate_used is not None and sys_ch_used is not None:
            producer_threads.append(
                threading.Thread(
                    target=_producer_thread,
                    name="sys-producer",
                    kwargs=dict(
                        stream=sys_stream,
                        source="sys",
                        capture_rate=sys_rate_used,
                        capture_channels=sys_ch_used,
                        target_rate=target_rate,
                        chunk_ms=chunk_ms,
                        energy_threshold=energy_threshold_sys,
                        frames_per_buffer=frames_per_buffer,
                        out_queue=sys_queue,
                        stop_all=stop_all,
                        stop_source=stop_sys,
                        recorder=sys_recorder,
                        calibration=sys_calibration,
                        timeline_base=timeline_base,
                        stats=sys_stats,
                        adaptive=adaptive_sys,
                    ),
                    daemon=True,
                )
            )
        if enable_mic and mic_stream is not None and mic_rate_used is not None and mic_ch_used is not None:
            producer_threads.append(
                threading.Thread(
                    target=_producer_thread,
                    name="mic-producer",
                    kwargs=dict(
                        stream=mic_stream,
                        source="mic",
                        capture_rate=mic_rate_used,
                        capture_channels=mic_ch_used,
                        target_rate=target_rate,
                        chunk_ms=chunk_ms,
                        energy_threshold=energy_threshold_mic,
                        frames_per_buffer=frames_per_buffer,
                        out_queue=mic_queue,
                        stop_all=stop_all,
                        stop_source=stop_mic,
                        recorder=mic_recorder,
                        calibration=mic_calibration,
                        timeline_base=timeline_base,
                        stats=mic_stats,
                        adaptive=adaptive_mic,
                        guard_cfg=guard_mic_cfg,
                    ),
                    daemon=True,
                )
            )
        for t in producer_threads:
            t.start()

        if status_interval > 0:
            metrics_task = asyncio.create_task(
                _metrics_logger(
                    sys_queue=sys_queue,
                    mic_queue=mic_queue,
                    sys_stats=sys_stats,
                    mic_stats=mic_stats,
                    timeline_base=timeline_base,
                    interval=status_interval,
                    stop_event=metrics_stop,
                    controller=controller,
                    status_path=status_path,
                    enable_sys=enable_sys,
                    enable_mic=enable_mic,
                    adaptive_sys=adaptive_sys,
                    adaptive_mic=adaptive_mic,
                )
            )

        stt_tasks = []
        if enable_sys:
            stt_tasks.append(
                asyncio.create_task(
                    _stt_worker(
                        name="sys",
                        cfg=stt_cfg,
                        chunk_queue=sys_queue,
                        repo=repo,
                        stop_global=stop_global,
                        stop_source_thread=stop_sys,
                        dead_flags=dead_flags,
                        controller=controller,
                        permanent_error_callback=_record_permanent_stt_error,
                    )
                )
            )
        if enable_mic:
            stt_tasks.append(
                asyncio.create_task(
                    _stt_worker(
                        name="mic",
                        cfg=stt_cfg,
                        chunk_queue=mic_queue,
                        repo=repo,
                        stop_global=stop_global,
                        stop_source_thread=stop_mic,
                        dead_flags=dead_flags,
                        controller=controller,
                        permanent_error_callback=_record_permanent_stt_error,
                    )
                )
            )

        async def _sleep_until_stop() -> None:
            wait_tasks = [asyncio.create_task(stop_global.wait())]
            if stop_event is not None:
                wait_tasks.append(asyncio.create_task(asyncio.to_thread(stop_event.wait)))

            try:
                if max_seconds:
                    done, pending = await asyncio.wait(
                        wait_tasks,
                        timeout=float(max_seconds),
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    if not done:
                        stop_global.set()
                    else:
                        stop_global.set()
                else:
                    await asyncio.wait(wait_tasks, return_when=asyncio.FIRST_COMPLETED)
                    stop_global.set()
            finally:
                for task in wait_tasks:
                    if not task.done():
                        task.cancel()

        try:
            await _sleep_until_stop()
        except KeyboardInterrupt:
            logger.info("Stopping streaming (user request)")
            stop_global.set()
        finally:
            _write_pipeline_status(
                status_path,
                phase="stopping",
                minutes_finalize={
                    "state": "running",
                    "message": "Stopping live transcription and preparing finalization.",
                    "progress_current": 0,
                    "progress_total": 0,
                    "progress_ratio": 0.0,
                    "eta_seconds": None,
                    "error": None,
                },
            )
            minutes_stop.set()
            metrics_stop.set()
            stop_all.set()
            stop_sys.set()
            stop_mic.set()

            # Let workers exit cleanly (no cancellation) to allow flush.
            await asyncio.gather(*stt_tasks, return_exceptions=True)

            record_dir = session_dir / recording_cfg["directory"] if recording_cfg["directory"] else session_dir
            catch_up_will_run = False
            if catch_up_cfg.get("enable", False):
                only_when_delay = bool(catch_up_cfg.get("only_when_delay", True))
                if (not only_when_delay) or controller.delay_mode_triggered:
                    if (recording_cfg.get("system") or recording_cfg.get("mic")) and record_dir.exists():
                        catch_up_will_run = True

            # Stop realtime minutes updater before snapshot/finalize to avoid races.
            if minutes_task is not None:
                with contextlib.suppress(Exception):
                    await minutes_task

            keep_realtime = bool(catch_up_cfg.get("keep_realtime_artifacts", False))
            if keep_realtime:
                try:
                    for name in ("minutes.json", "minutes.md"):
                        src = session_dir / name
                        if not src.exists():
                            continue
                        dst = src.with_name(f"{src.stem}_realtime{src.suffix}")
                        if dst.exists():
                            dst.unlink()
                        shutil.copy2(src, dst)
                    if catch_up_will_run:
                        logger.info("Realtime minutes snapshot saved (before catch-up).")
                    else:
                        logger.info("Realtime minutes snapshot saved (no catch-up).")
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Failed to snapshot realtime minutes: %s", exc)

            # Final minutes flush (captures any last transcript appended).
            if catch_up_will_run:
                logger.info("Running provisional final minutes flush (before catch-up).")
                _write_pipeline_status(
                    status_path,
                    phase="provisional_finalize",
                    minutes_finalize={
                        "state": "provisional_finalize",
                        "message": "Generating provisional final minutes before catch-up.",
                        "eta_seconds": None,
                        "error": None,
                    },
                )
                try:
                    if llm_updater.llm_cfg.enable:
                        await llm_updater.finalize(repo.memory)
                    else:
                        await _write_minutes_rule_based(repo, session_dir, effective_minutes_cfg)
                    logger.info("Provisional final minutes flush completed.")
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "Provisional final minutes flush failed (catch-up will continue): %s",
                        exc,
                    )
                    _write_pipeline_status(
                        status_path,
                        phase="provisional_finalize",
                        minutes_finalize={
                            "state": "provisional_finalize",
                            "message": "Provisional finalization failed; continuing to catch-up.",
                            "error": str(exc),
                        },
                    )
            else:
                _write_pipeline_status(
                    status_path,
                    phase="provisional_finalize",
                    minutes_finalize={
                        "state": "provisional_finalize",
                        "message": "Generating final minutes.",
                        "eta_seconds": None,
                        "error": None,
                    },
                )
                try:
                    if llm_updater.llm_cfg.enable:
                        await llm_updater.finalize(repo.memory)
                    else:
                        await _write_minutes_rule_based(repo, session_dir, effective_minutes_cfg)
                    _write_pipeline_status(
                        status_path,
                        phase="completed",
                        minutes_finalize={
                            "state": "completed",
                            "message": "Final minutes are ready.",
                            "progress_ratio": 1.0,
                            "eta_seconds": 0.0,
                            "completed_at": time.time(),
                            "error": None,
                        },
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.exception("Final minutes flush failed: %s", exc)
                    _write_pipeline_status(
                        status_path,
                        phase="failed",
                        minutes_finalize={
                            "state": "failed",
                            "message": "Final minutes generation failed.",
                            "error": str(exc),
                            "eta_seconds": None,
                        },
                    )

            if metrics_task is not None:
                with contextlib.suppress(Exception):
                    await metrics_task

            try:
                await _run_catch_up(
                    session_dir=session_dir,
                    status_path=status_path,
                    audio_cfg=cfg,
                    stt_cfg=stt_cfg,
                    minutes_cfg=effective_minutes_cfg,
                    recording_cfg=recording_cfg,
                    catch_cfg=catch_up_cfg,
                    controller=controller,
                    permanent_stt_errors=permanent_stt_errors,
                )
            except Exception as exc:  # noqa: BLE001
                logger.exception("Catch-up execution failed: %s", exc)
                _write_pipeline_status(
                    status_path,
                    phase="failed",
                    minutes_finalize={
                        "state": "failed",
                        "message": "Catch-up execution failed.",
                        "error": str(exc),
                        "eta_seconds": None,
                    },
                )

            logger.info("Streaming stopped: session_dir=%s", session_dir)

    finally:
        for t in producer_threads:
            t.join(timeout=2.0)

        if sys_stream:
            with contextlib.suppress(Exception):
                sys_stream.close()
        if mic_stream:
            with contextlib.suppress(Exception):
                mic_stream.close()
        pa.terminate()


async def run_streaming(
    cfg: dict,
    stt_cfg: dict,
    minutes_cfg: dict,
    session_dir: Path,
    recording_cfg: Optional[dict] = None,
    max_seconds: Optional[float] = None,
    resilience_cfg: Optional[dict] = None,
    stop_event: Optional[threading.Event] = None,
    control_queue: queue.Queue[InputSourceUpdate] | None = None,
    level_callback: Callable[[LiveAudioLevel], None] | None = None,
    diagnostic_event_callback: Callable[[AudioDecisionEvent], None] | None = None,
    fast_shutdown_event: Optional[threading.Event] = None,
) -> None:
    """Start streaming and allow source-level hot-swap without ending the session."""
    if not stt_cfg.get("enable", True):
        logger.warning("STT is disabled in config; streaming will not run.")
        return

    capture_rate = int(cfg["capture_rate"])
    target_rate = int(cfg["target_rate"])
    frames_per_buffer = int(cfg["frames_per_buffer"])
    chunk_ms = int(cfg["chunk_ms"])
    queue_max = int(cfg["queue_max_chunks"])
    energy_threshold_sys = float(cfg["energy_threshold_sys"])
    energy_threshold_mic = float(cfg["energy_threshold_mic"])
    ch_sys = int(cfg["channels_system"])
    ch_mic = int(cfg["channels_mic"])
    level_interval = float(cfg.get("level_interval_seconds", 0.08) or 0.08)
    metrics_interval = float(cfg.get("metrics_interval_seconds", 10.0))
    resilience_cfg = resilience_cfg or {}
    status_interval = float(resilience_cfg.get("status_interval_seconds", metrics_interval))
    catch_up_cfg = resilience_cfg.get("catch_up", {}) if isinstance(resilience_cfg, dict) else {}
    vad_cfg = cfg.get("vad") if isinstance(cfg.get("vad"), dict) else {}
    adaptive_cfg = vad_cfg.get("adaptive") if isinstance(vad_cfg, dict) else {}
    guard_mic_cfg = vad_cfg.get("guard_mic") if isinstance(vad_cfg.get("guard_mic"), dict) else None

    recording_cfg = recording_cfg or resolve_recording_config(cfg)
    calibration_cfg = resolve_calibration_config(cfg)
    status_path = session_dir / "status.json"

    stop_all = threading.Event()
    stop_global = asyncio.Event()
    minutes_stop = asyncio.Event()
    metrics_stop = asyncio.Event()

    repo = TranscriptRepo(session_dir / "transcript.jsonl")
    effective_minutes_cfg = apply_minutes_profile(minutes_cfg)
    llm_updater = LlmMinutesUpdater(
        session_dir=session_dir,
        minutes_cfg=effective_minutes_cfg,
        api_key_priority=stt_cfg.get("api_key_priority") or [],
    )
    controller = ResilienceController(
        cfg=resilience_cfg,
        base_segment_max_seconds=float(stt_cfg.get("segment_max_seconds", 12.0)),
        base_minutes_interval=float(effective_minutes_cfg.get("update_interval_seconds", 60)),
        queue_max=queue_max,
    )
    permanent_stt_errors: dict[str, str] = {}

    source_state: dict[str, dict[str, Any]] = {
        "sys": {
            "enabled": _coerce_bool(cfg.get("enable_system", True)),
            "device_index": cfg.get("system_device_index"),
            "follow_default": bool(cfg.get("system_device_follow_default", True)),
            "error": None,
        },
        "mic": {
            "enabled": _coerce_bool(cfg.get("enable_mic", True)),
            "device_index": cfg.get("mic_device_index"),
            "follow_default": True,
            "error": None,
        },
    }

    def _record_permanent_stt_error(source: str, info: SttErrorInfo) -> None:
        source = str(source).strip().lower()
        if source not in source_state:
            return
        permanent_stt_errors[source] = info.safe_message
        source_state[source]["error"] = info.safe_message
        source_state[source]["stt_error_classification"] = info.classification
        source_state[source]["stt_error_category"] = stt_error_safe_category(info)
        enabled_sources = {name for name, state in source_state.items() if bool(state.get("enabled", False))}
        if enabled_sources and enabled_sources.issubset(permanent_stt_errors):
            logger.error("All active STT sources failed permanently; stopping streaming.")
            stop_global.set()
        _write_audio_status()
        _emit_inactive(source, error=info.safe_message)

    thresholds = {"sys": energy_threshold_sys, "mic": energy_threshold_mic}
    stats_by_source = {
        "sys": ProducerStats(energy_threshold=energy_threshold_sys),
        "mic": ProducerStats(energy_threshold=energy_threshold_mic),
    }
    queues_by_source: dict[str, queue.Queue] = {
        "sys": queue.Queue(maxsize=queue_max),
        "mic": queue.Queue(maxsize=queue_max),
    }
    runtimes: dict[str, SourceRuntime] = {}
    dead_flags = {"sys": True, "mic": True}
    timeline_base = time.monotonic()

    def _fast_shutdown_requested() -> bool:
        return bool(fast_shutdown_event is not None and fast_shutdown_event.is_set())

    def _emit_level(level: LiveAudioLevel) -> None:
        if level_callback is not None:
            with contextlib.suppress(Exception):
                level_callback(level)

    def _emit_inactive(source: str, *, error: str | None = None) -> None:
        _emit_level(
            inactive_level(
                source=source,
                threshold=thresholds[source],
                error=error,
                device_index=source_state[source].get("device_index"),
            )
        )

    def _source_status(source: str) -> dict[str, Any]:
        runtime = runtimes.get(source)
        stats = stats_by_source[source].snapshot()
        desired = source_state[source]
        return {
            "rms": float(stats.get("last_rms", 0.0)),
            "threshold": float(stats.get("energy_threshold", thresholds[source])),
            "noise_rms": stats.get("noise_rms"),
            "enabled": bool(desired.get("enabled", False)),
            "active": runtime is not None,
            "error": desired.get("error"),
            "stt_error_classification": desired.get("stt_error_classification"),
            "stt_error_category": desired.get("stt_error_category"),
            "device_index": runtime.actual_device_index if runtime is not None else desired.get("device_index"),
            "follow_default": bool(desired.get("follow_default", True)),
        }

    def _write_audio_status() -> None:
        try:
            payload = _read_status_json(status_path)
            audio = payload.get("audio")
            if not isinstance(audio, dict):
                audio = {}
                payload["audio"] = audio
            audio["sys"] = _source_status("sys")
            audio["mic"] = _source_status("mic")
            payload["timestamp"] = time.time()
            write_text_atomic(
                status_path,
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("Failed to write source status: %s", exc)

    def _build_adaptive(source: str, base_threshold: float) -> Optional[AdaptiveVadController]:
        if not isinstance(adaptive_cfg, dict) or not bool(adaptive_cfg.get("enable", False)):
            return None
        min_thr = adaptive_cfg.get(f"min_threshold_{source}")
        max_thr = adaptive_cfg.get(f"max_threshold_{source}")
        if min_thr is None:
            min_thr = calibration_cfg.get(f"min_threshold_{source}")
        if max_thr is None:
            max_thr = calibration_cfg.get(f"max_threshold_{source}")
        cfg_obj = AdaptiveVadConfig(
            enable=True,
            update_interval_seconds=float(adaptive_cfg.get("update_interval_seconds", 30.0)),
            target_drop_rate=float(adaptive_cfg.get("target_drop_rate", 0.4)),
            deadband=float(adaptive_cfg.get("deadband", 0.1)),
            max_step_ratio=float(adaptive_cfg.get("max_step_ratio", 0.15)),
            smoothing=float(adaptive_cfg.get("smoothing", 0.7)),
            min_samples=int(adaptive_cfg.get("min_samples", 40)),
            min_change_ratio=float(adaptive_cfg.get("min_change_ratio", 0.03)),
            min_threshold=float(min_thr) if min_thr is not None else None,
            max_threshold=float(max_thr) if max_thr is not None else None,
        )
        return AdaptiveVadController(
            base_threshold=float(base_threshold),
            start_threshold=None,
            stop_threshold=None,
            cfg=cfg_obj,
        )

    def _source_calibration(source: str, base_threshold: float) -> dict:
        source_calibration = build_source_calibration(
            calibration_cfg,
            source=source,
            fallback_threshold=base_threshold,
        )
        source_calibration["hysteresis"] = _resolve_hysteresis_cfg(
            vad_cfg,
            source=source,
            base_threshold=base_threshold,
        )
        if isinstance(source_calibration.get("hysteresis"), dict):
            source_calibration["hysteresis"]["min_voice_chunks"] = int(
                vad_cfg.get(f"min_voice_chunks_{source}", 1)
            )
        return source_calibration

    def _device_name(pa: pyaudio.PyAudio, device_index: int | None) -> str | None:
        if device_index is None:
            return None
        try:
            return str(pa.get_device_info_by_index(int(device_index)).get("name", "")).strip() or None
        except Exception:
            return None

    def _prepare_source(pa: pyaudio.PyAudio, source: str) -> SourceRuntime:
        desired = source_state[source]
        threshold = thresholds[source]
        if source == "sys":
            stream, actual_device, rate_used, ch_used = open_loopback_stream(
                pa,
                capture_rate,
                ch_sys,
                frames_per_buffer,
                follow_default=bool(desired.get("follow_default", True)),
                select_each_time=False,
                device_index=desired.get("device_index"),
            )
            basename = "system"
            rec_enabled = bool(recording_cfg.get("system"))
        else:
            stream, actual_device, rate_used, ch_used = open_mic_stream(
                pa,
                capture_rate,
                ch_mic,
                frames_per_buffer,
                device_index=desired.get("device_index"),
            )
            basename = "mic"
            rec_enabled = bool(recording_cfg.get("mic"))

        device_info = None
        with contextlib.suppress(Exception):
            device_info = build_capture_device_info(
                pa,
                actual_device,
                capture_rate=rate_used,
                channels=ch_used,
                frames_per_buffer=frames_per_buffer,
            )

        record_dir = session_dir / recording_cfg["directory"] if recording_cfg["directory"] else session_dir
        recorder = None
        if rec_enabled and rate_used is not None and ch_used is not None:
            recorder = AudioRecorder(
                base_dir=record_dir,
                basename=basename,
                sample_rate=rate_used,
                channels=ch_used,
                sample_width=2,
                fmt=recording_cfg["format"],
                rotate_seconds=recording_cfg["rotate_seconds"],
                rotate_bytes=recording_cfg["rotate_bytes"],
                always_index=True,
            )

        stats = ProducerStats(energy_threshold=threshold)
        runtime = SourceRuntime(
            name=source,
            enabled=True,
            device_index=desired.get("device_index"),
            follow_default=bool(desired.get("follow_default", True)),
            stream=stream,
            producer_thread=None,
            queue=queue.Queue(maxsize=queue_max),
            stt_task=None,
            stop_source=threading.Event(),
            stt_stop=asyncio.Event(),
            recorder=recorder,
            stats=stats,
            adaptive=_build_adaptive(source, threshold),
            calibration=_source_calibration(source, threshold),
            rate_used=rate_used,
            channels_used=ch_used,
            actual_device_index=actual_device,
            device_info=device_info,
        )
        return runtime

    def _write_device_info_current() -> None:
        device_info: dict[str, Any] = {}
        sys_rt = runtimes.get("sys")
        mic_rt = runtimes.get("mic")
        if sys_rt is not None and sys_rt.device_info is not None:
            device_info["system"] = sys_rt.device_info
        if mic_rt is not None and mic_rt.device_info is not None:
            device_info["mic"] = mic_rt.device_info
        if device_info:
            write_device_info(session_dir, device_info)

    def _activate_runtime(pa: pyaudio.PyAudio, runtime: SourceRuntime) -> None:
        source = runtime.name
        device_name = _device_name(pa, runtime.actual_device_index)
        runtime.producer_thread = threading.Thread(
            target=_producer_thread,
            name=f"{source}-producer",
            kwargs=dict(
                stream=runtime.stream,
                source=source,
                capture_rate=int(runtime.rate_used or capture_rate),
                capture_channels=int(runtime.channels_used or (ch_sys if source == "sys" else ch_mic)),
                target_rate=target_rate,
                chunk_ms=chunk_ms,
                energy_threshold=thresholds[source],
                frames_per_buffer=frames_per_buffer,
                out_queue=runtime.queue,
                stop_all=stop_all,
                stop_source=runtime.stop_source,
                recorder=runtime.recorder,
                calibration=runtime.calibration,
                timeline_base=timeline_base,
                stats=runtime.stats,
                adaptive=runtime.adaptive,
                guard_cfg=guard_mic_cfg if source == "mic" else None,
                level_callback=_emit_level,
                diagnostic_event_callback=diagnostic_event_callback,
                level_interval_seconds=level_interval,
                device_index=runtime.actual_device_index,
                device_name=device_name,
            ),
            daemon=True,
        )
        runtimes[source] = runtime
        queues_by_source[source] = runtime.queue
        stats_by_source[source] = runtime.stats
        dead_flags[source] = False
        permanent_stt_errors.pop(source, None)
        source_state[source]["error"] = None
        source_state[source].pop("stt_error_classification", None)
        runtime.producer_thread.start()
        runtime.stt_task = asyncio.create_task(
            _stt_worker(
                name=source,
                cfg=stt_cfg,
                chunk_queue=runtime.queue,
                repo=repo,
                stop_global=stop_global,
                stop_source_async=runtime.stt_stop,
                stop_source_thread=runtime.stop_source,
                dead_flags=dead_flags,
                controller=controller,
                stop_on_all_dead=False,
                permanent_error_callback=_record_permanent_stt_error,
            )
        )
        logger.info(
            "%s source active: device=%s follow_default=%s",
            source,
            runtime.actual_device_index,
            runtime.follow_default,
        )

    async def _stop_runtime(source: str, *, emit: bool = True, cancel_task: bool = False) -> None:
        runtime = runtimes.pop(source, None)
        if runtime is None:
            dead_flags[source] = True
            if emit:
                _emit_inactive(source)
            return
        runtime.stop_source.set()
        runtime.stt_stop.set()
        if runtime.stt_task is not None:
            if cancel_task:
                runtime.stt_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await runtime.stt_task
        if runtime.producer_thread is not None:
            await asyncio.to_thread(runtime.producer_thread.join, 2.0)
        if runtime.stream is not None:
            with contextlib.suppress(Exception):
                runtime.stream.close()
        queues_by_source[source] = queue.Queue(maxsize=queue_max)
        stats_by_source[source] = ProducerStats(energy_threshold=thresholds[source])
        dead_flags[source] = True
        if emit:
            _emit_inactive(source)
        logger.info("%s source inactive", source)

    async def _apply_source_update(pa: pyaudio.PyAudio, update: InputSourceUpdate) -> None:
        source = str(update.source).strip().lower()
        if source == "system":
            source = "sys"
        if source not in {"sys", "mic"}:
            logger.warning("Ignoring unknown source update: %s", update)
            return
        updated_cfg = apply_input_update_to_audio_config(cfg, update)
        cfg.clear()
        cfg.update(updated_cfg)
        if source == "sys":
            source_state[source].update(
                {
                    "enabled": bool(update.enabled),
                    "device_index": update.device_index,
                    "follow_default": bool(update.follow_default)
                    if update.follow_default is not None
                    else update.device_index is None,
                    "error": None,
                }
            )
        else:
            source_state[source].update(
                {
                    "enabled": bool(update.enabled),
                    "device_index": update.device_index,
                    "follow_default": True,
                    "error": None,
                }
            )

        if not update.enabled:
            await _stop_runtime(source)
            _write_audio_status()
            return

        try:
            next_runtime = _prepare_source(pa, source)
        except Exception as exc:  # noqa: BLE001
            source_state[source]["error"] = str(exc)
            logger.warning("%s source update failed; keeping existing source when present: %s", source, exc)
            _emit_inactive(source, error=str(exc))
            _write_audio_status()
            return

        old_runtime = runtimes.get(source)
        if old_runtime is not None:
            await _stop_runtime(source, emit=False)
        _activate_runtime(pa, next_runtime)
        with contextlib.suppress(Exception):
            _write_device_info_current()
        _write_audio_status()

    async def _control_loop(pa: pyaudio.PyAudio) -> None:
        if control_queue is None:
            return
        while not stop_global.is_set():
            try:
                update = await asyncio.to_thread(control_queue.get, True, 0.2)
            except queue.Empty:
                continue
            if not isinstance(update, InputSourceUpdate):
                logger.warning("Ignoring invalid control message: %r", update)
                continue
            await _apply_source_update(pa, update)

    async def _metrics_loop() -> None:
        while not metrics_stop.is_set():
            now = time.monotonic()
            status_audio = {"sys": _source_status("sys"), "mic": _source_status("mic")}
            for source in ("sys", "mic"):
                runtime = runtimes.get(source)
                stats = stats_by_source[source].snapshot()
                queue_obj = queues_by_source[source]
                active = runtime is not None
                delay = (
                    _compute_delay(now, timeline_base=timeline_base, last_t1=stats.get("last_chunk_t1"))
                    if active
                    else None
                )
                drop = _compute_drop_rate(stats) if active else 0.0
                vad_drop = _compute_vad_drop_rate(stats) if active else 0.0
                if runtime is not None and runtime.adaptive is not None:
                    change = runtime.adaptive.maybe_update(
                        drop_rate=vad_drop,
                        sample_count=int(stats.get("produced", 0)) + int(stats.get("dropped_energy", 0)),
                        now=now,
                    )
                    if change:
                        old, new = change
                        logger.info("%s adaptive VAD: drop=%.2f threshold %.1f -> %.1f", source, vad_drop, old, new)
                        runtime.stats.update(energy_threshold=new)
                if active:
                    controller.update_metrics(
                        source,
                        queue_size=queue_obj.qsize(),
                        delay_seconds=delay,
                        drop_rate=drop / 100.0,
                    )
                else:
                    controller.update_metrics(source, queue_size=0, delay_seconds=None, drop_rate=0.0)

            mode_changed = controller.evaluate_mode()
            if mode_changed:
                logger.warning("Resilience mode changed: %s", controller.mode)
            logger.info(
                "metrics: mode=%s sys active=%s q=%d rms=%.1f | mic active=%s q=%d rms=%.1f",
                controller.mode,
                "sys" in runtimes,
                queues_by_source["sys"].qsize(),
                status_audio["sys"]["rms"],
                "mic" in runtimes,
                queues_by_source["mic"].qsize(),
                status_audio["mic"]["rms"],
            )
            try:
                existing_status = _read_status_json(status_path)
                status_payload = controller.status_payload()
                status_payload["timestamp"] = time.time()
                status_payload["audio"] = status_audio
                for key in ("pipeline", "minutes_finalize"):
                    value = existing_status.get(key)
                    if isinstance(value, dict):
                        status_payload[key] = value
                write_text_atomic(
                    status_path,
                    json.dumps(status_payload, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            except Exception as exc:  # noqa: BLE001
                logger.debug("Failed to write status.json: %s", exc)

            try:
                await asyncio.wait_for(metrics_stop.wait(), timeout=float(status_interval))
            except asyncio.TimeoutError:
                continue

    async def _sleep_until_stop() -> None:
        wait_tasks: list[asyncio.Task] = [asyncio.create_task(stop_global.wait())]
        if stop_event is not None:
            wait_tasks.append(asyncio.create_task(asyncio.to_thread(stop_event.wait)))
        try:
            if max_seconds:
                done, pending = await asyncio.wait(
                    wait_tasks,
                    timeout=float(max_seconds),
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if not done:
                    stop_global.set()
                else:
                    stop_global.set()
            else:
                await asyncio.wait(wait_tasks, return_when=asyncio.FIRST_COMPLETED)
                stop_global.set()
        finally:
            for task in wait_tasks:
                if not task.done():
                    task.cancel()

    _write_pipeline_status(
        status_path,
        phase="running",
        minutes_finalize={
            "state": "idle",
            "message": "Realtime minutes are updating.",
            "progress_current": 0,
            "progress_total": 0,
            "progress_ratio": 0.0,
            "eta_seconds": None,
            "error": None,
        },
    )

    pa = pyaudio.PyAudio()
    minutes_task: asyncio.Task | None = None
    metrics_task: asyncio.Task | None = None
    control_task: asyncio.Task | None = None
    try:
        minutes_task = asyncio.create_task(
            _minutes_updater(
                repo,
                session_dir,
                float(effective_minutes_cfg.get("update_interval_seconds", 60)),
                effective_minutes_cfg,
                minutes_stop,
                llm_updater,
                controller,
            )
        )

        for source in ("sys", "mic"):
            if not bool(source_state[source].get("enabled", False)):
                _emit_inactive(source)
                continue
            try:
                runtime = _prepare_source(pa, source)
                _activate_runtime(pa, runtime)
            except Exception as exc:  # noqa: BLE001
                source_state[source]["error"] = str(exc)
                logger.warning("%s source failed to start; session remains open: %s", source, exc)
                _emit_inactive(source, error=str(exc))

        if not runtimes:
            logger.warning("No active audio sources; session remains in input-waiting state.")
        with contextlib.suppress(Exception):
            _write_device_info_current()
        _write_audio_status()

        if status_interval > 0:
            metrics_task = asyncio.create_task(_metrics_loop())
        control_task = asyncio.create_task(_control_loop(pa))

        try:
            await _sleep_until_stop()
        except KeyboardInterrupt:
            logger.info("Stopping streaming (user request)")
            stop_global.set()
        finally:
            _write_pipeline_status(
                status_path,
                phase="stopping",
                minutes_finalize={
                    "state": "running",
                    "message": "Stopping live transcription and preparing finalization.",
                    "progress_current": 0,
                    "progress_total": 0,
                    "progress_ratio": 0.0,
                    "eta_seconds": None,
                    "error": None,
                },
            )
            if control_task is not None:
                control_task.cancel()
            stop_all.set()
            fast_shutdown = _fast_shutdown_requested()
            for source in list(runtimes):
                await _stop_runtime(source, emit=False, cancel_task=fast_shutdown)
            minutes_stop.set()
            metrics_stop.set()
            if fast_shutdown and minutes_task is not None:
                minutes_task.cancel()

            if control_task is not None:
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await control_task
            if metrics_task is not None:
                with contextlib.suppress(Exception):
                    await metrics_task

            if fast_shutdown:
                _write_pipeline_status(
                    status_path,
                    phase="stopped",
                    pipeline_fields={
                        "shutdown_mode": "fast",
                        "fast_shutdown": True,
                    },
                    minutes_finalize={
                        "state": "skipped",
                        "message": "Finalization skipped because the app window is closing.",
                        "progress_current": 0,
                        "progress_total": 0,
                        "progress_ratio": 0.0,
                        "eta_seconds": None,
                        "error": None,
                    },
                )
                if minutes_task is not None:
                    with contextlib.suppress(asyncio.CancelledError, Exception):
                        await minutes_task
                logger.info("Streaming stopped by fast shutdown: session_dir=%s", session_dir)
                return

            record_dir = session_dir / recording_cfg["directory"] if recording_cfg["directory"] else session_dir
            catch_up_will_run = False
            if catch_up_cfg.get("enable", False):
                only_when_delay = bool(catch_up_cfg.get("only_when_delay", True))
                if (not only_when_delay) or controller.delay_mode_triggered:
                    if (recording_cfg.get("system") or recording_cfg.get("mic")) and record_dir.exists():
                        catch_up_will_run = True

            if minutes_task is not None:
                with contextlib.suppress(Exception):
                    await minutes_task

            keep_realtime = bool(catch_up_cfg.get("keep_realtime_artifacts", False))
            if keep_realtime:
                try:
                    for name in ("minutes.json", "minutes.md"):
                        src = session_dir / name
                        if not src.exists():
                            continue
                        dst = src.with_name(f"{src.stem}_realtime{src.suffix}")
                        if dst.exists():
                            dst.unlink()
                        shutil.copy2(src, dst)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Failed to snapshot realtime minutes: %s", exc)

            if catch_up_will_run:
                logger.info("Running provisional final minutes flush (before catch-up).")
                _write_pipeline_status(
                    status_path,
                    phase="provisional_finalize",
                    minutes_finalize={
                        "state": "provisional_finalize",
                        "message": "Generating provisional final minutes before catch-up.",
                        "eta_seconds": None,
                        "error": None,
                    },
                )
                try:
                    if llm_updater.llm_cfg.enable:
                        await llm_updater.finalize(repo.memory)
                    else:
                        await _write_minutes_rule_based(repo, session_dir, effective_minutes_cfg)
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "Provisional final minutes flush failed (catch-up will continue): %s",
                        exc,
                    )
                    _write_pipeline_status(
                        status_path,
                        phase="provisional_finalize",
                        minutes_finalize={
                            "state": "provisional_finalize",
                            "message": "Provisional finalization failed; continuing to catch-up.",
                            "error": str(exc),
                        },
                    )
            else:
                _write_pipeline_status(
                    status_path,
                    phase="provisional_finalize",
                    minutes_finalize={
                        "state": "provisional_finalize",
                        "message": "Generating final minutes.",
                        "eta_seconds": None,
                        "error": None,
                    },
                )
                try:
                    if llm_updater.llm_cfg.enable:
                        await llm_updater.finalize(repo.memory)
                    else:
                        await _write_minutes_rule_based(repo, session_dir, effective_minutes_cfg)
                    _write_pipeline_status(
                        status_path,
                        phase="completed",
                        minutes_finalize={
                            "state": "completed",
                            "message": "Final minutes are ready.",
                            "progress_ratio": 1.0,
                            "eta_seconds": 0.0,
                            "completed_at": time.time(),
                            "error": None,
                        },
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.exception("Final minutes flush failed: %s", exc)
                    _write_pipeline_status(
                        status_path,
                        phase="failed",
                        minutes_finalize={
                            "state": "failed",
                            "message": "Final minutes generation failed.",
                            "error": str(exc),
                            "eta_seconds": None,
                        },
                    )

            try:
                await _run_catch_up(
                    session_dir=session_dir,
                    status_path=status_path,
                    audio_cfg=cfg,
                    stt_cfg=stt_cfg,
                    minutes_cfg=effective_minutes_cfg,
                    recording_cfg=recording_cfg,
                    catch_cfg=catch_up_cfg,
                    controller=controller,
                    permanent_stt_errors=permanent_stt_errors,
                )
            except Exception as exc:  # noqa: BLE001
                logger.exception("Catch-up execution failed: %s", exc)
                _write_pipeline_status(
                    status_path,
                    phase="failed",
                    minutes_finalize={
                        "state": "failed",
                        "message": "Catch-up execution failed.",
                        "error": str(exc),
                        "eta_seconds": None,
                    },
                )

            logger.info("Streaming stopped: session_dir=%s", session_dir)
    finally:
        for source in list(runtimes):
            with contextlib.suppress(Exception):
                await _stop_runtime(source, emit=False)
        pa.terminate()
