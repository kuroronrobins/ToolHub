"""Offline STT helpers for once-mode and catch-up processing."""
from __future__ import annotations

import logging
import re
import wave
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Tuple

import numpy as np

try:  # Optional dependency for FLAC support
    import soundfile as sf  # type: ignore
except Exception:  # pragma: no cover - handled at runtime
    sf = None

from agendasnap.audio.calibration import (
    build_source_calibration,
    estimate_threshold_from_frames,
    resolve_calibration_config,
)
from agendasnap.audio.resample import resample_pcm16
from agendasnap.audio.vad import energy_vad_segments, energy_vad_segments_hysteresis
from agendasnap.bus.events import AudioChunk, TranscriptSegment
from agendasnap.minutes.generator import generate_minutes
from agendasnap.minutes.llm_summarizer import LlmMinutesUpdater
from agendasnap.minutes.render_md import render as render_minutes
from agendasnap.minutes.ssot import save_minutes_json_atomic
from agendasnap.store.atomic import write_text_atomic
from agendasnap.store.transcript_repo import TranscriptRepo
from agendasnap.stt.provider_factory import build_realtime_engine

logger = logging.getLogger(__name__)


def _split_pcm_turn(
    pcm: bytes,
    *,
    sample_rate: int,
    t0: float,
    max_seconds: float,
    source: str,
    t0_offset: float = 0.0,
) -> List[AudioChunk]:
    """Split a PCM16 mono segment into <=max_seconds chunks with updated t0/t1."""
    if max_seconds <= 0:
        return [
            AudioChunk(
                pcm=pcm,
                sample_rate=sample_rate,
                channels=1,
                source=source,
                t0=t0_offset + t0,
                t1=t0_offset + t0,
            )
        ]

    bytes_per_sample = 2
    samples_total = len(pcm) // bytes_per_sample
    max_samples = int(max_seconds * sample_rate)

    if max_samples <= 0 or samples_total <= max_samples:
        t1 = t0 + (samples_total / sample_rate if sample_rate else 0.0)
        return [
            AudioChunk(
                pcm=pcm,
                sample_rate=sample_rate,
                channels=1,
                source=source,
                t0=t0_offset + t0,
                t1=t0_offset + t1,
            )
        ]

    out: List[AudioChunk] = []
    pos = 0
    while pos < samples_total:
        end = min(samples_total, pos + max_samples)
        chunk_pcm = pcm[pos * bytes_per_sample : end * bytes_per_sample]
        ct0 = t0_offset + t0 + (pos / sample_rate)
        ct1 = t0_offset + t0 + (end / sample_rate)
        out.append(AudioChunk(pcm=chunk_pcm, sample_rate=sample_rate, channels=1, source=source, t0=ct0, t1=ct1))
        pos = end
    return out


def build_turns_from_frames(
    *,
    frames: List[bytes],
    capture_rate: int,
    capture_channels: int,
    target_rate: int,
    source: str,
    energy_threshold: float,
    max_turn_seconds: float,
    max_gap_ms: int = 120,
    min_segment_ms: int = 250,
    start_threshold: float | None = None,
    stop_threshold: float | None = None,
    t0_offset: float = 0.0,
) -> List[AudioChunk]:
    """Resample to target_rate/mono, run VAD, and return AudioChunks as turns."""
    if not frames:
        return []

    pcm = b"".join(frames)
    resampled, _frames_cnt, used_rate, _used_ch = resample_pcm16(
        pcm,
        src_rate=int(capture_rate),
        dst_rate=int(target_rate),
        src_channels=int(capture_channels),
        target_channels=1,
    )
    if not resampled:
        return []

    if start_threshold is not None and stop_threshold is not None:
        segments = energy_vad_segments_hysteresis(
            resampled,
            sample_rate=int(used_rate),
            channels=1,
            start_threshold=float(start_threshold),
            stop_threshold=float(stop_threshold),
            frame_ms=30,
            max_gap_ms=int(max_gap_ms),
            min_segment_ms=int(min_segment_ms),
        )
    else:
        segments = energy_vad_segments(
            resampled,
            sample_rate=int(used_rate),
            channels=1,
            energy_threshold=float(energy_threshold),
            frame_ms=30,
            max_gap_ms=int(max_gap_ms),
            min_segment_ms=int(min_segment_ms),
        )

    turns: List[AudioChunk] = []
    for start, end, seg_pcm in segments:
        # segment timings are within the resampled timeline
        turns.extend(
            _split_pcm_turn(
                seg_pcm,
                sample_rate=int(used_rate),
                t0=float(start),
                max_seconds=float(max_turn_seconds),
                source=source,
                t0_offset=float(t0_offset),
            )
        )

    return turns


