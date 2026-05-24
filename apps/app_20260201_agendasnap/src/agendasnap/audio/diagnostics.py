"""User-facing audio diagnosis and safe tuning helpers."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, replace
import math
import time
from typing import Any, Iterable

from agendasnap.audio.levels import LiveAudioLevel, PCM16_CLIP_LEVEL


@dataclass(frozen=True)
class DiagnosisCard:
    title: str
    severity: str
    message: str
    actions: tuple[str, ...]
    reason: str = ""
    category: str = "current"
    created_at: float = 0.0
    last_updated_at: float = 0.0
    expires_at: float | None = None
    sticky: bool = False
    confidence: str = ""


@dataclass(frozen=True)
class ThresholdLine:
    id: str
    label: str
    value: float
    config_key: str | None
    draggable: bool
    warning: str | None = None


@dataclass(frozen=True)
class ConfigChange:
    key: str
    before: Any
    after: Any
    timing: str
    effect: str
    side_effect: str = ""


@dataclass(frozen=True)
class GraphInterpretation:
    title: str
    severity: str
    message: str
    action: str
    reason: str


@dataclass(frozen=True)
class AudioDecisionEvent:
    source: str
    t0: float
    t1: float
    rms: float
    peak: float
    dbfs: float
    threshold: float
    start_threshold: float
    stop_threshold: float
    noise_rms: float | None
    clipped: bool
    decision: str
    reason: str
    produced_count: int | None = None
    dropped_energy_count: int | None = None
    dropped_full_count: int | None = None
    queue_size: int | None = None
    queue_max: int | None = None
    estimated: bool = False

    @property
    def duration(self) -> float:
        return max(0.0, float(self.t1) - float(self.t0))


@dataclass(frozen=True)
class AudioDecisionTrace:
    source: str
    events: tuple[AudioDecisionEvent, ...]
    estimated: bool = False
    note: str = ""


@dataclass(frozen=True)
class DecisionTraceMetrics:
    stt_candidate_count: int
    stt_candidate_seconds: float
    vad_discarded_count: int
    vad_discarded_seconds: float
    queue_dropped_count: int
    clipped_count: int
    average_candidate_seconds: float
    longest_discarded_seconds: float


@dataclass(frozen=True)
class DecisionTraceComparison:
    before: DecisionTraceMetrics
    after: DecisionTraceMetrics
    summary: str
    estimated: bool


@dataclass(frozen=True)
class CandidateVisibilityIssue:
    state: str
    title: str
    message: str
    next_action: str


@dataclass(frozen=True)
class TuningRecommendation:
    id: str
    title: str
    what_changes: str
    effect: str
    side_effect: str
    timing: str
    reversible: bool = True
    changes: tuple[ConfigChange, ...] = ()


@dataclass(frozen=True)
class StableDiagnosis:
    source: str
    state: str
    title: str
    message: str
    reason: str
    confidence: str
    recommended_action: TuningRecommendation | None
    alternative_actions: tuple[TuningRecommendation, ...]
    observed_seconds: float
    sample_count: int
    created_at: float
    expires_at: float | None = None
    sticky: bool = False
    cards: tuple[DiagnosisCard, ...] = ()
    warning_history: tuple[DiagnosisCard, ...] = ()


class AudioLevelRingBuffer:
    def __init__(self, *, seconds: float = 20.0, sample_interval: float = 0.2) -> None:
        maxlen = max(1, int(float(seconds) / max(float(sample_interval), 0.05)))
        self._items: deque[dict[str, Any]] = deque(maxlen=maxlen)
        self._last_counts: dict[str, tuple[int, int, int]] = {}

    def add(self, level: LiveAudioLevel | dict[str, Any]) -> None:
        data = level.to_dict() if isinstance(level, LiveAudioLevel) else dict(level)
        source = str(data.get("source") or "")
        produced_raw = data.get("produced")
        dropped_energy_raw = data.get("dropped_energy")
        dropped_full_raw = data.get("dropped_full")
        produced = _as_int(produced_raw)
        dropped_energy = _as_int(dropped_energy_raw)
        dropped_full = _as_int(dropped_full_raw)
        last_counts = self._last_counts.get(source)
        stt_candidate = bool(data.get("stt_send_candidate", False))
        vad_discarded = bool(data.get("vad_discarded", False))
        queue_dropped = bool(data.get("queue_dropped", False))
        if last_counts is not None:
            stt_candidate = stt_candidate or produced > last_counts[0]
            vad_discarded = vad_discarded or dropped_energy > last_counts[1]
            queue_dropped = queue_dropped or dropped_full > last_counts[2]
        if source:
            self._last_counts[source] = (produced, dropped_energy, dropped_full)
        threshold = float(data.get("threshold", data.get("energy_threshold", 0.0)) or 0.0)
        sample = {
            "source": source,
            "timestamp": float(data.get("timestamp", 0.0) or 0.0),
            "rms": float(data.get("rms", 0.0) or 0.0),
            "peak": float(data.get("peak", 0.0) or 0.0),
            "threshold": threshold,
            "vad_active": bool(data.get("vad_active", False)),
            "clipped": bool(data.get("clipped", False)),
            "noise_rms": _as_optional_float(data.get("noise_rms")),
            "energy_threshold": _as_optional_float(data.get("energy_threshold", threshold)),
            "produced": produced if produced_raw is not None else None,
            "dropped_energy": dropped_energy if dropped_energy_raw is not None else None,
            "dropped_full": dropped_full if dropped_full_raw is not None else None,
            "queue_size": _as_optional_int(data.get("queue_size")),
            "queue_max": _as_optional_int(data.get("queue_max")),
            "stt_send_candidate": stt_candidate,
            "vad_discarded": vad_discarded,
            "queue_dropped": queue_dropped,
        }
        sample["sample_kind"] = graph_sample_kind(sample)
        self._items.append(sample)

    def samples(self) -> list[dict[str, Any]]:
        return list(self._items)


def _data(level: LiveAudioLevel | dict[str, Any]) -> dict[str, Any]:
    return level.to_dict() if isinstance(level, LiveAudioLevel) else dict(level)


def _as_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _as_optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return None


def _as_optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def vad_discard_rate(stats: LiveAudioLevel | dict[str, Any]) -> float:
    data = _data(stats)
    produced = _as_int(data.get("produced"))
    dropped = _as_int(data.get("dropped_energy"))
    total = produced + dropped
    return (dropped / total) if total > 0 else 0.0


def queue_drop_rate(stats: LiveAudioLevel | dict[str, Any]) -> float:
    data = _data(stats)
    produced = _as_int(data.get("produced"))
    dropped = _as_int(data.get("dropped_full"))
    total = produced + dropped
    return (dropped / total) if total > 0 else 0.0


def data_sufficiency(
    level: LiveAudioLevel | dict[str, Any],
    history: Iterable[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    data = _data(level)
    recent = list(history or [])[-100:]
    if not recent:
        recent = []
    sample_count = len(recent)
    nonzero_samples = sum(
        1
        for item in recent
        if float(item.get("rms", 0.0) or 0.0) > 0 or float(item.get("peak", 0.0) or 0.0) > 0
    )
    produced = max([_as_int(data.get("produced")), *[_as_int(item.get("produced")) for item in recent]])
    dropped_energy = max(
        [_as_int(data.get("dropped_energy")), *[_as_int(item.get("dropped_energy")) for item in recent]]
    )
    dropped_full = max([_as_int(data.get("dropped_full")), *[_as_int(item.get("dropped_full")) for item in recent]])
    observed_events = produced + dropped_energy + dropped_full
    has_audio = nonzero_samples > 0 or observed_events > 0
    enough = sample_count >= 5 and (nonzero_samples >= 3 or observed_events > 0)
    if enough:
        state = "ok"
        reason = "診断に必要な音声データがあります。"
    elif has_audio:
        state = "insufficient"
        reason = "サンプル数が少ないため、まだ診断できません。"
    else:
        state = "unmeasured"
        reason = "まだ診断に必要な音声データがありません。"
    return {
        "state": state,
        "enough": enough,
        "sample_count": sample_count,
        "nonzero_samples": nonzero_samples,
        "produced": produced,
        "dropped_energy": dropped_energy,
        "dropped_full": dropped_full,
        "observed_events": observed_events,
        "reason": reason,
    }


def graph_sample_kind(sample: LiveAudioLevel | dict[str, Any]) -> str:
    data = _data(sample)
    if bool(data.get("clipped", False)) or float(data.get("peak", 0.0) or 0.0) >= PCM16_CLIP_LEVEL:
        return "clip"
    if bool(data.get("queue_dropped", False)):
        return "queue_dropped"
    if bool(data.get("stt_send_candidate", False)):
        return "stt_candidate"
    if bool(data.get("vad_discarded", False)):
        return "vad_discarded"
    if bool(data.get("vad_active", False)):
        return "vad_active"
    return "idle"


def graph_sample_label(sample: LiveAudioLevel | dict[str, Any]) -> str:
    return {
        "clip": "クリップ",
        "queue_dropped": "キュー破棄",
        "stt_candidate": "STT送信候補",
        "vad_discarded": "VAD破棄",
        "vad_active": "VAD検出",
        "idle": "待機",
    }.get(graph_sample_kind(sample), "待機")


def _sample_decision_reason(data: dict[str, Any], decision: str) -> str:
    if decision == "clipped":
        return "clipped"
    if decision == "queue_dropped":
        return "queue_full"
    if decision == "stt_candidate":
        return "enqueued"
    if decision == "vad_discarded":
        return str(data.get("decision_reason") or data.get("reason") or "below_start_threshold")
    if data.get("produced") is None and data.get("dropped_energy") is None and data.get("dropped_full") is None:
        return "telemetry_missing"
    threshold = float(data.get("threshold", data.get("energy_threshold", 0.0)) or 0.0)
    rms = float(data.get("rms", 0.0) or 0.0)
    if threshold > 0 and rms < threshold:
        return "below_start_threshold"
    return "insufficient_data"


def decision_event_from_level(
    level: LiveAudioLevel | dict[str, Any],
    *,
    t0: float | None = None,
    t1: float | None = None,
    previous: LiveAudioLevel | dict[str, Any] | None = None,
    estimated: bool = False,
) -> AudioDecisionEvent:
    data = _data(level)
    prev = _data(previous) if previous is not None else None
    timestamp = float(data.get("timestamp", 0.0) or 0.0)
    end = float(t1) if t1 is not None else timestamp
    start = float(t0) if t0 is not None else max(0.0, end - 0.2)
    threshold = float(data.get("threshold", data.get("energy_threshold", 0.0)) or 0.0)
    start_threshold = float(data.get("start_threshold", threshold) or threshold)
    stop_threshold = float(data.get("stop_threshold", threshold) or threshold)
    produced = _as_optional_int(data.get("produced"))
    dropped_energy = _as_optional_int(data.get("dropped_energy"))
    dropped_full = _as_optional_int(data.get("dropped_full"))
    produced_delta = None if produced is None else produced - _as_int(prev.get("produced") if prev else 0)
    dropped_energy_delta = (
        None if dropped_energy is None else dropped_energy - _as_int(prev.get("dropped_energy") if prev else 0)
    )
    dropped_full_delta = None if dropped_full is None else dropped_full - _as_int(prev.get("dropped_full") if prev else 0)
    kind = graph_sample_kind(
        {
            **data,
            "stt_send_candidate": bool(data.get("stt_send_candidate")) or bool(produced_delta and produced_delta > 0),
            "vad_discarded": bool(data.get("vad_discarded")) or bool(dropped_energy_delta and dropped_energy_delta > 0),
            "queue_dropped": bool(data.get("queue_dropped")) or bool(dropped_full_delta and dropped_full_delta > 0),
        }
    )
    decision = {
        "clip": "clipped",
        "queue_dropped": "queue_dropped",
        "stt_candidate": "stt_candidate",
        "vad_discarded": "vad_discarded",
        "vad_active": "vad_active",
        "idle": "idle",
    }.get(kind, "unknown")
    return AudioDecisionEvent(
        source=str(data.get("source") or ""),
        t0=start,
        t1=max(end, start),
        rms=float(data.get("rms", 0.0) or 0.0),
        peak=float(data.get("peak", 0.0) or 0.0),
        dbfs=float(data.get("dbfs", -120.0) or -120.0),
        threshold=threshold,
        start_threshold=start_threshold,
        stop_threshold=stop_threshold,
        noise_rms=_as_optional_float(data.get("noise_rms")),
        clipped=bool(data.get("clipped", False)),
        decision=decision,
        reason=_sample_decision_reason(data, decision),
        produced_count=produced,
        dropped_energy_count=dropped_energy,
        dropped_full_count=dropped_full,
        queue_size=_as_optional_int(data.get("queue_size")),
        queue_max=_as_optional_int(data.get("queue_max")),
        estimated=estimated,
    )


def build_decision_trace_from_samples(
    samples: Iterable[LiveAudioLevel | dict[str, Any]],
    *,
    source: str,
    sample_interval: float = 0.2,
    estimated: bool | None = None,
) -> AudioDecisionTrace:
    items = [_data(sample) for sample in samples]
    events: list[AudioDecisionEvent] = []
    previous: dict[str, Any] | None = None
    for index, item in enumerate(items):
        ts = float(item.get("timestamp", 0.0) or 0.0)
        if index > 0:
            prev_ts = float(items[index - 1].get("timestamp", 0.0) or 0.0)
            t0 = prev_ts if prev_ts > 0 and ts >= prev_ts else max(0.0, ts - sample_interval)
        else:
            t0 = max(0.0, ts - sample_interval)
        event = decision_event_from_level(item, t0=t0, t1=ts, previous=previous, estimated=False)
        if event.source == source or not event.source:
            events.append(replace(event, source=source))
        previous = item
    has_counter = any(event.produced_count is not None for event in events)
    trace_estimated = (not has_counter) if estimated is None else bool(estimated)
    if trace_estimated:
        events = [replace(event, estimated=True) for event in events]
    return AudioDecisionTrace(
        source=source,
        events=tuple(events),
        estimated=trace_estimated,
        note="producer統計がないためRMS/Peakから推定しています。" if trace_estimated else "producer統計を含む判定履歴です。",
    )


def _history_summary(
    level: LiveAudioLevel | dict[str, Any],
    history: Iterable[dict[str, Any]] | None,
) -> dict[str, Any]:
    data = _data(level)
    recent = list(history or [])[-100:]
    if not recent:
        recent = [data]
    suff = data_sufficiency(data, history)
    rms_values = [float(item.get("rms", 0.0) or 0.0) for item in recent]
    threshold_values = [
        float(item.get("threshold", item.get("energy_threshold", 0.0)) or 0.0)
        for item in recent
        if float(item.get("threshold", item.get("energy_threshold", 0.0)) or 0.0) > 0
    ]
    threshold = float(data.get("threshold", data.get("energy_threshold", 0.0)) or 0.0)
    if threshold <= 0 and threshold_values:
        threshold = sum(threshold_values) / len(threshold_values)
    avg_rms = sum(rms_values) / len(rms_values) if rms_values else 0.0
    variance = sum((value - avg_rms) ** 2 for value in rms_values) / len(rms_values) if rms_values else 0.0
    rms_std = math.sqrt(variance)
    rms_cv = rms_std / max(avg_rms, 1.0)
    active_ratio = sum(1 for item in recent if item.get("vad_active")) / len(recent)
    clipped_recent = any(
        bool(item.get("clipped", False)) or float(item.get("peak", 0.0) or 0.0) >= PCM16_CLIP_LEVEL
        for item in recent
    )
    near_ratio = 0.0
    low_ratio = 0.0
    below_ratio = 0.0
    if threshold > 0 and recent:
        near_ratio = sum(1 for value in rms_values if threshold * 0.75 <= value <= threshold * 1.2) / len(recent)
        low_ratio = sum(1 for value in rms_values if 0 < value < threshold * 0.6) / len(recent)
        below_ratio = sum(1 for value in rms_values if value < threshold) / len(recent)
    noise_rms = _as_optional_float(data.get("noise_rms"))
    if noise_rms is None:
        for item in reversed(recent):
            noise_rms = _as_optional_float(item.get("noise_rms"))
            if noise_rms is not None:
                break
    noise_close = bool(threshold > 0 and noise_rms is not None and noise_rms >= threshold * 0.7)
    enough_history = len(recent) >= 5
    noise_like = bool(
        enough_history
        and active_ratio >= 0.35
        and threshold > 0
        and (avg_rms <= threshold * 1.15 or noise_close or (rms_cv <= 0.25 and avg_rms <= threshold * 1.3))
    )
    boundary = bool(enough_history and threshold > 0 and near_ratio >= 0.35 and not noise_like)
    return {
        "recent_count": len(recent),
        "active_ratio": active_ratio,
        "clipped_recent": clipped_recent,
        "avg_rms": avg_rms,
        "rms_cv": rms_cv,
        "threshold": threshold,
        "noise_rms": noise_rms,
        "noise_close": noise_close,
        "noise_like": noise_like,
        "boundary": boundary,
        "near_ratio": near_ratio,
        "low_ratio": low_ratio,
        "below_ratio": below_ratio,
        "vad_discard_rate": vad_discard_rate(data),
        "queue_drop_rate": queue_drop_rate(data),
        "sufficiency": suff,
    }


def user_state_label(level: LiveAudioLevel | dict[str, Any], history: Iterable[dict[str, Any]] | None = None) -> str:
    data = _data(level)
    summary = _history_summary(data, history)
    if data.get("error"):
        return "デバイスエラー"
    if not bool(data.get("enabled", False)):
        return "OFF"
    if summary["clipped_recent"]:
        return "クリップ"
    suff = summary["sufficiency"]
    if not suff["enough"]:
        return "未計測" if suff["state"] == "unmeasured" else "未判定"
    rms = float(data.get("rms", 0.0) or 0.0)
    threshold = float(summary["threshold"] or 0.0)
    if summary["noise_like"]:
        return "ノイズ多め"
    if rms <= 0:
        return "無音"
    if threshold > 0 and (rms < threshold * 0.6 or summary["low_ratio"] >= 0.6):
        return "小さすぎる"
    if summary["boundary"]:
        return "境界付近"
    if bool(data.get("vad_active", False)) or summary["active_ratio"] >= 0.2:
        return "音声検出中"
    return "無音"


def build_diagnosis_cards(
    level: LiveAudioLevel | dict[str, Any],
    *,
    source: str,
    history: Iterable[dict[str, Any]] | None = None,
) -> list[DiagnosisCard]:
    state = user_state_label(level, history)
    data = _data(level)
    summary = _history_summary(data, history)
    threshold = float(summary["threshold"] or 0.0)
    rms = float(data.get("rms", 0.0) or 0.0)
    suff = summary["sufficiency"]
    cards: list[DiagnosisCard] = []

    if state == "OFF":
        cards.append(
            DiagnosisCard(
                "入力がOFFです",
                "warning",
                "この入力ソースは録音・文字起こしに使われません。",
                ("入力をONにする",),
                reason="入力ソースが無効化されています。",
            )
        )
        return cards
    if state == "デバイスエラー":
        cards.append(
            DiagnosisCard(
                "デバイスエラー",
                "danger",
                str(data.get("error") or "入力デバイスを開けません。"),
                ("デバイスを選び直す",),
                reason="入力デバイスからエラーが返されています。",
            )
        )
        return cards
    if state == "クリップ":
        cards.append(
            DiagnosisCard(
                "音割れしています",
                "danger",
                "Peakがクリップ付近に達しています。AgendaSnapのしきい値ではなく、Windows/マイク/Teams側の音量を下げてください。",
                ("Windowsまたはマイク側の入力音量を下げる", "Teams/会議アプリ側のマイク音量を下げる"),
                reason="Peakがクリップ警告ラインに達した履歴があります。",
            )
        )
    if state in {"未計測", "未判定"}:
        source_hint = (
            "SYSTEM音声の場合は、Teams/Zoomなどで音声を再生してください。"
            if source == "sys"
            else "MICの場合は、マイクに向かって10秒ほど話してください。"
        )
        cards.append(
            DiagnosisCard(
                "まだ診断に必要な音声データがありません" if state == "未計測" else "まだ診断できません",
                "info",
                f"入力テストまたは会議開始後に10秒ほど音声を入れてください。{source_hint}",
                ("音声を入れてから更新する",),
                reason=str(suff["reason"]),
            )
        )
        return cards
    if threshold > 0 and (rms > 0 and rms < threshold * 0.6 or summary["low_ratio"] >= 0.6):
        cards.append(
            DiagnosisCard(
                "声が拾われにくい",
                "warning",
                "直近10秒の多くでしきい値未満です。小さい声がVADに届いていない可能性があります。",
                ("小さい声も拾う", "声の拾いやすさを少し上げる"),
                reason="RMSはありますが音声開始ラインを十分に超えていません。",
            )
        )
    if state == "境界付近":
        cards.append(
            DiagnosisCard(
                "しきい値の境界付近です",
                "warning",
                "RMSがしきい値付近を行き来しています。声が切れるなら拾いやすく、ノイズが多いなら拾いにくくします。",
                ("声が切れるなら声の拾いやすさを上げる", "ノイズが多いならノイズ除去の強さを上げる"),
                reason="RMSがしきい値の前後に集中しています。",
            )
        )
    if state == "ノイズ多め" or summary["noise_close"]:
        cards.append(
            DiagnosisCard(
                "ノイズを拾いすぎています",
                "warning",
                "無音に近いRMSなのにVADが反応しています。ノイズ床としきい値が近い可能性があります。",
                ("ノイズを拾いにくくする", "ノイズ除去の強さを上げる"),
                reason="直近履歴のVAD反応率が高く、RMS変動が小さい状態です。",
            )
        )
    if float(summary["vad_discard_rate"] or 0.0) >= 0.45:
        cards.append(
            DiagnosisCard(
                "VADで破棄される区間が多い",
                "warning",
                f"producer統計ではVAD破棄率が{summary['vad_discard_rate'] * 100:.0f}%です。声が小さいか、しきい値が高すぎる可能性があります。",
                ("声の拾いやすさを少し上げる", "ノイズが多い場合はノイズ除去を先に確認する"),
                reason="producedに対してdropped_energyが多い状態です。",
            )
        )
    if float(summary["queue_drop_rate"] or 0.0) > 0.05:
        cards.append(
            DiagnosisCard(
                "処理キューが詰まり気味です",
                "warning",
                f"producer統計ではキュー破棄率が{summary['queue_drop_rate'] * 100:.0f}%です。遅延や欠落の原因になります。",
                ("反応速度を速める", "他の重い処理を止める"),
                reason="producer統計でdropped_fullが発生しています。",
            )
        )
    if state == "音声検出中":
        cards.append(
            DiagnosisCard(
                "音声を拾えています",
                "ok",
                "現在の入力は声として検出されています。",
                ("この状態を基準に調整する",),
                reason="直近履歴でVADが音声として扱っています。",
            )
        )
    return cards


def _get(cfg: dict, path: str, default: Any = None) -> Any:
    cur: Any = cfg
    for key in path.split("."):
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return cur


def help_cards() -> list[DiagnosisCard]:
    return [
        DiagnosisCard(
            "声の頭が切れる場合",
            "info",
            "話し始めが欠けるときは、最初の小さい音を声として扱いやすくします。",
            ("声の頭切れを防ぐ",),
            reason="これは現在診断ではなく、困ったときのヒントです。",
            category="help",
        ),
        DiagnosisCard(
            "声の終わりが切れる場合",
            "info",
            "語尾が欠けるときは、短い無音で発話を終えにくくします。",
            ("声の終わりを長めに拾う",),
            reason="これは現在診断ではなく、困ったときのヒントです。",
            category="help",
        ),
        DiagnosisCard(
            "遅延が大きい場合",
            "info",
            "字幕や文字起こしの反応が遅いときは、短い単位で処理します。ただし安定性と精度に影響します。",
            ("反応を速くする", "精度を安定させる"),
            reason="これは現在診断ではなく、困ったときのヒントです。",
            category="help",
        ),
        DiagnosisCard(
            "文字起こし精度を上げたい場合",
            "info",
            "音は拾えているのに認識が悪い場合は、会議テーマや専門用語ヒントも見直します。",
            ("meeting.topic / glossary を入力する", "noise reduction を見直す"),
            reason="VADしきい値だけで直す問題ではない場合があります。",
            category="help",
        ),
    ]


def _change(
    cfg: dict,
    path: str,
    after: Any,
    effect: str,
    *,
    timing: str = "次回開始時に反映",
    side_effect: str = "",
) -> ConfigChange:
    return ConfigChange(path, _get(cfg, path), after, timing, effect, side_effect)


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def threshold_lines(source: str, audio_cfg: dict, level: LiveAudioLevel | dict[str, Any]) -> list[ThresholdLine]:
    data = _data(level)
    source_key = "sys" if source == "sys" else "mic"
    threshold = float(data.get("threshold", 0.0) or _get(audio_cfg, f"energy_threshold_{source_key}", 0.0) or 0.0)
    cal = audio_cfg.get("calibration") if isinstance(audio_cfg.get("calibration"), dict) else {}
    multiplier = float(cal.get("multiplier", 1.0) or 1.0)
    measured_noise = _as_optional_float(data.get("noise_rms"))
    noise_floor = max(0.0, measured_noise if measured_noise is not None else threshold / max(multiplier, 0.1))
    vad = audio_cfg.get("vad") if isinstance(audio_cfg.get("vad"), dict) else {}
    start_ratio = float(vad.get(f"start_ratio_{source_key}", 1.1 if source_key == "sys" else 1.8))
    stop_ratio = float(vad.get(f"stop_ratio_{source_key}", 0.85 if source_key == "sys" else 1.2))
    stop_value = max(noise_floor + 1.0, threshold * stop_ratio)
    start_value = max(stop_value + 1.0, threshold * start_ratio)
    return [
        ThresholdLine("noise", "ノイズ床", noise_floor, None, False),
        ThresholdLine("start", "音声開始ライン", start_value, f"audio.vad.start_ratio_{source_key}", True),
        ThresholdLine("stop", "音声継続ライン", stop_value, f"audio.vad.stop_ratio_{source_key}", True),
        ThresholdLine("clip", "クリップ警告", float(PCM16_CLIP_LEVEL), None, False),
    ]


def threshold_line_labels(lines: Iterable[ThresholdLine], *, expert: bool = False) -> list[str]:
    labels: list[str] = []
    for line in lines:
        text = f"{line.label}: {line.value:.0f}"
        if expert and line.config_key:
            text += f" ({line.config_key})"
        labels.append(text)
    return labels


def build_graph_interpretations(
    level: LiveAudioLevel | dict[str, Any],
    *,
    source: str,
    history: Iterable[dict[str, Any]] | None,
) -> tuple[GraphInterpretation, ...]:
    data = _data(level)
    samples = list(history or [])
    if not samples:
        samples = [data]
    visibility = analyze_candidate_visibility(build_decision_trace_from_samples(samples, source=source))
    summary = _history_summary(data, samples)
    count = max(len(samples), 1)
    threshold = float(summary.get("threshold", 0.0) or 0.0)
    rms_values = [float(item.get("rms", 0.0) or 0.0) for item in samples]
    nonzero_ratio = sum(1 for value in rms_values if value > 0.0) / count
    over_start_ratio = 0.0
    if threshold > 0:
        over_start_ratio = sum(1 for value in rms_values if value >= threshold) / count
    stt_candidate_ratio = sum(
        1 for item in samples if bool(item.get("stt_send_candidate", False)) or graph_sample_kind(item) == "stt_candidate"
    ) / count
    sample_vad_discard_ratio = sum(
        1 for item in samples if bool(item.get("vad_discarded", False)) or graph_sample_kind(item) == "vad_discarded"
    ) / count
    vad_drop = max(float(summary.get("vad_discard_rate", 0.0) or 0.0), sample_vad_discard_ratio)
    clipped = bool(summary.get("clipped_recent"))
    interpretations: list[GraphInterpretation] = []

    if clipped:
        interpretations.append(
            GraphInterpretation(
                title="赤いクリップがあります",
                severity="danger",
                message="入力音量が大きすぎます。AgendaSnap設定ではなく、Windows/マイク/Teams側の音量を下げてください。",
                action="Windows/マイク/Teams側の音量を下げる",
                reason="Peakがクリップ警告ラインに達した履歴があります。",
            )
        )
    if visibility.state != "ok":
        interpretations.append(
            GraphInterpretation(
                title=visibility.title,
                severity="info" if visibility.state in {"telemetry_missing", "display_mismatch"} else "warning",
                message=visibility.message,
                action=visibility.next_action,
                reason=visibility.state,
            )
        )
    if threshold > 0 and nonzero_ratio >= 0.3 and over_start_ratio <= 0.25:
        interpretations.append(
            GraphInterpretation(
                title="小さい声が捨てられている可能性",
                severity="warning",
                message="RMSが音声開始ラインを超えた割合が低く、声として扱われていない区間が多い可能性があります。",
                action="小さい声も拾う方向を試す",
                reason=f"音声開始ライン超過は{over_start_ratio * 100:.0f}%です。",
            )
        )
    if vad_drop >= 0.35:
        interpretations.append(
            GraphInterpretation(
                title="VAD破棄が多い",
                severity="warning",
                message="音は入っていますが、しきい値またはマイクガードが強すぎて捨てられている可能性があります。",
                action="声の拾いやすさを上げる。ノイズが多い場合はノイズ対策を先に確認する",
                reason=f"VAD破棄率は{vad_drop * 100:.0f}%です。",
            )
        )
    if stt_candidate_ratio <= 0.15 and nonzero_ratio >= 0.3 and not clipped:
        interpretations.append(
            GraphInterpretation(
                title="STT送信候補が少ない",
                severity="warning",
                message="グラフ上の緑はSTT送信候補です。送信済みとは断定せず、候補が少ない場合は音声として渡っていない可能性があります。",
                action="入力音量、音声開始ライン、VAD破棄を確認する",
                reason=f"STT送信候補の割合は{stt_candidate_ratio * 100:.0f}%です。",
            )
        )
    if bool(summary.get("noise_like")) or bool(summary.get("noise_close")):
        interpretations.append(
            GraphInterpretation(
                title="ノイズを拾いすぎている可能性",
                severity="warning",
                message="RMSがノイズ床付近に留まっているのにVADが反応しています。",
                action="ノイズを拾いにくくする方向を試す",
                reason="VAD反応率、RMS変動、ノイズ床の近さから判断しています。",
            )
        )
    if float(summary.get("queue_drop_rate", 0.0) or 0.0) > 0.05:
        interpretations.append(
            GraphInterpretation(
                title="queueが詰まっています",
                severity="warning",
                message="STT workerへ渡る前のqueueで破棄が起きています。設定調整だけでなく処理負荷も確認してください。",
                action="まずは『反応を速くする』を1段階上げるか、重い処理を止めてください",
                reason=f"queue破棄率は{float(summary.get('queue_drop_rate', 0.0) or 0.0) * 100:.0f}%です。",
            )
        )
    if not interpretations:
        interpretations.append(
            GraphInterpretation(
                title="大きな問題は見えていません",
                severity="ok",
                message="この観測範囲では、クリップや極端なVAD破棄は見つかっていません。",
                action="適用後も同じ条件で再診断する",
                reason=f"音声開始ライン超過は{over_start_ratio * 100:.0f}%、VAD破棄率は{vad_drop * 100:.0f}%です。",
            )
        )
    return tuple(interpretations)


SYMPTOM_LABELS = {
    "small_voice": "小さい声も拾う",
    "reduce_noise": "ノイズを減らす",
    "head_cut": "声の頭切れを防ぐ",
    "tail_cut": "声の終わりを長めに拾う",
    "faster": "反応を速くする",
    "stable": "精度を安定させる",
}


def symptom_tuning_changes(source: str, cfg: dict, symptom: str) -> list[ConfigChange]:
    symptom_key = str(symptom or "").strip().lower()
    if symptom_key == "small_voice":
        return easy_tuning_changes(source, cfg, "voice_pickup", 1)
    if symptom_key == "reduce_noise":
        return easy_tuning_changes(source, cfg, "noise_reduction", 1)
    if symptom_key == "head_cut":
        return easy_tuning_changes(source, cfg, "voice_pickup", 1)
    if symptom_key == "tail_cut":
        return easy_tuning_changes(source, cfg, "speech_continuity", 1)
    if symptom_key == "faster":
        return easy_tuning_changes(source, cfg, "response_speed", 1)
    if symptom_key == "stable":
        changes = easy_tuning_changes(source, cfg, "response_speed", -1)
        changes.extend(easy_tuning_changes(source, cfg, "noise_reduction", 1))
        return changes
    return []


def tuning_change_summary(change: ConfigChange) -> str:
    return f"{change.effect}: {change.before} -> {change.after}"


def easy_tuning_changes(source: str, cfg: dict, slider: str, value: int | str) -> list[ConfigChange]:
    source_key = "sys" if source == "sys" else "mic"
    level = int(value) if str(value).lstrip("-").isdigit() else 0
    level = int(_clamp(level, -2, 2))
    changes: list[ConfigChange] = []
    if slider == "voice_pickup":
        delta = -0.15 * level
        changes.append(_change(cfg, f"audio.vad.start_ratio_{source_key}", round(_clamp(float(_get(cfg, f"audio.vad.start_ratio_{source_key}", 1.5)) + delta, 0.5, 3.0), 2), "音声開始ラインを少し動かす", side_effect="下げると小さい声を拾いやすくなりますが、ノイズも拾いやすくなります。"))
        changes.append(_change(cfg, "audio.calibration.multiplier", round(_clamp(float(_get(cfg, "audio.calibration.multiplier", 1.6)) - 0.1 * level, 1.0, 3.0), 2), "自動しきい値の余裕を調整する", side_effect="下げると拾いやすくなりますが、環境ノイズにも反応しやすくなります。"))
        changes.append(_change(cfg, f"audio.vad.min_voice_chunks_{source_key}", max(1, int(_get(cfg, f"audio.vad.min_voice_chunks_{source_key}", 2)) - max(level, 0)), "声の頭の拾いやすさを調整する", side_effect="下げると反応は早くなりますが、一瞬のノイズも拾いやすくなります。"))
    elif slider == "noise_reduction":
        changes.append(_change(cfg, f"audio.vad.start_ratio_{source_key}", round(_clamp(float(_get(cfg, f"audio.vad.start_ratio_{source_key}", 1.5)) + 0.15 * level, 0.5, 3.5), 2), "ノイズを拾いにくくする", side_effect="上げすぎると小さい声を捨てやすくなります。"))
        changes.append(_change(cfg, "audio.calibration.multiplier", round(_clamp(float(_get(cfg, "audio.calibration.multiplier", 1.6)) + 0.15 * level, 1.0, 3.5), 2), "ノイズ床からの余裕を増やす", side_effect="上げると誤検出は減りますが、遠い声には弱くなります。"))
        changes.append(_change(cfg, f"audio.vad.min_voice_chunks_{source_key}", max(1, int(_get(cfg, f"audio.vad.min_voice_chunks_{source_key}", 1)) + max(level, 0)), "一瞬の音を捨てやすくする", side_effect="上げると短い発話の頭が遅れる可能性があります。"))
        if source_key == "mic" and level > 0:
            changes.append(_change(cfg, "audio.vad.guard_mic.enable", True, "マイクの定常ノイズを抑える", side_effect="弱い声や一定音量の話し方を拾いにくくする場合があります。"))
    elif slider == "speech_continuity":
        changes.append(_change(cfg, f"audio.vad.stop_ratio_{source_key}", round(_clamp(float(_get(cfg, f"audio.vad.stop_ratio_{source_key}", 1.0)) - 0.1 * level, 0.4, 2.5), 2), "語尾を切れにくくする", side_effect="下げすぎると無音やノイズまで発話につながりやすくなります。"))
        changes.append(_change(cfg, "stt.segment_gap_ms", max(200, int(_get(cfg, "stt.segment_gap_ms", 800)) + 100 * level), "短い間を同じ発話として扱う", side_effect="長くすると反応が少し遅くなります。"))
        changes.append(_change(cfg, "stt.min_turn_seconds", round(max(0.1, float(_get(cfg, "stt.min_turn_seconds", 0.6)) + 0.1 * level), 2), "短い発話をまとめる", side_effect="長くすると短い返答の確定が遅くなります。"))
    elif slider == "response_speed":
        changes.append(_change(cfg, "audio.chunk_ms", max(250, int(_get(cfg, "audio.chunk_ms", 500)) - 100 * level), "処理単位を短くする", side_effect="短くすると反応は速くなりますが、安定性や精度が下がる場合があります。"))
        changes.append(_change(cfg, "stt.segment_max_seconds", max(4, int(_get(cfg, "stt.segment_max_seconds", 12)) - 2 * level), "長い待ちを減らす", side_effect="短くすると文脈が分かれやすくなる場合があります。"))
        changes.append(_change(cfg, "stt.segment_gap_ms", max(300, int(_get(cfg, "stt.segment_gap_ms", 800)) - 100 * level), "発話区切りを早める", side_effect="短くすると語尾や短い間が分断される場合があります。"))
    elif slider == "auto_adjustment":
        mode = str(value).strip().lower()
        mapping = {
            "off": (False, 30, 0.1, 0.8),
            "weak": (True, 30, 0.1, 0.75),
            "standard": (True, 20, 0.2, 0.6),
            "strong": (True, 15, 0.25, 0.5),
        }
        enable, interval, max_step, smoothing = mapping.get(mode, mapping["standard"])
        changes.extend(
            [
                _change(cfg, "audio.vad.adaptive.enable", enable, "自動調整のON/OFF"),
                _change(cfg, "audio.vad.adaptive.update_interval_seconds", interval, "調整の頻度"),
                _change(cfg, "audio.vad.adaptive.max_step_ratio", max_step, "1回の調整幅"),
                _change(cfg, "audio.vad.adaptive.smoothing", smoothing, "急な変化を抑える"),
            ]
        )
    return [change for change in changes if change.before != change.after]


def diagnosis_instruction(source: str) -> str:
    if source == "sys":
        return "SYSTEMの場合: Teams/Zoomなどで音声を再生してください。"
    return "MICの場合: 普段の声量で話してください。"


def _stamp_card(
    card: DiagnosisCard,
    *,
    now: float,
    hold_seconds: float,
    confidence: str = "",
    sticky: bool | None = None,
) -> DiagnosisCard:
    sticky_value = bool(card.sticky) if sticky is None else bool(sticky)
    expires_at = None if sticky_value else now + max(1.0, float(hold_seconds))
    return DiagnosisCard(
        title=card.title,
        severity=card.severity,
        message=card.message,
        actions=card.actions,
        reason=card.reason,
        category=card.category,
        created_at=card.created_at or now,
        last_updated_at=now,
        expires_at=expires_at,
        sticky=sticky_value,
        confidence=confidence or card.confidence,
    )


def _is_important_warning(card: DiagnosisCard) -> bool:
    if card.severity == "danger":
        return True
    text = f"{card.title} {card.message}"
    return any(word in text for word in ("クリップ", "音割れ", "デバイスエラー", "ノイズ"))


def merge_warning_history(
    existing: Iterable[DiagnosisCard],
    cards: Iterable[DiagnosisCard],
    *,
    now: float | None = None,
    hold_seconds: float = 60.0,
) -> tuple[DiagnosisCard, ...]:
    """Keep important warning cards readable after the live state changes."""
    current_time = time.time() if now is None else float(now)
    merged: dict[str, DiagnosisCard] = {}
    for card in existing:
        expires_at = card.expires_at
        if card.sticky or expires_at is None or expires_at >= current_time:
            merged[card.title] = card
    for card in cards:
        if not _is_important_warning(card):
            continue
        merged[card.title] = _stamp_card(
            card,
            now=current_time,
            hold_seconds=hold_seconds,
            confidence=card.confidence,
            sticky=card.severity == "danger",
        )
    return tuple(sorted(merged.values(), key=lambda item: item.last_updated_at, reverse=True))


def _window_samples(
    history: Iterable[dict[str, Any]] | None,
    *,
    window_seconds: float,
    sample_interval: float,
) -> list[dict[str, Any]]:
    samples = [dict(item) for item in (history or [])]
    if not samples:
        return []
    timestamps = [float(item.get("timestamp", 0.0) or 0.0) for item in samples]
    end = max(timestamps)
    if end > 0.0:
        window = [item for item in samples if end - float(item.get("timestamp", 0.0) or 0.0) <= window_seconds]
        if window:
            return window
    count = max(1, int(math.ceil(float(window_seconds) / max(float(sample_interval), 0.05))))
    return samples[-count:]


def _observed_seconds(samples: Iterable[dict[str, Any]], *, sample_interval: float) -> float:
    items = list(samples)
    if len(items) < 2:
        return 0.0
    timestamps = [float(item.get("timestamp", 0.0) or 0.0) for item in items]
    positive = [value for value in timestamps if value > 0.0]
    if len(positive) >= 2:
        span = max(positive) - min(positive)
        if span > 0.0:
            return span
    return max(0.0, (len(items) - 1) * max(float(sample_interval), 0.05))


def _confidence_label(observed_seconds: float, sample_count: int) -> str:
    if observed_seconds >= 14.0 and sample_count >= 20:
        return "高"
    if observed_seconds >= 10.0 and sample_count >= 5:
        return "中"
    return "低"


def _action_id_for_card(card: DiagnosisCard) -> str | None:
    title = card.title
    if "音割れ" in title or "クリップ" in title:
        return "lower_input_gain"
    if "入力がOFF" in title:
        return "enable_input"
    if "デバイスエラー" in title:
        return "select_device"
    if "ノイズ" in title:
        return "reduce_noise"
    if "声が拾われにくい" in title or "VADで破棄" in title or "境界" in title:
        return "small_voice"
    if "キュー" in title:
        return "faster"
    return None


def _recommendation_from_id(
    action_id: str,
    *,
    source: str,
    cfg: dict | None,
) -> TuningRecommendation:
    cfg_data = cfg or {}
    if action_id == "small_voice":
        changes = tuple(easy_tuning_changes(source, cfg_data, "voice_pickup", 1)) if cfg else ()
        return TuningRecommendation(
            id=action_id,
            title="小さい声も拾う",
            what_changes="音声開始ラインを少し下げ、声として扱うまでの条件を緩めます。",
            effect="声の頭や小さい声がVADに届きやすくなります。",
            side_effect="環境ノイズも拾いやすくなる可能性があります。",
            timing="設定保存後に反映します。実行中に安全反映できない項目は次回開始時に反映します。",
            changes=changes,
        )
    if action_id == "reduce_noise":
        changes = tuple(easy_tuning_changes(source, cfg_data, "noise_reduction", 1)) if cfg else ()
        return TuningRecommendation(
            id=action_id,
            title="ノイズを拾いにくくする",
            what_changes="音声開始ラインとノイズ床からの余裕を少し上げます。",
            effect="無音時の誤検出やノイズ起点の送信候補を減らします。",
            side_effect="遠い声や小さい声を捨てやすくなる可能性があります。",
            timing="設定保存後に反映します。実行中に安全反映できない項目は次回開始時に反映します。",
            changes=changes,
        )
    if action_id == "faster":
        changes = tuple(easy_tuning_changes(source, cfg_data, "response_speed", 1)) if cfg else ()
        return TuningRecommendation(
            id=action_id,
            title="反応を速くする",
            what_changes="音声チャンクや発話区切りの待ち時間を短くします。",
            effect="字幕や文字起こし候補の反応が早くなります。",
            side_effect="文脈が分かれやすくなり、安定性や精度に影響する場合があります。",
            timing="設定保存後に反映します。実行中に安全反映できない項目は次回開始時に反映します。",
            changes=changes,
        )
    if action_id == "lower_input_gain":
        return TuningRecommendation(
            id=action_id,
            title="Windows/会議アプリ側の入力音量を下げる",
            what_changes="AgendaSnapのVADしきい値ではなく、入力元の音量を下げます。",
            effect="音割れした波形を避け、文字起こし前の音声品質を守ります。",
            side_effect="下げすぎると小さい声が拾われにくくなります。",
            timing="Windows、マイク、Teams/Zoom側で調整すると即時に影響します。",
            changes=(),
        )
    if action_id == "enable_input":
        source_key = "mic" if source == "mic" else "system"
        key = f"audio.enable_{source_key}"
        change = _change(cfg_data, key, True, "入力ソースをONにする", timing="保存後すぐに参照されます") if cfg else None
        return TuningRecommendation(
            id=action_id,
            title="入力をONにする",
            what_changes="選択中の入力ソースを有効にします。",
            effect="この入力から音声を取得できる状態に戻します。",
            side_effect="使わない入力をONにすると不要な音も拾う可能性があります。",
            timing="設定保存後すぐに参照されます。会議セッションは終了しません。",
            changes=tuple([change] if change is not None and change.before != change.after else []),
        )
    if action_id == "select_device":
        return TuningRecommendation(
            id=action_id,
            title="デバイスを選び直す",
            what_changes="使用する入力デバイスを選び直します。",
            effect="開けないデバイスや外れたデバイスを避けられます。",
            side_effect="別デバイスを選ぶと音量やノイズ条件が変わります。",
            timing="設定保存後に反映します。入力変更は会議終了操作ではありません。",
            changes=(),
        )
    return TuningRecommendation(
        id=action_id,
        title="再診断する",
        what_changes="設定を変えず、もう一度15秒観測します。",
        effect="現在の音の状態で判断し直せます。",
        side_effect="設定値は変わりません。",
        timing="いつでも実行できます。",
        changes=(),
    )


def _recommendations_for_cards(
    cards: Iterable[DiagnosisCard],
    *,
    source: str,
    cfg: dict | None,
) -> tuple[TuningRecommendation | None, tuple[TuningRecommendation, ...]]:
    seen: set[str] = set()
    actions: list[TuningRecommendation] = []
    for card in cards:
        action_id = _action_id_for_card(card)
        if not action_id or action_id in seen:
            continue
        seen.add(action_id)
        actions.append(_recommendation_from_id(action_id, source=source, cfg=cfg))
    if not actions:
        return None, ()
    return actions[0], tuple(actions[1:])


def _stable_reason(summary: dict[str, Any], *, observed_seconds: float, sample_count: int) -> str:
    parts = [
        f"観測 {observed_seconds:.1f}秒",
        f"サンプル {sample_count}件",
        f"VAD反応 {float(summary.get('active_ratio', 0.0) or 0.0) * 100:.0f}%",
        f"開始ライン未満 {float(summary.get('below_ratio', 0.0) or 0.0) * 100:.0f}%",
        f"VAD破棄 {float(summary.get('vad_discard_rate', 0.0) or 0.0) * 100:.0f}%",
    ]
    if summary.get("clipped_recent"):
        parts.append("クリップ履歴あり")
    if summary.get("noise_close"):
        parts.append("ノイズ床が開始ラインに近い")
    return " / ".join(parts)


def _audio_get(cfg: dict, path: str, default: Any = None) -> Any:
    if path.startswith("audio."):
        value = _get(cfg, path, None)
        if value is not None:
            return value
        return _get(cfg.get("audio", {}) if isinstance(cfg.get("audio"), dict) else cfg, path[6:], default)
    value = _get(cfg, path, None)
    if value is not None:
        return value
    audio = cfg.get("audio") if isinstance(cfg.get("audio"), dict) else None
    if audio is not None:
        return _get(audio, path, default)
    return default


def _thresholds_for_event(event: AudioDecisionEvent, cfg: dict, source: str) -> tuple[float, float, float]:
    source_key = "sys" if source == "sys" else "mic"
    configured_base = _audio_get(cfg, f"audio.energy_threshold_{source_key}", None)
    base = float(configured_base if configured_base is not None else event.threshold or 0.0)
    multiplier = float(_audio_get(cfg, "audio.calibration.multiplier", 1.0) or 1.0)
    if event.noise_rms is not None and event.noise_rms > 0:
        base = max(base, float(event.noise_rms) * multiplier)
    start_ratio = float(_audio_get(cfg, f"audio.vad.start_ratio_{source_key}", 1.1 if source_key == "sys" else 1.8) or 1.0)
    stop_ratio = float(_audio_get(cfg, f"audio.vad.stop_ratio_{source_key}", 0.85 if source_key == "sys" else 1.2) or 1.0)
    return base, max(0.0, base * start_ratio), max(0.0, base * stop_ratio)


def simulate_decisions_for_config(
    trace: AudioDecisionTrace,
    cfg: dict,
    *,
    source: str | None = None,
) -> AudioDecisionTrace:
    source_key = source or trace.source
    min_voice_chunks = max(1, int(_audio_get(cfg, f"audio.vad.min_voice_chunks_{source_key}", 1) or 1))
    guard = _audio_get(cfg, "audio.vad.guard_mic.enable", False)
    guard_enabled = source_key == "mic" and bool(guard)
    prebuffer_chunks = max(0, int(_audio_get(cfg, "audio.vad.guard_mic.prebuffer_chunks", 0) or 0))
    events: list[AudioDecisionEvent] = []
    in_voice = False
    voiced_streak = 0
    for event in trace.events:
        base, start_thr, stop_thr = _thresholds_for_event(event, cfg, source_key)
        decision = "idle"
        reason = "below_start_threshold"
        if event.clipped or event.peak >= PCM16_CLIP_LEVEL:
            decision = "clipped"
            reason = "clipped"
            in_voice = False
            voiced_streak = 0
        elif event.rms <= 0:
            decision = "idle"
            reason = "insufficient_data"
            in_voice = False
            voiced_streak = 0
        elif guard_enabled and not in_voice and event.rms < start_thr * 1.15:
            decision = "vad_discarded"
            reason = "mic_guard"
            voiced_streak = 0
        elif not in_voice:
            if event.rms < start_thr:
                decision = "vad_discarded"
                reason = "below_start_threshold"
                voiced_streak = 0
            else:
                voiced_streak += 1
                if voiced_streak < min_voice_chunks:
                    decision = "vad_discarded"
                    reason = "min_voice_chunks"
                else:
                    decision = "stt_candidate"
                    reason = "enqueued"
                    in_voice = True
                    voiced_streak = 0
        else:
            if event.rms < stop_thr:
                decision = "vad_discarded"
                reason = "below_stop_threshold"
                in_voice = False
                voiced_streak = 0
            else:
                decision = "stt_candidate"
                reason = "enqueued"
        events.append(
            replace(
                event,
                threshold=base,
                start_threshold=start_thr,
                stop_threshold=stop_thr,
                decision=decision,
                reason=reason,
                estimated=True,
            )
        )
    if prebuffer_chunks > 0:
        mutable = list(events)
        for index, event in enumerate(list(mutable)):
            prev_decision = mutable[index - 1].decision if index > 0 else ""
            if event.decision == "stt_candidate" and prev_decision != "stt_candidate":
                start = max(0, index - prebuffer_chunks)
                for pre_index in range(start, index):
                    if mutable[pre_index].decision in {"vad_discarded", "idle"}:
                        mutable[pre_index] = replace(
                            mutable[pre_index],
                            decision="stt_candidate",
                            reason="enqueued",
                            estimated=True,
                        )
        events = mutable
    return AudioDecisionTrace(
        source=source_key,
        events=tuple(events),
        estimated=True,
        note="同じ15秒診断メタデータを調整後設定で再判定した推定です。raw PCMは使っていません。",
    )


def decision_trace_metrics(trace: AudioDecisionTrace) -> DecisionTraceMetrics:
    candidates = [event for event in trace.events if event.decision == "stt_candidate"]
    discarded = [event for event in trace.events if event.decision == "vad_discarded"]
    queue_dropped = [event for event in trace.events if event.decision == "queue_dropped"]
    clipped = [event for event in trace.events if event.decision == "clipped"]
    candidate_seconds = sum(event.duration for event in candidates)
    discarded_seconds = sum(event.duration for event in discarded)
    return DecisionTraceMetrics(
        stt_candidate_count=len(candidates),
        stt_candidate_seconds=candidate_seconds,
        vad_discarded_count=len(discarded),
        vad_discarded_seconds=discarded_seconds,
        queue_dropped_count=len(queue_dropped),
        clipped_count=len(clipped),
        average_candidate_seconds=(candidate_seconds / len(candidates)) if candidates else 0.0,
        longest_discarded_seconds=max([event.duration for event in discarded], default=0.0),
    )


def compare_decision_traces(
    before_trace: AudioDecisionTrace,
    after_trace: AudioDecisionTrace,
) -> DecisionTraceComparison:
    before = decision_trace_metrics(before_trace)
    after = decision_trace_metrics(after_trace)
    candidate_delta = after.stt_candidate_count - before.stt_candidate_count
    discard_delta = after.vad_discarded_count - before.vad_discarded_count
    if candidate_delta > 0 and discard_delta <= 0:
        summary = "STT送信候補が増え、VAD破棄が減る見込みです。ただしノイズも拾いやすくなる可能性があります。"
    elif candidate_delta < 0:
        summary = "STT送信候補が減る見込みです。ノイズ対策には有効でも、小さい声を捨てる可能性があります。"
    elif discard_delta > 0:
        summary = "VAD破棄が増える見込みです。声の取りこぼしに注意してください。"
    else:
        summary = "判定区間の大きな変化は推定されません。"
    return DecisionTraceComparison(before=before, after=after, summary=summary, estimated=after_trace.estimated)


def analyze_candidate_visibility(trace: AudioDecisionTrace) -> CandidateVisibilityIssue:
    events = list(trace.events)
    if not events:
        return CandidateVisibilityIssue(
            "insufficient_data",
            "診断データが不足しています",
            "STT送信候補を判断するための軽量メタデータがありません。",
            "15秒診断を再実行してください",
        )
    if all(event.produced_count is None for event in events):
        return CandidateVisibilityIssue(
            "telemetry_missing",
            "STT候補統計がUIに届いていません",
            "RMS/Peakは見えていますが、producerのproduced統計がありません。設定問題と断定できません。",
            "15秒診断を再実行し、続く場合はtelemetry経路を確認してください",
        )
    max_produced = max((event.produced_count or 0) for event in events)
    max_dropped = max((event.dropped_energy_count or 0) for event in events)
    has_audio = any(event.rms > 0 or event.peak > 0 for event in events)
    has_green = any(event.decision == "stt_candidate" for event in events)
    if max_produced == 0 and max_dropped > 0:
        return CandidateVisibilityIssue(
            "vad_discarded",
            "VADで破棄されています",
            "producedは0ですがdropped_energyが増えています。音は入っていますがSTT送信候補になっていません。",
            "まずは『小さい声も拾う』または『声の頭切れを防ぐ』を1段階上げて再計算してください",
        )
    if max_produced == 0 and max_dropped == 0 and has_audio:
        return CandidateVisibilityIssue(
            "decision_not_reached",
            "音量は見えていますが、送信候補判定まで届いていません",
            "RMS/Peakはありますがproducerの候補/破棄統計が増えていません。",
            "入力テストを再実行し、改善しない場合はtelemetry経路を確認してください",
        )
    if max_produced > 0 and not has_green:
        return CandidateVisibilityIssue(
            "display_mismatch",
            "producedは増えていますが緑表示がありません",
            "STT送信候補統計は増えているため、設定よりもグラフ表示またはイベント変換の確認が必要です。",
            "表示側の診断イベント変換を確認してください",
        )
    return CandidateVisibilityIssue(
        "ok",
        "STT送信候補を確認できます",
        "緑の区間はSTT workerへ渡る候補です。送信済みや認識完了ではありません。",
        "必要ならbefore/after比較で候補数と破棄数を確認してください",
    )


def build_stable_diagnosis(
    level: LiveAudioLevel | dict[str, Any],
    *,
    source: str,
    history: Iterable[dict[str, Any]] | None,
    cfg: dict | None = None,
    now: float | None = None,
    window_seconds: float = 15.0,
    min_observed_seconds: float = 10.0,
    sample_interval: float = 0.2,
    previous_warnings: Iterable[DiagnosisCard] | None = None,
) -> StableDiagnosis:
    """Build a held diagnosis from an observation window, not from one live frame."""
    created_at = time.time() if now is None else float(now)
    data = _data(level)
    samples = _window_samples(history, window_seconds=window_seconds, sample_interval=sample_interval)
    if not samples:
        samples = [data]
    observed_seconds = _observed_seconds(samples, sample_interval=sample_interval)
    sample_count = len(samples)
    summary = _history_summary(data, samples)
    suff = summary["sufficiency"]
    state = user_state_label(data, samples)
    confidence = _confidence_label(observed_seconds, sample_count)
    live_cards = build_diagnosis_cards(data, source=source, history=samples)
    warning_history = merge_warning_history(
        previous_warnings or (),
        live_cards,
        now=created_at,
        hold_seconds=60.0,
    )
    has_enough_data = bool(suff.get("enough")) and observed_seconds >= float(min_observed_seconds)
    if state not in {"OFF", "デバイスエラー"} and not has_enough_data:
        reason = (
            f"{suff.get('reason', '診断に必要なデータが不足しています')} "
            f"観測 {observed_seconds:.1f}秒 / サンプル {sample_count}件。"
        )
        card = DiagnosisCard(
            "診断に必要なデータが足りません",
            "info",
            f"15秒診断をもう一度開始してください。{diagnosis_instruction(source)}",
            ("再診断する",),
            reason=reason,
            confidence="低",
        )
        stamped = (_stamp_card(card, now=created_at, hold_seconds=30.0, confidence="低"),)
        return StableDiagnosis(
            source=source,
            state="insufficient",
            title=card.title,
            message=card.message,
            reason=reason,
            confidence="低",
            recommended_action=None,
            alternative_actions=(),
            observed_seconds=observed_seconds,
            sample_count=sample_count,
            created_at=created_at,
            expires_at=created_at + 90.0,
            sticky=False,
            cards=stamped,
            warning_history=warning_history,
        )

    stamped_cards = tuple(
        _stamp_card(card, now=created_at, hold_seconds=90.0, confidence=confidence)
        for card in (live_cards or ())
    )
    if not stamped_cards:
        ok_card = DiagnosisCard(
            "入力は安定しています",
            "ok",
            "直近15秒では大きな音割れやVAD破棄の偏りは見つかりませんでした。",
            ("適用後も再診断で確認する",),
            reason=_stable_reason(summary, observed_seconds=observed_seconds, sample_count=sample_count),
            confidence=confidence,
        )
        stamped_cards = (_stamp_card(ok_card, now=created_at, hold_seconds=90.0, confidence=confidence),)
    recommended, alternatives = _recommendations_for_cards(stamped_cards, source=source, cfg=cfg)
    primary = stamped_cards[0]
    return StableDiagnosis(
        source=source,
        state=state,
        title=primary.title,
        message=primary.message,
        reason=_stable_reason(summary, observed_seconds=observed_seconds, sample_count=sample_count),
        confidence=confidence,
        recommended_action=recommended,
        alternative_actions=alternatives,
        observed_seconds=observed_seconds,
        sample_count=sample_count,
        created_at=created_at,
        expires_at=created_at + 90.0,
        sticky=False,
        cards=stamped_cards,
        warning_history=warning_history,
    )
