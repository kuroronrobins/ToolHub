"""Mock UI for AgendaSnap (visual-only)."""
from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import math
import queue
import subprocess
import sys
import threading
import time
from array import array
from dataclasses import dataclass
from pathlib import Path

import flet as ft
import flet.canvas as cv
import pyaudiowpatch as pyaudio
import yaml

from agendasnap.audio.recording import resolve_recording_config
from agendasnap.audio.capture_mic import open_mic_stream
from agendasnap.audio.capture_wasapi import open_loopback_stream
from agendasnap.config.ai_providers import normalize_api_key_priority
from agendasnap.config.glossary import build_minutes_context_prompt, build_transcription_prompt
from agendasnap.config.loader import load_config
from agendasnap.config.validate import validate_config
from agendasnap.audio.levels import level_state_label
from agendasnap.pipeline.streaming import InputSourceUpdate, run_streaming
from agendasnap.store.session_fs import (
    close_session_logging,
    create_session,
    init_session_artifacts,
    setup_session_logging,
)
from agendasnap.stt.errors import stt_error_safe_category
from agendasnap.ui.device_picker import (
    DevicePickerDialog,
    build_device_choices,
    device_tooltip,
    short_device_label,
)
TITLE_TEXT = "AdgendaSnap"
SCALE = 0.41
BASE_WINDOW_WIDTH = 980
BASE_WINDOW_HEIGHT = 980


def s(value: float) -> int:
    return int(round(value * SCALE))


PLAY_SIZE = s(220)
WIFI_SIZE = s(150)
SIDE_BLOCK_WIDTH = s(280)
DEVICE_LABEL_WIDTH = s(240)
DEVICE_TEXT_WIDTH = s(210)
WIFI_SHIFT_RATIO = 0.5
WIFI_OUTER_RADIUS_RATIO = 0.42
WIFI_LABEL_PULL = 2.2
DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "default.yaml"

COLORS = {
    "bg_top": "#FFFFFF",
    "bg_bottom": "#F7F7F7",
    "play_red": "#C40000",
    "mic_blue": "#1F9BD7",
    "sys_orange": "#F2A521",
    "text": "#111111",
    "muted": "#666666",
    "footer_bg": "#EFEFEF",
    "footer_border": "#E0E0E0",
    "bar_border": "#C9C9C9",
}


def _with_alpha(color: str, alpha: float) -> str:
    value = color.lstrip("#")
    if len(value) != 6:
        return color
    alpha = max(0.0, min(1.0, alpha))
    a = int(alpha * 255)
    return f"#{a:02X}{value}"


def _hex_to_rgb(color: str) -> tuple[int, int, int]:
    value = color.lstrip("#")
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


def _blend(c1: str, c2: str, t: float) -> str:
    t = max(0.0, min(1.0, t))
    r1, g1, b1 = _hex_to_rgb(c1)
    r2, g2, b2 = _hex_to_rgb(c2)
    r = int(r1 + (r2 - r1) * t)
    g = int(g1 + (g2 - g1) * t)
    b = int(b1 + (b2 - b1) * t)
    return f"#{r:02X}{g:02X}{b:02X}"


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


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


def _format_stt_issue_summary(payload: dict) -> str:
    audio = payload.get("audio") if isinstance(payload, dict) else {}
    if not isinstance(audio, dict):
        audio = {}
    stt = payload.get("stt") if isinstance(payload, dict) else {}
    if not isinstance(stt, dict):
        stt = {}
    states = stt.get("state") if isinstance(stt.get("state"), dict) else {}
    last_errors = stt.get("last_errors") if isinstance(stt.get("last_errors"), dict) else {}

    parts: list[str] = []
    for source, label in (("sys", "SYSTEM"), ("mic", "MIC")):
        source_audio = audio.get(source) if isinstance(audio.get(source), dict) else {}
        classification = str(source_audio.get("stt_error_classification") or "").strip().lower()
        state = str(states.get(source) or "").strip().lower()
        if classification != "permanent" and state != "permanent_error":
            continue
        category = (
            str(source_audio.get("stt_error_category") or "").strip()
            or stt_error_safe_category(last_errors.get(source) or source_audio.get("error"))
        )
        parts.append(f"{label}: {category or 'permanent'}")
    return ", ".join(parts)


@dataclass(frozen=True)
class InputSelection:
    source: str
    value: str
    enabled: bool
    device_index: int | None
    follow_default: bool | None


def normalize_input_kind(kind: object) -> str:
    source = str(kind or "").strip().lower()
    if source == "system":
        source = "sys"
    if source not in {"mic", "sys"}:
        raise ValueError(f"unknown input source: {kind!r}")
    return source


def _normalize_input_value(value: object) -> tuple[str, int | None]:
    if isinstance(value, bool):
        raise ValueError(f"invalid input device value: {value!r}")
    if isinstance(value, int):
        if value < 0:
            raise ValueError(f"invalid input device index: {value}")
        return str(value), value
    text = str(value).strip().lower()
    if text in {"off", "auto", "default"}:
        return ("auto" if text == "default" else text), None
    try:
        index = int(text)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid input device value: {value!r}") from exc
    if index < 0:
        raise ValueError(f"invalid input device index: {index}")
    return str(index), index


def _validate_device_index(index: int | None, options: list[tuple[int, str]] | None) -> None:
    if index is None or options is None:
        return
    valid_indexes = {int(item_idx) for item_idx, _name in options}
    if index not in valid_indexes:
        raise ValueError(f"device index {index} is not available")


def resolve_input_selection(
    kind: object,
    value: object,
    *,
    available_options: list[tuple[int, str]] | None = None,
) -> InputSelection:
    source = normalize_input_kind(kind)
    normalized_value, device_index = _normalize_input_value(value)
    _validate_device_index(device_index, available_options)

    if source == "mic":
        if normalized_value == "off":
            return InputSelection("mic", "off", False, None, None)
        return InputSelection("mic", normalized_value, True, device_index, None)

    if normalized_value == "off":
        return InputSelection("sys", "off", False, None, True)
    if device_index is None:
        return InputSelection("sys", "auto", True, None, True)
    return InputSelection("sys", normalized_value, True, device_index, False)


def apply_input_selection_to_audio_config(
    audio_cfg: dict,
    kind: object,
    value: object,
    *,
    available_options: list[tuple[int, str]] | None = None,
) -> InputSourceUpdate:
    selection = resolve_input_selection(kind, value, available_options=available_options)

    if selection.source == "mic":
        audio_cfg["enable_mic"] = selection.enabled
        audio_cfg.pop("mic_device_index", None)
        if selection.enabled and selection.device_index is not None:
            audio_cfg["mic_device_index"] = selection.device_index
        return InputSourceUpdate(
            source="mic",
            enabled=selection.enabled,
            device_index=selection.device_index,
            follow_default=selection.follow_default,
        )

    audio_cfg["enable_system"] = selection.enabled
    audio_cfg["system_device_follow_default"] = True if not selection.enabled else bool(selection.follow_default)
    audio_cfg.pop("system_device_index", None)
    if selection.enabled and not selection.follow_default and selection.device_index is not None:
        audio_cfg["system_device_index"] = selection.device_index
    return InputSourceUpdate(
        source="sys",
        enabled=selection.enabled,
        device_index=selection.device_index,
        follow_default=selection.follow_default,
    )


def select_input_device(
    *,
    config_path: Path,
    controller: object | None,
    kind: object,
    value: object,
    running: bool,
    available_options: list[tuple[int, str]] | None = None,
) -> InputSourceUpdate:
    cfg = _load_config_yaml(config_path)
    audio_cfg = cfg.get("audio")
    if not isinstance(audio_cfg, dict):
        audio_cfg = {}
        cfg["audio"] = audio_cfg

    update = apply_input_selection_to_audio_config(
        audio_cfg,
        kind,
        value,
        available_options=available_options,
    )
    _save_config_yaml(config_path, cfg)

    if running and controller is not None:
        controller.apply_input_change(
            source=update.source,
            enabled=update.enabled,
            device_index=update.device_index,
            follow_default=update.follow_default,
        )
    return update