def resolve_source_thresholds(
    *,
    frames: List[bytes],
    capture_rate: int,
    capture_channels: int,
    target_rate: int,
    source: str,
    audio_cfg: Dict[str, object],
    log: Optional[logging.Logger] = None,
) -> Tuple[float, Optional[float], Optional[float], Optional[float]]:
    """Return (energy_threshold, start_threshold, stop_threshold, noise_rms)."""
    base_threshold = float(
        audio_cfg.get("energy_threshold_sys" if source == "sys" else "energy_threshold_mic", 0.0)
    )
    calibration_cfg = resolve_calibration_config(audio_cfg)
    if calibration_cfg.get("enable"):
        cal = build_source_calibration(
            calibration_cfg,
            source=source,
            fallback_threshold=base_threshold,
        )
        base_threshold, noise_rms = estimate_threshold_from_frames(
            frames=frames,
            capture_rate=int(capture_rate),
            capture_channels=int(capture_channels),
            target_rate=int(target_rate),
            calibration=cal,
            fallback_threshold=base_threshold,
        )
        if log is not None and noise_rms is not None:
            log.info("%s calibration: noise_rms=%.1f threshold=%.1f", source, noise_rms, base_threshold)
    else:
        noise_rms = None

    vad_cfg = audio_cfg.get("vad") if isinstance(audio_cfg.get("vad"), dict) else {}
    hyst_enabled = bool(vad_cfg.get("enable_hysteresis", False)) if isinstance(vad_cfg, dict) else False

    start_thr = vad_cfg.get(f"start_threshold_{source}") if isinstance(vad_cfg, dict) else None
    stop_thr = vad_cfg.get(f"stop_threshold_{source}") if isinstance(vad_cfg, dict) else None
    start_ratio = vad_cfg.get(f"start_ratio_{source}") if isinstance(vad_cfg, dict) else None
    stop_ratio = vad_cfg.get(f"stop_ratio_{source}") if isinstance(vad_cfg, dict) else None

    if hyst_enabled or start_thr is not None or stop_thr is not None:
        if start_thr is None and start_ratio is not None:
            start_thr = float(base_threshold) * float(start_ratio)
        start_thr = float(start_thr) if start_thr is not None else float(base_threshold)
        if stop_thr is None and stop_ratio is not None:
            stop_thr = float(base_threshold) * float(stop_ratio)
        stop_thr = float(stop_thr) if stop_thr is not None else float(base_threshold)
    else:
        start_thr = stop_thr = None

    return float(base_threshold), start_thr, stop_thr, noise_rms


def _read_audio_file(path: Path) -> Tuple[bytes, int, int]:
    """Return (pcm_bytes, sample_rate, channels)."""
    suffix = path.suffix.lower()
    if suffix == ".wav":
        with wave.open(str(path), "rb") as wf:
            channels = int(wf.getnchannels())
            rate = int(wf.getframerate())
            sampwidth = int(wf.getsampwidth())
            if sampwidth != 2:
                raise ValueError(f"Unsupported WAV sample width: {sampwidth} bytes")
            pcm = wf.readframes(wf.getnframes())
        return pcm, rate, channels

    if suffix == ".flac":
        if sf is None:
            raise RuntimeError("FLAC catch-up requires the 'soundfile' package.")
        data, rate = sf.read(str(path), dtype="int16", always_2d=True)
        if data.size == 0:
            return b"", int(rate), int(data.shape[1] if data.ndim > 1 else 1)
        channels = int(data.shape[1])
        pcm = data.astype(np.int16, copy=False).tobytes()
        return pcm, int(rate), channels

    raise ValueError(f"Unsupported audio format: {suffix}")


def _list_recording_files(record_dir: Path, basename: str, fmt: str) -> List[Path]:
    fmt = str(fmt).lower().lstrip(".")
    if not record_dir.exists():
        return []

    files = list(record_dir.glob(f"{basename}*.{fmt}"))
    if not files:
        return []

    def _sort_key(path: Path) -> Tuple[int, int, str]:
        match = re.search(rf"{re.escape(basename)}_(\d+)\.{re.escape(fmt)}$", path.name)
        if match:
            return (0, int(match.group(1)), path.name)
        if path.name == f"{basename}.{fmt}":
            return (-1, 0, path.name)
        return (1, 0, path.name)

    return sorted(files, key=_sort_key)


