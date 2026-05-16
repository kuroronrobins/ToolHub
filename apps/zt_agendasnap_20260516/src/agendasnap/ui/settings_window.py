"""Settings window for AgendaSnap."""
from __future__ import annotations

import argparse
import contextlib
import copy
import logging
from pathlib import Path
import threading
import time
from typing import Any

import flet as ft
import pyaudiowpatch as pyaudio
import yaml

from agendasnap.apikeys.service import ApiKeyManager, ApiKeyTestResult, normalize_priority
from agendasnap.audio.capture_mic import open_mic_stream
from agendasnap.audio.capture_wasapi import open_loopback_stream
from agendasnap.audio.diagnostics import (
    AudioLevelRingBuffer,
    AudioDecisionTrace,
    analyze_candidate_visibility,
    build_decision_trace_from_samples,
    build_diagnosis_cards,
    build_graph_interpretations,
    build_stable_diagnosis,
    diagnosis_instruction,
    easy_tuning_changes,
    graph_sample_label,
    help_cards,
    queue_drop_rate,
    simulate_decisions_for_config,
    threshold_lines,
    user_state_label,
    vad_discard_rate,
)
from agendasnap.audio.levels import LiveAudioLevel, compute_pcm16_level
from agendasnap.config.loader import default_user_config_path, load_config, save_config, should_use_user_config
from agendasnap.config.glossary import (
    GLOSSARY_CATEGORIES,
    GlossaryTerm,
    ROLLING_CONTEXT_GUARD_STYLES,
    build_rolling_transcription_prompt,
    glossary_preview_text,
    glossary_to_config,
    normalize_rolling_context_settings,
    normalize_glossary,
    rolling_transcription_prompt_metadata,
    split_glossary_values,
)
from agendasnap.config.validate import validate_config
from agendasnap.minutes.profiles import MINUTES_PROFILE_IDS, MINUTES_PROFILE_LABELS
from agendasnap.ui.audio_tuning_view import (
    GRAPH_SAMPLE_COLORS,
    LIGHT_MUTED,
    THRESHOLD_LINE_COLORS,
    ADJUSTMENT_AXES,
    DecisionGraphViewModel,
    adjustment_axis_display,
    adjustment_marker_text,
    adjustment_step,
    build_before_after_decision_graphs,
    candidate_visibility_from_graph,
    compact_change_summary,
    decision_interval_color,
    graph_peak_color,
    graph_placeholder_message,
    graph_sample_color,
    graph_scale_max,
    line_top,
    live_status_display,
    sample_bar_heights,
    should_show_graph,
    should_show_no_candidate_help,
    split_cards,
    stable_diagnosis_display,
    threshold_line_text,
)

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "default.yaml"
logger = logging.getLogger(__name__)
TAB_INDEX_BY_NAME = {"basic": 0, "audio_tuning": 1, "ai_keys": 2, "expert": 3}


PRESETS: dict[str, dict[str, Any]] = {
    "PC会議音声中心": {
        "description": "Teams/ZoomなどPC側の音を主に拾い、マイクは必要時だけ使います。",
        "live": ["audio.enable_system", "audio.enable_mic"],
        "restart": ["stt.noise_reduction_sys"],
        "values": {
            "audio.enable_system": True,
            "audio.enable_mic": False,
            "stt.noise_reduction_sys": "near_field",
            "audio.vad.start_ratio_sys": 1.1,
            "audio.vad.stop_ratio_sys": 0.85,
        },
    },
    "ヘッドセットマイク": {
        "description": "口元に近いマイクを使う個人参加向けです。",
        "live": ["audio.enable_system", "audio.enable_mic"],
        "restart": ["stt.noise_reduction_mic"],
        "values": {
            "audio.enable_system": False,
            "audio.enable_mic": True,
            "stt.noise_reduction_mic": "near_field",
            "audio.vad.start_ratio_mic": 1.4,
            "audio.vad.stop_ratio_mic": 1.0,
            "audio.vad.min_voice_chunks_mic": 1,
        },
    },
    "会議室マイク": {
        "description": "離れた位置のマイクで複数人の発話を拾う設定です。",
        "live": ["audio.enable_system", "audio.enable_mic"],
        "restart": ["stt.noise_reduction_mic"],
        "values": {
            "audio.enable_system": False,
            "audio.enable_mic": True,
            "stt.noise_reduction_mic": "far_field",
            "audio.vad.start_ratio_mic": 1.8,
            "audio.vad.stop_ratio_mic": 1.2,
            "audio.vad.min_voice_chunks_mic": 2,
            "audio.vad.guard_mic.enable": True,
        },
    },
    "ハイブリッド": {
        "description": "PC音声とマイク音声の両方を継続して拾います。",
        "live": ["audio.enable_system", "audio.enable_mic"],
        "restart": ["stt.noise_reduction_sys", "stt.noise_reduction_mic"],
        "values": {
            "audio.enable_system": True,
            "audio.enable_mic": True,
            "stt.noise_reduction_sys": "near_field",
            "stt.noise_reduction_mic": "far_field",
        },
    },
    "ノイズが多い部屋": {
        "description": "空調音や周囲の会話が多い場所で誤検出を抑えます。",
        "live": [],
        "restart": ["audio.calibration", "audio.vad", "stt.noise_reduction_mic"],
        "values": {
            "audio.calibration.enable": True,
            "audio.calibration.multiplier": 2.0,
            "audio.vad.start_ratio_mic": 2.2,
            "audio.vad.stop_ratio_mic": 1.4,
            "audio.vad.min_voice_chunks_mic": 3,
            "audio.vad.guard_mic.enable": True,
            "stt.noise_reduction_mic": "far_field",
        },
    },
    "精度優先": {
        "description": "少し待ち時間を許容して、文脈と安定性を優先します。",
        "live": [],
        "restart": ["audio.chunk_ms", "stt.segment_max_seconds", "stt.segment_gap_ms"],
        "values": {
            "audio.chunk_ms": 500,
            "stt.segment_max_seconds": 12,
            "stt.segment_gap_ms": 900,
            "stt.min_turn_seconds": 0.7,
            "audio.vad.adaptive.enable": True,
        },
    },
    "低遅延優先": {
        "description": "字幕の追従を優先し、短めの発話単位で処理します。",
        "live": [],
        "restart": ["audio.chunk_ms", "stt.segment_max_seconds", "stt.segment_gap_ms"],
        "values": {
            "audio.chunk_ms": 250,
            "stt.segment_max_seconds": 6,
            "stt.segment_gap_ms": 500,
            "stt.min_turn_seconds": 0.3,
        },
    },
}


ROLLING_CONTEXT_PRESETS: dict[str, dict[str, Any]] = {
    "safe_guard": {
        "label": "安全ガードのみ（推奨）",
        "description": "実測で最も安定した標準設定です。topic/glossary/recentは使いません。",
        "settings": {
            "enable": True,
            "guard_style": "current",
            "use_topic": False,
            "use_glossary": False,
            "use_recent_final_transcript": False,
            "max_recent_segments": 1,
            "max_recent_chars": 200,
            "max_glossary_terms": 20,
            "max_prompt_chars": 1200,
        },
    },
    "glossary_only": {
        "label": "専門用語重視",
        "description": "glossary onlyです。専門用語や疑問文末に効く可能性がありますが、会議ごとにA/B評価してください。",
        "settings": {
            "enable": True,
            "guard_style": "current",
            "use_topic": False,
            "use_glossary": True,
            "use_recent_final_transcript": False,
            "max_recent_segments": 1,
            "max_recent_chars": 200,
            "max_glossary_terms": 20,
            "max_prompt_chars": 1200,
        },
    },
    "topic_glossary": {
        "label": "会議テーマ＋専門用語",
        "description": "専門性が強い会議向けです。topic/glossaryの過誘導に注意してください。",
        "settings": {
            "enable": True,
            "guard_style": "current",
            "use_topic": True,
            "use_glossary": True,
            "use_recent_final_transcript": False,
            "max_recent_segments": 1,
            "max_recent_chars": 200,
            "max_glossary_terms": 20,
            "max_prompt_chars": 1200,
        },
    },
    "recent_experimental": {
        "label": "直近発話も使う（実験）",
        "description": "実測で悪化例があります。標準非推奨です。A/B評価後に1文/100文字程度から試してください。",
        "settings": {
            "enable": True,
            "guard_style": "current",
            "use_topic": True,
            "use_glossary": True,
            "use_recent_final_transcript": True,
            "max_recent_segments": 1,
            "max_recent_chars": 100,
            "max_glossary_terms": 20,
            "max_prompt_chars": 1200,
        },
    },
}


ROLLING_GUARD_STYLE_OPTIONS: dict[str, str] = {
    "current": "現行詳細ガード",
    "minimal": "最小ガード",
    "sentence_end_only": "文末注意のみ",
    "no_repetition_only": "繰り返し防止のみ",
    "none": "ガードなし",
}

ROLLING_GUARD_STYLE_HELP: dict[str, str] = {
    "current": "file APIでは有効例がありますが、Realtime direct-WAVでは悪化例があります。",
    "minimal": "Realtime direct-WAVで有望だった短いガードです。WASAPI評価の次候補です。",
    "sentence_end_only": "CER改善例はありますが、疑問文末一致率の改善は未確認です。",
    "no_repetition_only": "直前文脈を使う場合の重複出力対策だけを入れます。",
    "none": "promptなしbaselineに近い条件です。",
}