def input_selection_message(update: InputSourceUpdate, *, running: bool) -> str:
    label = "MIC" if normalize_input_kind(update.source) == "mic" else "SYSTEM"
    if not update.enabled:
        action = "OFFにしました"
    elif update.device_index is None:
        action = "Default / Autoにしました"
    else:
        action = f"index {update.device_index}にしました"
    suffix = "（セッションは継続）" if running else "（次回開始時に反映）"
    return f"{label}入力を{action}{suffix}"


def _rms_from_bytes(data: bytes) -> float:
    if not data:
        return 0.0
    samples = array("h")
    samples.frombytes(data)
    if sys.byteorder == "big":
        samples.byteswap()
    if not samples:
        return 0.0
    total = 0.0
    for sample in samples:
        total += sample * sample
    return math.sqrt(total / len(samples))


class StreamController:
    def __init__(self, config_path: Path):
        self.config_path = config_path
        self.stop_event = threading.Event()
        self.control_queue: queue.Queue[InputSourceUpdate] = queue.Queue()
        self.thread: threading.Thread | None = None
        self.session_dir: Path | None = None
        self.running = False
        self.last_error: str | None = None
        self._levels: dict[str, dict] = {}
        self._lock = threading.Lock()
        self.fast_shutdown_event = threading.Event()

    def _store_level(self, level) -> None:
        payload = level.to_dict() if hasattr(level, "to_dict") else dict(level)
        source = str(payload.get("source") or "")
        if source not in {"sys", "mic"}:
            return
        with self._lock:
            self._levels[source] = payload

    def latest_levels(self) -> dict[str, dict]:
        with self._lock:
            return {key: dict(value) for key, value in self._levels.items()}

    def apply_input_change(
        self,
        *,
        source: str,
        enabled: bool,
        device_index: int | None = None,
        follow_default: bool | None = None,
    ) -> None:
        update = InputSourceUpdate(
            source=source,
            enabled=enabled,
            device_index=device_index,
            follow_default=follow_default,
        )
        with self._lock:
            if not self.running:
                return
        self.control_queue.put(update)

    def start(self) -> Path:
        with self._lock:
            if self.running:
                raise RuntimeError("Streaming is already running.")

            cfg = load_config(self.config_path)
            validate_config(cfg)

            audio_cfg = cfg["audio"]
            stt_cfg = cfg["stt"]
            minutes_cfg = cfg.get("minutes", {"update_interval_seconds": 60})
            resilience_cfg = cfg.get("resilience", {})
            recording_cfg = resolve_recording_config(audio_cfg)

            global_priority = normalize_api_key_priority(cfg.get("secrets", {}).get("priority"))
            stt_cfg["api_key_priority"] = normalize_api_key_priority(
                stt_cfg.get("api_key_priority")
                if "api_key_priority" in stt_cfg
                else stt_cfg.get("api_key_source"),
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

            session_root = Path(audio_cfg.get("session_root", "sessions"))
            session_dir = create_session(session_root)
            setup_session_logging(session_dir)
            init_session_artifacts(session_dir, cfg)

            self.stop_event.clear()
            self.fast_shutdown_event.clear()
            while True:
                try:
                    self.control_queue.get_nowait()
                except queue.Empty:
                    break
            self.session_dir = session_dir
            self.last_error = None
            self._levels = {}

            def _runner() -> None:
                try:
                    asyncio.run(
                        run_streaming(
                            audio_cfg,
                            stt_cfg,
                            minutes_cfg,
                            session_dir=session_dir,
                            recording_cfg=recording_cfg,
                            resilience_cfg=resilience_cfg,
                            stop_event=self.stop_event,
                            control_queue=self.control_queue,
                            level_callback=self._store_level,
                            fast_shutdown_event=self.fast_shutdown_event,
                        )
                    )
                except Exception as exc:  # noqa: BLE001
                    self.last_error = str(exc)
                finally:
                    close_session_logging(session_dir)
                    with self._lock:
                        self.running = False

            self.thread = threading.Thread(target=_runner, name="streaming-worker", daemon=True)
            self.running = True
            self.thread.start()

            return session_dir

    def request_stop(self, *, finalize: bool = True) -> None:
        with self._lock:
            thread = self.thread
            active = self.running or (thread is not None and thread.is_alive())
            if not active:
                return
            if not finalize:
                self.fast_shutdown_event.set()
            self.stop_event.set()

    def join(self, timeout: float | None = None) -> bool:
        with self._lock:
            thread = self.thread
            session_dir = self.session_dir
        if thread is not None and thread.is_alive() and threading.current_thread() is not thread:
            thread.join(timeout=timeout)
        finished = thread is None or not thread.is_alive()
        if finished and session_dir is not None:
            close_session_logging(session_dir)
        return finished

    def stop(self, *, wait: bool = False, timeout: float | None = None, finalize: bool = True) -> bool:
        self.request_stop(finalize=finalize)
        if wait:
            return self.join(timeout=timeout)
        with self._lock:
            thread = self.thread
        return thread is None or not thread.is_alive()

    def close_session_log(self) -> None:
        with self._lock:
            session_dir = self.session_dir
        if session_dir is not None:
            close_session_logging(session_dir)


def _wifi_visual_center_offset(size: int, side: str) -> float:
    shift = size * WIFI_SHIFT_RATIO if side == "left" else -size * WIFI_SHIFT_RATIO
    cx = size / 2 + shift
    outer_radius = size * WIFI_OUTER_RADIUS_RATIO
    visible_min = max(0.0, cx - outer_radius)
    visible_max = min(size, cx + outer_radius)
    visual_center = (visible_min + visible_max) / 2
    return visual_center - size / 2


def _load_config_yaml(path: Path) -> dict:
    cfg = load_config(path)
    if not isinstance(cfg, dict):
        raise ValueError("Config root must be a mapping.")
    return cfg


def _save_config_yaml(path: Path, cfg: dict) -> None:
    path.write_text(
        yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def _load_delay_thresholds(path: Path) -> dict:
    cfg = _load_config_yaml(path)
    resilience_cfg = cfg.get("resilience", {}) if isinstance(cfg, dict) else {}
    delay_cfg = resilience_cfg.get("delay_mode", {}) if isinstance(resilience_cfg, dict) else {}
    return {
        "queue_ratio": float(delay_cfg.get("queue_ratio", 0.7)),
        "delay_seconds": float(delay_cfg.get("delay_seconds", 10.0)),
        "drop_rate": float(delay_cfg.get("drop_rate", 0.5)),
    }


class GainMonitor:
    def __init__(self, *, config_path: Path, on_update) -> None:
        self.config_path = config_path
        self.on_update = on_update
        self.stop_event = threading.Event()
        self.restart_event = threading.Event()
        self.thread: threading.Thread | None = None

    def start(self) -> None:
        if self.thread and self.thread.is_alive():
            return
        self.stop_event.clear()
        self.restart_event.clear()
        self.thread = threading.Thread(target=self._run, name="gain-monitor", daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        self.restart_event.set()
        if self.thread and threading.current_thread() is not self.thread:
            self.thread.join(timeout=1.0)
            if not self.thread.is_alive():
                self.thread = None

    def request_restart(self) -> None:
        self.restart_event.set()

    def _run(self) -> None:
        while not self.stop_event.is_set():
            cfg = _load_config_yaml(self.config_path)
            audio_cfg = cfg.get("audio", {})
            enable_sys = _coerce_bool(audio_cfg.get("enable_system", True))
            enable_mic = _coerce_bool(audio_cfg.get("enable_mic", True))
            sys_rms = mic_rms = 0.0
            sys_thr = float(audio_cfg.get("energy_threshold_sys", 0.0) or 0.0)
            mic_thr = float(audio_cfg.get("energy_threshold_mic", 0.0) or 0.0)

            if not enable_sys and not enable_mic:
                self.on_update(
                    mic_rms=0.0,
                    mic_thr=mic_thr,
                    mic_enabled=False,
                    sys_rms=0.0,
                    sys_thr=sys_thr,
                    sys_enabled=False,
                )
                time.sleep(0.5)
                continue

            pa = pyaudio.PyAudio()
            sys_stream = mic_stream = None
            frames_per_buffer = int(audio_cfg.get("frames_per_buffer", 1024))
            capture_rate = int(audio_cfg.get("capture_rate", 48000))
            ch_sys = int(audio_cfg.get("channels_system", 2))
            ch_mic = int(audio_cfg.get("channels_mic", 1))
            try:
                if enable_sys:
                    sys_stream, _sys_dev, _sys_rate, _sys_ch = open_loopback_stream(
                        pa,
                        capture_rate,
                        ch_sys,
                        frames_per_buffer,
                        follow_default=bool(audio_cfg.get("system_device_follow_default", True)),
                        select_each_time=bool(audio_cfg.get("system_device_prompt", False)),
                        device_index=audio_cfg.get("system_device_index"),
                    )
                if enable_mic:
                    mic_stream, _mic_dev, _mic_rate, _mic_ch = open_mic_stream(
                        pa,
                        capture_rate,
                        ch_mic,
                        frames_per_buffer,
                        device_index=audio_cfg.get("mic_device_index"),
                    )

                while not self.stop_event.is_set():
                    if self.restart_event.is_set():
                        self.restart_event.clear()
                        break
                    if enable_sys and sys_stream is not None:
                        data = sys_stream.read(frames_per_buffer, exception_on_overflow=False)
                        sys_rms = float(_rms_from_bytes(data))
                    else:
                        sys_rms = 0.0
                    if enable_mic and mic_stream is not None:
                        data = mic_stream.read(frames_per_buffer, exception_on_overflow=False)
                        mic_rms = float(_rms_from_bytes(data))
                    else:
                        mic_rms = 0.0

                    self.on_update(
                        mic_rms=mic_rms,
                        mic_thr=mic_thr,
                        mic_enabled=enable_mic,
                        sys_rms=sys_rms,
                        sys_thr=sys_thr,
                        sys_enabled=enable_sys,
                    )
                    time.sleep(0.2)
            except Exception as exc:  # noqa: BLE001
                logging.getLogger("agendasnap.ui").warning("Gain monitor failed: %s", exc)
                time.sleep(0.5)
            finally:
                with contextlib.suppress(Exception):
                    if sys_stream:
                        sys_stream.close()
                with contextlib.suppress(Exception):
                    if mic_stream:
                        mic_stream.close()
                pa.terminate()


def _list_devices() -> tuple[list[tuple[int, str]], list[tuple[int, str]]]:
    pa = pyaudio.PyAudio()
    try:
        loopbacks = []
        try:
            for dev in pa.get_loopback_device_info_generator():
                loopbacks.append((int(dev.get("index", -1)), str(dev.get("name", ""))))
        except Exception:
            loopbacks = []

        mics = []
        for i in range(pa.get_device_count()):
            info = pa.get_device_info_by_index(i)
            if int(info.get("maxInputChannels", 0) or 0) > 0:
                mics.append((int(info.get("index", -1)), str(info.get("name", ""))))
    finally:
        pa.terminate()
    return loopbacks, mics


def _wifi_icon(
    color: str,
    side: str,
    *,
    size: int = 180,
    bg: str = "#FFFFFF",
    active_rings: int = 3,
) -> ft.Container:
    if side not in {"left", "right"}:
        raise ValueError("side must be 'left' or 'right'")

    sweep = math.radians(165)
    start = math.pi - sweep / 2 if side == "left" else -sweep / 2
    shift = size * WIFI_SHIFT_RATIO if side == "left" else -size * WIFI_SHIFT_RATIO
    cx = size / 2 + shift
    cy = size / 2

    ring_widths = [size * 0.06, size * 0.045, size * 0.032]
    radii = [size * WIFI_OUTER_RADIUS_RATIO, size * 0.31, size * 0.22]
    shapes: list[cv.Shape] = []

    beam = ft.Paint(
        color=_with_alpha(color, 0.08),
        style=ft.PaintingStyle.FILL,
    )
    shapes.append(
        cv.Arc(
            x=cx - size * 0.36,
            y=cy - size * 0.36,
            width=size * 0.72,
            height=size * 0.72,
            start_angle=start,
            sweep_angle=sweep,
            use_center=True,
            paint=beam,
        )
    )

    active_rings = max(1, min(3, int(active_rings)))
    active_set = set(range(3 - active_rings, 3))  # inner-first
    for idx, radius in enumerate(radii):
        stroke = ring_widths[min(idx, len(ring_widths) - 1)]
        active = idx in active_set
        intensity = 1.0 if active else 0.22
        base = _blend(color, "#FFFFFF", 0.0 if active else 0.8)
        shadow_paint = ft.Paint(
            color=_with_alpha(_blend(base, "#000000", 0.35), 0.18 * intensity),
            stroke_width=stroke + size * (0.01 if active else 0.006),
            style=ft.PaintingStyle.STROKE,
            stroke_cap=ft.StrokeCap.ROUND,
        )
        highlight_paint = ft.Paint(
            color=_with_alpha(_blend(base, "#FFFFFF", 0.35), (0.75 - idx * 0.12) * intensity),
            stroke_width=max(1.0, stroke * (0.6 if active else 0.4)),
            style=ft.PaintingStyle.STROKE,
            stroke_cap=ft.StrokeCap.ROUND,
        )
        main_paint = ft.Paint(
            color=_with_alpha(base, (0.98 - idx * 0.16) * intensity),
            stroke_width=stroke,
            style=ft.PaintingStyle.STROKE,
            stroke_cap=ft.StrokeCap.ROUND,
        )
        shapes.append(
            cv.Arc(
                x=cx - radius,
                y=cy - radius,
                width=radius * 2,
                height=radius * 2,
                start_angle=start,
                sweep_angle=sweep,
                use_center=False,
                paint=shadow_paint,
            )
        )
        shapes.append(
            cv.Arc(
                x=cx - radius,
                y=cy - radius,
                width=radius * 2,
                height=radius * 2,
                start_angle=start,
                sweep_angle=sweep,
                use_center=False,
                paint=main_paint,
            )
        )
        shapes.append(
            cv.Arc(
                x=cx - radius,
                y=cy - radius,
                width=radius * 2,
                height=radius * 2,
                start_angle=start,
                sweep_angle=sweep,
                use_center=False,
                paint=highlight_paint,
            )
        )

    core_intensity = 0.85 if active_rings >= 2 else 0.45
    core = cv.Circle(
        x=cx,
        y=cy,
        radius=size * 0.032,
        paint=ft.Paint(color=_with_alpha(color, core_intensity)),
    )
    shapes.append(core)

    arcs = cv.Canvas(width=size, height=size, shapes=shapes)

    tint_light = _blend(color, "#FFFFFF", 0.8)
    tint_mid = _blend(color, "#FFFFFF", 0.92)
    outer_radius = radii[0]
    visible_min = max(0.0, cx - outer_radius)
    visible_max = min(size, cx + outer_radius)
    visual_center_x = (visible_min + visible_max) / 2
    center_x_norm = _clamp((visual_center_x * 2 / size) - 1, -1.0, 1.0)
    disc_center = ft.alignment.Alignment(center_x_norm, 0)
    disc = ft.Container(
        width=size,
        height=size,
        border_radius=size / 2,
        gradient=ft.RadialGradient(
            colors=[_with_alpha(tint_light, 0.6), _with_alpha(tint_mid, 0.16), bg],
            stops=[0.0, 0.62, 1.0],
            center=disc_center,
            radius=0.9,
        ),
        border=ft.border.all(1, _with_alpha(color, 0.1)),
        shadow=ft.BoxShadow(
            blur_radius=size * 0.18,
            spread_radius=size * 0.01,
            color=_with_alpha(color, 0.14),
            offset=ft.Offset(0, size * 0.04),
        ),
    )
    inner_glow = ft.Container(
        width=size,
        height=size,
        border_radius=size / 2,
        gradient=ft.RadialGradient(
            colors=[_with_alpha(color, 0.24), _with_alpha(color, 0.07), "#00FFFFFF"],
            stops=[0.0, 0.58, 1.0],
            center=disc_center,
            radius=0.62,
        ),
    )

    return ft.Container(
        width=size,
        height=size,
        content=ft.Stack(
            width=size,
            height=size,
            alignment=ft.alignment.center,
            controls=[disc, inner_glow, arcs],
        ),
    )


def _task_load_bar(width: int = 520, height: int = 18) -> tuple[ft.Container, list[ft.Container], list[str]]:
    colors = ["#5CBF4A", "#7AD44A", "#A8E05F", "#E9D65C", "#F0B54B", "#D5573B"]
    segments = []
    for idx, col in enumerate(colors):
        border = ft.border.only(
            right=ft.border.BorderSide(max(1, int(height * 0.06)), "#00000022")
            if idx < len(colors) - 1
            else None
        )
        segments.append(ft.Container(expand=1, bgcolor=col, border=border))

    bar = ft.Container(
        width=width,
        height=height,
        border_radius=height / 2,
        border=ft.border.all(max(1, int(height * 0.06)), COLORS["bar_border"]),
        clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
        content=ft.Row(expand=True, spacing=0, controls=segments),
    )
    return bar, segments, colors


def main(page: ft.Page) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        force=True,
    )
    ui_logger = logging.getLogger("agendasnap.ui")
    page.title = "AgendaSnap UI"
    page.bgcolor = COLORS["bg_top"]
    page.padding = 0
    page.scroll = ft.ScrollMode.AUTO
    page.theme = ft.Theme(font_family="Yu Gothic UI")
    page.window.width = s(BASE_WINDOW_WIDTH)
    page.window.height = s(BASE_WINDOW_HEIGHT)
    page.window.min_width = s(BASE_WINDOW_WIDTH)
    page.window.min_height = s(BASE_WINDOW_HEIGHT)
    page.window.max_width = s(BASE_WINDOW_WIDTH)
    page.window.max_height = s(BASE_WINDOW_HEIGHT)
    page.window.resizable = False
    page.window.title_bar_hidden = True
    page.window.title_bar_buttons_hidden = True

    def show_placeholder(title: str) -> None:
        page.snack_bar = ft.SnackBar(
            ft.Text(title, color=COLORS["text"]),
            bgcolor="#FFFFFF",
        )
        page.snack_bar.open = True
        page.update()

    controller = StreamController(DEFAULT_CONFIG_PATH)
    status_stop = threading.Event()
    delay_thresholds = _load_delay_thresholds(DEFAULT_CONFIG_PATH)

    play_icon = ft.Icon(ft.Icons.PLAY_ARROW, size=s(120), color=ft.Colors.WHITE)
    stop_icon = ft.Icon(ft.Icons.STOP, size=s(110), color=ft.Colors.WHITE)
    session_text = ft.Text(
        "Session: -",
        size=s(34),
        color=COLORS["muted"],
        max_lines=1,
        overflow=ft.TextOverflow.ELLIPSIS,
    )
    status_text = ft.Text(
        "Status: idle",
        size=s(34),
        color=COLORS["muted"],
        max_lines=1,
        overflow=ft.TextOverflow.ELLIPSIS,
    )
    minutes_text = ft.Text(
        "Minutes: -",
        size=s(34),
        color=COLORS["muted"],
        max_lines=1,
        overflow=ft.TextOverflow.ELLIPSIS,
    )
    mic_level_text = ft.Text(
        "RMS: - / THR: -",
        size=s(22),
        color=COLORS["muted"],
        max_lines=1,
        no_wrap=True,
        overflow=ft.TextOverflow.ELLIPSIS,
        text_align=ft.TextAlign.CENTER,
        width=DEVICE_LABEL_WIDTH,
    )
    sys_level_text = ft.Text(
        "RMS: - / THR: -",
        size=s(22),
        color=COLORS["muted"],
        max_lines=1,
        no_wrap=True,
        overflow=ft.TextOverflow.ELLIPSIS,
        text_align=ft.TextAlign.CENTER,
        width=DEVICE_LABEL_WIDTH,
    )
    switcher = ft.AnimatedSwitcher(
        content=play_icon,
        transition=ft.AnimatedSwitcherTransition.FADE,
        duration=250,
    )
    running = {"value": False}
    finalizing = {"since": None}
    ui_locked = {"value": False}
    finalize_active_states = {
        "running",
        "provisional_finalize",
        "catch_up_prepare",
        "catch_up_stt",
        "catch_up_finalize",
    }
    gain_monitor: GainMonitor | None = None

    def _apply_play_state() -> None:
        if ui_locked["value"]:
            play_button.bgcolor = "#BDBDBD"
            switcher.content = play_icon
            play_button.disabled = True
            return
        play_button.disabled = False
        play_button.bgcolor = COLORS["play_red"]
        switcher.content = stop_icon if running["value"] else play_icon

    def toggle_play(e: ft.ControlEvent) -> None:
        if ui_locked["value"]:
            show_placeholder("議事録の最終処理中のため操作できません")
            return
        if not running["value"]:
            if gain_monitor is not None:
                gain_monitor.stop()
            try:
                session_dir = controller.start()
            except Exception as exc:  # noqa: BLE001
                show_placeholder(f"Start failed: {exc}")
                if gain_monitor is not None and not closing.is_set():
                    gain_monitor.start()
                return
            running["value"] = True
            ui_locked["value"] = False
            session_text.value = f"Session: {session_dir.name}"
            status_text.value = "Status: running"
            minutes_text.value = "Minutes: live"
            finalizing["since"] = None
            _apply_play_state()
            show_placeholder(f"Recording started: {session_dir.name}")
            page.update()
            return

        controller.stop()
        running["value"] = False
        ui_locked["value"] = True
        status_text.value = "Status: stopped"
        minutes_text.value = "Minutes: finalizing"
        finalizing["since"] = time.time()
        _apply_play_state()
        show_placeholder("Recording stopped")
        page.update()
        if gain_monitor is not None:
            def _restart_gain_monitor() -> None:
                if not closing.is_set() and not status_stop.is_set():
                    gain_monitor.start()

            threading.Timer(0.8, _restart_gain_monitor).start()

    play_button = ft.Container(
        width=PLAY_SIZE,
        height=PLAY_SIZE,
        bgcolor=COLORS["play_red"],
        border_radius=PLAY_SIZE / 2,
        alignment=ft.alignment.center,
        content=switcher,
        on_click=toggle_play,
        shadow=ft.BoxShadow(
            blur_radius=s(18),
            color="#00000033",
            offset=ft.Offset(0, s(6)),
        ),
    )

    def _get_default_device_names() -> tuple[str | None, str | None]:
        pa = pyaudio.PyAudio()
        try:
            mic_name = None
            sys_name = None
            try:
                mic_name = str(pa.get_default_input_device_info().get("name", "")).strip() or None
            except Exception:
                pass
            try:
                sys_name = str(pa.get_default_output_device_info().get("name", "")).strip() or None
            except Exception:
                pass
        finally:
            pa.terminate()
        return mic_name, sys_name

    device_cache: dict[str, object] = {"mic_options": [], "sys_options": [], "mic_default": None, "sys_default": None}

    mic_label_text = ft.Text(
        "",
        size=s(34),
        color=COLORS["text"],
        max_lines=1,
        overflow=ft.TextOverflow.ELLIPSIS,
        no_wrap=True,
        text_align=ft.TextAlign.CENTER,
        width=DEVICE_TEXT_WIDTH,
    )
    sys_label_text = ft.Text(
        "",
        size=s(34),
        color=COLORS["text"],
        max_lines=1,
        overflow=ft.TextOverflow.ELLIPSIS,
        no_wrap=True,
        text_align=ft.TextAlign.CENTER,
        width=DEVICE_TEXT_WIDTH,
    )

    menu_width = DEVICE_LABEL_WIDTH + s(60)
    menu_height = s(220)
    menu_item_height = s(40)

    mic_menu_open = {"value": False}
    sys_menu_open = {"value": False}

    mic_menu_list = ft.ListView(
        height=menu_height,
        spacing=0,
        padding=0,
    )
    sys_menu_list = ft.ListView(
        height=menu_height,
        spacing=0,
        padding=0,
    )

    mic_menu_container = ft.Container(
        width=menu_width,
        bgcolor="#FFFFFF",
        border=ft.border.all(1, "#D1D5DB"),
        border_radius=10,
        padding=ft.padding.symmetric(vertical=4),
        shadow=ft.BoxShadow(blur_radius=s(16), color="#00000022", offset=ft.Offset(0, s(6))),
        visible=False,
        content=mic_menu_list,
    )
    sys_menu_container = ft.Container(
        width=menu_width,
        bgcolor="#FFFFFF",
        border=ft.border.all(1, "#D1D5DB"),
        border_radius=10,
        padding=ft.padding.symmetric(vertical=4),
        shadow=ft.BoxShadow(blur_radius=s(16), color="#00000022", offset=ft.Offset(0, s(6))),
        visible=False,
        content=sys_menu_list,
    )

    def _menu_overlay_positions() -> tuple[float, float, float]:
        window_w = s(BASE_WINDOW_WIDTH)
        row_w = SIDE_BLOCK_WIDTH * 2 + PLAY_SIZE + s(24) * 2
        left = (window_w - row_w) / 2
        mic_center = left + SIDE_BLOCK_WIDTH / 2
        sys_center = left + SIDE_BLOCK_WIDTH + s(24) + PLAY_SIZE + s(24) + SIDE_BLOCK_WIDTH / 2
        menu_left_mic = mic_center - menu_width / 2
        menu_left_sys = sys_center - menu_width / 2
        menu_top = (
            s(10)
            + s(96)
            + s(2)
            + s(36)
            + PLAY_SIZE
            + s(1)
            + s(44)
            + s(6)
            + s(46)
        )
        return menu_left_mic, menu_left_sys, menu_top

    menu_left_mic, menu_left_sys, menu_top = _menu_overlay_positions()

    mic_menu_overlay = ft.Container(
        left=menu_left_mic,
        top=menu_top,
        content=mic_menu_container,
        visible=False,
    )
    sys_menu_overlay = ft.Container(
        left=menu_left_sys,
        top=menu_top,
        content=sys_menu_container,
        visible=False,
    )

    menu_backdrop = ft.Container(
        expand=True,
        bgcolor="#00000000",
        visible=False,
        on_click=lambda _e: _close_menus(),
    )

    def _reload_device_cache() -> None:
        loopback_options, mic_options = _list_devices()
        mic_default, sys_default = _get_default_device_names()
        device_cache["mic_options"] = mic_options
        device_cache["sys_options"] = loopback_options
        device_cache["mic_default"] = mic_default
        device_cache["sys_default"] = sys_default

    def _selected_value(kind: str) -> str:
        kind = normalize_input_kind(kind)
        cfg_selected = _load_config_yaml(DEFAULT_CONFIG_PATH)
        audio_cfg = cfg_selected.get("audio", {})
        if kind == "mic":
            if not _coerce_bool(audio_cfg.get("enable_mic", True)):
                return "off"
            mic_idx = audio_cfg.get("mic_device_index")
            return "auto" if mic_idx is None else str(mic_idx)
        if not _coerce_bool(audio_cfg.get("enable_system", True)):
            return "off"
        sys_idx = audio_cfg.get("system_device_index")
        follow_default = bool(audio_cfg.get("system_device_follow_default", True))
        return "auto" if follow_default or sys_idx is None else str(sys_idx)

    def _choices_for(kind: str):
        kind = normalize_input_kind(kind)
        _reload_device_cache()
        if kind == "mic":
            return build_device_choices(
                source="mic",
                options=device_cache.get("mic_options", []),
                default_name=device_cache.get("mic_default"),
            )
        return build_device_choices(
            source="sys",
            options=device_cache.get("sys_options", []),
            default_name=device_cache.get("sys_default"),
        )

    def _open_device_picker(kind: str) -> None:
        kind = normalize_input_kind(kind)
        source_label = "MIC" if kind == "mic" else "SYSTEM"
        dialog = DevicePickerDialog(
            page=page,
            source=kind,
            title=f"{source_label} 入力を選択",
            selected_value=_selected_value(kind),
            choices_provider=lambda k=kind: _choices_for(k),
            on_select=lambda value, k=kind: _select_device(k, value),
        )
        dialog.open()

    def _toggle_menu(kind: str) -> None:
        _close_menus()
        _open_device_picker(kind)

    def _close_menus() -> None:
        mic_menu_open["value"] = False
        sys_menu_open["value"] = False
        _update_menu_visibility()

    def _update_menu_visibility() -> None:
        # Legacy dropdown overlays are inert; DevicePickerDialog is the only selector.
        mic_menu_open["value"] = False
        sys_menu_open["value"] = False
        mic_menu_container.visible = False
        sys_menu_container.visible = False
        mic_menu_overlay.visible = False
        sys_menu_overlay.visible = False
        menu_backdrop.visible = False
        page.update()

    def _menu_toggle_row(label_text: ft.Text, kind: str) -> ft.Container:
        return ft.Container(
            width=DEVICE_LABEL_WIDTH,
            height=s(44),
            alignment=ft.alignment.center,
            on_click=lambda _e: _toggle_menu(kind),
            content=ft.Row(
                spacing=s(4),
                alignment=ft.MainAxisAlignment.CENTER,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                tight=True,
                controls=[
                    label_text,
                    ft.Icon(ft.Icons.ARROW_DROP_DOWN, size=s(22), color=COLORS["text"]),
                ],
            ),
        )

    mic_menu = _menu_toggle_row(mic_label_text, "mic")
    sys_menu = _menu_toggle_row(sys_label_text, "sys")

    def _auto_label(name: str | None) -> str:
        return f"Default ({name})" if name else "Default (unavailable)"

    def _find_name(options: list[tuple[int, str]], idx: int | None) -> str:
        if idx is None:
            return ""
        for item_idx, name in options:
            if int(item_idx) == int(idx):
                return name
        return f"Device {idx}"

    def _update_device_labels() -> None:
        cfg = _load_config_yaml(DEFAULT_CONFIG_PATH)
        audio_cfg = cfg.get("audio", {})
        mic_idx = audio_cfg.get("mic_device_index")
        sys_idx = audio_cfg.get("system_device_index")
        follow_default = bool(audio_cfg.get("system_device_follow_default", True))
        mic_enabled = _coerce_bool(audio_cfg.get("enable_mic", True))
        sys_enabled = _coerce_bool(audio_cfg.get("enable_system", True))
        mic_default = device_cache.get("mic_default")
        sys_default = device_cache.get("sys_default")
        mic_options = device_cache.get("mic_options", [])
        sys_options = device_cache.get("sys_options", [])
        if not mic_enabled:
            mic_label_text.value = "OFF"
            mic_label_text.tooltip = "MIC input OFF"
            mic_label_text.color = COLORS["muted"]
        else:
            mic_label_text.color = COLORS["text"]
            if mic_idx is None:
                full_label = _auto_label(mic_default)
                mic_label_text.value = short_device_label(full_label, max_chars=22)
                mic_label_text.tooltip = device_tooltip(mic_default or full_label, source_label="MIC")
            else:
                full_label = _find_name(mic_options, mic_idx)
                mic_label_text.value = short_device_label(full_label, max_chars=22)
                mic_label_text.tooltip = device_tooltip(full_label, index=int(mic_idx), source_label="MIC")
        if not sys_enabled:
            sys_label_text.value = "OFF"
            sys_label_text.tooltip = "SYSTEM input OFF"
            sys_label_text.color = COLORS["muted"]
        else:
            sys_label_text.color = COLORS["text"]
            if follow_default or sys_idx is None:
                full_label = _auto_label(sys_default)
                sys_label_text.value = short_device_label(full_label, max_chars=22)
                sys_label_text.tooltip = device_tooltip(sys_default or full_label, source_label="SYSTEM")
            else:
                full_label = _find_name(sys_options, sys_idx)
                sys_label_text.value = short_device_label(full_label, max_chars=22)
                sys_label_text.tooltip = device_tooltip(full_label, index=int(sys_idx), source_label="SYSTEM")

    def _select_device(kind: str, value: object) -> None:
        normalized_kind = normalize_input_kind(kind)
        option_key = "mic_options" if normalized_kind == "mic" else "sys_options"
        options = device_cache.get(option_key)
        if not isinstance(options, list):
            options = None
        running_now = bool(running["value"])
        session_before = controller.session_dir
        try:
            update = select_input_device(
                config_path=DEFAULT_CONFIG_PATH,
                controller=controller,
                kind=normalized_kind,
                value=value,
                running=running_now,
                available_options=options,
            )
        except Exception as exc:  # noqa: BLE001
            ui_logger.exception("Input source selection failed: %s=%s", normalized_kind, value)
            show_placeholder(f"入力ソースを変更できません: {exc}")
            page.update()
            raise

        _reload_device_cache()
        _update_device_labels()
        ui_logger.info(
            "Input source updated: %s=%s running=%s session_dir=%s",
            update.source,
            value,
            running_now,
            controller.session_dir,
        )
        if running_now and controller.session_dir != session_before:
            ui_logger.error(
                "Input source update changed session_dir unexpectedly: before=%s after=%s",
                session_before,
                controller.session_dir,
            )
        if not running_now and gain_monitor is not None:
            gain_monitor.request_restart()
        show_placeholder(input_selection_message(update, running=running_now))
        page.update()

    def _make_item(kind: str, value: str, label: str, checked: bool) -> ft.Container:
        def _on_click(_e: ft.ControlEvent, k: str = kind, v: str = value) -> None:
            ui_logger.info("Input menu clicked: %s=%s", k, v)
            _select_device(k, v)
            _close_menus()

        check_icon = (
            ft.Icon(ft.Icons.CHECK, size=s(18), color=COLORS["text"])
            if checked
            else ft.Container(width=s(18))
        )
        return ft.Container(
            height=menu_item_height,
            padding=ft.padding.symmetric(horizontal=10),
            bgcolor="#F3F4F6" if checked else "#FFFFFF",
            alignment=ft.alignment.center_left,
            on_click=_on_click,
            content=ft.Row(
                spacing=s(8),
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    check_icon,
                    ft.Text(
                        label,
                        size=s(26),
                        color=COLORS["text"],
                        max_lines=1,
                        overflow=ft.TextOverflow.ELLIPSIS,
                        no_wrap=True,
                    ),
                ],
            ),
        )

    def _refresh_device_options() -> None:
        _reload_device_cache()
        _update_device_labels()
        _update_menu_visibility()

    _refresh_device_options()

    left_wave = _wifi_icon(COLORS["mic_blue"], "left", size=WIFI_SIZE, bg=COLORS["bg_top"])
    right_wave = _wifi_icon(COLORS["sys_orange"], "right", size=WIFI_SIZE, bg=COLORS["bg_top"])
    wave_box_left = ft.Container(
        height=PLAY_SIZE,
        alignment=ft.alignment.center,
        content=left_wave,
    )
    wave_box_right = ft.Container(
        height=PLAY_SIZE,
        alignment=ft.alignment.center,
        content=right_wave,
    )

    label_offset_left = _wifi_visual_center_offset(WIFI_SIZE, "left") * WIFI_LABEL_PULL
    label_offset_right = _wifi_visual_center_offset(WIFI_SIZE, "right") * WIFI_LABEL_PULL

    def build_label_block(title: str, offset_px: float) -> ft.Container:
        margin = ft.margin.only(
            left=max(0.0, offset_px),
            right=max(0.0, -offset_px),
        )
        device_control = mic_menu if title == "MIC" else sys_menu
        return ft.Container(
            width=SIDE_BLOCK_WIDTH,
            margin=margin,
            content=ft.Column(
                spacing=s(6),
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Text(title, size=s(44), weight=ft.FontWeight.W_600, color=COLORS["text"]),
                    ft.Container(
                        width=DEVICE_LABEL_WIDTH,
                        alignment=ft.alignment.center,
                        content=device_control,
                    ),
                    mic_level_text if title == "MIC" else sys_level_text,
                ],
            ),
        )

    mic_block = ft.Container(
        width=SIDE_BLOCK_WIDTH,
        alignment=ft.alignment.top_center,
        content=ft.Column(
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=s(1),
            controls=[
                wave_box_left,
                build_label_block("MIC", label_offset_left),
            ],
        ),
    )

    sys_block = ft.Container(
        width=SIDE_BLOCK_WIDTH,
        alignment=ft.alignment.top_center,
        content=ft.Column(
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=s(1),
            controls=[
                wave_box_right,
                build_label_block("SYSTEM", label_offset_right),
            ],
        ),
    )

    center_row = ft.Row(
        alignment=ft.MainAxisAlignment.CENTER,
        vertical_alignment=ft.CrossAxisAlignment.START,
        spacing=s(24),
        controls=[mic_block, play_button, sys_block],
    )

    task_bar, task_segments, task_colors = _task_load_bar(width=s(520), height=s(18))

    load_section = ft.Column(
        alignment=ft.MainAxisAlignment.CENTER,
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        spacing=s(2),
        controls=[
            task_bar,
            ft.Text("Task Load", size=s(40), color=COLORS["text"]),
        ],
    )
    def _open_caption_window() -> None:
        if controller.session_dir is None:
            cfg = _load_config_yaml(DEFAULT_CONFIG_PATH)
            session_root = Path(cfg.get("audio", {}).get("session_root", "sessions"))
            launch_args = ["--session-root", str(session_root)]
        else:
            launch_args = ["--session-dir", str(controller.session_dir)]
        subprocess.Popen(
            [
                sys.executable,
                "-m",
                "agendasnap.ui.caption_window",
                "--config",
                str(DEFAULT_CONFIG_PATH),
                *launch_args,
            ],
            close_fds=True,
        )

    def _open_minutes_window() -> None:
        if controller.session_dir is None:
            show_placeholder("Session not started yet.")
            return
        subprocess.Popen(
            [
                sys.executable,
                "-m",
                "agendasnap.ui.minutes_window",
                "--session-dir",
                str(controller.session_dir),
            ],
            close_fds=True,
        )

    def _open_settings_window(tab: str | None = None) -> None:
        args = [
            sys.executable,
            "-m",
            "agendasnap.ui.settings_window",
            "--config",
            str(DEFAULT_CONFIG_PATH),
        ]
        if tab:
            args.extend(["--tab", tab])
        if running["value"]:
            args.append("--session-running")
        subprocess.Popen(args, close_fds=True)

    footer = ft.Container(
        height=s(70),
        bgcolor=COLORS["footer_bg"],
        border=ft.border.only(top=ft.border.BorderSide(1, COLORS["footer_border"])),
        padding=ft.padding.symmetric(horizontal=s(28)),
        content=ft.Row(
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.IconButton(
                    icon=ft.Icons.SETTINGS,
                    icon_color=COLORS["text"],
                    icon_size=s(34),
                    on_click=lambda e: _open_settings_window(),
                ),
                ft.Row(
                    spacing=s(18),
                    controls=[
                        ft.IconButton(
                            icon=ft.Icons.GRAPHIC_EQ,
                            icon_color=COLORS["text"],
                            icon_size=s(32),
                            tooltip="音声設定を開く",
                            on_click=lambda e: _open_settings_window("audio_tuning"),
                        ),
                        ft.IconButton(
                            icon=ft.Icons.CLOSED_CAPTION,
                            icon_color=COLORS["text"],
                            icon_size=s(32),
                            on_click=lambda e: _open_caption_window(),
                        ),
                        ft.IconButton(
                            icon=ft.Icons.DESCRIPTION,
                            icon_color=COLORS["text"],
                            icon_size=s(32),
                            on_click=lambda e: _open_minutes_window(),
                        ),
                    ],
                ),
            ],
        ),
    )

    root = ft.Container(
        expand=True,
        gradient=ft.LinearGradient(
            colors=[COLORS["bg_top"], COLORS["bg_bottom"]],
            begin=ft.alignment.top_center,
            end=ft.alignment.bottom_center,
        ),
        padding=ft.padding.only(left=s(24), right=s(24), top=s(10)),
        content=ft.Column(
            expand=True,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Text(
                    TITLE_TEXT,
                    size=s(96),
                    weight=ft.FontWeight.W_600,
                    color=COLORS["text"],
                ),
                ft.Container(height=s(2)),
                ft.Column(
                    spacing=s(2),
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Row(
                            spacing=s(24),
                            alignment=ft.MainAxisAlignment.CENTER,
                            controls=[session_text, status_text],
                        ),
                        ft.Row(
                            alignment=ft.MainAxisAlignment.CENTER,
                            controls=[minutes_text],
                        ),
                    ],
                ),
                center_row,
                ft.Container(height=s(3)),
                load_section,
                ft.Container(expand=True),
                footer,
            ],
        ),
    )

    def _set_task_load(load_value: float, *, delay_mode: bool) -> None:
        load_value = _clamp(load_value, 0.0, 1.0)
        active = int(math.ceil(load_value * len(task_segments)))
        if delay_mode:
            active_colors = ["#C81E1E", "#D63A2A", "#E0512F", "#EA6A2E", "#F2822B", "#F79A2A"]
            inactive_color = "#F4D3D3"
        else:
            active_colors = list(task_colors)
            inactive_color = "#E6E6E6"

        for idx, seg in enumerate(task_segments):
            if idx < active:
                seg.bgcolor = active_colors[idx % len(active_colors)]
            else:
                seg.bgcolor = inactive_color

    def _apply_gain_visuals(
        *,
        mic_rms: float,
        mic_thr: float,
        mic_enabled: bool,
        sys_rms: float,
        sys_thr: float,
        sys_enabled: bool,
        mic_payload: dict | None = None,
        sys_payload: dict | None = None,
    ) -> None:
        def _text(source: str, rms: float, thr: float, enabled: bool, payload: dict | None) -> str:
            data = {
                "source": source,
                "enabled": enabled,
                "rms": rms,
                "threshold": thr,
                "vad_active": bool(enabled and thr > 0 and rms >= thr),
                "clipped": False,
                "error": None,
            }
            if payload:
                data.update(payload)
                rms = float(data.get("rms", rms) or 0.0)
                thr = float(data.get("threshold", thr) or 0.0)
            state = level_state_label(data)
            if state in {"OFF", "デバイスエラー"}:
                return state
            return f"{state} RMS {rms:.0f} / THR {thr:.0f}"

        mic_level_text.value = _text("mic", mic_rms, mic_thr, mic_enabled, mic_payload)
        sys_level_text.value = _text("sys", sys_rms, sys_thr, sys_enabled, sys_payload)

        def _active_rings(rms: float, thr: float) -> int:
            if thr <= 0:
                return 1
            ratio = rms / thr
            if ratio < 0.8:
                return 1
            if ratio < 1.3:
                return 2
            return 3

        mic_active = _active_rings(mic_rms, mic_thr) if mic_enabled else 1
        sys_active = _active_rings(sys_rms, sys_thr) if sys_enabled else 1

        mic_color = COLORS["mic_blue"] if mic_enabled else COLORS["muted"]
        sys_color = COLORS["sys_orange"] if sys_enabled else COLORS["muted"]

        wave_box_left.content = _wifi_icon(
            mic_color, "left", size=WIFI_SIZE, bg=COLORS["bg_top"], active_rings=mic_active
        )
        wave_box_right.content = _wifi_icon(
            sys_color, "right", size=WIFI_SIZE, bg=COLORS["bg_top"], active_rings=sys_active
        )

    def _on_gain_update(
        *,
        mic_rms: float,
        mic_thr: float,
        mic_enabled: bool,
        sys_rms: float,
        sys_thr: float,
        sys_enabled: bool,
    ) -> None:
        if running["value"] or status_stop.is_set() or closing.is_set():
            return
        _apply_gain_visuals(
            mic_rms=mic_rms,
            mic_thr=mic_thr,
            mic_enabled=mic_enabled,
            sys_rms=sys_rms,
            sys_thr=sys_thr,
            sys_enabled=sys_enabled,
        )
        with contextlib.suppress(Exception):
            page.update()

    def _as_float(value: object) -> float | None:
        try:
            if value is None:
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    def _format_duration(seconds: float | None) -> str:
        if seconds is None:
            return "-"
        total = max(0, int(round(float(seconds))))
        mins, sec = divmod(total, 60)
        hours, mins = divmod(mins, 60)
        if hours > 0:
            return f"{hours}h {mins:02d}m"
        if mins > 0:
            return f"{mins}m {sec:02d}s"
        return f"{sec}s"

    def _release_finalize_lock_if_minutes_ready() -> None:
        if finalizing["since"] is None or controller.session_dir is None:
            return
        minutes_path = controller.session_dir / "minutes.md"
        if not minutes_path.exists():
            return
        if minutes_path.stat().st_mtime < finalizing["since"]:
            return
        minutes_text.value = "Minutes: completed"
        finalizing["since"] = None
        if not running["value"]:
            ui_locked["value"] = False
            _apply_play_state()

    def _update_from_status(payload: dict) -> None:
        mode = str(payload.get("mode", "normal"))
        delay_mode = mode == "delay"
        base_status = f"Status: {mode}"
        status_text.value = base_status

        metrics = payload.get("metrics") or {}
        sys_m = metrics.get("sys") or {}
        mic_m = metrics.get("mic") or {}
        queue_ratio = max(float(sys_m.get("queue_ratio", 0.0) or 0.0), float(mic_m.get("queue_ratio", 0.0) or 0.0))
        drop_rate = max(float(sys_m.get("drop_rate", 0.0) or 0.0), float(mic_m.get("drop_rate", 0.0) or 0.0))

        delay_seconds = max(
            float(sys_m.get("delay_seconds", 0.0) or 0.0),
            float(mic_m.get("delay_seconds", 0.0) or 0.0),
        )
        queue_thresh = float(delay_thresholds.get("queue_ratio", 0.7))
        delay_thresh = float(delay_thresholds.get("delay_seconds", 10.0))
        drop_thresh = float(delay_thresholds.get("drop_rate", 0.5))

        queue_norm = queue_ratio / queue_thresh if queue_thresh > 0 else 0.0
        delay_norm = 0.0
        drop_norm = 0.0
        if queue_ratio > 0:
            if delay_thresh > 0:
                delay_norm = delay_seconds / delay_thresh
            if drop_thresh > 0:
                drop_norm = drop_rate / drop_thresh

        load_value = max(queue_norm, delay_norm, drop_norm)
        _set_task_load(load_value, delay_mode=delay_mode)

        audio = payload.get("audio") or {}
        sys_audio = audio.get("sys") or {}
        mic_audio = audio.get("mic") or {}
        sys_enabled = bool(sys_audio.get("enabled", True))
        mic_enabled = bool(mic_audio.get("enabled", True))
        sys_rms = float(sys_audio.get("rms", 0.0) or 0.0)
        sys_thr = float(sys_audio.get("threshold", 0.0) or 0.0)
        mic_rms = float(mic_audio.get("rms", 0.0) or 0.0)
        mic_thr = float(mic_audio.get("threshold", 0.0) or 0.0)
        _apply_gain_visuals(
            mic_rms=mic_rms,
            mic_thr=mic_thr,
            mic_enabled=mic_enabled,
            sys_rms=sys_rms,
            sys_thr=sys_thr,
            sys_enabled=sys_enabled,
        )
        stt_issue_summary = _format_stt_issue_summary(payload)

        def _status_with_stt_issue(value: str) -> str:
            if not stt_issue_summary:
                return value
            return f"{value} | STT permanent: {stt_issue_summary}"

        finalize = payload.get("minutes_finalize")
        if not isinstance(finalize, dict):
            if stt_issue_summary:
                status_text.value = _status_with_stt_issue(base_status)
            _release_finalize_lock_if_minutes_ready()
            return

        state = str(finalize.get("state", "")).strip().lower()
        if not state:
            if stt_issue_summary:
                status_text.value = _status_with_stt_issue(base_status)
            _release_finalize_lock_if_minutes_ready()
            return

        now = time.time()
        updated_at = _as_float(finalize.get("updated_at"))
        started_at = _as_float(finalize.get("started_at"))
        elapsed = (now - started_at) if started_at is not None else None
        stale = bool(updated_at is not None and (now - updated_at) > 45.0)

        progress_current = int(finalize.get("progress_current", 0) or 0)
        progress_total = int(finalize.get("progress_total", 0) or 0)
        progress_ratio = _as_float(finalize.get("progress_ratio"))
        if progress_ratio is None and progress_total > 0:
            progress_ratio = progress_current / progress_total
        if progress_ratio is not None:
            progress_ratio = _clamp(progress_ratio, 0.0, 1.0)
        eta_seconds = _as_float(finalize.get("eta_seconds"))

        message = str(finalize.get("message", "")).strip()
        error = str(finalize.get("error", "")).strip()

        if state in finalize_active_states:
            detail = message or state
            if progress_total > 0:
                progress_part = f" {progress_current}/{progress_total}"
            elif progress_ratio is not None:
                progress_part = f" {progress_ratio * 100:.0f}%"
            else:
                progress_part = ""
            eta_part = f" ETA {_format_duration(eta_seconds)}" if eta_seconds is not None and eta_seconds > 0 else ""
            elapsed_part = f" elapsed {_format_duration(elapsed)}" if elapsed is not None else ""
            stale_part = " (stalled?)" if stale else ""

            status_text.value = _status_with_stt_issue(f"Status: {detail}{stale_part}")
            minutes_text.value = f"Minutes: finalizing{progress_part}{eta_part}{elapsed_part}"
            finalizing["since"] = finalizing["since"] or now
            if not running["value"]:
                ui_locked["value"] = True
                _apply_play_state()
            return

        if state == "completed":
            status_text.value = _status_with_stt_issue("Status: finalization completed")
            minutes_text.value = "Minutes: completed"
            finalizing["since"] = None
            if not running["value"]:
                ui_locked["value"] = False
                _apply_play_state()
            return

        if state == "failed":
            detail = error or message or "unknown error"
            status_text.value = _status_with_stt_issue(f"Status: finalize failed ({detail})")
            minutes_text.value = "Minutes: failed"
            finalizing["since"] = None
            if not running["value"]:
                ui_locked["value"] = False
                _apply_play_state()
            return

        _release_finalize_lock_if_minutes_ready()

    _set_task_load(0.0, delay_mode=False)
    _apply_play_state()
    closing = threading.Event()
    destroyed = threading.Event()
    close_lock = threading.Lock()
    CLOSE_JOIN_TIMEOUT_SECONDS = 2.0

    def _cleanup() -> None:
        status_stop.set()
        if gain_monitor is not None:
            gain_monitor.stop()
        ui_logger.info(
            "UI close cleanup starting: fast_shutdown=True bounded_join_timeout_seconds=%.1f",
            CLOSE_JOIN_TIMEOUT_SECONDS,
        )
        finished = controller.stop(wait=True, timeout=CLOSE_JOIN_TIMEOUT_SECONDS, finalize=False)
        ui_logger.info(
            "UI close cleanup finished: streaming_worker_finished=%s",
            finished,
        )
        controller.close_session_log()

    def _show_closing() -> None:
        with contextlib.suppress(Exception):
            page.snack_bar = ft.SnackBar(
                ft.Text("終了中...", color=COLORS["text"]),
                bgcolor="#FFFFFF",
                duration=2000,
            )
            page.snack_bar.open = True
            close_button.disabled = True
            page.update()

    def _destroy_window() -> None:
        with close_lock:
            if destroyed.is_set():
                return
            destroyed.set()
        with contextlib.suppress(Exception):
            page.window.destroy()

    def _begin_close() -> None:
        with close_lock:
            if closing.is_set():
                return
            closing.set()
        _show_closing()

        def _close_worker() -> None:
            try:
                _cleanup()
            finally:
                _destroy_window()

        threading.Thread(target=_close_worker, name="ui-close-cleanup", daemon=True).start()

    def _on_close_button(_e: ft.ControlEvent) -> None:
        _begin_close()

    def _on_close(_e: ft.ControlEvent) -> None:
        _begin_close()

    page.on_close = _on_close

    close_icon_size = s(56)
    chrome_height = close_icon_size + s(10)
    close_button = ft.IconButton(
        icon=ft.Icons.CLOSE,
        icon_color=COLORS["text"],
        icon_size=close_icon_size,
        tooltip="Close",
        on_click=_on_close_button,
        style=ft.ButtonStyle(padding=ft.padding.all(0)),
    )
    close_button_box = ft.Container(
        width=chrome_height,
        height=chrome_height,
        alignment=ft.alignment.center,
        content=close_button,
    )
    drag_area = ft.WindowDragArea(
        content=ft.Container(height=chrome_height, bgcolor="#00000000")
    )
    chrome_bar = ft.Container(
        height=chrome_height,
        padding=ft.padding.only(top=s(2), left=s(6), right=s(6)),
        content=ft.Row(
            expand=True,
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            controls=[
                ft.Container(expand=True, content=drag_area),
                close_button_box,
            ],
        ),
    )
    chrome_overlay = ft.Container(
        expand=True,
        alignment=ft.alignment.top_center,
        content=chrome_bar,
    )
    page.add(
        ft.Stack(
            expand=True,
            controls=[
                root,
                chrome_overlay,
            ],
        )
    )

    gain_monitor = GainMonitor(config_path=DEFAULT_CONFIG_PATH, on_update=_on_gain_update)
    gain_monitor.start()

    def _status_loop() -> None:
        last_status_read = 0.0
        while not status_stop.is_set() and not closing.is_set():
            live_levels = controller.latest_levels() if running["value"] else {}
            if live_levels:
                mic_payload = live_levels.get("mic")
                sys_payload = live_levels.get("sys")
                if mic_payload or sys_payload:
                    mic_rms = float((mic_payload or {}).get("rms", 0.0) or 0.0)
                    mic_thr = float((mic_payload or {}).get("threshold", 0.0) or 0.0)
                    sys_rms = float((sys_payload or {}).get("rms", 0.0) or 0.0)
                    sys_thr = float((sys_payload or {}).get("threshold", 0.0) or 0.0)
                    _apply_gain_visuals(
                        mic_rms=mic_rms,
                        mic_thr=mic_thr,
                        mic_enabled=bool((mic_payload or {}).get("enabled", mic_payload is not None)),
                        sys_rms=sys_rms,
                        sys_thr=sys_thr,
                        sys_enabled=bool((sys_payload or {}).get("enabled", sys_payload is not None)),
                        mic_payload=mic_payload,
                        sys_payload=sys_payload,
                    )
                    if closing.is_set() or status_stop.is_set():
                        break
                    with contextlib.suppress(Exception):
                        page.update()

            now = time.time()
            if now - last_status_read < 1.0:
                time.sleep(0.1)
                continue
            last_status_read = now
            if controller.session_dir is None:
                _set_task_load(0.0, delay_mode=False)
                time.sleep(0.5)
                continue
            status_path = controller.session_dir / "status.json"
            if status_path.exists():
                try:
                    payload = json.loads(status_path.read_text(encoding="utf-8"))
                    _update_from_status(payload)
                    if not closing.is_set() and not status_stop.is_set():
                        with contextlib.suppress(Exception):
                            page.update()
                except Exception:
                    pass
            else:
                _set_task_load(0.0, delay_mode=False)
                if ui_locked["value"]:
                    _release_finalize_lock_if_minutes_ready()
                    if not closing.is_set() and not status_stop.is_set():
                        with contextlib.suppress(Exception):
                            page.update()
                if not running["value"] and not ui_locked["value"]:
                    status_text.value = "Status: idle"
                    minutes_text.value = "Minutes: -"
                    if not closing.is_set() and not status_stop.is_set():
                        with contextlib.suppress(Exception):
                            page.update()
            time.sleep(0.1)

    page.run_thread(_status_loop)


if __name__ == "__main__":
    ft.app(target=main)

