"""CLI entry point for AgendaSnap."""
from __future__ import annotations

import argparse
import asyncio
import logging
import threading
import time
from pathlib import Path
from typing import Dict, List, Tuple

import pyaudiowpatch as pyaudio

from agendasnap.audio.capture_mic import open_mic_stream
from agendasnap.audio.capture_wasapi import open_loopback_stream
from agendasnap.audio.devices import build_capture_device_info
from agendasnap.audio.recording import AudioRecorder, resolve_recording_config
from agendasnap.config.ai_providers import normalize_api_key_priority
from agendasnap.config.glossary import build_minutes_context_prompt, build_transcription_prompt
from agendasnap.config.loader import load_config
from agendasnap.config.validate import validate_config
from agendasnap.minutes.schema import MinutesDocument
from agendasnap.minutes.ssot import save_minutes_json_atomic
from agendasnap.pipeline.streaming import run_streaming
from agendasnap.store.atomic import write_text_atomic
from agendasnap.store.session_fs import (
    close_session_logging,
    create_session,
    init_session_artifacts,
    setup_session_logging,
    write_device_info,
)
from agendasnap.stt.offline import build_turns_from_frames, resolve_source_thresholds, run_stt_once

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("agendasnap.app")


def _record_stream_to_list(
    stream: pyaudio.Stream,
    frames_per_buffer: int,
    stop_event: threading.Event,
    out_list: List[bytes],
    err_list: List[BaseException],
    meta: dict | None = None,
) -> None:
    try:
        while not stop_event.is_set():
            data = stream.read(frames_per_buffer, exception_on_overflow=False)
            if meta is not None and "first_time" not in meta:
                meta["first_time"] = time.monotonic()
            out_list.append(data)
    except BaseException as exc:  # noqa: BLE001
        err_list.append(exc)
        stop_event.set()


def capture_once(
    *,
    duration: float,
    session_dir: Path,
    rate: int,
    frames_per_buffer: int,
    channels_sys: int,
    channels_mic: int,
    follow_default_output: bool,
    select_system_device_each_time: bool,
) -> Tuple[List[bytes], List[bytes], int, int, int, int, float, float]:
    """Capture a fixed duration from system loopback and microphone."""
    pa = pyaudio.PyAudio()
    sys_stream = mic_stream = None

    try:
        sys_stream, sys_device, sys_rate_used, sys_ch_used = open_loopback_stream(
            pa,
            rate,
            channels_sys,
            frames_per_buffer,
            follow_default=follow_default_output,
            select_each_time=select_system_device_each_time,
        )
        mic_stream, mic_device, mic_rate_used, mic_ch_used = open_mic_stream(
            pa, rate, channels_mic, frames_per_buffer
        )

        logger.info(
            "Recording for %.1f sec... (system device=%s, mic device=%s)",
            duration,
            sys_device,
            mic_device,
        )

        try:
            device_info = {
                "system": build_capture_device_info(
                    pa,
                    sys_device,
                    capture_rate=sys_rate_used,
                    channels=sys_ch_used,
                    frames_per_buffer=frames_per_buffer,
                ),
                "mic": build_capture_device_info(
                    pa,
                    mic_device,
                    capture_rate=mic_rate_used,
                    channels=mic_ch_used,
                    frames_per_buffer=frames_per_buffer,
                ),
            }
            write_device_info(session_dir, device_info)
        except Exception:  # noqa: BLE001
            logger.exception("Failed to write device info.")

        sys_frames: List[bytes] = []
        mic_frames: List[bytes] = []
        sys_err: List[BaseException] = []
        mic_err: List[BaseException] = []
        sys_meta: dict = {}
        mic_meta: dict = {}

        stop_event = threading.Event()
        threads = [
            threading.Thread(
                target=_record_stream_to_list,
                args=(sys_stream, frames_per_buffer, stop_event, sys_frames, sys_err, sys_meta),
                name="sys-recorder",
                daemon=True,
            ),
            threading.Thread(
                target=_record_stream_to_list,
                args=(mic_stream, frames_per_buffer, stop_event, mic_frames, mic_err, mic_meta),
                name="mic-recorder",
                daemon=True,
            ),
        ]
        start_time = time.monotonic()
        for t in threads:
            t.start()

        time.sleep(float(duration))
        stop_event.set()

        # Stop streams to unblock any pending read
        with suppress_exc():
            sys_stream.stop_stream()
        with suppress_exc():
            mic_stream.stop_stream()

        for t in threads:
            t.join(timeout=2.0)

        if sys_err:
            raise RuntimeError(f"System capture error: {sys_err[0]!r}") from sys_err[0]
        if mic_err:
            raise RuntimeError(f"Mic capture error: {mic_err[0]!r}") from mic_err[0]

        if not sys_frames:
            logger.warning("No system audio frames captured.")
        if not mic_frames:
            logger.warning("No mic audio frames captured.")

        sys_first = sys_meta.get("first_time")
        mic_first = mic_meta.get("first_time")
        sys_offset = max(0.0, float(sys_first - start_time)) if sys_first is not None else 0.0
        mic_offset = max(0.0, float(mic_first - start_time)) if mic_first is not None else 0.0

        return (
            sys_frames,
            mic_frames,
            sys_rate_used,
            sys_ch_used,
            mic_rate_used,
            mic_ch_used,
            sys_offset,
            mic_offset,
        )

    finally:
        if sys_stream:
            with suppress_exc():
                sys_stream.close()
        if mic_stream:
            with suppress_exc():
                mic_stream.close()
        pa.terminate()