def apply_rolling_context_preset(
    preset_id: str,
    base_settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return normalized Rolling STT Context settings after applying a UI preset."""
    settings = normalize_rolling_context_settings(base_settings or {})
    preset = ROLLING_CONTEXT_PRESETS.get(str(preset_id or ""))
    if not preset:
        return settings
    settings.update(dict(preset.get("settings", {})))
    settings["include_partial"] = False
    settings["include_low_confidence"] = False
    return normalize_rolling_context_settings(settings)


def _get_nested(cfg: dict, path: str, default: Any = None) -> Any:
    cur: Any = cfg
    for key in path.split("."):
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return cur


def _set_nested(cfg: dict, path: str, value: Any, *, remove_if_none: bool = False) -> None:
    keys = path.split(".")
    cur = cfg
    for key in keys[:-1]:
        if key not in cur or not isinstance(cur[key], dict):
            cur[key] = {}
        cur = cur[key]
    if value is None and remove_if_none:
        cur.pop(keys[-1], None)
    else:
        cur[keys[-1]] = value


def parse_rolling_context_ui_values(
    values: dict[str, Any],
    base_settings: dict[str, Any] | None = None,
    *,
    strict: bool = False,
) -> dict[str, Any]:
    """Normalize Rolling STT Context values from Settings controls."""
    result = normalize_rolling_context_settings(base_settings or {})

    def _bool(key: str) -> bool:
        value = values.get(key, result.get(key))
        if isinstance(value, bool):
            return value
        if value is None:
            return bool(result.get(key, False))
        if isinstance(value, str):
            text = value.strip().lower()
            if text in {"1", "true", "yes", "on", "enabled"}:
                return True
            if text in {"0", "false", "no", "off", "disabled"}:
                return False
        return bool(value)

    def _int(key: str, *, minimum: int, label: str) -> int:
        raw = values.get(key, result.get(key))
        if raw is None or str(raw).strip() == "":
            return int(result.get(key, minimum))
        try:
            parsed = int(str(raw).strip())
        except ValueError as exc:
            if strict:
                raise ValueError(f"{label} は整数で入力してください。") from exc
            return int(result.get(key, minimum))
        if parsed < minimum:
            if strict:
                raise ValueError(f"{label} は {minimum} 以上で入力してください。")
            return minimum
        return parsed

    for key in ("enable", "use_recent_final_transcript", "use_topic", "use_glossary"):
        result[key] = _bool(key)
    guard_style = str(values.get("guard_style", result.get("guard_style", "current")) or "").strip()
    if guard_style not in ROLLING_CONTEXT_GUARD_STYLES:
        if strict:
            raise ValueError("guard_style must be one of: " + ", ".join(ROLLING_CONTEXT_GUARD_STYLES))
        guard_style = "current"
    result["guard_style"] = guard_style
    result["max_recent_segments"] = _int("max_recent_segments", minimum=0, label="直近発話数")
    result["max_recent_chars"] = _int("max_recent_chars", minimum=0, label="直近context最大文字数")
    result["max_prompt_chars"] = _int("max_prompt_chars", minimum=200, label="prompt最大文字数")
    result["include_partial"] = False
    result["include_low_confidence"] = False
    return normalize_rolling_context_settings(result)


def format_rolling_context_metadata(metadata: dict[str, Any]) -> str:
    """Format safe Rolling STT Context diagnostics without prompt text."""
    return (
        f"enabled={bool(metadata.get('rolling_context_enabled'))} / "
        f"policy={metadata.get('update_policy', '')} / "
        f"guard={metadata.get('guard_style', 'current')} / "
        f"prompt={metadata.get('prompt_chars', 0)}/{metadata.get('max_prompt_chars', 0)} chars / "
        f"recent={metadata.get('recent_segments_count', 0)} segments, "
        f"{metadata.get('recent_chars', 0)} chars / "
        f"glossary={metadata.get('glossary_terms_count', 0)} terms / "
        f"topic={bool(metadata.get('topic_used'))} / "
        f"summary={bool(metadata.get('summary_used'))} / "
        f"partial={bool(metadata.get('include_partial'))} / "
        f"low_confidence={bool(metadata.get('include_low_confidence'))}"
    )


def _list_text(value: Any) -> str:
    if isinstance(value, list):
        return "\n".join(str(item) for item in value)
    return ""


def parse_settings_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=False)
    parser.add_argument(
        "--tab",
        choices=sorted(TAB_INDEX_BY_NAME.keys()),
        default="basic",
        help="Initial settings tab.",
    )
    parser.add_argument(
        "--session-running",
        action="store_true",
        help="Disable settings-window input test to avoid competing with an active meeting session.",
    )
    args, _unknown = parser.parse_known_args(argv)
    return args


class SettingsInputTestMonitor:
    """Temporary level monitor for the settings input test. It never stores audio."""

    def __init__(self, *, config_path: Path, on_update, on_error) -> None:
        self.config_path = config_path
        self.on_update = on_update
        self.on_error = on_error
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None

    def start(self, source: str) -> None:
        self.stop()
        self.stop_event.clear()
        self.thread = threading.Thread(
            target=self._run,
            args=(source,),
            name="settings-audio-test",
            daemon=True,
        )
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        if self.thread and self.thread.is_alive() and threading.current_thread() is not self.thread:
            self.thread.join(timeout=1.0)
        self.thread = None

    def _run(self, source: str) -> None:
        pa = None
        stream = None
        try:
            cfg = load_config(self.config_path)
            audio = cfg.get("audio") if isinstance(cfg.get("audio"), dict) else {}
            capture_rate = int(audio.get("capture_rate", 48000))
            frames_per_buffer = int(audio.get("frames_per_buffer", 1024))
            pa = pyaudio.PyAudio()
            if source == "mic":
                enabled = bool(audio.get("enable_mic", True))
                threshold = float(audio.get("energy_threshold_mic", 0.0) or 0.0)
                if not enabled:
                    self.on_error(source, "MIC入力がOFFです。")
                    return
                channels = int(audio.get("channels_mic", 1))
                stream, device_index, _rate, _channels = open_mic_stream(
                    pa,
                    capture_rate,
                    channels,
                    frames_per_buffer,
                    device_index=audio.get("mic_device_index"),
                )
            else:
                enabled = bool(audio.get("enable_system", True))
                threshold = float(audio.get("energy_threshold_sys", 0.0) or 0.0)
                if not enabled:
                    self.on_error(source, "SYSTEM入力がOFFです。")
                    return
                channels = int(audio.get("channels_system", 2))
                stream, device_index, _rate, _channels = open_loopback_stream(
                    pa,
                    capture_rate,
                    channels,
                    frames_per_buffer,
                    follow_default=bool(audio.get("system_device_follow_default", True)),
                    select_each_time=False,
                    device_index=audio.get("system_device_index"),
                )
            while not self.stop_event.is_set():
                data = stream.read(frames_per_buffer, exception_on_overflow=False)
                level = compute_pcm16_level(
                    data,
                    source=source,
                    threshold=threshold,
                    enabled=True,
                    timestamp=time.time(),
                    device_index=int(device_index) if device_index is not None else None,
                )
                self.on_update(level)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Settings input test monitor failed: %s", exc)
            self.on_error(source, str(exc))
        finally:
            with contextlib.suppress(Exception):
                if stream is not None:
                    stream.close()
            with contextlib.suppress(Exception):
                if pa is not None:
                    pa.terminate()


def main(page: ft.Page) -> None:
    args = parse_settings_args()

    config_path = args.config or DEFAULT_CONFIG_PATH
    page.title = "AgendaSnap Settings"
    page.window.width = 900
    page.window.height = 760
    page.window.resizable = True
    page.scroll = ft.ScrollMode.AUTO
    page.padding = 16
    page.theme_mode = ft.ThemeMode.LIGHT
    page.bgcolor = "#FFFFFF"
    page.theme = ft.Theme(font_family="Yu Gothic UI")

    fields: list[dict[str, Any]] = []
    controls: dict[str, ft.Control] = {}
    helpers: dict[str, str] = {
        # Audio / Device
        "audio.capture_rate": "デバイスから取得するサンプルレート。単位: Hz。",
        "audio.target_rate": "STTへ送る前にリサンプルする目標レート。単位: Hz。",
        "audio.frames_per_buffer": "音声APIの1回の読み取りフレーム数。小さいほど低遅延。単位: フレーム。",
        "audio.chunk_ms": "STTに渡す音声チャンク長。単位: ms。",
        "audio.energy_threshold_sys": "システム入力のRMSしきい値。これ以上で音声あり判定。単位: RMS。",
        "audio.energy_threshold_mic": "マイク入力のRMSしきい値。これ以上で音声あり判定。単位: RMS。",
        "audio.enable_system": "システム入力を有効化する。",
        "audio.enable_mic": "マイク入力を有効化する。",
        "audio.system_device_follow_default": "既定の出力デバイス(ループバック)に追従するか。",
        "audio.system_device_prompt": "起動時にシステム入力デバイス選択を表示するか。",
        "audio.system_device_index": "システム入力(ループバック)のデバイスindexを固定指定。空欄で既定に追従。",
        "audio.mic_device_index": "マイク入力のデバイスindexを固定指定。空欄で既定入力。",
        "audio.queue_max_chunks": "音声キューの最大チャンク数。超えるとドロップ。単位: チャンク。",
        "audio.metrics_interval_seconds": "status.jsonなどのメトリクス更新間隔。単位: 秒。",
        "audio.session_root": "セッション保存先のルートフォルダ。",
        # Calibration
        "audio.calibration.enable": "起動時にノイズ床を自動較正するか。",
        "audio.calibration.seconds": "較正に使う録音時間。単位: 秒。",
        "audio.calibration.percentile": "ノイズ床として採用する分位点。単位: % (0-100)。",
        "audio.calibration.multiplier": "ノイズ床に掛ける倍率。しきい値=床×倍率。",
        "audio.calibration.min_threshold_sys": "較正後しきい値の下限(システム)。単位: RMS。",
        "audio.calibration.min_threshold_mic": "較正後しきい値の下限(マイク)。単位: RMS。",
        "audio.calibration.max_threshold_sys": "較正後しきい値の上限(システム)。単位: RMS。",
        "audio.calibration.max_threshold_mic": "較正後しきい値の上限(マイク)。単位: RMS。",
        "audio.calibration.recalibration_interval_seconds": "再較正の実行間隔。単位: 秒。",
        "audio.calibration.recalibration_window_seconds": "再較正に使う直近データの窓幅。単位: 秒。",
        "audio.calibration.recalibration_min_samples": "再較正に必要な最小サンプル数。単位: チャンク。",
        "audio.calibration.recalibration_min_change_ratio": "再較正を実施する最小変化率。単位: 比率(0-1)。",
        # VAD
        "audio.vad.enable_hysteresis": "開始/終了でしきい値を分けて誤検知を抑える。",
        "audio.vad.start_ratio_sys": "開始判定倍率(システム)。threshold×倍率。単位: 比率。",
        "audio.vad.stop_ratio_sys": "終了判定倍率(システム)。threshold×倍率。単位: 比率。",
        "audio.vad.start_ratio_mic": "開始判定倍率(マイク)。threshold×倍率。単位: 比率。",
        "audio.vad.stop_ratio_mic": "終了判定倍率(マイク)。threshold×倍率。単位: 比率。",
        "audio.vad.min_voice_chunks_sys": "音声確定に必要な連続チャンク数(システム)。単位: チャンク。",
        "audio.vad.min_voice_chunks_mic": "音声確定に必要な連続チャンク数(マイク)。単位: チャンク。",
        "audio.vad.guard_mic.enable": "マイクの誤検出を抑える追加ガードを有効化。",
        "audio.vad.guard_mic.frame_ms": "ガード判定のフレーム長。単位: ms。",
        "audio.vad.guard_mic.min_voiced_ms": "音声と判定する最小継続時間。単位: ms。",
        "audio.vad.guard_mic.min_rms_std_ratio": "RMS変動率の下限。定常ノイズを除外。",
        "audio.vad.guard_mic.strong_rms_ratio": "強い発話の優先通過倍率。threshold×倍率。",
        "audio.vad.guard_mic.prebuffer_chunks": "発話冒頭を補うためのプレバッファ数。単位: チャンク。",
        # VAD Adaptive
        "audio.vad.adaptive.enable": "ドロップ率に合わせてしきい値を自動調整する。",
        "audio.vad.adaptive.update_interval_seconds": "自動調整の更新間隔。単位: 秒。",
        "audio.vad.adaptive.target_drop_rate": "目標ドロップ率。単位: 比率(0-1)。",
        "audio.vad.adaptive.deadband": "調整しない許容帯。単位: 比率(0-1)。",
        "audio.vad.adaptive.max_step_ratio": "1回の更新での最大調整率。単位: 比率(0-1)。",
        "audio.vad.adaptive.smoothing": "平滑化係数。単位: 比率(0-1)。",
        "audio.vad.adaptive.min_samples": "調整に必要な最小サンプル数。単位: チャンク。",
        "audio.vad.adaptive.min_change_ratio": "調整を反映する最小変化率。単位: 比率(0-1)。",
        "audio.vad.adaptive.min_threshold_sys": "自動調整の下限(システム)。単位: RMS。",
        "audio.vad.adaptive.max_threshold_sys": "自動調整の上限(システム)。単位: RMS。",
        "audio.vad.adaptive.min_threshold_mic": "自動調整の下限(マイク)。単位: RMS。",
        "audio.vad.adaptive.max_threshold_mic": "自動調整の上限(マイク)。単位: RMS。",
        # Recording
        "audio.recording.system": "システム音声を録音保存する。",
        "audio.recording.mic": "マイク音声を録音保存する。",
        "audio.recording.format": "録音ファイル形式。例: wav/flac。",
        "audio.recording.rotate_seconds": "この秒数ごとにファイル分割。0で無効。単位: 秒。",
        "audio.recording.rotate_mb": "このサイズ(MB)を超えると分割。0で無効。",
        "audio.recording.directory": "録音ファイルの保存フォルダ名。",
        # STT
        "stt.enable": "リアルタイム文字起こしを有効化。",
        "stt.provider": "STTプロバイダ名。",
        "stt.language": "認識言語コード。例: ja。",
        "stt.model": "Realtime接続に使うモデル名。",
        "stt.url": "Realtime WebSocket URL。",
        "stt.transcription_model": "音声→テキストに使うモデル名。",
        "stt.noise_reduction_sys": "ノイズ抑制プリセット(システム)。",
        "stt.noise_reduction_mic": "ノイズ抑制プリセット(マイク)。",
        "stt.segment_max_seconds": "1セグメントの最大長。単位: 秒。",
        "stt.segment_gap_ms": "セグメント分割の無音ギャップ。単位: ms。",
        "stt.api_key_source": "APIキー取得元。env/wincred/embedded。",
        "stt.rolling_session_minutes": "Realtimeセッションを回し替える間隔。単位: 分。",
        "stt.rolling_overlap_seconds": "セッション切替時の重複送信時間。単位: 秒。",
        "stt.min_turn_seconds": "最小発話長。これ未満は短文としてまとめる。単位: 秒。",
        "stt.max_consecutive_failures": "連続失敗の許容回数。超えると再接続。単位: 回。",
        "stt.reconnect_enable": "切断時に自動再接続する。",
        "stt.reconnect_backoff_seconds": "再接続の初期待機時間。単位: 秒。",
        "stt.reconnect_max_backoff_seconds": "再接続待機時間の上限。単位: 秒。",
        # Translation
        "translation.enable": "キャプションの自動翻訳を有効化する。",
        "translation.target_language": "翻訳先言語コード(共通)。例: en/ja/zh/ko。",
        "translation.target_language_mic": "マイク入力の翻訳先言語コード。例: en/ja/zh/ko。",
        "translation.target_language_sys": "システム入力の翻訳先言語コード。例: en/ja/zh/ko。",
        "translation.model": "翻訳に使うLLMモデル名。",
        "translation.batch_wait_ms": "翻訳バッチの最大待ち時間。単位: ms。",
        "translation.batch_lines": "1回の翻訳でまとめる最大行数。単位: 行。",
        "translation.batch_chars": "1回の翻訳でまとめる最大文字数。単位: 文字。",
        "translation.request_timeout_seconds": "翻訳APIのタイムアウト。単位: 秒。",
        "translation.max_output_tokens": "翻訳出力の最大トークン数。",
        "translation.backfill_lines": "翻訳ON時に遡って翻訳する行数。単位: 行。",
        # Minutes
        "minutes.update_interval_seconds": "議事録更新の間隔。単位: 秒。",
        "minutes.merge_enable": "近接するセグメントを統合する。",
        "minutes.merge_min_seconds": "統合対象とみなす最小長。単位: 秒。",
        "minutes.merge_max_seconds": "統合対象とみなす最大長。単位: 秒。",
        "minutes.merge_gap_seconds": "セグメント間の許容ギャップ。これ以下なら統合。単位: 秒。",
        "minutes.merge_by_source": "入力ソースごとに統合する。",
        "minutes.dedupe_enable": "重複発話の除去を有効化。",
        "minutes.dedupe_window_seconds": "重複判定の時間窓。単位: 秒。",
        "minutes.dedupe_similarity": "重複判定の類似度しきい値。単位: 比率(0-1)。",
        "minutes.profile": (
            "議事録LLMのコストprofile。current_baselineは現行挙動です。"
            "low_cost_incrementalは実運用試験候補です。realtime中の暫定メモを低コスト化し、finalは高品質モデルを維持します。"
            "default化前にllm_costs.jsonlで確認してください。balanced_incrementalは追加比較候補、final_quality_onlyはrealtime中のLLM増分を抑制、"
            "hybrid/high_quality_final_modernは実験用です。default.yamlではなくuser_configで実測してください。"
        ),
        "minutes.filter.enable": "短すぎる発話を除外する。",
        "minutes.filter.min_chars": "残す最小文字数。単位: 文字。",
        "minutes.filter.allowlist": "短文でも残す語のリスト。1行1語。",
        # Minutes LLM
        "minutes.llm.enable": "LLMで議事録を整形/要約する。",
        "minutes.llm.model": "リアルタイム整形に使うLLMモデル。",
        "minutes.llm.final_model": "最終整形に使うLLMモデル。",
        "minutes.llm.temperature": "生成温度。単位: 比率(0-1)。",
        "minutes.llm.max_output_tokens": "LLM出力の最大トークン数。",
        "minutes.llm.min_interval_seconds": "LLM呼び出しの最小間隔。単位: 秒。",
        "minutes.llm.min_new_segments": "新規セグメントがこの数以上で実行。単位: 件。",
        "minutes.llm.max_segments_per_call": "1回の呼び出しで扱う最大セグメント数。単位: 件。",
        "minutes.llm.request_timeout_seconds": "APIタイムアウト。単位: 秒。",
        "minutes.llm.confidence_threshold": "採用する最低信頼度。単位: 比率(0-1)。",
        "minutes.llm.dedupe_similarity": "LLMの重複判定類似度。単位: 比率(0-1)。",
        "minutes.llm.prompt_version": "使用するプロンプトのバージョン。",
        "minutes.llm.language": "出力言語コード。例: ja。",
        "minutes.llm.cost_tracking.enable": (
            "LLM呼び出しごとの安全なコストメタ情報をllm_costs.jsonlへ保存します。"
            "試験時だけON推奨です。prompt本文/APIキー/議事録本文は保存しません。生成ログはGitに入れないでください。"
        ),
        "minutes.llm.cost_tracking.filename": "コストログのファイル名。パスではなくファイル名のみ指定します。例: llm_costs.jsonl。",
        # Resilience
        "resilience.enable": "負荷に応じた遅延/回復制御を有効化。",
        "resilience.status_interval_seconds": "負荷ステータス更新間隔。単位: 秒。",
        # Delay Mode
        "resilience.delay_mode.queue_ratio": "遅延モードに入るキュー使用率。単位: 比率(0-1)。",
        "resilience.delay_mode.delay_seconds": "遅延モードに入る遅延時間。単位: 秒。",
        "resilience.delay_mode.drop_rate": "遅延モードに入るドロップ率。単位: 比率(0-1)。",
        "resilience.delay_mode.recover_queue_ratio": "回復に入るキュー使用率。単位: 比率(0-1)。",
        "resilience.delay_mode.recover_delay_seconds": "回復に入る遅延時間。単位: 秒。",
        "resilience.delay_mode.recover_drop_rate": "回復に入るドロップ率。単位: 比率(0-1)。",
        # Resilience Actions
        "resilience.actions.segment_max_seconds_boost": "遅延時にセグメント最大長をこの秒数へ拡大。単位: 秒。",
        "resilience.actions.minutes_interval_boost": "遅延時に議事録更新間隔をこの秒数へ延長。単位: 秒。",
        # Catch-up
        "resilience.catch_up.enable": "遅延回復後に追いつき処理を行う。",
        "resilience.catch_up.only_when_delay": "遅延モード中のみ追いつき処理を行う。",
        "resilience.catch_up.overwrite_transcript": "追いつき時にtranscriptを上書きする。",
        "resilience.catch_up.keep_realtime_artifacts": "Realtimeの一時ファイルを保持する。",
    }

    def add_field(
        *,
        section: str,
        path: str,
        label: str,
        kind: str = "str",
        options: list[str] | None = None,
        option_labels: dict[str, str] | None = None,
        helper: str | None = None,
        optional: bool = False,
    ) -> None:
        if helper is None:
            helper = helpers.get(path)
        fields.append(
            {
                "section": section,
                "path": path,
                "label": label,
                "kind": kind,
                "options": options,
                "option_labels": option_labels or {},
                "helper": helper,
                "optional": optional,
            }
        )

    # Audio / Device
    add_field(section="Audio / Device", path="audio.capture_rate", label="Capture rate (Hz)", kind="int")
    add_field(section="Audio / Device", path="audio.target_rate", label="Target rate (Hz)", kind="int")
    add_field(section="Audio / Device", path="audio.frames_per_buffer", label="Frames per buffer", kind="int")
    add_field(section="Audio / Device", path="audio.chunk_ms", label="Chunk size (ms)", kind="int")
    add_field(section="Audio / Device", path="audio.level_interval_seconds", label="Live level interval (s)", kind="float", helper="実行中の音量メーター更新間隔。status.jsonの周期とは独立します。")
    add_field(section="Audio / Device", path="audio.energy_threshold_sys", label="Energy threshold (system)", kind="float")
    add_field(section="Audio / Device", path="audio.energy_threshold_mic", label="Energy threshold (mic)", kind="float")
    add_field(section="Audio / Device", path="audio.enable_system", label="Enable system input", kind="bool")
    add_field(section="Audio / Device", path="audio.enable_mic", label="Enable mic input", kind="bool")
    add_field(section="Audio / Device", path="audio.system_device_follow_default", label="System device follow default", kind="bool")
    add_field(section="Audio / Device", path="audio.system_device_prompt", label="Prompt device at start", kind="bool")
    add_field(
        section="Audio / Device",
        path="audio.system_device_index",
        label="System device index (optional)",
        kind="int",
        optional=True,
        helper="空欄で既定の出力デバイスに追従",
    )
    add_field(
        section="Audio / Device",
        path="audio.mic_device_index",
        label="Mic device index (optional)",
        kind="int",
        optional=True,
        helper="空欄で既定の入力デバイス",
    )
    add_field(section="Audio / Device", path="audio.queue_max_chunks", label="Queue max chunks", kind="int")
    add_field(section="Audio / Device", path="audio.metrics_interval_seconds", label="Metrics interval (s)", kind="int")
    add_field(section="Audio / Device", path="audio.session_root", label="Session root", kind="str")

    # Calibration
    add_field(section="Calibration", path="audio.calibration.enable", label="Enable calibration", kind="bool")
    add_field(section="Calibration", path="audio.calibration.seconds", label="Calibration seconds", kind="int")
    add_field(section="Calibration", path="audio.calibration.percentile", label="Calibration percentile", kind="int")
    add_field(section="Calibration", path="audio.calibration.multiplier", label="Calibration multiplier", kind="float")
    add_field(section="Calibration", path="audio.calibration.min_threshold_sys", label="Min threshold (sys)", kind="float", optional=True)
    add_field(section="Calibration", path="audio.calibration.min_threshold_mic", label="Min threshold (mic)", kind="float", optional=True)
    add_field(section="Calibration", path="audio.calibration.max_threshold_sys", label="Max threshold (sys)", kind="float", optional=True)
    add_field(section="Calibration", path="audio.calibration.max_threshold_mic", label="Max threshold (mic)", kind="float", optional=True)
    add_field(section="Calibration", path="audio.calibration.recalibration_interval_seconds", label="Recalibration interval (s)", kind="int")
    add_field(section="Calibration", path="audio.calibration.recalibration_window_seconds", label="Recalibration window (s)", kind="int")
    add_field(section="Calibration", path="audio.calibration.recalibration_min_samples", label="Recalibration min samples", kind="int")
    add_field(section="Calibration", path="audio.calibration.recalibration_min_change_ratio", label="Recalibration min change ratio", kind="float")

    # VAD
    add_field(section="VAD", path="audio.vad.enable_hysteresis", label="Enable hysteresis", kind="bool")
    add_field(section="VAD", path="audio.vad.start_ratio_sys", label="Start ratio (sys)", kind="float")
    add_field(section="VAD", path="audio.vad.stop_ratio_sys", label="Stop ratio (sys)", kind="float")
    add_field(section="VAD", path="audio.vad.start_ratio_mic", label="Start ratio (mic)", kind="float")
    add_field(section="VAD", path="audio.vad.stop_ratio_mic", label="Stop ratio (mic)", kind="float")
    add_field(section="VAD", path="audio.vad.min_voice_chunks_sys", label="Min voice chunks (sys)", kind="int")
    add_field(section="VAD", path="audio.vad.min_voice_chunks_mic", label="Min voice chunks (mic)", kind="int")
    add_field(section="VAD Mic Guard", path="audio.vad.guard_mic.enable", label="Guard mic enable", kind="bool")
    add_field(section="VAD Mic Guard", path="audio.vad.guard_mic.frame_ms", label="Guard frame ms", kind="int")
    add_field(section="VAD Mic Guard", path="audio.vad.guard_mic.min_voiced_ms", label="Guard min voiced ms", kind="int")
    add_field(section="VAD Mic Guard", path="audio.vad.guard_mic.min_rms_std_ratio", label="Guard min rms std ratio", kind="float")
    add_field(section="VAD Mic Guard", path="audio.vad.guard_mic.strong_rms_ratio", label="Guard strong rms ratio", kind="float")
    add_field(section="VAD Mic Guard", path="audio.vad.guard_mic.prebuffer_chunks", label="Guard prebuffer chunks", kind="int")
    add_field(section="VAD Adaptive", path="audio.vad.adaptive.enable", label="Adaptive VAD enable", kind="bool")
    add_field(section="VAD Adaptive", path="audio.vad.adaptive.update_interval_seconds", label="Update interval (s)", kind="int")
    add_field(section="VAD Adaptive", path="audio.vad.adaptive.target_drop_rate", label="Target drop rate", kind="float")
    add_field(section="VAD Adaptive", path="audio.vad.adaptive.deadband", label="Deadband", kind="float")
    add_field(section="VAD Adaptive", path="audio.vad.adaptive.max_step_ratio", label="Max step ratio", kind="float")
    add_field(section="VAD Adaptive", path="audio.vad.adaptive.smoothing", label="Smoothing", kind="float")
    add_field(section="VAD Adaptive", path="audio.vad.adaptive.min_samples", label="Min samples", kind="int")
    add_field(section="VAD Adaptive", path="audio.vad.adaptive.min_change_ratio", label="Min change ratio", kind="float")
    add_field(section="VAD Adaptive", path="audio.vad.adaptive.min_threshold_sys", label="Min threshold sys", kind="float")
    add_field(section="VAD Adaptive", path="audio.vad.adaptive.max_threshold_sys", label="Max threshold sys", kind="float")
    add_field(section="VAD Adaptive", path="audio.vad.adaptive.min_threshold_mic", label="Min threshold mic", kind="float")
    add_field(section="VAD Adaptive", path="audio.vad.adaptive.max_threshold_mic", label="Max threshold mic", kind="float")

    # Recording
    add_field(section="Recording", path="audio.recording.system", label="Record system audio", kind="bool")
    add_field(section="Recording", path="audio.recording.mic", label="Record mic audio", kind="bool")
    add_field(section="Recording", path="audio.recording.format", label="Recording format", kind="dropdown", options=["wav", "flac"])
    add_field(section="Recording", path="audio.recording.rotate_seconds", label="Rotate seconds", kind="int")
    add_field(section="Recording", path="audio.recording.rotate_mb", label="Rotate MB", kind="int")
    add_field(section="Recording", path="audio.recording.directory", label="Recording directory", kind="str")

    # STT
    add_field(section="STT", path="stt.enable", label="Enable STT", kind="bool")
    add_field(
        section="STT",
        path="stt.provider",
        label="Provider",
        kind="dropdown",
        options=[
            "openai_realtime",
            "openai_compatible_realtime",
            "dashscope_realtime",
            "baidu_realtime",
            "zhipu_realtime",
            "custom_realtime",
        ],
    )
    add_field(section="STT", path="stt.cost_profile", label="Cost profile", kind="dropdown", options=["standard", "low_cost"])
    add_field(section="STT", path="stt.api_key_service", label="API key service", kind="dropdown", options=["openai", "dashscope", "baidu", "zhipu", "custom"])
    add_field(section="STT", path="stt.api_key_priority", label="API key priority (one per line)", kind="list")
    add_field(section="STT", path="stt.language", label="Language", kind="str")
    add_field(section="STT", path="stt.model", label="Realtime model", kind="str")
    add_field(section="STT", path="stt.low_cost_model", label="Realtime model (low cost)", kind="str")
    add_field(section="STT", path="stt.url", label="Realtime URL", kind="str")
    add_field(section="STT", path="stt.transcription_model", label="Transcription model", kind="str")
    add_field(section="STT", path="stt.low_cost_transcription_model", label="Transcription model (low cost)", kind="str")
    add_field(section="STT", path="stt.noise_reduction_sys", label="Noise reduction (sys)", kind="dropdown", options=["near_field", "far_field", "none"])
    add_field(section="STT", path="stt.noise_reduction_mic", label="Noise reduction (mic)", kind="dropdown", options=["near_field", "far_field", "none"])
    add_field(section="STT", path="stt.segment_max_seconds", label="Segment max seconds", kind="int")
    add_field(section="STT", path="stt.segment_gap_ms", label="Segment gap ms", kind="int")
    add_field(section="STT", path="stt.api_key_source", label="API key source", kind="dropdown", options=["env", "wincred", "embedded"])
    add_field(section="STT", path="stt.rolling_session_minutes", label="Rolling session minutes", kind="int")
    add_field(section="STT", path="stt.rolling_overlap_seconds", label="Rolling overlap seconds", kind="int")
    add_field(section="STT", path="stt.min_turn_seconds", label="Min turn seconds", kind="float")
    add_field(section="STT", path="stt.include_logprobs", label="Include logprobs (experimental)", kind="bool")
    add_field(section="STT", path="stt.low_confidence_marking", label="Low confidence marking (experimental)", kind="bool")
    add_field(section="STT", path="stt.max_consecutive_failures", label="Max consecutive failures", kind="int")
    add_field(section="STT", path="stt.reconnect_enable", label="Reconnect enable", kind="bool")
    add_field(section="STT", path="stt.reconnect_backoff_seconds", label="Reconnect backoff seconds", kind="int")
    add_field(section="STT", path="stt.reconnect_max_backoff_seconds", label="Reconnect max backoff seconds", kind="int")

    # Translation
    add_field(section="Translation", path="translation.enable", label="Enable translation", kind="bool")
    add_field(section="Translation", path="translation.provider", label="Provider", kind="dropdown", options=["openai", "dashscope", "baidu", "zhipu", "custom"])
    add_field(section="Translation", path="translation.cost_profile", label="Cost profile", kind="dropdown", options=["standard", "low_cost"])
    add_field(section="Translation", path="translation.api_key_service", label="API key service", kind="dropdown", options=["openai", "dashscope", "baidu", "zhipu", "custom"])
    add_field(section="Translation", path="translation.api_key_priority", label="API key priority (one per line)", kind="list")
    add_field(section="Translation", path="translation.base_url", label="Responses API base URL", kind="str")
    add_field(section="Translation", path="translation.target_language_mic", label="Target language (mic)", kind="str")
    add_field(section="Translation", path="translation.target_language_sys", label="Target language (sys)", kind="str")
    add_field(section="Translation", path="translation.model", label="Translation model", kind="str")
    add_field(section="Translation", path="translation.low_cost_model", label="Translation model (low cost)", kind="str")
    add_field(section="Translation", path="translation.batch_wait_ms", label="Batch wait ms", kind="int")
    add_field(section="Translation", path="translation.batch_lines", label="Batch lines", kind="int")
    add_field(section="Translation", path="translation.batch_chars", label="Batch chars", kind="int")
    add_field(section="Translation", path="translation.request_timeout_seconds", label="Request timeout seconds", kind="int")
    add_field(section="Translation", path="translation.max_output_tokens", label="Max output tokens", kind="int")
    add_field(section="Translation", path="translation.backfill_lines", label="Backfill lines", kind="int")

    # Caption UI
    add_field(section="Caption UI", path="ui.caption.font_size", label="Caption font size", kind="int")
    add_field(section="Caption UI", path="ui.caption.min_font_size", label="Caption min font size", kind="int")
    add_field(section="Caption UI", path="ui.caption.max_font_size", label="Caption max font size", kind="int")

    # Minutes
    add_field(section="Minutes", path="minutes.update_interval_seconds", label="Update interval seconds", kind="int")
    add_field(section="Minutes", path="minutes.merge_enable", label="Merge enable", kind="bool")
    add_field(section="Minutes", path="minutes.merge_min_seconds", label="Merge min seconds", kind="int")
    add_field(section="Minutes", path="minutes.merge_max_seconds", label="Merge max seconds", kind="int")
    add_field(section="Minutes", path="minutes.merge_gap_seconds", label="Merge gap seconds", kind="float")
    add_field(section="Minutes", path="minutes.merge_by_source", label="Merge by source", kind="bool")
    add_field(section="Minutes", path="minutes.dedupe_enable", label="Dedupe enable", kind="bool")
    add_field(section="Minutes", path="minutes.dedupe_window_seconds", label="Dedupe window seconds", kind="float")
    add_field(section="Minutes", path="minutes.dedupe_similarity", label="Dedupe similarity", kind="float")
    add_field(
        section="Minutes LLM",
        path="minutes.profile",
        label="Minutes cost profile",
        kind="dropdown",
        options=list(MINUTES_PROFILE_IDS),
        option_labels=MINUTES_PROFILE_LABELS,
        helper=(
            "現行品質優先は既存挙動互換です。低コスト増分は実運用試験候補で、realtime中を安く短くし、"
            "final_modelで最終議事録を整えます。balancedは追加比較候補、final品質優先はrealtime LLM増分を抑制、"
            "hybrid/modernは実験です。まずcost_trackingで実測し、ログや評価結果はGitに入れないでください。"
            "この画面で保存すると試験設定はuser_config差分として保存されます。"
        ),
    )
    add_field(
        section="Minutes LLM",
        path="minutes.profile_overrides.low_cost_incremental.incremental_model",
        label="Test default incremental model",
        kind="str",
        helper=(
            "Test-operation default: gpt-5.4-nano. Use gpt-4o-mini for cheapest mode "
            "or gpt-5.4-mini via balanced_incremental."
        ),
    )
    add_field(
        section="Minutes LLM",
        path="minutes.profile_overrides.low_cost_incremental.final_model",
        label="Test default final model",
        kind="str",
        helper=(
            "Test-operation final candidate: gpt-5.4. Compare with gpt-5.2 before "
            "formal production default confirmation."
        ),
    )
    add_field(
        section="Minutes LLM",
        path="minutes.profile_overrides.low_cost_incremental.update_interval_seconds",
        label="Test default update interval seconds",
        kind="int",
        helper=(
            "Test-operation cadence for low_cost_incremental. Formal production default "
            "still requires real llm_costs.jsonl and human review."
        ),
    )
    add_field(section="Minutes LLM", path="minutes.profile_overrides.low_cost_incremental.min_interval_seconds", label="Test default min interval seconds", kind="int")
    add_field(section="Minutes LLM", path="minutes.profile_overrides.low_cost_incremental.min_new_segments", label="Test default min new segments", kind="int")
    add_field(section="Minutes LLM", path="minutes.profile_overrides.low_cost_incremental.max_segments_per_call", label="Test default max segments per call", kind="int")
    add_field(section="Minutes LLM", path="minutes.profile_overrides.low_cost_incremental.incremental_max_output_tokens", label="Test default incremental max output tokens", kind="int")
    add_field(section="Minutes", path="minutes.filter.enable", label="Filter enable", kind="bool")
    add_field(section="Minutes", path="minutes.filter.min_chars", label="Filter min chars", kind="int")
    add_field(section="Minutes", path="minutes.filter.allowlist", label="Filter allowlist (one per line)", kind="list")
    add_field(section="Minutes LLM", path="minutes.llm.enable", label="LLM enable", kind="bool")
    add_field(section="Minutes LLM", path="minutes.llm.provider", label="Provider", kind="dropdown", options=["openai", "dashscope", "baidu", "zhipu", "custom"])
    add_field(section="Minutes LLM", path="minutes.llm.cost_profile", label="Cost profile", kind="dropdown", options=["standard", "low_cost"])
    add_field(section="Minutes LLM", path="minutes.llm.api_key_service", label="API key service", kind="dropdown", options=["openai", "dashscope", "baidu", "zhipu", "custom"])
    add_field(section="Minutes LLM", path="minutes.llm.api_key_priority", label="API key priority (one per line)", kind="list")
    add_field(section="Minutes LLM", path="minutes.llm.base_url", label="Responses API base URL", kind="str")
    add_field(section="Minutes LLM", path="minutes.llm.model", label="LLM model", kind="str")
    add_field(section="Minutes LLM", path="minutes.llm.low_cost_model", label="LLM model (low cost)", kind="str")
    add_field(section="Minutes LLM", path="minutes.llm.final_model", label="LLM final model", kind="str")
    add_field(section="Minutes LLM", path="minutes.llm.low_cost_final_model", label="LLM final model (low cost)", kind="str")
    add_field(section="Minutes LLM", path="minutes.llm.temperature", label="LLM temperature", kind="float")
    add_field(section="Minutes LLM", path="minutes.llm.max_output_tokens", label="Max output tokens", kind="int")
    add_field(section="Minutes LLM", path="minutes.llm.min_interval_seconds", label="Min interval seconds", kind="int")
    add_field(section="Minutes LLM", path="minutes.llm.min_new_segments", label="Min new segments", kind="int")
    add_field(section="Minutes LLM", path="minutes.llm.max_segments_per_call", label="Max segments per call", kind="int")
    add_field(section="Minutes LLM", path="minutes.llm.request_timeout_seconds", label="Request timeout seconds", kind="int")
    add_field(section="Minutes LLM", path="minutes.llm.confidence_threshold", label="Confidence threshold", kind="float")
    add_field(section="Minutes LLM", path="minutes.llm.dedupe_similarity", label="LLM dedupe similarity", kind="float")
    add_field(section="Minutes LLM", path="minutes.llm.prompt_version", label="Prompt version", kind="str")
    add_field(section="Minutes LLM", path="minutes.llm.language", label="LLM language", kind="str")
    add_field(section="Minutes LLM", path="minutes.llm.cost_tracking.enable", label="Cost tracking enable", kind="bool")
    add_field(section="Minutes LLM", path="minutes.llm.cost_tracking.filename", label="Cost tracking filename", kind="str")
    add_field(section="Minutes LLM", path="minutes.finalize.low_cost_fallback_model", label="Finalize fallback model (low cost)", kind="str")

    # Resilience
    add_field(section="Resilience", path="resilience.enable", label="Enable resilience", kind="bool")
    add_field(section="Resilience", path="resilience.status_interval_seconds", label="Status interval seconds", kind="int")
    add_field(section="Delay Mode", path="resilience.delay_mode.queue_ratio", label="Queue ratio threshold", kind="float")
    add_field(section="Delay Mode", path="resilience.delay_mode.delay_seconds", label="Delay seconds threshold", kind="float")
    add_field(section="Delay Mode", path="resilience.delay_mode.drop_rate", label="Drop rate threshold", kind="float")
    add_field(section="Delay Mode", path="resilience.delay_mode.recover_queue_ratio", label="Recover queue ratio", kind="float")
    add_field(section="Delay Mode", path="resilience.delay_mode.recover_delay_seconds", label="Recover delay seconds", kind="float")
    add_field(section="Delay Mode", path="resilience.delay_mode.recover_drop_rate", label="Recover drop rate", kind="float")
    add_field(section="Resilience Actions", path="resilience.actions.segment_max_seconds_boost", label="Segment max seconds boost", kind="int")
    add_field(section="Resilience Actions", path="resilience.actions.minutes_interval_boost", label="Minutes interval boost", kind="int")
    add_field(section="Catch-up", path="resilience.catch_up.enable", label="Catch-up enable", kind="bool")
    add_field(section="Catch-up", path="resilience.catch_up.only_when_delay", label="Only when delay", kind="bool")
    add_field(section="Catch-up", path="resilience.catch_up.overwrite_transcript", label="Overwrite transcript", kind="bool")
    add_field(section="Catch-up", path="resilience.catch_up.keep_realtime_artifacts", label="Keep realtime artifacts", kind="bool")

    def _info_tooltip(text: str) -> ft.Control:
        return ft.Icon(
            ft.Icons.INFO_OUTLINE,
            size=16,
            color="#6B7280",
            tooltip=text,
        )

    def _wrap_control(spec: dict, ctrl: ft.Control) -> ft.Control:
        help_text = spec.get("helper") or f"{spec['label']} の説明は未登録です。"
        info = _info_tooltip(help_text)
        if isinstance(ctrl, ft.Switch):
            return ft.Row(
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[ctrl, info],
            )
        label_row = ft.Row(
            spacing=6,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[ft.Text(spec["label"], weight=ft.FontWeight.W_600), info],
        )
        return ft.Column(spacing=6, controls=[label_row, ctrl])

    def build_control(spec: dict, cfg: dict) -> ft.Control:
        value = _get_nested(cfg, spec["path"])
        kind = spec["kind"]
        helper = spec.get("helper")
        if kind == "bool":
            ctrl = ft.Switch(label=spec["label"], value=bool(value))
        elif kind == "dropdown":
            options = spec.get("options") or []
            option_labels = spec.get("option_labels") or {}
            ctrl = ft.Dropdown(
                options=[
                    ft.dropdown.Option(key=opt, text=option_labels.get(opt, opt))
                    for opt in options
                ],
                value=value if value in options else (options[0] if options else None),
                width=420,
            )
        elif kind == "list":
            ctrl = ft.TextField(
                value=_list_text(value),
                multiline=True,
                min_lines=3,
                max_lines=6,
            )
        else:
            ctrl = ft.TextField(
                value="" if value is None else str(value),
                helper_text=None,
                keyboard_type=ft.KeyboardType.NUMBER if kind in {"int", "float"} else ft.KeyboardType.TEXT,
            )
        controls[spec["path"]] = ctrl
        return _wrap_control(spec, ctrl)

    def _build_sections(cfg: dict) -> list[ft.Control]:
        sections: dict[str, list[ft.Control]] = {}
        for spec in fields:
            section = spec["section"]
            sections.setdefault(section, []).append(build_control(spec, cfg))
        tiles: list[ft.Control] = []
        for section_name, items in sections.items():
            tiles.append(
                ft.ExpansionTile(
                    title=ft.Text(section_name, weight=ft.FontWeight.W_600),
                    controls=items,
                    initially_expanded=False,
                    collapsed_bgcolor="#F7F7F7",
                    bgcolor="#FFFFFF",
                )
            )
        return tiles

    cfg = load_config(config_path)
    baseline_cfg = copy.deepcopy(cfg)
    tiles = _build_sections(cfg)
    preset_dropdown = ft.Dropdown(
        label="利用シーン",
        options=[ft.dropdown.Option(name) for name in PRESETS],
        value=next(iter(PRESETS)),
        width=360,
    )
    preset_summary = ft.Text("", color="#374151", selectable=True)
    preset_changes = ft.Text("", color="#6B7280", selectable=True)
    prompt_field = ft.TextField(
        label="文字起こしヒント",
        value=str(_get_nested(cfg, "stt.transcription_prompt", "") or ""),
        multiline=True,
        min_lines=3,
        max_lines=6,
        hint_text="専門用語、製品名、人名、部署名などを1行ずつ入力",
    )
    meeting_topic_field = ft.TextField(
        label="今日の会議テーマ",
        value=str(_get_nested(cfg, "meeting.topic", "") or ""),
        hint_text="例: 4月リリースの障害対応レビュー",
    )
    glossary_field = ft.TextField(
        label="専門用語・固有名詞",
        value=glossary_preview_text(normalize_glossary(_get_nested(cfg, "meeting.glossary", []) or [])),
        multiline=True,
        min_lines=3,
        max_lines=6,
        read_only=True,
        hint_text="1行に1語。製品名、人名、部署名、略語など",
    )

    glossary_terms: list[GlossaryTerm] = normalize_glossary(_get_nested(cfg, "meeting.glossary", []) or [])
    glossary_selected_index: int | None = None
    glossary_rows = ft.Column(spacing=6)
    glossary_surface_field = ft.TextField(label="表記", hint_text="例: 検証 / 杭州", width=180)
    glossary_readings_field = ft.TextField(label="読み・聞こえ方", hint_text="例: けんしょう / こうしゅう / くうしゅう", width=260)
    glossary_aliases_field = ft.TextField(label="誤変換・類似表記", hint_text="例: 健勝 / 県証 / 空襲", width=260)
    glossary_category_dropdown = ft.Dropdown(
        label="カテゴリ",
        options=[ft.dropdown.Option(category) for category in GLOSSARY_CATEGORIES],
        value="general",
        width=180,
    )
    glossary_enabled_switch = ft.Switch(label="有効", value=True)
    glossary_note_field = ft.TextField(
        label="文脈説明",
        hint_text="例: バリデーションや確認の意味 / 中国の地名、杭州側",
        multiline=True,
        min_lines=2,
        max_lines=3,
        width=560,
    )
    rolling_context_settings = normalize_rolling_context_settings(
        _get_nested(cfg, "stt.rolling_context", {}) or {}
    )
    rolling_enable_switch = ft.Switch(
        label="安全ガードのみ（推奨）",
        value=bool(rolling_context_settings["enable"]),
    )
    rolling_recent_switch = ft.Switch(
        label="直近発話も使う（注意: 悪化する場合あり）",
        value=bool(rolling_context_settings["use_recent_final_transcript"]),
    )
    rolling_topic_switch = ft.Switch(
        label="会議テーマも使う",
        value=bool(rolling_context_settings["use_topic"]),
    )
    rolling_glossary_switch = ft.Switch(
        label="専門用語辞書も使う",
        value=bool(rolling_context_settings["use_glossary"]),
    )
    rolling_guard_style_dropdown = ft.Dropdown(
        label="ガード文",
        options=[
            ft.dropdown.Option(key=style, text=ROLLING_GUARD_STYLE_OPTIONS.get(style, style))
            for style in ROLLING_CONTEXT_GUARD_STYLES
        ],
        value=str(rolling_context_settings.get("guard_style", "current")),
        width=240,
    )
    rolling_guard_style_help = ft.Text(
        ROLLING_GUARD_STYLE_HELP.get(str(rolling_guard_style_dropdown.value or "current"), ""),
        color="#4B5563",
        selectable=True,
    )
    rolling_recent_segments_field = ft.TextField(
        label="直近発話数",
        value=str(rolling_context_settings["max_recent_segments"]),
        width=140,
        keyboard_type=ft.KeyboardType.NUMBER,
    )
    rolling_recent_chars_field = ft.TextField(
        label="直近context最大文字数",
        value=str(rolling_context_settings["max_recent_chars"]),
        width=180,
        keyboard_type=ft.KeyboardType.NUMBER,
    )
    rolling_prompt_chars_field = ft.TextField(
        label="prompt最大文字数",
        value=str(rolling_context_settings["max_prompt_chars"]),
        width=160,
        keyboard_type=ft.KeyboardType.NUMBER,
    )
    rolling_prompt_count = ft.Text("", color="#6B7280", selectable=True)
    rolling_prompt_metadata_text = ft.Text("", color="#374151", selectable=True)
    rolling_prompt_preview = ft.TextField(
        label="Rolling prompt preview",
        multiline=True,
        min_lines=6,
        max_lines=10,
        read_only=True,
        value="",
    )
    rolling_preset_dropdown = ft.Dropdown(
        label="Rolling STT Contextプリセット",
        options=[
            ft.dropdown.Option(key=preset_id, text=str(preset["label"]))
            for preset_id, preset in ROLLING_CONTEXT_PRESETS.items()
        ],
        value="safe_guard",
        width=320,
    )
    rolling_preset_summary = ft.Text("", color="#4B5563", selectable=True)

    def _rolling_settings_from_controls(*, strict: bool = False) -> dict[str, Any]:
        return parse_rolling_context_ui_values(
            {
                "enable": bool(rolling_enable_switch.value),
                "use_recent_final_transcript": bool(rolling_recent_switch.value),
                "use_topic": bool(rolling_topic_switch.value),
                "use_glossary": bool(rolling_glossary_switch.value),
                "guard_style": str(rolling_guard_style_dropdown.value or "current"),
                "max_recent_segments": rolling_recent_segments_field.value,
                "max_recent_chars": rolling_recent_chars_field.value,
                "max_prompt_chars": rolling_prompt_chars_field.value,
            },
            rolling_context_settings,
            strict=strict,
        )

    def _refresh_rolling_prompt_preview(update: bool = False) -> None:
        try:
            settings = _rolling_settings_from_controls(strict=False)
            placeholder_recent = (
                ["実行中は直近のfinal確定発話だけを短く入れます。partialや未確定発話は入りません。"]
                if settings["use_recent_final_transcript"]
                else []
            )
            prompt = build_rolling_transcription_prompt(
                str(prompt_field.value or ""),
                str(meeting_topic_field.value or ""),
                glossary_to_config(glossary_terms),
                placeholder_recent,
                settings=settings,
            )
            metadata = rolling_transcription_prompt_metadata(
                str(prompt_field.value or ""),
                str(meeting_topic_field.value or ""),
                glossary_to_config(glossary_terms),
                placeholder_recent,
                settings=settings,
            )
            rolling_prompt_preview.value = prompt
            rolling_prompt_count.value = f"{len(prompt)} / {settings['max_prompt_chars']} chars"
            rolling_prompt_metadata_text.value = format_rolling_context_metadata(metadata)
            rolling_guard_style_help.value = ROLLING_GUARD_STYLE_HELP.get(str(settings.get("guard_style", "current")), "")
        except Exception as exc:  # noqa: BLE001
            rolling_prompt_preview.value = f"プレビューを生成できません: {exc}"
            rolling_prompt_count.value = ""
            rolling_prompt_metadata_text.value = "Rolling STT Context metadata unavailable"
        if update:
            page.update()

    def _set_rolling_context_control_values(settings: dict[str, Any]) -> None:
        rolling_enable_switch.value = bool(settings["enable"])
        rolling_recent_switch.value = bool(settings["use_recent_final_transcript"])
        rolling_topic_switch.value = bool(settings["use_topic"])
        rolling_glossary_switch.value = bool(settings["use_glossary"])
        rolling_guard_style_dropdown.value = str(settings.get("guard_style", "current"))
        rolling_guard_style_help.value = ROLLING_GUARD_STYLE_HELP.get(str(settings.get("guard_style", "current")), "")
        rolling_recent_segments_field.value = str(settings["max_recent_segments"])
        rolling_recent_chars_field.value = str(settings["max_recent_chars"])
        rolling_prompt_chars_field.value = str(settings["max_prompt_chars"])
        _refresh_rolling_prompt_preview()

    def _load_rolling_context_controls(cfg_local: dict) -> None:
        nonlocal rolling_context_settings
        rolling_context_settings = normalize_rolling_context_settings(
            _get_nested(cfg_local, "stt.rolling_context", {}) or {}
        )
        _set_rolling_context_control_values(rolling_context_settings)

    def _refresh_rolling_preset_summary() -> None:
        preset = ROLLING_CONTEXT_PRESETS.get(str(rolling_preset_dropdown.value or ""))
        rolling_preset_summary.value = "" if not preset else str(preset.get("description", ""))

    def _apply_rolling_preset(_e: ft.ControlEvent | None = None) -> None:
        nonlocal rolling_context_settings
        rolling_context_settings = apply_rolling_context_preset(
            str(rolling_preset_dropdown.value or ""),
            rolling_context_settings,
        )
        _set_rolling_context_control_values(rolling_context_settings)
        _refresh_rolling_preset_summary()
        page.update()

    def _refresh_glossary_preview() -> None:
        glossary_field.value = glossary_preview_text(glossary_terms)
        rows: list[ft.Control] = []
        for idx, term in enumerate(glossary_terms):
            reads = " / ".join(term.readings) if term.readings else "-"
            aliases = " / ".join(term.aliases) if term.aliases else "-"
            status = "ON" if term.enabled else "OFF"
            rows.append(
                ft.Container(
                    padding=8,
                    border=ft.border.all(1, "#E5E7EB"),
                    border_radius=8,
                    content=ft.Row(
                        wrap=True,
                        spacing=8,
                        run_spacing=6,
                        controls=[
                            ft.Text(f"[{status}] {term.surface}", weight=ft.FontWeight.W_600, width=150),
                            ft.Text(f"読み: {reads}", width=220, selectable=True),
                            ft.Text(f"誤変換: {aliases}", width=220, selectable=True),
                            ft.Text(term.category, width=90),
                            ft.TextButton("編集", on_click=lambda _e, i=idx: _load_glossary_term(i)),
                            ft.TextButton("削除", on_click=lambda _e, i=idx: _delete_glossary_term(i)),
                        ],
                    ),
                )
            )
        glossary_rows.controls = rows or [ft.Text("専門用語はまだ登録されていません。", color="#4B5563")]
        _refresh_rolling_prompt_preview()

    def _clear_glossary_editor(_e: ft.ControlEvent | None = None) -> None:
        nonlocal glossary_selected_index
        glossary_selected_index = None
        glossary_surface_field.value = ""
        glossary_readings_field.value = ""
        glossary_aliases_field.value = ""
        glossary_category_dropdown.value = "general"
        glossary_enabled_switch.value = True
        glossary_note_field.value = ""
        page.update()

    def _load_glossary_term(index: int) -> None:
        nonlocal glossary_selected_index
        if not (0 <= int(index) < len(glossary_terms)):
            return
        term = glossary_terms[int(index)]
        glossary_selected_index = int(index)
        glossary_surface_field.value = term.surface
        glossary_readings_field.value = " / ".join(term.readings)
        glossary_aliases_field.value = " / ".join(term.aliases)
        glossary_category_dropdown.value = term.category
        glossary_enabled_switch.value = term.enabled
        glossary_note_field.value = term.note
        page.update()

    def _upsert_glossary_term(_e: ft.ControlEvent | None = None) -> None:
        nonlocal glossary_selected_index
        surface = str(glossary_surface_field.value or "").strip()
        if not surface:
            _snack("表記を入力してください。", error=True)
            page.update()
            return
        term = GlossaryTerm(
            surface=surface,
            readings=split_glossary_values(glossary_readings_field.value),
            aliases=split_glossary_values(glossary_aliases_field.value),
            category=str(glossary_category_dropdown.value or "general"),
            note=str(glossary_note_field.value or "").strip(),
            enabled=bool(glossary_enabled_switch.value),
        )
        if glossary_selected_index is None:
            glossary_terms.append(term)
        else:
            glossary_terms[glossary_selected_index] = term
        glossary_selected_index = None
        _refresh_glossary_preview()
        _clear_glossary_editor()

    def _delete_glossary_term(index: int) -> None:
        nonlocal glossary_selected_index
        if 0 <= int(index) < len(glossary_terms):
            del glossary_terms[int(index)]
        glossary_selected_index = None
        _refresh_glossary_preview()
        page.update()

    _refresh_glossary_preview()
    for _rolling_ctrl in (
        rolling_enable_switch,
        rolling_recent_switch,
        rolling_topic_switch,
        rolling_glossary_switch,
        rolling_guard_style_dropdown,
        rolling_recent_segments_field,
        rolling_recent_chars_field,
        rolling_prompt_chars_field,
    ):
        _rolling_ctrl.on_change = lambda _e: _refresh_rolling_prompt_preview(update=True)
    prompt_field.on_change = lambda _e: _refresh_rolling_prompt_preview(update=True)
    meeting_topic_field.on_change = lambda _e: _refresh_rolling_prompt_preview(update=True)

    def _set_control_value(path: str, value: Any) -> None:
        ctrl = controls.get(path)
        if ctrl is None:
            return
        if isinstance(ctrl, ft.Switch):
            ctrl.value = bool(value)
            return
        if isinstance(ctrl, ft.Dropdown):
            ctrl.value = str(value)
            return
        ctrl.value = "" if value is None else str(value)

    def _update_preset_summary() -> None:
        preset = PRESETS.get(str(preset_dropdown.value or ""))
        if not preset:
            preset_summary.value = ""
            preset_changes.value = ""
            return
        values = preset.get("values", {})
        live = ", ".join(preset.get("live", [])) or "なし"
        restart = ", ".join(preset.get("restart", [])) or "なし"
        changed = ", ".join(values.keys())
        preset_summary.value = str(preset.get("description", ""))
        preset_changes.value = (
            f"主な変更: {changed}\n"
            f"実行中に反映しやすい項目: {live}\n"
            f"次回開始時に反映する項目: {restart}"
        )

    def _apply_preset(_e: ft.ControlEvent | None = None) -> None:
        preset = PRESETS.get(str(preset_dropdown.value or ""))
        if not preset:
            return
        for path, value in preset.get("values", {}).items():
            _set_control_value(path, value)
        _update_preset_summary()
        page.update()

    preset_dropdown.on_change = lambda _e: (_update_preset_summary(), page.update())
    _update_preset_summary()
    rolling_preset_dropdown.on_change = lambda _e: (_refresh_rolling_preset_summary(), page.update())
    _refresh_rolling_preset_summary()

    use_user_config = should_use_user_config(config_path)
    user_config_path = default_user_config_path()
    header = ft.Column(
        spacing=6,
        controls=[
            ft.Text("AgendaSnap Settings", size=22, weight=ft.FontWeight.W_600),
            ft.Text(f"Default config: {config_path}", size=12, color="#666666"),
            ft.Text(
                f"User config: {user_config_path if use_user_config else 'disabled for custom --config'}",
                size=12,
                color="#666666",
                selectable=True,
            ),
        ],
    )

    def _parse_value(spec: dict, ctrl: ft.Control) -> Any:
        kind = spec["kind"]
        optional = bool(spec.get("optional"))
        if kind == "bool":
            return bool(getattr(ctrl, "value", False))
        value = getattr(ctrl, "value", "")
        if kind == "list":
            items: list[str] = []
            for part in str(value).replace(",", "\n").splitlines():
                part = part.strip()
                if part:
                    items.append(part)
            return items
        if kind == "dropdown":
            return value
        if kind == "int":
            if value is None or str(value).strip() == "":
                return None if optional else 0
            return int(str(value).strip())
        if kind == "float":
            if value is None or str(value).strip() == "":
                return None if optional else 0.0
            return float(str(value).strip())
        return str(value).strip()

    def _collect_cfg_from_controls() -> dict:
        cfg_local = load_config(config_path)
        errors: list[str] = []
        for spec in fields:
            ctrl = controls.get(spec["path"])
            if ctrl is None:
                continue
            try:
                parsed = _parse_value(spec, ctrl)
            except Exception:
                errors.append(spec["label"])
                continue
            _set_nested(cfg_local, spec["path"], parsed, remove_if_none=spec.get("optional", False))
        _set_nested(cfg_local, "stt.transcription_prompt", str(prompt_field.value or "").strip())
        _set_nested(cfg_local, "meeting.topic", str(meeting_topic_field.value or "").strip())
        _set_nested(cfg_local, "meeting.glossary", glossary_to_config(glossary_terms))
        _set_nested(cfg_local, "stt.rolling_context", _rolling_settings_from_controls(strict=True))
        if errors:
            raise ValueError(f"Invalid values: {', '.join(errors)}")
        validate_config(cfg_local)
        return cfg_local

    def _save_config(_e: ft.ControlEvent) -> None:
        try:
            cfg_local = _collect_cfg_from_controls()
        except Exception as exc:  # noqa: BLE001
            page.snack_bar = ft.SnackBar(ft.Text(str(exc)), bgcolor="#FFF1F2")
            page.snack_bar.open = True
            page.update()
            return

        saved_path = save_config(config_path, cfg_local)
        page.snack_bar = ft.SnackBar(ft.Text(f"Saved: {saved_path}"), bgcolor="#E7F7EE")
        page.snack_bar.open = True
        page.update()

    def _reload(_e: ft.ControlEvent) -> None:
        cfg_local = load_config(config_path)
        for spec in fields:
            ctrl = controls.get(spec["path"])
            if ctrl is None:
                continue
            value = _get_nested(cfg_local, spec["path"])
            if spec["kind"] == "bool":
                ctrl.value = bool(value)
            elif spec["kind"] == "list":
                ctrl.value = _list_text(value)
            elif spec["kind"] == "dropdown":
                options = spec.get("options") or []
                ctrl.value = value if value in options else (options[0] if options else None)
            else:
                ctrl.value = "" if value is None else str(value)
        prompt_field.value = str(_get_nested(cfg_local, "stt.transcription_prompt", "") or "")
        meeting_topic_field.value = str(_get_nested(cfg_local, "meeting.topic", "") or "")
        nonlocal glossary_terms
        glossary_terms = normalize_glossary(_get_nested(cfg_local, "meeting.glossary", []) or [])
        _refresh_glossary_preview()
        _load_rolling_context_controls(cfg_local)
        page.update()

    def _reset(_e: ft.ControlEvent) -> None:
        cfg_local = load_config(config_path, include_user_config=False)
        for spec in fields:
            ctrl = controls.get(spec["path"])
            if ctrl is None:
                continue
            value = _get_nested(cfg_local, spec["path"])
            if spec["kind"] == "bool":
                ctrl.value = bool(value)
            elif spec["kind"] == "list":
                ctrl.value = _list_text(value)
            elif spec["kind"] == "dropdown":
                options = spec.get("options") or []
                ctrl.value = value if value in options else (options[0] if options else None)
            else:
                ctrl.value = "" if value is None else str(value)
        prompt_field.value = str(_get_nested(cfg_local, "stt.transcription_prompt", "") or "")
        meeting_topic_field.value = str(_get_nested(cfg_local, "meeting.topic", "") or "")
        nonlocal glossary_terms
        glossary_terms = normalize_glossary(_get_nested(cfg_local, "meeting.glossary", []) or [])
        _refresh_glossary_preview()
        _load_rolling_context_controls(cfg_local)
        saved_path = save_config(config_path, cfg_local)
        page.snack_bar = ft.SnackBar(ft.Text(f"Reset to defaults: {saved_path}"), bgcolor="#E7F7EE")
        page.snack_bar.open = True
        page.update()

    export_picker = ft.FilePicker()
    import_picker = ft.FilePicker()
    page.overlay.extend([export_picker, import_picker])

    def _export(_e: ft.ControlEvent) -> None:
        export_picker.save_file(
            dialog_title="Export settings",
            file_name="agendasnap_config.yaml",
            allowed_extensions=["yaml", "yml"],
        )

    def _import(_e: ft.ControlEvent) -> None:
        import_picker.pick_files(
            dialog_title="Import settings",
            allowed_extensions=["yaml", "yml"],
        )

    def _on_export_result(e: ft.FilePickerResultEvent) -> None:
        if not e.path:
            return
        try:
            cfg_local = _collect_cfg_from_controls()
        except Exception as exc:  # noqa: BLE001
            page.snack_bar = ft.SnackBar(ft.Text(str(exc)), bgcolor="#FFF1F2")
            page.snack_bar.open = True
            page.update()
            return
        Path(e.path).write_text(
            yaml.safe_dump(cfg_local, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
        page.snack_bar = ft.SnackBar(ft.Text("Exported"), bgcolor="#E7F7EE")
        page.snack_bar.open = True
        page.update()

    def _on_import_result(e: ft.FilePickerResultEvent) -> None:
        if not e.files:
            return
        file_path = Path(e.files[0].path)
        try:
            imported = yaml.safe_load(file_path.read_text(encoding="utf-8")) or {}
            if not isinstance(imported, dict):
                raise ValueError("Invalid config file")
            validate_config(imported)
        except Exception as exc:  # noqa: BLE001
            page.snack_bar = ft.SnackBar(ft.Text(f"Import error: {exc}"), bgcolor="#FFF1F2")
            page.snack_bar.open = True
            page.update()
            return
        nonlocal baseline_cfg
        baseline_cfg = copy.deepcopy(imported)
        for spec in fields:
            ctrl = controls.get(spec["path"])
            if ctrl is None:
                continue
            value = _get_nested(imported, spec["path"])
            if spec["kind"] == "bool":
                ctrl.value = bool(value)
            elif spec["kind"] == "list":
                ctrl.value = _list_text(value)
            elif spec["kind"] == "dropdown":
                options = spec.get("options") or []
                ctrl.value = value if value in options else (options[0] if options else None)
            else:
                ctrl.value = "" if value is None else str(value)
        prompt_field.value = str(_get_nested(imported, "stt.transcription_prompt", "") or "")
        meeting_topic_field.value = str(_get_nested(imported, "meeting.topic", "") or "")
        nonlocal glossary_terms
        glossary_terms = normalize_glossary(_get_nested(imported, "meeting.glossary", []) or [])
        _refresh_glossary_preview()
        _load_rolling_context_controls(imported)
        saved_path = save_config(config_path, imported)
        page.snack_bar = ft.SnackBar(ft.Text(f"Imported: {saved_path}"), bgcolor="#E7F7EE")
        page.snack_bar.open = True
        page.update()

    export_picker.on_result = _on_export_result
    import_picker.on_result = _on_import_result

    api_key_manager = ApiKeyManager()
    openai_status_text = ft.Text("", selectable=True)
    openai_source_text = ft.Text("", selectable=True)
    openai_masked_text = ft.Text("", selectable=True)
    openai_env_text = ft.Text("", color="#4B5563", selectable=True)
    openai_wincred_text = ft.Text("", color="#4B5563", selectable=True)
    openai_test_result = ft.Text("", color="#4B5563", selectable=True)
    openai_key_field = ft.TextField(
        label="OpenAI APIキー",
        password=True,
        hint_text="このPCのWindows資格情報に保存します",
        expand=True,
    )
    openai_reveal = {"value": False}

    def _snack(message: str, *, error: bool = False) -> None:
        page.snack_bar = ft.SnackBar(
            ft.Text(message),
            bgcolor="#FFF1F2" if error else "#E7F7EE",
        )
        page.snack_bar.open = True

    def _api_key_priority() -> list[str]:
        cfg_local = load_config(config_path)
        secrets = cfg_local.get("secrets") if isinstance(cfg_local.get("secrets"), dict) else {}
        stt = cfg_local.get("stt") if isinstance(cfg_local.get("stt"), dict) else {}
        priority = stt.get("api_key_priority") or secrets.get("priority")
        return normalize_priority(priority)

    def _refresh_api_key_status() -> None:
        priority = _api_key_priority()
        status = api_key_manager.get_status("openai", priority=priority)
        openai_status_text.value = f"状態: {status.status_label}"
        openai_source_text.value = f"使用中の取得元: {status.effective_source or '未設定'}"
        openai_masked_text.value = f"マスク済みキー: {status.masked_key or '未表示'}"
        openai_wincred_text.value = (
            f"保存先: Windows資格情報 {status.wincred_target}"
            if status.wincred_supported
            else "保存先: Windows資格情報マネージャーはこの環境では利用できません"
        )
        if status.env_present:
            openai_env_text.value = (
                f"環境変数 {status.env_name} が検出されています。"
                "環境変数はWindows側で管理され、削除ボタンでは削除されません。"
            )
        else:
            openai_env_text.value = f"環境変数 {status.env_name}: 未検出"

    def _toggle_openai_key_visibility(_e: ft.ControlEvent) -> None:
        openai_reveal["value"] = not openai_reveal["value"]
        openai_key_field.password = not openai_reveal["value"]
        page.update()

    def _save_openai_key(_e: ft.ControlEvent) -> None:
        key = str(openai_key_field.value or "").strip()
        try:
            if not key:
                _snack("APIキーを入力してください。", error=True)
                page.update()
                return
            api_key_manager.set_key("openai", key)
            _snack("OpenAI APIキーをWindows資格情報に保存しました。")
        except Exception:  # noqa: BLE001
            _snack("OpenAI APIキーを保存できませんでした。", error=True)
        finally:
            key = ""
            openai_key_field.value = ""
            openai_key_field.password = True
            openai_reveal["value"] = False
            _refresh_api_key_status()
            page.update()

    def _show_dialog(dialog: ft.AlertDialog) -> None:
        show_dialog = getattr(page, "show_dialog", None)
        if callable(show_dialog):
            show_dialog(dialog)
            return
        open_control = getattr(page, "open", None)
        if callable(open_control):
            open_control(dialog)
            return
        page.dialog = dialog
        dialog.open = True
        page.update()

    def _close_dialog(dialog: ft.AlertDialog) -> None:
        pop_dialog = getattr(page, "pop_dialog", None)
        if callable(pop_dialog):
            pop_dialog()
            dialog.open = False
            return
        close_control = getattr(page, "close", None)
        if callable(close_control):
            close_control(dialog)
            dialog.open = False
            return
        dialog.open = False
        page.update()

    def _delete_openai_key(dialog: ft.AlertDialog) -> None:
        try:
            deleted = api_key_manager.delete_key("openai")
            _snack(
                "Windows資格情報からOpenAI APIキーを削除しました。"
                if deleted
                else "Windows資格情報に削除対象のOpenAI APIキーはありません。"
            )
        except Exception:  # noqa: BLE001
            _snack("OpenAI APIキーを削除できませんでした。", error=True)
        finally:
            _close_dialog(dialog)
            _refresh_api_key_status()
            page.update()

    def _confirm_delete_openai_key(_e: ft.ControlEvent) -> None:
        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("OpenAI APIキーを削除"),
            content=ft.Text(
                "このPCのWindows資格情報に保存されたOpenAI APIキーだけを削除します。"
                "環境変数 OPENAI_API_KEY は削除されません。"
            ),
            actions=[
                ft.TextButton("キャンセル", on_click=lambda _event: _close_dialog(dialog)),
                ft.TextButton("削除", on_click=lambda _event: _delete_openai_key(dialog)),
            ],
        )
        _show_dialog(dialog)

    def _test_openai_connection(_e: ft.ControlEvent) -> None:
        openai_test_result.color = "#4B5563"
        openai_test_result.value = "接続テスト中..."
        page.update()
        result: ApiKeyTestResult = api_key_manager.test_connection(
            "openai",
            priority=_api_key_priority(),
            timeout_seconds=10.0,
        )
        openai_test_result.value = result.message
        openai_test_result.color = "#047857" if result.ok else "#B91C1C"
        _refresh_api_key_status()
        page.update()

    _refresh_api_key_status()

    actions = ft.Row(
        spacing=10,
        controls=[
            ft.ElevatedButton("Save", on_click=_save_config),
            ft.OutlinedButton("Reload", on_click=_reload),
            ft.OutlinedButton("Reset", on_click=_reset),
            ft.OutlinedButton("Export", on_click=_export),
            ft.OutlinedButton("Import", on_click=_import),
        ],
    )

    basic_tab = ft.Column(
        spacing=14,
        controls=[
            ft.Text("Basic", size=18, weight=ft.FontWeight.W_600),
            ft.Text(
                "会議中の入力ON/OFFやデバイス変更はメイン画面から切り替えできます。"
                "STTモデルやVADなどの詳細項目は次回開始時の反映として扱ってください。",
                color="#4B5563",
            ),
            ft.Row(
                spacing=10,
                vertical_alignment=ft.CrossAxisAlignment.END,
                controls=[
                    preset_dropdown,
                    ft.ElevatedButton("プリセットを適用", on_click=_apply_preset),
                ],
            ),
            preset_summary,
            preset_changes,
            ft.Divider(),
            meeting_topic_field,
            glossary_field,
            ft.Container(
                padding=10,
                border=ft.border.all(1, "#E5E7EB"),
                border_radius=8,
                content=ft.Column(
                    spacing=8,
                    controls=[
                        ft.Text("専門用語辞書", weight=ft.FontWeight.W_600),
                        ft.Text(
                            "専門用語辞書はユーザー固有設定としてuser_configへ保存します。待機中は次回開始時のSTT prompt / minutes promptに反映し、実行中は次のRealtime sessionまたはrolling sessionから反映します。",
                            color="#4B5563",
                            selectable=True,
                        ),
                        glossary_rows,
                        ft.Row(
                            wrap=True,
                            spacing=8,
                            run_spacing=6,
                            vertical_alignment=ft.CrossAxisAlignment.END,
                            controls=[
                                glossary_surface_field,
                                glossary_readings_field,
                                glossary_aliases_field,
                                glossary_category_dropdown,
                                glossary_enabled_switch,
                            ],
                        ),
                        glossary_note_field,
                        ft.Row(
                            spacing=8,
                            controls=[
                                ft.ElevatedButton("追加/更新", on_click=_upsert_glossary_term),
                                ft.OutlinedButton("入力をクリア", on_click=_clear_glossary_editor),
                            ],
                        ),
                    ],
                ),
            ),
            ft.Container(
                padding=10,
                border=ft.border.all(1, "#E5E7EB"),
                border_radius=8,
                content=ft.Column(
                    spacing=8,
                    controls=[
                        ft.Text("Rolling STT Context", weight=ft.FontWeight.W_600),
                        ft.Row(
                            wrap=True,
                            spacing=12,
                            run_spacing=6,
                            vertical_alignment=ft.CrossAxisAlignment.END,
                            controls=[
                                rolling_preset_dropdown,
                                ft.ElevatedButton("プリセットを適用", on_click=_apply_rolling_preset),
                            ],
                        ),
                        rolling_preset_summary,
                        ft.Text(
                            "標準推奨は安全ガードのみです。音声にない内容を追加しない、直前文脈を繰り返さない、文末の「です/ですか」を落とさない指示だけを送ります。"
                            "実行中の反映は次のRealtime session / rolling sessionからです。",
                            color="#4B5563",
                            selectable=True,
                        ),
                        ft.Text(
                            "会議テーマと専門用語辞書は、専門用語が多い会議で必要な場合だけ有効化してください。"
                            "直近発話は実測で悪化する場合があり、直前文脈に引っ張られて誤認識が増える可能性があります。",
                            color="#4B5563",
                            selectable=True,
                        ),
                        ft.Text(
                            "直近発話をONにする場合は、まず1文/200文字以下で試し、A/B評価で悪化していないか確認してください。"
                            "partialや未確定発話は使いません。",
                            color="#4B5563",
                            selectable=True,
                        ),
                        ft.Row(
                            wrap=True,
                            spacing=12,
                            run_spacing=6,
                            controls=[
                                rolling_enable_switch,
                                rolling_recent_switch,
                                rolling_topic_switch,
                                rolling_glossary_switch,
                                rolling_guard_style_dropdown,
                            ],
                        ),
                        rolling_guard_style_help,
                        ft.Row(
                            wrap=True,
                            spacing=10,
                            run_spacing=6,
                            controls=[
                                rolling_recent_segments_field,
                                rolling_recent_chars_field,
                                rolling_prompt_chars_field,
                                rolling_prompt_count,
                            ],
                        ),
                        rolling_prompt_metadata_text,
                        ft.ExpansionTile(
                            title=ft.Text("Prompt preview（明示表示）"),
                            subtitle=ft.Text(
                                "topicや辞書を含むため、必要なときだけ開いて確認してください。",
                                color="#6B7280",
                            ),
                            initially_expanded=False,
                            controls=[rolling_prompt_preview],
                        ),
                    ],
                ),
            ),
            prompt_field,
        ],
    )
    expert_tab = ft.Column(spacing=8, controls=tiles)
    ai_key_tab = ft.Column(
        spacing=14,
        controls=[
            ft.Text("AI利用設定", size=18, weight=ft.FontWeight.W_600),
            ft.Text(
                "APIキーはこのPCのWindows資格情報に保存され、設定ファイルには保存されません。",
                color="#4B5563",
                selectable=True,
            ),
            ft.Container(
                padding=12,
                border=ft.border.all(1, "#E5E7EB"),
                border_radius=8,
                content=ft.Column(
                    spacing=10,
                    controls=[
                        ft.Text("OpenAI", size=16, weight=ft.FontWeight.W_600),
                        openai_status_text,
                        openai_source_text,
                        openai_masked_text,
                        openai_wincred_text,
                        openai_env_text,
                        ft.Row(
                            spacing=8,
                            vertical_alignment=ft.CrossAxisAlignment.END,
                            controls=[
                                openai_key_field,
                                ft.OutlinedButton("表示/非表示", on_click=_toggle_openai_key_visibility),
                                ft.ElevatedButton("APIキーを登録/更新", on_click=_save_openai_key),
                            ],
                        ),
                        ft.Row(
                            spacing=8,
                            controls=[
                                ft.OutlinedButton("接続テスト", on_click=_test_openai_connection),
                                ft.OutlinedButton("削除", on_click=_confirm_delete_openai_key),
                            ],
                        ),
                        openai_test_result,
                    ],
                ),
            ),
            ft.ExpansionTile(
                title=ft.Text("その他のプロバイダー"),
                initially_expanded=False,
                controls=[
                    ft.Text("DashScope / Baidu / Zhipu / Custom のUI登録は準備中です。"),
                    ft.Text(
                        "内部の取得元定義は env / wincred / embedded の優先順位に対応しています。",
                        color="#4B5563",
                    ),
                ],
            ),
        ],
    )

    diagnosis_source = ft.Dropdown(
        label="入力ソース",
        options=[ft.dropdown.Option("sys", text="SYSTEM"), ft.dropdown.Option("mic", text="MIC")],
        value="sys",
        width=220,
    )
    diagnosis_state = ft.Text("", size=16, weight=ft.FontWeight.W_600, selectable=True)
    diagnosis_device = ft.Text("", selectable=True)
    diagnosis_metrics = ft.Text("", selectable=True)
    diagnosis_stats = ft.Text("", selectable=True)
    diagnosis_live_hint = ft.Text("", color="#4B5563", selectable=True)
    diagnosis_observing = ft.Text("", color="#4B5563", selectable=True)
    diagnosis_lines = ft.Text("", selectable=True)
    diagnosis_line_details = ft.Text("", selectable=True)
    diagnosis_cards_column = ft.Column(spacing=8)
    diagnosis_graph = ft.Row(height=170, spacing=2, vertical_alignment=ft.CrossAxisAlignment.END)
    diagnosis_graph_reading = ft.Column(spacing=6)
    diagnosis_stable_column = ft.Column(spacing=8)
    diagnosis_recommendation = ft.Column(spacing=8)
    diagnosis_next_step = ft.Text("", color="#111827", weight=ft.FontWeight.W_600, selectable=True)
    diagnosis_recent_warnings = ft.Column(spacing=6)
    diagnosis_changes = ft.Column(spacing=6)
    diagnosis_adjustments = ft.Column(spacing=8)
    diagnosis_compare = ft.Column(spacing=6)
    diagnosis_trace_lanes = ft.Column(spacing=8)
    diagnosis_trace_compare = ft.Column(spacing=6)
    diagnosis_visibility = ft.Column(spacing=6)
    diagnosis_visibility_section = ft.Column(spacing=6)
    diagnosis_ring = {"sys": AudioLevelRingBuffer(seconds=20), "mic": AudioLevelRingBuffer(seconds=20)}
    diagnosis_latest: dict[str, LiveAudioLevel | dict[str, Any]] = {}
    diagnosis_pending_changes: list = []
    diagnosis_undo_cfg: dict | None = None
    diagnosis_stable_results = {"sys": None, "mic": None}
    diagnosis_warning_history = {"sys": tuple(), "mic": tuple()}
    diagnosis_before_result = {"sys": None, "mic": None}
    diagnosis_after_result = {"sys": None, "mic": None}
    diagnosis_decision_traces: dict[str, AudioDecisionTrace | None] = {"sys": None, "mic": None}
    diagnosis_live_mode = {"sys": "idle", "mic": "idle"}
    diagnosis_last_observed_at = {"sys": None, "mic": None}
    diagnosis_test = {
        "active": False,
        "source": "sys",
        "started_at": 0.0,
        "duration": 15.0,
        "samples": [],
    }
    diagnosis_monitor = SettingsInputTestMonitor(
        config_path=config_path,
        on_update=lambda level: _on_input_test_level(level),
        on_error=lambda source, message: _on_input_test_error(source, message),
    )
    adjustment_levels = {axis.key: 0 for axis in ADJUSTMENT_AXES}

    def _source_level_from_config(cfg_local: dict, source: str) -> LiveAudioLevel:
        audio = cfg_local.get("audio") if isinstance(cfg_local.get("audio"), dict) else {}
        if source == "mic":
            enabled = bool(audio.get("enable_mic", True))
            threshold = float(audio.get("energy_threshold_mic", 0.0) or 0.0)
            device_index = audio.get("mic_device_index")
        else:
            enabled = bool(audio.get("enable_system", True))
            threshold = float(audio.get("energy_threshold_sys", 0.0) or 0.0)
            device_index = audio.get("system_device_index")
        return LiveAudioLevel(
            source=source,
            enabled=enabled,
            timestamp=0.0,
            rms=0.0,
            peak=0.0,
            dbfs=-120.0,
            threshold=threshold,
            vad_active=False,
            clipped=False,
            error=None,
            device_index=int(device_index) if device_index is not None else None,
            device_name=None,
            noise_rms=None,
            energy_threshold=threshold,
            produced=0,
            dropped_energy=0,
            dropped_full=0,
            queue_size=0,
            queue_max=None,
        )

    def _render_graph(source: str, level: LiveAudioLevel | dict[str, Any], samples: list[dict[str, Any]], lines) -> None:
        level_data = level.to_dict() if isinstance(level, LiveAudioLevel) else dict(level)
        if not should_show_graph(level_data, samples):
            diagnosis_graph.controls = [
                ft.Container(
                    height=150,
                    padding=16,
                    border=ft.border.all(1, "#E5E7EB"),
                    border_radius=8,
                    alignment=ft.alignment.center,
                    content=ft.Column(
                        tight=True,
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=8,
                        controls=[
                            ft.Text("まだ音声データがありません", weight=ft.FontWeight.W_600),
                            ft.Text(
                                graph_placeholder_message(source, settings=True),
                                color=LIGHT_MUTED,
                                text_align=ft.TextAlign.CENTER,
                                selectable=True,
                            ),
                        ],
                    ),
                )
            ]
            return
        graph_height = 120
        max_value = graph_scale_max(samples, lines)
        bars: list[ft.Control] = []
        for item in samples[-80:]:
            rms = float(item.get("rms", 0.0) or 0.0)
            peak = float(item.get("peak", 0.0) or 0.0)
            label = graph_sample_label(item)
            rms_height, peak_height = sample_bar_heights(item, graph_height=graph_height, scale_max=max_value)
            stack_items: list[ft.Control] = [
                ft.Container(top=0, width=7, height=8, bgcolor="#FCA5A5" if label == "クリップ" else None),
                ft.Container(
                    bottom=0,
                    width=7,
                    height=peak_height,
                    alignment=ft.alignment.bottom_center,
                    bgcolor=graph_peak_color(item),
                    content=ft.Container(width=7, height=rms_height, bgcolor=graph_sample_color(item)),
                ),
            ]
            for line in lines:
                stack_items.append(
                    ft.Container(
                        top=line_top(line, graph_height=graph_height, scale_max=max_value),
                        width=7,
                        height=2 if line.id in {"start", "stop"} else 1,
                        bgcolor=THRESHOLD_LINE_COLORS.get(line.id, "#111827"),
                    )
                )
            bars.append(
                ft.Container(
                    width=7,
                    height=graph_height,
                    content=ft.Stack(width=7, height=graph_height, controls=stack_items),
                    tooltip=f"{label}: RMS {rms:.0f} / Peak {peak:.0f}",
                )
            )
        diagnosis_graph.controls = [
            ft.Column(
                spacing=4,
                controls=[
                    ft.Row(height=graph_height, spacing=2, vertical_alignment=ft.CrossAxisAlignment.END, controls=bars),
                    ft.Text("左から右へ時間推移。濃い棒=RMS、薄い棒=Peak、上端の赤帯=クリップ警告。", color=LIGHT_MUTED),
                ],
            )
        ]

    def _level_dict(level: LiveAudioLevel | dict[str, Any]) -> dict[str, Any]:
        return level.to_dict() if isinstance(level, LiveAudioLevel) else dict(level)

    def _current_level(cfg_local: dict, source: str) -> LiveAudioLevel | dict[str, Any]:
        return diagnosis_latest.get(source) or _source_level_from_config(cfg_local, source)

    def _render_stable_result(source: str) -> None:
        result = diagnosis_stable_results.get(source)
        display = stable_diagnosis_display(result)
        if display is None:
            diagnosis_stable_column.controls = [
                ft.Text("まだ15秒診断の結果はありません。", color="#4B5563", selectable=True),
            ]
            return
        card_controls = [
            ft.Container(
                padding=10,
                border=ft.border.all(1, "#E5E7EB"),
                border_radius=8,
                content=ft.Column(
                    spacing=4,
                    controls=[
                        ft.Text(card.title, weight=ft.FontWeight.W_600),
                        ft.Text(card.message, color="#4B5563", selectable=True),
                        ft.Text(f"根拠: {card.reason or result.reason}", color="#4B5563", selectable=True),
                        ft.Text(f"信頼度: {card.confidence or result.confidence}", color="#111827", selectable=True),
                    ],
                ),
            )
            for card in result.cards
        ]
        diagnosis_stable_column.controls = [
            ft.Text(display.observed, color="#4B5563", selectable=True),
            *card_controls,
        ]

    def _dedupe_changes(changes: list) -> list:
        by_key: dict[str, Any] = {}
        for change in changes:
            by_key[change.key] = change
        return [change for change in by_key.values() if change.before != change.after]

    def _auto_adjustment_mode(level: int) -> str:
        if level <= -2:
            return "off"
        if level == -1:
            return "weak"
        if level == 0:
            return "standard"
        return "strong"

    def _manual_adjustment_changes(source: str, cfg_local: dict) -> list:
        changes: list = []
        voice_level = int(adjustment_levels.get("voice_pickup", 0))
        if voice_level > 0:
            changes.extend(easy_tuning_changes(source, cfg_local, "voice_pickup", voice_level))
        elif voice_level < 0:
            changes.extend(easy_tuning_changes(source, cfg_local, "noise_reduction", abs(voice_level)))
        start_level = int(adjustment_levels.get("speech_start", 0))
        if start_level > 0:
            changes.extend(easy_tuning_changes(source, cfg_local, "voice_pickup", start_level))
        elif start_level < 0:
            changes.extend(easy_tuning_changes(source, cfg_local, "noise_reduction", abs(start_level)))
        continuity_level = int(adjustment_levels.get("speech_continuity", 0))
        if continuity_level:
            changes.extend(easy_tuning_changes(source, cfg_local, "speech_continuity", continuity_level))
        speed_level = int(adjustment_levels.get("response_speed", 0))
        if speed_level:
            changes.extend(easy_tuning_changes(source, cfg_local, "response_speed", speed_level))
        auto_level = int(adjustment_levels.get("auto_adjustment", 0))
        if auto_level:
            changes.extend(easy_tuning_changes(source, cfg_local, "auto_adjustment", _auto_adjustment_mode(auto_level)))
        return _dedupe_changes(changes)

    def _manual_adjustment_title() -> str:
        active = [
            adjustment_axis_display(key, level)
            for key, level in adjustment_levels.items()
            if int(level) != 0
        ]
        if not active:
            return "標準"
        labels = [f"{axis.label} Lv.{axis.after:+d}" for axis in active]
        return " / ".join(labels)

    def _render_compact_changes(changes: list, *, title: str, source: str, result_action=None) -> list[ft.Control]:
        if result_action is not None:
            summary = compact_change_summary(
                changes,
                title=f"変更候補: {title}",
                what_changes=result_action.what_changes,
                effect=result_action.effect,
                side_effect=result_action.side_effect,
                timing=result_action.timing,
                reversible=result_action.reversible,
            )
        else:
            summary = compact_change_summary(
                changes,
                title=f"変更候補: {title}",
                what_changes="選択した調整軸の段階に合わせて複数の音声設定をまとめて変更します。",
                effect="グラフ読み取りと診断結果に合わせて拾いやすさ、継続、応答性を調整します。",
                side_effect="強くしすぎると、ノイズ増加、短い発話の取りこぼし、精度低下のいずれかが起きる可能性があります。",
                timing="設定保存後に反映します。実行中に安全反映できない項目は次回開始時に反映します。",
                reversible=True,
            )
        chip_controls = [
            ft.Container(
                padding=ft.padding.symmetric(horizontal=8, vertical=6),
                border=ft.border.all(1, "#CBD5E1"),
                border_radius=6,
                content=ft.Text(
                    f"{chip.label} {chip.before} -> {chip.after}",
                    size=12,
                    selectable=True,
                ),
            )
            for chip in summary.chips
        ]
        return [
            ft.Container(
                padding=10,
                border=ft.border.all(1, "#E5E7EB"),
                border_radius=8,
                content=ft.Column(
                    spacing=6,
                    controls=[
                        ft.Text(summary.title, weight=ft.FontWeight.W_600),
                        ft.Text(f"何が変わるか: {summary.what_changes}", selectable=True),
                        ft.Text(f"効果: {summary.effect}", selectable=True),
                        ft.Text(f"副作用: {summary.side_effect}", color="#4B5563", selectable=True),
                        ft.Text(f"適用タイミング: {summary.timing}", color="#4B5563", selectable=True),
                        ft.Text(summary.reversible, color="#4B5563", selectable=True),
                        ft.Row(wrap=True, spacing=6, run_spacing=6, controls=chip_controls),
                        ft.ExpansionTile(
                            title=ft.Text("Expert key/value"),
                            initially_expanded=False,
                            controls=[ft.Text(line, selectable=True) for line in summary.expert_lines],
                        ),
                    ],
                ),
            )
        ]

    def _cfg_with_changes(cfg_local: dict, changes: list) -> dict:
        preview = copy.deepcopy(cfg_local)
        for change in changes:
            _set_nested(preview, change.key, change.after)
        return preview

    def _decision_line_top(line_id: str, value: float, *, graph_height: int, scale_max: float) -> int:
        if line_id == "clip":
            return 0
        clamped = min(max(float(value or 0.0), 0.0), max(scale_max, 1.0))
        return max(0, graph_height - int(graph_height * clamped / max(scale_max, 1.0)))

    def _decision_width(seconds: float) -> int:
        return max(7, min(90, int(max(float(seconds), 0.08) * 42)))

    def _render_decision_graph(graph: DecisionGraphViewModel) -> ft.Control:
        if not graph.samples:
            return ft.Text(f"{graph.title}: 判定用メタデータがありません。", color="#4B5563", selectable=True)
        graph_height = 112
        bars: list[ft.Control] = []
        for index, sample in enumerate(graph.samples):
            width = max(7, int(sample.width or _decision_width(sample.t1 - sample.t0)))
            rms_height = max(2, int(graph_height * min(sample.rms, graph.scale_max) / max(graph.scale_max, 1.0)))
            capped_peak = min(sample.peak, max(graph.scale_max, 1.0))
            peak_height = max(rms_height, int(graph_height * capped_peak / max(graph.scale_max, 1.0)))
            stack_items: list[ft.Control] = [
                ft.Container(
                    bottom=0,
                    width=width,
                    height=peak_height,
                    alignment=ft.alignment.bottom_center,
                    bgcolor="#BFDBFE",
                    content=ft.Container(width=max(3, width - 4), height=rms_height, bgcolor="#2563EB"),
                )
            ]
            for line in graph.threshold_lines:
                value = line.values[index] if index < len(line.values) else line.value
                if line.id == "noise" and value <= 0:
                    continue
                stack_items.append(
                    ft.Container(
                        top=_decision_line_top(line.id, value, graph_height=graph_height, scale_max=graph.scale_max),
                        width=width,
                        height=2 if line.id in {"start", "stop"} else 1,
                        bgcolor=THRESHOLD_LINE_COLORS.get(line.id, "#111827"),
                    )
                )
            bars.append(
                ft.Container(
                    width=width,
                    height=graph_height,
                    border=ft.border.only(right=ft.border.BorderSide(1, "#F3F4F6")),
                    content=ft.Stack(width=width, height=graph_height, controls=stack_items),
                    tooltip=(
                        f"{sample.t0 - graph.time_start:.1f}-{sample.t1 - graph.time_start:.1f}秒 / "
                        f"RMS {sample.rms:.0f} / Peak {sample.peak:.0f} / 理由 {sample.reason}"
                    ),
                )
            )
        intervals: list[ft.Control] = []
        for interval in graph.intervals:
            width = max(7, int(interval.width or _decision_width(interval.duration)))
            label = interval.label if width >= 54 else {
                "stt_candidate": "STT",
                "vad_discarded": "VAD",
                "short_discard": "短",
                "queue_dropped": "Q",
                "clipped": "clip",
                "guard_discard": "guard",
                "vad_active": "VAD",
                "idle": "",
            }.get(interval.kind, "")
            intervals.append(
                ft.Container(
                    width=width,
                    height=28,
                    padding=ft.padding.symmetric(horizontal=4, vertical=2),
                    bgcolor=decision_interval_color(interval.kind),
                    border=ft.border.only(right=ft.border.BorderSide(1, "#FFFFFF")),
                    alignment=ft.alignment.center,
                    tooltip=(
                        f"{interval.t0 - graph.time_start:.1f}-{interval.t1 - graph.time_start:.1f}秒 / "
                        f"{interval.label} / {interval.reason or '-'} / {interval.chunk_count} chunk"
                    ),
                    content=ft.Text(label, size=10, color="#FFFFFF") if label else None,
                )
            )
        threshold_text = " / ".join(
            f"{line.label}: {'変動/推定' if line.variable else (str(round(line.value)) if line.value > 0 else '-')}"
            for line in graph.threshold_lines
        )
        short_text = (
            f"短すぎて破棄: {graph.short_discard_count}区間 "
            f"(最短 {graph.shortest_short_discard_seconds:.1f}秒 / 最長 {graph.longest_short_discard_seconds:.1f}秒)"
            if graph.short_discard_count
            else "短すぎて破棄: 0区間"
        )
        return ft.Container(
            padding=10,
            border=ft.border.all(1, "#E5E7EB"),
            border_radius=8,
            content=ft.Column(
                spacing=6,
                controls=[
                    ft.Text(f"{graph.title}: {'推定' if graph.estimated else 'producer統計'}", weight=ft.FontWeight.W_600),
                    ft.Text(graph.note, color="#4B5563", selectable=True),
                    ft.Row(spacing=1, controls=bars),
                    ft.Row(spacing=1, controls=intervals),
                    ft.Text("上段: RMS(濃青) / Peak(淡青)。下段: 同じ時間軸の判定区間。", color="#4B5563", selectable=True),
                    ft.Text(f"しきい値線: {threshold_text}", color="#4B5563", selectable=True),
                    ft.Text(short_text + "。min_voice_chunks相当の連続条件に届かなかった区間です。", color="#4B5563", selectable=True),
                ],
            ),
        )

    def _base_decision_trace(source: str, samples: list[dict[str, Any]], cfg_local: dict) -> tuple[AudioDecisionTrace, AudioDecisionTrace]:
        raw_trace = diagnosis_decision_traces.get(source)
        if raw_trace is None:
            raw_trace = build_decision_trace_from_samples(samples, source=source, sample_interval=0.5)
        if raw_trace.estimated:
            before_trace = simulate_decisions_for_config(raw_trace, cfg_local, source=source)
            before_trace = AudioDecisionTrace(
                source=before_trace.source,
                events=before_trace.events,
                estimated=True,
                note="producer統計がないため、現設定で同じ15秒メタデータを再判定した推定です。",
            )
        else:
            before_trace = raw_trace
        return raw_trace, before_trace

    def _render_decision_preview(source: str, cfg_local: dict, samples: list[dict[str, Any]]) -> None:
        raw_trace, before_trace = _base_decision_trace(source, samples, cfg_local)
        changes = _manual_adjustment_changes(source, cfg_local) or list(diagnosis_pending_changes)
        after_cfg = _cfg_with_changes(cfg_local, changes) if changes else copy.deepcopy(cfg_local)
        after_trace = simulate_decisions_for_config(before_trace, after_cfg, source=source)
        graph_vm = build_before_after_decision_graphs(before_trace, after_trace)
        before_visibility = candidate_visibility_from_graph(graph_vm.before)
        after_visibility = candidate_visibility_from_graph(graph_vm.after)
        visibility = analyze_candidate_visibility(raw_trace)

        diagnosis_trace_lanes.controls = [
            ft.Text("before と after は上下別グラフです。横軸、サンプル幅、縦スケールを揃えています。", color="#4B5563", selectable=True),
            _render_decision_graph(graph_vm.before),
            _render_decision_graph(graph_vm.after),
            ft.Text(
                "afterはraw PCMを使わず、15秒診断の軽量メタデータで再判定した推定です。",
                color="#4B5563",
                selectable=True,
            ),
        ]
        diagnosis_trace_compare.controls = [
            ft.Row(
                wrap=True,
                spacing=6,
                run_spacing=6,
                controls=[
                    ft.Container(
                        padding=ft.padding.symmetric(horizontal=8, vertical=5),
                        border=ft.border.all(1, "#CBD5E1"),
                        border_radius=6,
                        content=ft.Text(line, size=12, selectable=True),
                    )
                    for line in graph_vm.summary_lines
                ],
            ),
            ft.Text("この比較から分かること: " + graph_vm.explanation, color="#111827", selectable=True),
        ]
        diagnosis_visibility.controls = [
            ft.Container(
                padding=8,
                border=ft.border.all(1, "#E5E7EB"),
                border_radius=6,
                content=ft.Column(
                    spacing=3,
                    controls=[
                        ft.Text(visibility.title, weight=ft.FontWeight.W_600),
                        ft.Text(visibility.message, color="#4B5563", selectable=True),
                        ft.Text(f"次に押す/確認すること: {visibility.next_action}", selectable=True),
                    ],
                ),
            )
        ]
        visibility_controls: list[ft.Control] = []
        if should_show_no_candidate_help(graph_vm.before):
            visibility_controls.append(
                ft.Container(
                    padding=8,
                    border=ft.border.all(1, "#E5E7EB"),
                    border_radius=6,
                    content=ft.Column(
                        spacing=3,
                        controls=[
                            ft.Text("before: 緑が出ない場合の切り分け", weight=ft.FontWeight.W_600),
                            ft.Text(before_visibility.message, color="#4B5563", selectable=True),
                            ft.Text(f"次に確認すること: {before_visibility.action}", selectable=True),
                        ],
                    ),
                )
            )
        if should_show_no_candidate_help(graph_vm.after):
            visibility_controls.append(
                ft.Container(
                    padding=8,
                    border=ft.border.all(1, "#E5E7EB"),
                    border_radius=6,
                    content=ft.Column(
                        spacing=3,
                        controls=[
                            ft.Text("after: 緑が出ない場合の切り分け", weight=ft.FontWeight.W_600),
                            ft.Text(after_visibility.message, color="#4B5563", selectable=True),
                            ft.Text(f"次に確認すること: {after_visibility.action}", selectable=True),
                        ],
                    ),
                )
            )
        diagnosis_visibility.controls = visibility_controls
        diagnosis_visibility_section.controls = (
            [
                ft.Text("緑が出ない場合の切り分け", weight=ft.FontWeight.W_600),
                diagnosis_visibility,
            ]
            if visibility_controls
            else []
        )

    def _render_adjustment_controls() -> None:
        rows: list[ft.Control] = []
        for template in ADJUSTMENT_AXES:
            axis = adjustment_axis_display(template.key, adjustment_levels.get(template.key, 0))
            rows.append(
                ft.Container(
                    padding=10,
                    border=ft.border.all(1, "#E5E7EB"),
                    border_radius=8,
                    content=ft.Column(
                        spacing=6,
                        controls=[
                            ft.Row(
                                spacing=8,
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                controls=[
                                    ft.OutlinedButton(axis.negative_label, on_click=_adjust_axis(axis.key, -1)),
                                    ft.Text(f"{axis.label}: Lv.{axis.after:+d}", width=130, text_align=ft.TextAlign.CENTER),
                                    ft.OutlinedButton(axis.positive_label, on_click=_adjust_axis(axis.key, 1)),
                                ],
                            ),
                            ft.Text(adjustment_marker_text(axis), color="#4B5563", selectable=True),
                            ft.Row(
                                spacing=2,
                                controls=[
                                    ft.Container(
                                        width=34,
                                        height=5,
                                        bgcolor="#2563EB" if step == axis.after else "#CBD5E1",
                                        tooltip=f"Lv.{step}",
                                    )
                                    for step in range(-2, 3)
                                ],
                            ),
                        ],
                    ),
                )
            )
        diagnosis_adjustments.controls = [
            ft.Row(wrap=True, spacing=8, run_spacing=8, controls=rows),
            ft.OutlinedButton("標準へ戻す", on_click=_reset_adjustments),
        ]

    def _render_next_step(source: str) -> None:
        result = diagnosis_stable_results.get(source)
        if result is None or result.state == "insufficient":
            diagnosis_next_step.value = "次にすること: まだ調整しないでください。まず15秒診断を実行してください。"
            return
        text = f"{result.title} {result.message}"
        if "クリップ" in text or "音割れ" in text:
            diagnosis_next_step.value = "次にすること: AgendaSnap設定ではなく、Windows/マイク/Teams側の音量を下げてください。"
        elif "ノイズ" in text:
            diagnosis_next_step.value = "次にすること: ノイズを拾いにくくする方向を試し、再診断してください。"
        elif "声が拾われにくい" in text or "小さ" in text:
            diagnosis_next_step.value = "次にすること: 小さい声も拾う方向を試し、再診断してください。"
        else:
            diagnosis_next_step.value = "次にすること: 第一候補を適用して、同じ条件で再診断してください。"

    def _render_recommendation(source: str, cfg_local: dict) -> None:
        nonlocal diagnosis_pending_changes
        result = diagnosis_stable_results.get(source)
        diagnosis_pending_changes = []
        _render_next_step(source)
        _render_adjustment_controls()
        if result and result.recommended_action is not None:
            action = result.recommended_action
            diagnosis_pending_changes = list(action.changes)
            recommendation_controls: list[ft.Control] = [
                ft.Container(
                    padding=12,
                    border=ft.border.all(1, "#BFDBFE"),
                    border_radius=8,
                    bgcolor="#EFF6FF",
                    content=ft.Column(
                        spacing=5,
                        controls=[
                            ft.Text(f"第一候補: {action.title}", weight=ft.FontWeight.W_600),
                            ft.Text(f"何が変わるか: {action.what_changes}", selectable=True),
                            ft.Text(f"期待される効果: {action.effect}", selectable=True),
                            ft.Text(f"副作用: {action.side_effect}", color="#4B5563", selectable=True),
                            ft.Text(f"適用タイミング: {action.timing}", color="#4B5563", selectable=True),
                            ft.Text("元に戻せます。", color="#4B5563", selectable=True),
                        ],
                    ),
                )
            ]
            if action.changes:
                recommendation_controls.append(
                    ft.ExpansionTile(
                        title=ft.Text("第一候補の変更値"),
                        initially_expanded=False,
                        controls=_render_compact_changes(
                            list(action.changes),
                            title=action.title,
                            source=source,
                            result_action=action,
                        ),
                    )
                )
            else:
                recommendation_controls.append(
                    ft.Text("AgendaSnap設定の変更候補はありません。入力元側で調整してください。", color="#4B5563")
                )
            if result.alternative_actions:
                recommendation_controls.append(
                    ft.ExpansionTile(
                        title=ft.Text("他の候補を見る"),
                        initially_expanded=False,
                        controls=[
                            ft.Text(
                                f"{action.title}: {action.effect} / 副作用: {action.side_effect}",
                                selectable=True,
                            )
                            for action in result.alternative_actions
                        ],
                    )
                )
            diagnosis_recommendation.controls = recommendation_controls
        elif result is not None:
            diagnosis_recommendation.controls = [
                ft.Text("十分なデータがないため、推奨調整は出していません。", color="#4B5563", selectable=True),
                ft.Text("音を入れてから15秒診断を再実行してください。", color="#4B5563", selectable=True),
            ]
        else:
            diagnosis_recommendation.controls = [
                ft.Text("15秒診断を完了すると第一候補を表示します。", color="#4B5563", selectable=True),
            ]

        manual_changes = _manual_adjustment_changes(source, cfg_local)
        if manual_changes:
            diagnosis_pending_changes = manual_changes
            diagnosis_changes.controls = _render_compact_changes(
                manual_changes,
                title=_manual_adjustment_title(),
                source=source,
            )
        elif diagnosis_pending_changes:
            diagnosis_changes.controls = _render_compact_changes(
                list(diagnosis_pending_changes),
                title=(result.recommended_action.title if result and result.recommended_action else "第一候補"),
                source=source,
                result_action=(result.recommended_action if result else None),
            )
        else:
            diagnosis_changes.controls = [
                ft.Text("対義ペアのボタンを押すか、15秒診断を完了すると変更候補が表示されます。", color="#4B5563"),
            ]

    def _render_recent_warnings(source: str) -> None:
        warnings = diagnosis_warning_history.get(source) or ()
        if not warnings:
            diagnosis_recent_warnings.controls = [
                ft.Text("最近保持している重要警告はありません。", color="#4B5563", selectable=True)
            ]
            return
        diagnosis_recent_warnings.controls = [
            ft.Text(
                f"{card.title}: {card.reason or card.message} (信頼度: {card.confidence or '-'})",
                color="#4B5563",
                selectable=True,
            )
            for card in warnings
        ]

    def _render_comparison(source: str) -> None:
        before = diagnosis_before_result.get(source)
        after = diagnosis_after_result.get(source)
        if before is None:
            diagnosis_compare.controls = [
                ft.Text("適用後は再診断して、変更前後を比較してください。", color="#4B5563", selectable=True)
            ]
            return
        if after is None:
            diagnosis_compare.controls = [
                ft.Text(f"変更前: {before.title} / 信頼度 {before.confidence}", selectable=True),
                ft.Text("変更後: 未診断です。保存後に15秒診断を再実行してください。", color="#4B5563", selectable=True),
            ]
            return
        diagnosis_compare.controls = [
            ft.Text(f"変更前: {before.title} / {before.reason}", selectable=True),
            ft.Text(f"変更後: {after.title} / {after.reason}", selectable=True),
        ]

    def _complete_diagnosis_session(source: str) -> None:
        cfg_local = load_config(config_path)
        samples = list(diagnosis_test["samples"]) or diagnosis_ring[source].samples()
        level = _current_level(cfg_local, source)
        result = build_stable_diagnosis(
            level,
            source=source,
            history=samples,
            cfg=cfg_local,
            now=time.time(),
            previous_warnings=diagnosis_warning_history[source],
            sample_interval=0.5,
        )
        diagnosis_stable_results[source] = result
        diagnosis_warning_history[source] = result.warning_history
        if diagnosis_before_result.get(source) is not None:
            diagnosis_after_result[source] = result
        diagnosis_test["active"] = False
        diagnosis_live_mode[source] = "final" if result.state != "insufficient" else "insufficient"
        observed_samples = list(samples)
        diagnosis_decision_traces[source] = build_decision_trace_from_samples(
            observed_samples,
            source=source,
            sample_interval=0.5,
        )
        if observed_samples:
            diagnosis_last_observed_at[source] = float(observed_samples[-1].get("timestamp", time.time()) or time.time())
        diagnosis_monitor.stop()
        diagnosis_observing.value = "診断完了。ライブ状態は停止中で、結果は固定表示しています。"
        _refresh_diagnosis(update=False)
        page.update()

    def _input_test_timer(source: str) -> None:
        while bool(diagnosis_test["active"]):
            remaining = max(0.0, float(diagnosis_test["duration"]) - (time.time() - float(diagnosis_test["started_at"])))
            diagnosis_observing.value = f"観測中: 残り {remaining:.0f}秒。{diagnosis_instruction(source)}"
            page.update()
            if remaining <= 0:
                _complete_diagnosis_session(source)
                return
            time.sleep(0.5)

    def _start_diagnosis_test(_e: ft.ControlEvent | None = None) -> None:
        source = str(diagnosis_source.value or "sys")
        if args.session_running:
            _snack("会議セッション実行中は設定画面の入力テストを無効化しています。メイン画面の状態を見てください。", error=True)
            page.update()
            return
        diagnosis_test["active"] = True
        diagnosis_test["source"] = source
        diagnosis_test["started_at"] = time.time()
        diagnosis_test["samples"] = []
        diagnosis_decision_traces[source] = None
        diagnosis_live_mode[source] = "running"
        diagnosis_last_observed_at[source] = None
        diagnosis_observing.value = f"観測中: 残り 15秒。{diagnosis_instruction(source)}"
        diagnosis_monitor.start(source)
        threading.Thread(target=_input_test_timer, args=(source,), daemon=True).start()
        _refresh_diagnosis()

    def _on_input_test_level(level: LiveAudioLevel) -> None:
        source = level.source
        data = level.to_dict()
        diagnosis_latest[source] = data
        diagnosis_ring[source].add(data)
        diagnosis_live_mode[source] = "running" if diagnosis_test["active"] else diagnosis_live_mode.get(source, "idle")
        diagnosis_last_observed_at[source] = float(data.get("timestamp", time.time()) or time.time())
        if diagnosis_test["active"] and diagnosis_test["source"] == source:
            diagnosis_test["samples"].append(data)
        _refresh_diagnosis(update=False)
        page.update()

    def _on_input_test_error(source: str, message: str) -> None:
        cfg_local = load_config(config_path)
        fallback = _source_level_from_config(cfg_local, source).to_dict()
        input_is_off = "OFF" in message
        fallback["enabled"] = not input_is_off
        fallback["timestamp"] = time.time()
        fallback["error"] = None if input_is_off else message
        diagnosis_latest[source] = fallback
        diagnosis_ring[source].add(fallback)
        diagnosis_live_mode[source] = "final"
        diagnosis_last_observed_at[source] = float(fallback["timestamp"])
        if diagnosis_test["active"] and diagnosis_test["source"] == source:
            diagnosis_test["samples"].append(fallback)
        diagnosis_observing.value = f"入力テストを開始できません: {message}"
        _refresh_diagnosis(update=False)
        page.update()

    def _refresh_diagnosis(_e: ft.ControlEvent | None = None, *, update: bool = True) -> None:
        cfg_local = load_config(config_path)
        source = str(diagnosis_source.value or "sys")
        level = _current_level(cfg_local, source)
        level_data = _level_dict(level)
        if not diagnosis_ring[source].samples():
            diagnosis_ring[source].add(level_data)
        samples = diagnosis_ring[source].samples()
        state = user_state_label(level_data, samples)
        device_name = str(level_data.get("device_name") or "").strip()
        device_index = level_data.get("device_index")
        live_status = live_status_display(diagnosis_live_mode.get(source, "idle"), diagnosis_last_observed_at.get(source))
        diagnosis_state.value = f"{live_status.title} / 入力状態: {state}"
        diagnosis_device.value = (
            f"{live_status.observed_label} / デバイス: "
            f"{device_name or ('index ' + str(device_index) if device_index is not None else 'Default / Auto または未計測')}"
        )
        value_prefix = "最終観測値" if diagnosis_live_mode.get(source) in {"final", "insufficient"} else "現在値"
        diagnosis_metrics.value = (
            f"{value_prefix}: RMS {float(level_data.get('rms', 0.0) or 0.0):.0f} / "
            f"Peak {float(level_data.get('peak', 0.0) or 0.0):.0f} / "
            f"dBFS {float(level_data.get('dbfs', -120.0) or -120.0):.1f} / "
            f"threshold {float(level_data.get('threshold', 0.0) or 0.0):.0f} / "
            f"VAD {bool(level_data.get('vad_active', False))} / "
            f"clip {bool(level_data.get('clipped', False))} / "
            f"error {level_data.get('error') or '-'}"
        )
        diagnosis_stats.value = (
            f"produced {int(level_data.get('produced', 0) or 0)} / "
            f"VAD破棄 {int(level_data.get('dropped_energy', 0) or 0)} "
            f"({vad_discard_rate(level_data) * 100:.0f}%) / "
            f"queue破棄 {int(level_data.get('dropped_full', 0) or 0)} "
            f"({queue_drop_rate(level_data) * 100:.0f}%) / "
            f"noise_rms {level_data.get('noise_rms') if level_data.get('noise_rms') is not None else '-'}"
        )
        if args.session_running:
            diagnosis_live_hint.value = (
                "会議セッション実行中のため、設定画面の入力テストは無効です。"
                "メイン画面のlive telemetryを確認し、このタブで設定保存と再診断導線を使ってください。"
            )
        else:
            diagnosis_live_hint.value = (
                live_status.note + " 設定画面の入力テストは一時的な軽量モニターです。音声データ本体は保存しません。"
            )
        if not diagnosis_test["active"] and not diagnosis_observing.value:
            diagnosis_observing.value = "15秒診断を開始すると、完了後に結果を固定表示します。"
        lines = threshold_lines(source, cfg_local.get("audio", {}), level_data)
        diagnosis_lines.value = "\n".join(threshold_line_text(lines))
        diagnosis_line_details.value = "\n".join(threshold_line_text(lines, expert=True))
        _render_graph(source, level_data, samples, lines)
        interpretations = build_graph_interpretations(level_data, source=source, history=samples)
        diagnosis_graph_reading.controls = [
            ft.Container(
                padding=8,
                border=ft.border.all(1, "#E5E7EB"),
                border_radius=6,
                content=ft.Column(
                    spacing=3,
                    controls=[
                        ft.Text(item.title, weight=ft.FontWeight.W_600),
                        ft.Text(item.message, color="#4B5563", selectable=True),
                        ft.Text(f"次にすること: {item.action}", selectable=True),
                        ft.Text(f"根拠: {item.reason}", color="#4B5563", selectable=True),
                    ],
                ),
            )
            for item in interpretations
        ]
        live_cards = build_diagnosis_cards(level_data, source=source, history=samples)
        visible_cards, _hidden_cards = split_cards(live_cards, limit=1)
        diagnosis_cards_column.controls = [
            ft.Text(
                visible_cards[0].message if visible_cards else "ライブ状態は診断結果を即時に置き換えません。",
                color="#4B5563",
                selectable=True,
            )
        ]
        _render_stable_result(source)
        _render_recommendation(source, cfg_local)
        _render_decision_preview(source, cfg_local, samples)
        _render_recent_warnings(source)
        _render_comparison(source)
        if update:
            page.update()

    def _apply_diagnosis_changes(_e: ft.ControlEvent) -> None:
        nonlocal diagnosis_undo_cfg
        if not diagnosis_pending_changes:
            _snack("保存するAgendaSnap設定候補がありません。入力元側の調整または再診断を行ってください。", error=True)
            page.update()
            return
        source = str(diagnosis_source.value or "sys")
        cfg_local = load_config(config_path)
        diagnosis_undo_cfg = copy.deepcopy(cfg_local)
        diagnosis_before_result[source] = diagnosis_stable_results.get(source)
        diagnosis_after_result[source] = None
        for change in diagnosis_pending_changes:
            _set_nested(cfg_local, change.key, change.after)
        try:
            validate_config(cfg_local)
        except Exception as exc:  # noqa: BLE001
            _snack(f"変更候補を適用できません: {exc}", error=True)
            page.update()
            return
        saved_path = save_config(config_path, cfg_local)
        _snack(f"音声調整を保存しました: {saved_path}。適用後は15秒診断を再実行してください。")
        _refresh_diagnosis()

    def _undo_diagnosis_changes(_e: ft.ControlEvent) -> None:
        nonlocal diagnosis_undo_cfg
        if diagnosis_undo_cfg is None:
            _snack("元に戻す変更はありません。", error=True)
            page.update()
            return
        save_config(config_path, diagnosis_undo_cfg)
        diagnosis_undo_cfg = None
        source = str(diagnosis_source.value or "sys")
        diagnosis_before_result[source] = None
        diagnosis_after_result[source] = None
        _snack("直前の音声調整を元に戻しました。")
        _refresh_diagnosis()

    def _adjust_axis(axis_key: str, direction: int):
        def _handler(_e: ft.ControlEvent) -> None:
            adjustment_levels[axis_key] = adjustment_step(adjustment_levels.get(axis_key, 0), direction)
            _refresh_diagnosis()

        return _handler

    def _reset_adjustments(_e: ft.ControlEvent | None = None) -> None:
        for axis in ADJUSTMENT_AXES:
            adjustment_levels[axis.key] = 0
        _refresh_diagnosis()

    diagnosis_source.on_change = _refresh_diagnosis
    _refresh_diagnosis(update=False)

    audio_diagnosis_tab = ft.Column(
        spacing=14,
        scroll=ft.ScrollMode.AUTO,
        expand=True,
        controls=[
            ft.Text("音声診断・調整", size=18, weight=ft.FontWeight.W_600),
            ft.Text(
                "ライブ状態と診断結果を分けて表示します。診断結果と推奨調整は15秒程度の観測完了後に固定表示します。",
                color="#4B5563",
                selectable=True,
            ),
            ft.Text("1. 入力ソース選択", weight=ft.FontWeight.W_600),
            ft.Row(
                spacing=10,
                controls=[
                    diagnosis_source,
                    ft.ElevatedButton(
                        "15秒診断を開始",
                        on_click=_start_diagnosis_test,
                        disabled=bool(args.session_running),
                    ),
                    ft.OutlinedButton("更新", on_click=_refresh_diagnosis),
                ],
            ),
            diagnosis_live_hint,
            ft.Text("2. ライブ状態", weight=ft.FontWeight.W_600),
            diagnosis_state,
            diagnosis_device,
            diagnosis_metrics,
            diagnosis_stats,
            ft.Text("ライブ状態からの最重要メッセージ", weight=ft.FontWeight.W_600),
            diagnosis_cards_column,
            ft.Text("3. 観測中ステータス", weight=ft.FontWeight.W_600),
            diagnosis_observing,
            ft.Text("RMS / Peak 推移", weight=ft.FontWeight.W_600),
            ft.Row(
                wrap=True,
                spacing=8,
                run_spacing=6,
                controls=[
                    ft.Container(width=10, height=10, bgcolor=GRAPH_SAMPLE_COLORS["STT送信候補"]),
                    ft.Text("STT送信候補", color=LIGHT_MUTED),
                    ft.Container(width=10, height=10, bgcolor=GRAPH_SAMPLE_COLORS["VAD破棄"]),
                    ft.Text("VAD破棄", color=LIGHT_MUTED),
                    ft.Container(width=10, height=10, bgcolor=GRAPH_SAMPLE_COLORS["クリップ"]),
                    ft.Text("クリップ", color=LIGHT_MUTED),
                    ft.Container(width=10, height=10, bgcolor=GRAPH_SAMPLE_COLORS["VAD検出"]),
                    ft.Text("VAD検出", color=LIGHT_MUTED),
                ],
            ),
            diagnosis_graph,
            ft.Text("4. グラフ読み取り結果", weight=ft.FontWeight.W_600),
            diagnosis_graph_reading,
            ft.Text("判定区間 before / after", weight=ft.FontWeight.W_600),
            diagnosis_trace_lanes,
            ft.Text("before / after 数値比較", weight=ft.FontWeight.W_600),
            diagnosis_trace_compare,
            diagnosis_visibility_section,
            ft.Text("グラフ上の線", weight=ft.FontWeight.W_600),
            diagnosis_lines,
            ft.Divider(),
            ft.Text("5. 直近15秒の診断結果", weight=ft.FontWeight.W_600),
            diagnosis_stable_column,
            ft.Text("調整ガイド", weight=ft.FontWeight.W_600),
            diagnosis_next_step,
            ft.Text("6. 推奨調整", weight=ft.FontWeight.W_600),
            diagnosis_recommendation,
            ft.Text("調整軸", weight=ft.FontWeight.W_600),
            ft.Text("左右のボタンで -2 から +2 まで段階的に調整します。▲が変更前、●が変更後です。", color="#4B5563"),
            diagnosis_adjustments,
            ft.Text("7. 変更候補", weight=ft.FontWeight.W_600),
            ft.Text("変更候補は一括サマリーとコンパクトな変更値で確認します。Basic表示ではExpert keyを主表示しません。", color="#4B5563"),
            diagnosis_changes,
            ft.Text("8. 適用 / 元に戻す", weight=ft.FontWeight.W_600),
            ft.Row(
                spacing=10,
                controls=[
                    ft.ElevatedButton("変更候補を保存", on_click=_apply_diagnosis_changes),
                    ft.OutlinedButton("元に戻す", on_click=_undo_diagnosis_changes),
                    ft.OutlinedButton("保存後に再診断", on_click=_start_diagnosis_test, disabled=bool(args.session_running)),
                ],
            ),
            ft.Text("変更前後の比較", weight=ft.FontWeight.W_600),
            diagnosis_compare,
            ft.Text("最近の警告", weight=ft.FontWeight.W_600),
            diagnosis_recent_warnings,
            ft.Text("9. 困ったときのヒント", weight=ft.FontWeight.W_600),
            ft.ExpansionTile(
                title=ft.Text("困ったときのヒント"),
                initially_expanded=False,
                controls=[
                    ft.Text(f"{card.title}: {card.message}", selectable=True)
                    for card in help_cards()
                ],
            ),
            ft.ExpansionTile(
                title=ft.Text("10. Expert詳細"),
                initially_expanded=False,
                controls=[diagnosis_line_details],
            ),
        ],
    )
    audio_diagnosis_tab.controls = [
        ft.Text("音声診断・調整", size=18, weight=ft.FontWeight.W_600),
        ft.Text(
            "ライブ状態と15秒診断結果を分けて表示します。診断完了後は、安定診断として第一候補とbefore / afterを固定表示します。",
            color="#4B5563",
            selectable=True,
        ),
        ft.Text("1. 入力ソース", weight=ft.FontWeight.W_600),
        diagnosis_source,
        ft.Text("2. 15秒診断開始", weight=ft.FontWeight.W_600),
        ft.Row(
            spacing=10,
            controls=[
                ft.ElevatedButton(
                    "15秒診断を開始",
                    on_click=_start_diagnosis_test,
                    disabled=bool(args.session_running),
                ),
                ft.Text(
                    "診断中の入力設定変更では会議セッションを終了しません。実行中は次の入力開始時に反映される項目があります。",
                    color="#4B5563",
                    selectable=True,
                    expand=True,
                ),
            ],
        ),
        ft.Text("3. 観測中ステータス", weight=ft.FontWeight.W_600),
        diagnosis_state,
        diagnosis_device,
        diagnosis_metrics,
        diagnosis_stats,
        diagnosis_observing,
        ft.Text("ライブ状態からの注意", weight=ft.FontWeight.W_600),
        diagnosis_cards_column,
        ft.Text("4. before / after グラフ", weight=ft.FontWeight.W_600),
        ft.Row(
            wrap=True,
            spacing=8,
            run_spacing=6,
            controls=[
                ft.Container(width=10, height=10, bgcolor=GRAPH_SAMPLE_COLORS["STT送信候補"]),
                ft.Text("STT送信候補", color=LIGHT_MUTED),
                ft.Container(width=10, height=10, bgcolor=GRAPH_SAMPLE_COLORS["VAD破棄"]),
                ft.Text("VAD破棄", color=LIGHT_MUTED),
                ft.Container(width=10, height=10, bgcolor=GRAPH_SAMPLE_COLORS["クリップ"]),
                ft.Text("クリップ", color=LIGHT_MUTED),
                ft.Container(width=10, height=10, bgcolor=GRAPH_SAMPLE_COLORS["VAD検出"]),
                ft.Text("短すぎ/guard/queue", color=LIGHT_MUTED),
            ],
        ),
        diagnosis_trace_lanes,
        ft.Text("しきい値ライン", weight=ft.FontWeight.W_600),
        diagnosis_lines,
        ft.Text("5. グラフ読み取り結果", weight=ft.FontWeight.W_600),
        diagnosis_graph_reading,
        diagnosis_visibility_section,
        ft.Text("6. 第一候補の推奨調整", weight=ft.FontWeight.W_600),
        diagnosis_stable_column,
        diagnosis_next_step,
        diagnosis_recommendation,
        ft.Text("7. 調整軸", weight=ft.FontWeight.W_600),
        ft.Text(
            "左右のボタンで -2 から +2 まで段階的に調整します。▲ が変更前、● が変更後です。",
            color="#4B5563",
            selectable=True,
        ),
        diagnosis_adjustments,
        ft.Text("8. 変更候補一覧", weight=ft.FontWeight.W_600),
        ft.Text(
            "Basic表示ではExpert keyを主表示せず、変更の意味と影響を優先します。Expert表示ではkey/valueを確認できます。",
            color="#4B5563",
            selectable=True,
        ),
        diagnosis_changes,
        ft.Text("9. 適用 / 元に戻す / 再診断", weight=ft.FontWeight.W_600),
        ft.Row(
            spacing=10,
            controls=[
                ft.ElevatedButton("変更候補を保存", on_click=_apply_diagnosis_changes),
                ft.OutlinedButton("元に戻す", on_click=_undo_diagnosis_changes),
                ft.OutlinedButton(
                    "保存後に再診断",
                    on_click=_start_diagnosis_test,
                    disabled=bool(args.session_running),
                ),
            ],
        ),
        ft.Text("before / after の比較サマリー", weight=ft.FontWeight.W_600),
        diagnosis_trace_compare,
        ft.Text("変更前後の比較", weight=ft.FontWeight.W_600),
        diagnosis_compare,
        ft.Text("最近の警告", weight=ft.FontWeight.W_600),
        diagnosis_recent_warnings,
        ft.Text("10. 困ったときのヒント", weight=ft.FontWeight.W_600),
        ft.ExpansionTile(
            title=ft.Text("困ったときのヒント"),
            initially_expanded=False,
            controls=[
                ft.Text(f"{card.title}: {card.message}", selectable=True)
                for card in help_cards()
            ],
        ),
        ft.Text("11. Expert詳細", weight=ft.FontWeight.W_600),
        ft.ExpansionTile(
            title=ft.Text("Expert詳細"),
            initially_expanded=False,
            controls=[diagnosis_line_details, diagnosis_graph],
        ),
    ]
    tabs = ft.Tabs(
        selected_index=TAB_INDEX_BY_NAME.get(str(args.tab), 0),
        animation_duration=150,
        tabs=[
            ft.Tab(text="Basic", content=basic_tab),
            ft.Tab(text="音声診断・調整", content=audio_diagnosis_tab),
            ft.Tab(text="AI利用設定", content=ai_key_tab),
            ft.Tab(text="Expert", content=expert_tab),
        ],
        expand=1,
    )
    tabs.tabs[1].text = "音声診断・調整"
    tabs.tabs[2].text = "AI利用設定"

    def _on_close(_e) -> None:
        diagnosis_monitor.stop()

    page.on_close = _on_close
    page.add(header, actions, ft.Divider(), tabs)


if __name__ == "__main__":
    ft.app(target=main)