def build_turns_from_recordings(
    *,
    record_dir: Path,
    basename: str,
    fmt: str,
    source: str,
    audio_cfg: Dict[str, object],
    stt_cfg: Dict[str, object],
    log: Optional[logging.Logger] = None,
) -> List[AudioChunk]:
    files = _list_recording_files(record_dir, basename, fmt)
    if not files:
        return []

    pcm0, rate0, ch0 = _read_audio_file(files[0])
    if not pcm0:
        return []

    threshold, start_thr, stop_thr, _noise = resolve_source_thresholds(
        frames=[pcm0],
        capture_rate=rate0,
        capture_channels=ch0,
        target_rate=int(audio_cfg.get("target_rate", rate0)),
        source=source,
        audio_cfg=audio_cfg,
        log=log,
    )

    max_turn_seconds = float(stt_cfg.get("segment_max_seconds", 12.0))
    max_gap_ms = int(stt_cfg.get("segment_gap_ms", 800))

    turns: List[AudioChunk] = []
    offset = 0.0
    for idx, path in enumerate(files):
        pcm, rate, ch = (pcm0, rate0, ch0) if idx == 0 else _read_audio_file(path)
        if not pcm:
            continue

        turns.extend(
            build_turns_from_frames(
                frames=[pcm],
                capture_rate=rate,
                capture_channels=ch,
                target_rate=int(audio_cfg.get("target_rate", rate)),
                source=source,
                energy_threshold=threshold,
                max_turn_seconds=max_turn_seconds,
                max_gap_ms=max_gap_ms,
                start_threshold=start_thr,
                stop_threshold=stop_thr,
                t0_offset=offset,
            )
        )

        bytes_per_sample = 2
        samples = len(pcm) // (bytes_per_sample * max(1, ch))
        offset += samples / float(rate) if rate else 0.0

    return turns


async def run_stt_once(
    *,
    stt_cfg: dict,
    turns_by_source: Dict[str, List[AudioChunk]],
    session_dir: Path,
    minutes_cfg: dict,
    transcript_path: Optional[Path] = None,
    progress_callback: Optional[Callable[[dict], None]] = None,
) -> None:
    """Run STT for once-mode and write transcript.jsonl + minutes.md."""
    repo = TranscriptRepo(transcript_path or (session_dir / "transcript.jsonl"))
    all_segments: List[TranscriptSegment] = []
    errors: List[str] = []
    total_turns = sum(len(turns) for turns in turns_by_source.values())
    processed_turns = 0

    def _emit_progress(**payload: object) -> None:
        if progress_callback is None:
            return
        data = {
            "processed_turns": processed_turns,
            "total_turns": total_turns,
        }
        data.update(payload)
        try:
            progress_callback(data)
        except Exception as exc:  # noqa: BLE001
            logger.debug("run_stt_once progress callback failed: %s", exc)

    _emit_progress(phase="stt")

    for source, turns in turns_by_source.items():
        if not turns:
            continue

        engine, _runtime = build_realtime_engine(
            source=source,
            stt_cfg=stt_cfg,
            fallback_priority=stt_cfg.get("api_key_priority"),
        )

        try:
            await engine.start()
            for turn in turns:
                try:
                    segs = await engine.push_audio([turn])
                    if segs:
                        for s in segs:
                            s.source = source
                        all_segments.extend(segs)
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"{source}: {exc}")
                finally:
                    processed_turns += 1
                    _emit_progress(phase="stt", source=source)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{source} connect: {exc}")
            processed_turns += len(turns)
            _emit_progress(phase="stt", source=source, error=str(exc))
        finally:
            with suppress_async_exc():
                await engine.stop()

    # Sort by start time (best-effort) before writing.
    all_segments.sort(key=lambda s: float(getattr(s, "start", 0.0) or 0.0))
    if all_segments:
        repo.append(all_segments)

    # Always write minutes (even if empty) for consistent outputs.
    _emit_progress(phase="finalize")
    llm_updater = LlmMinutesUpdater(
        session_dir=session_dir,
        minutes_cfg=minutes_cfg,
        api_key_priority=stt_cfg.get("api_key_priority") or [],
    )
    if llm_updater.llm_cfg.enable:
        await llm_updater.finalize(repo.memory)
    else:
        minutes_doc = generate_minutes(repo.memory, minutes_cfg)
        save_minutes_json_atomic(session_dir / "minutes.json", minutes_doc)
        minutes_md = render_minutes(minutes_doc)
        write_text_atomic(session_dir / "minutes.md", minutes_md, encoding="utf-8")

    if errors:
        _emit_progress(phase="failed", error="; ".join(errors[:3]))
        raise RuntimeError("STT errors:\n" + "\n".join(errors))

    _emit_progress(phase="completed")


class suppress_async_exc:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return True