class suppress_exc:
    """Tiny context manager to suppress exceptions without importing contextlib in hot path."""

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AgendaSnap audio capture")
    parser.add_argument("--mode", choices=["stream", "once"], default="stream", help="stream: continuous / once: fixed duration")
    parser.add_argument("--duration", type=float, default=5.0, help="Record duration in seconds (once mode only).")
    parser.add_argument("--max-seconds", type=float, default=None, help="Optional stop time for stream mode.")
    parser.add_argument(
        "--session-dir",
        type=Path,
        default=None,
        help="Output directory. If omitted, a timestamped folder under config.audio.session_root is used.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).parent / "config" / "default.yaml",
        help="Path to config yaml.",
    )
    parser.add_argument("--no-wav", action="store_true", help="Disable audio recording (wav/flac).")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cfg = load_config(args.config)
    validate_config(cfg)

    audio_cfg = cfg["audio"]
    stt_cfg = cfg["stt"]
    minutes_cfg = cfg.get("minutes", {"update_interval_seconds": 60})
    resilience_cfg = cfg.get("resilience", {})
    recording_cfg = resolve_recording_config(audio_cfg)

    # Resolve API key priority for STT with backward compatibility.
    global_priority = normalize_api_key_priority(cfg.get("secrets", {}).get("priority"))
    stt_cfg["api_key_priority"] = normalize_api_key_priority(
        stt_cfg.get("api_key_priority") if "api_key_priority" in stt_cfg else stt_cfg.get("api_key_source"),
        fallback=global_priority,
    )
    meeting_cfg = cfg.get("meeting") if isinstance(cfg.get("meeting"), dict) else {}
    topic = str(meeting_cfg.get("topic") or "").strip()
    glossary = meeting_cfg.get("glossary") if isinstance(meeting_cfg, dict) else []
    base_transcription_prompt = str(stt_cfg.get("transcription_prompt") or "").strip()
    stt_cfg["base_transcription_prompt"] = base_transcription_prompt
    stt_cfg["meeting_topic"] = topic
    stt_cfg["meeting_glossary"] = glossary
    stt_cfg["transcription_prompt"] = build_transcription_prompt(
        base_transcription_prompt,
        topic,
        glossary,
    )
    minutes_context = build_minutes_context_prompt(topic, glossary)
    if minutes_context:
        llm_cfg = minutes_cfg.setdefault("llm", {})
        existing_prompt = str(llm_cfg.get("system_prompt") or "").strip()
        llm_cfg["system_prompt"] = "\n".join(
            part for part in [existing_prompt, minutes_context] if part
        )

    if args.no_wav:
        recording_cfg["system"] = False
        recording_cfg["mic"] = False

    session_root = Path(audio_cfg.get("session_root", "sessions"))
    if args.session_dir:
        session_dir = args.session_dir
        session_dir.mkdir(parents=True, exist_ok=True)
    else:
        session_dir = create_session(session_root)

    setup_session_logging(session_dir)
    init_session_artifacts(session_dir, cfg)
    logger.info("Session initialized: %s", session_dir)
    logger.info("Config path: %s", args.config)
    logger.info("Mode: %s", args.mode)

    try:
        if args.mode == "stream":
            logger.info("Starting continuous streaming mode...")
            asyncio.run(
                run_streaming(
                    audio_cfg,
                    stt_cfg,
                    minutes_cfg,
                    session_dir=session_dir,
                    recording_cfg=recording_cfg,
                    max_seconds=args.max_seconds,
                    resilience_cfg=resilience_cfg,
                )
            )
        else:
            (
                sys_frames,
                mic_frames,
                sys_rate_used,
                sys_ch_used,
                mic_rate_used,
                mic_ch_used,
                sys_offset,
                mic_offset,
            ) = capture_once(
                duration=float(args.duration),
                session_dir=session_dir,
                rate=int(audio_cfg["capture_rate"]),
                frames_per_buffer=int(audio_cfg["frames_per_buffer"]),
                channels_sys=int(audio_cfg["channels_system"]),
                channels_mic=int(audio_cfg["channels_mic"]),
                follow_default_output=bool(audio_cfg.get("system_device_follow_default", True)),
                select_system_device_each_time=bool(audio_cfg.get("system_device_prompt", False)),
            )
            logger.info("Capture offsets: sys=%.3fs mic=%.3fs", sys_offset, mic_offset)

            record_dir = session_dir / recording_cfg["directory"] if recording_cfg["directory"] else session_dir
            sample_width = 2  # PCM16 (paInt16)

            def _needs_rotation(rate: int, channels: int) -> bool:
                if recording_cfg["rotate_seconds"] and args.duration > recording_cfg["rotate_seconds"]:
                    return True
                if recording_cfg["rotate_bytes"]:
                    bytes_per_second = rate * channels * sample_width
                    total_bytes = bytes_per_second * args.duration
                    return total_bytes > recording_cfg["rotate_bytes"]
                return False

            if recording_cfg["system"]:
                sys_recorder = AudioRecorder(
                    base_dir=record_dir,
                    basename="system",
                    sample_rate=sys_rate_used,
                    channels=sys_ch_used,
                    sample_width=sample_width,
                    fmt=recording_cfg["format"],
                    rotate_seconds=recording_cfg["rotate_seconds"],
                    rotate_bytes=recording_cfg["rotate_bytes"],
                    always_index=_needs_rotation(sys_rate_used, sys_ch_used),
                )
                sys_recorder.start()
                for frame in sys_frames:
                    sys_recorder.write(frame)
                sys_recorder.close()

            if recording_cfg["mic"]:
                mic_recorder = AudioRecorder(
                    base_dir=record_dir,
                    basename="mic",
                    sample_rate=mic_rate_used,
                    channels=mic_ch_used,
                    sample_width=sample_width,
                    fmt=recording_cfg["format"],
                    rotate_seconds=recording_cfg["rotate_seconds"],
                    rotate_bytes=recording_cfg["rotate_bytes"],
                    always_index=_needs_rotation(mic_rate_used, mic_ch_used),
                )
                mic_recorder.start()
                for frame in mic_frames:
                    mic_recorder.write(frame)
                mic_recorder.close()

            sys_threshold, sys_start, sys_stop, _sys_noise = resolve_source_thresholds(
                frames=sys_frames,
                capture_rate=sys_rate_used,
                capture_channels=sys_ch_used,
                target_rate=int(audio_cfg["target_rate"]),
                source="sys",
                audio_cfg=audio_cfg,
                log=logger,
            )
            mic_threshold, mic_start, mic_stop, _mic_noise = resolve_source_thresholds(
                frames=mic_frames,
                capture_rate=mic_rate_used,
                capture_channels=mic_ch_used,
                target_rate=int(audio_cfg["target_rate"]),
                source="mic",
                audio_cfg=audio_cfg,
                log=logger,
            )

            turns_by_source = {
                "sys": build_turns_from_frames(
                    frames=sys_frames,
                    capture_rate=sys_rate_used,
                    capture_channels=sys_ch_used,
                    target_rate=int(audio_cfg["target_rate"]),
                    source="sys",
                    energy_threshold=float(sys_threshold),
                    max_turn_seconds=float(stt_cfg["segment_max_seconds"]),
                    max_gap_ms=int(stt_cfg["segment_gap_ms"]),
                    start_threshold=sys_start,
                    stop_threshold=sys_stop,
                    t0_offset=sys_offset,
                ),
                "mic": build_turns_from_frames(
                    frames=mic_frames,
                    capture_rate=mic_rate_used,
                    capture_channels=mic_ch_used,
                    target_rate=int(audio_cfg["target_rate"]),
                    source="mic",
                    energy_threshold=float(mic_threshold),
                    max_turn_seconds=float(stt_cfg["segment_max_seconds"]),
                    max_gap_ms=int(stt_cfg["segment_gap_ms"]),
                    start_threshold=mic_start,
                    stop_threshold=mic_stop,
                    t0_offset=mic_offset,
                ),
            }

            total_turns = sum(len(v) for v in turns_by_source.values())
            logger.info("Total STT turns: %d (sys=%d, mic=%d)", total_turns, len(turns_by_source["sys"]), len(turns_by_source["mic"]))

            if stt_cfg.get("enable", False):
                asyncio.run(
                    run_stt_once(
                        stt_cfg=stt_cfg,
                        turns_by_source=turns_by_source,
                        session_dir=session_dir,
                        minutes_cfg=minutes_cfg,
                    )
                )
            else:
                logger.info("STT is disabled; skipping transcription.")
                # still create empty minutes for consistency
                save_minutes_json_atomic(session_dir / "minutes.json", MinutesDocument())
                write_text_atomic(session_dir / "minutes.md", "# Minutes\n\n_STT disabled_", encoding="utf-8")

    except Exception as exc:  # noqa: BLE001
        logger.exception("Run failed: %s", exc)
        raise SystemExit(1) from exc
    finally:
        close_session_logging(session_dir)


if __name__ == "__main__":
    main()
