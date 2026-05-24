"""Shared view helpers for the audio diagnosis UI."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from agendasnap.audio.diagnostics import (
    AudioDecisionTrace,
    ConfigChange,
    DiagnosisCard,
    GraphInterpretation,
    StableDiagnosis,
    ThresholdLine,
    TuningRecommendation,
    data_sufficiency,
    graph_sample_label,
    threshold_line_labels,
    user_state_label,
)
from agendasnap.audio.levels import PCM16_CLIP_LEVEL


DARK_TEXT = "#F9FAFB"
DARK_MUTED = "#D1D5DB"
DARK_PANEL = "#0F172A"
DARK_CARD = "#111827"
DARK_BORDER = "#374151"

LIGHT_MUTED = "#4B5563"

GRAPH_SAMPLE_COLORS = {
    "クリップ": "#DC2626",
    "キュー破棄": "#7C2D12",
    "STT送信候補": "#059669",
    "VAD破棄": "#D97706",
    "VAD検出": "#2563EB",
    "待機": "#60A5FA",
}
GRAPH_SAMPLE_PEAK_COLORS = {
    "クリップ": "#FCA5A5",
    "キュー破棄": "#FED7AA",
    "STT送信候補": "#A7F3D0",
    "VAD破棄": "#FDE68A",
    "VAD検出": "#BFDBFE",
    "待機": "#E5E7EB",
}
THRESHOLD_LINE_COLORS = {
    "noise": "#94A3B8",
    "start": "#EF4444",
    "stop": "#F59E0B",
    "clip": "#DC2626",
}

CHANGE_LABELS = {
    "audio.vad.start_ratio_sys": "音声開始ライン",
    "audio.vad.start_ratio_mic": "音声開始ライン",
    "audio.vad.stop_ratio_sys": "音声継続ライン",
    "audio.vad.stop_ratio_mic": "音声継続ライン",
    "audio.vad.min_voice_chunks_sys": "最小発話判定",
    "audio.vad.min_voice_chunks_mic": "最小発話判定",
    "audio.calibration.multiplier": "自動しきい値倍率",
    "audio.vad.guard_mic.enable": "マイクノイズガード",
    "audio.vad.adaptive.enable": "自動調整",
    "audio.vad.adaptive.update_interval_seconds": "自動調整間隔",
    "audio.vad.adaptive.max_step_ratio": "自動調整幅",
    "audio.vad.adaptive.smoothing": "自動調整の平滑化",
    "audio.chunk_ms": "処理単位",
    "stt.segment_max_seconds": "最大発話長",
    "stt.segment_gap_ms": "発話区切り",
    "stt.min_turn_seconds": "最小発話長",
}

@dataclass(frozen=True)
class ChangeDisplay:
    summary: str
    effect: str
    side_effect: str
    timing: str
    expert: str


@dataclass(frozen=True)
class RecommendationDisplay:
    title: str
    what_changes: str
    effect: str
    side_effect: str
    timing: str
    reversible: str
    expert_lines: tuple[str, ...]


@dataclass(frozen=True)
class StableDiagnosisDisplay:
    title: str
    message: str
    reason: str
    confidence: str
    observed: str
    primary_action: RecommendationDisplay | None


@dataclass(frozen=True)
class MiniDiagnosisViewModel:
    source: str
    state: str
    meter_ratio: float
    message: str


@dataclass(frozen=True)
class ChangeChip:
    label: str
    before: str
    after: str
    direction: str


@dataclass(frozen=True)
class ChangeSummaryDisplay:
    title: str
    what_changes: str
    effect: str
    side_effect: str
    timing: str
    reversible: str
    chips: tuple[ChangeChip, ...]
    expert_lines: tuple[str, ...]


@dataclass(frozen=True)
class AdjustmentAxis:
    key: str
    label: str
    negative_label: str
    positive_label: str
    before: int
    after: int


@dataclass(frozen=True)
class LiveStatusDisplay:
    title: str
    observed_label: str
    note: str


@dataclass(frozen=True)
class DecisionGraphSample:
    t0: float
    t1: float
    rms: float
    peak: float
    decision: str
    reason: str
    produced_count: int | None = None
    dropped_energy_count: int | None = None
    dropped_full_count: int | None = None
    x: int = 0
    width: int = 0


@dataclass(frozen=True)
class DecisionGraphInterval:
    kind: str
    label: str
    reason: str
    t0: float
    t1: float
    duration: float
    chunk_count: int
    x: int = 0
    width: int = 0


@dataclass(frozen=True)
class DecisionGraphStats:
    stt_candidate_count: int
    stt_candidate_seconds: float
    stt_candidate_average_seconds: float
    stt_candidate_min_seconds: float
    stt_candidate_max_seconds: float
    vad_discarded_count: int
    vad_discarded_seconds: float
    short_discard_count: int
    short_discard_seconds: float
    queue_dropped_count: int
    clipped_count: int
    guard_discard_count: int
    produced_max: int
    dropped_energy_max: int
    dropped_full_max: int
    has_energy_samples: bool
    has_decision_intervals: bool


@dataclass(frozen=True)
class DecisionGraphThresholdLine:
    id: str
    label: str
    values: tuple[float, ...]
    value: float
    variable: bool


@dataclass(frozen=True)
class DecisionGraphViewModel:
    title: str
    note: str
    estimated: bool
    time_start: float
    time_end: float
    duration: float
    scale_max: float
    samples: tuple[DecisionGraphSample, ...]
    intervals: tuple[DecisionGraphInterval, ...]
    threshold_lines: tuple[DecisionGraphThresholdLine, ...]
    stats: DecisionGraphStats
    short_discard_count: int
    shortest_short_discard_seconds: float
    longest_short_discard_seconds: float


@dataclass(frozen=True)
class BeforeAfterDecisionGraphViewModel:
    before: DecisionGraphViewModel
    after: DecisionGraphViewModel
    summary_lines: tuple[str, ...]
    explanation: str


ADJUSTMENT_AXES = (
    AdjustmentAxis("voice_pickup", "声の拾いやすさ", "ノイズを拾いにくく", "小さい声も拾う", 0, 0),
    AdjustmentAxis("speech_start", "発話開始", "一瞬のノイズを捨てる", "声の頭切れを防ぐ", 0, 0),
    AdjustmentAxis("speech_continuity", "発話継続", "短く区切る", "声の終わりを長めに拾う", 0, 0),
    AdjustmentAxis("response_speed", "応答性", "精度を安定させる", "反応を速くする", 0, 0),
    AdjustmentAxis("auto_adjustment", "自動調整", "自動調整を弱める", "自動調整を強める", 0, 0),
)

DECISION_INTERVAL_COLORS = {
    "stt_candidate": "#059669",
    "vad_discarded": "#D97706",
    "short_discard": "#EA580C",
    "queue_dropped": "#7C2D12",
    "clipped": "#DC2626",
    "guard_discard": "#A16207",
    "vad_active": "#2563EB",
    "idle": "#CBD5E1",
    "unknown": "#9CA3AF",
}


def decision_interval_color(kind: str) -> str:
    return DECISION_INTERVAL_COLORS.get(kind, DECISION_INTERVAL_COLORS["unknown"])


def decision_interval_label(decision: str, reason: str = "") -> tuple[str, str]:
    reason_value = str(reason or "")
    if decision == "stt_candidate":
        return "stt_candidate", "STT候補"
    if decision == "queue_dropped":
        return "queue_dropped", "queue破棄"
    if decision == "clipped":
        return "clipped", "clip"
    if decision == "vad_discarded" and reason_value == "min_voice_chunks":
        return "short_discard", "短すぎて破棄"
    if decision == "vad_discarded" and reason_value == "mic_guard":
        return "guard_discard", "guard破棄"
    if decision == "vad_discarded":
        return "vad_discarded", "VAD破棄"
    if decision == "vad_active":
        return "vad_active", "VAD検出"
    if decision == "idle":
        return "idle", "待機"
    return "unknown", "不明"


def source_label(source: str) -> str:
    return "SYSTEM" if source == "sys" else "MIC"


def mini_diagnosis_view_model(
    level: dict,
    *,
    source: str,
    history: Iterable[dict] | None = None,
) -> MiniDiagnosisViewModel:
    state = user_state_label(level, history)
    rms = float(level.get("rms", 0.0) or 0.0)
    threshold = float(level.get("threshold", 0.0) or 0.0)
    if threshold > 0:
        meter_ratio = min(1.0, max(0.0, rms / max(threshold * 1.5, 1.0)))
    else:
        meter_ratio = min(1.0, max(0.0, rms / 1000.0))
    label = source_label(source)
    if state == "デバイスエラー":
        message = f"{label}: デバイスを確認してください"
    elif state == "OFF":
        message = f"{label}: 入力はOFFです"
    elif state == "クリップ":
        message = f"{label}: 入力音量が大きすぎます"
    elif state in {"未計測", "未判定"}:
        message = f"{label}: 15秒診断で確認してください"
    elif state == "音声検出中":
        message = f"{label}: 音声を拾えています"
    elif state == "小さすぎる":
        message = f"{label}: 音が小さめです"
    elif state == "ノイズ多め":
        message = f"{label}: ノイズが多めです"
    else:
        message = f"{label}: {state}"
    return MiniDiagnosisViewModel(source=label, state=state, meter_ratio=meter_ratio, message=message)


def graph_placeholder_message(source: str, *, settings: bool = False) -> str:
    if settings:
        return (
            "この画面ではライブ音声は未計測です。"
            "実行中のRMS推移はメイン画面の音声診断で確認してください。"
        )
    if source == "sys":
        return "まだ音声データがありません。SYSTEMの場合はTeams/Zoomなどで音声を再生してください。"
    return "まだ音声データがありません。MICの場合はマイクに向かって話してください。"


def should_show_graph(level: dict, samples: Iterable[dict]) -> bool:
    recent = list(samples)
    if not recent:
        return False
    sufficiency = data_sufficiency(level, recent)
    return bool(sufficiency.get("enough"))


def graph_scale_max(samples: Iterable[dict], lines: Iterable[ThresholdLine]) -> float:
    recent = list(samples)[-80:]
    non_clip_lines = [float(line.value) for line in lines if line.id != "clip"]
    base_values = [1.0, *non_clip_lines]
    base_values.extend(float(item.get("rms", 0.0) or 0.0) for item in recent)
    base = max(base_values)
    peak_cap = max(base * 1.8, 1.0)
    capped_peaks = [min(float(item.get("peak", 0.0) or 0.0), peak_cap) for item in recent]
    return max([base, *capped_peaks, 1.0]) * 1.15


def _trace_threshold_lines(events) -> tuple[DecisionGraphThresholdLine, ...]:
    start_values = tuple(float(event.start_threshold or event.threshold or 0.0) for event in events)
    stop_values = tuple(float(event.stop_threshold or event.threshold or 0.0) for event in events)
    noise_values = tuple(float(event.noise_rms or 0.0) for event in events)
    clip_values = tuple(float(PCM16_CLIP_LEVEL) for _ in events)

    def _line(line_id: str, label: str, values: tuple[float, ...]) -> DecisionGraphThresholdLine:
        nonzero = [value for value in values if value > 0]
        value = nonzero[-1] if nonzero else 0.0
        variable = bool(nonzero) and (max(nonzero) - min(nonzero) > max(1.0, value * 0.03))
        return DecisionGraphThresholdLine(line_id, label, values, value, variable)

    return (
        _line("noise", "ノイズ床", noise_values),
        _line("start", "音声開始ライン", start_values),
        _line("stop", "音声継続ライン", stop_values),
        _line("clip", "クリップ警告", clip_values),
    )


def _trace_scale_max(traces: Iterable[AudioDecisionTrace]) -> float:
    values = [1.0]
    for trace in traces:
        for event in trace.events:
            values.append(float(event.rms or 0.0))
            values.append(min(float(event.peak or 0.0), max(float(event.rms or 0.0) * 2.5, 1.0)))
            values.append(float(event.start_threshold or event.threshold or 0.0))
            values.append(float(event.stop_threshold or event.threshold or 0.0))
            if event.noise_rms is not None:
                values.append(float(event.noise_rms or 0.0))
    return max(values) * 1.15


def decision_bin_width(seconds: float) -> int:
    """One shared pixel width for graph bars and decision lanes."""
    return max(7, int(round(max(float(seconds), 0.08) * 42)))


def _sample_bins(events) -> tuple[DecisionGraphSample, ...]:
    samples: list[DecisionGraphSample] = []
    x = 0
    for event in events:
        width = decision_bin_width(float(event.t1) - float(event.t0))
        samples.append(
            DecisionGraphSample(
                t0=float(event.t0),
                t1=float(event.t1),
                rms=float(event.rms or 0.0),
                peak=float(event.peak or 0.0),
                decision=event.decision,
                reason=event.reason,
                produced_count=event.produced_count,
                dropped_energy_count=event.dropped_energy_count,
                dropped_full_count=event.dropped_full_count,
                x=x,
                width=width,
            )
        )
        x += width
    return tuple(samples)


def _event_intervals(samples: tuple[DecisionGraphSample, ...]) -> tuple[DecisionGraphInterval, ...]:
    intervals: list[DecisionGraphInterval] = []
    for sample in samples:
        kind, label = decision_interval_label(sample.decision, sample.reason)
        t0 = float(sample.t0)
        t1 = max(float(sample.t1), t0)
        if intervals and intervals[-1].kind == kind and intervals[-1].reason == sample.reason and t0 <= intervals[-1].t1 + 0.025:
            prev = intervals[-1]
            intervals[-1] = DecisionGraphInterval(
                kind=prev.kind,
                label=prev.label,
                reason=prev.reason,
                t0=prev.t0,
                t1=max(prev.t1, t1),
                duration=max(prev.t1, t1) - prev.t0,
                chunk_count=prev.chunk_count + 1,
                x=prev.x,
                width=prev.width + sample.width,
            )
        else:
            intervals.append(
                DecisionGraphInterval(
                    kind=kind,
                    label=label,
                    reason=str(sample.reason or ""),
                    t0=t0,
                    t1=t1,
                    duration=t1 - t0,
                    chunk_count=1,
                    x=sample.x,
                    width=sample.width,
                )
            )
    return tuple(intervals)


def _stats_from_graph_parts(
    samples: tuple[DecisionGraphSample, ...],
    intervals: tuple[DecisionGraphInterval, ...],
) -> DecisionGraphStats:
    def _interval_stats(kind: str) -> dict[str, float]:
        selected = [interval for interval in intervals if interval.kind == kind]
        durations = [interval.duration for interval in selected]
        total = sum(durations)
        return {
            "count": float(len(selected)),
            "seconds": total,
            "average": (total / len(selected)) if selected else 0.0,
            "min": min(durations, default=0.0),
            "max": max(durations, default=0.0),
        }

    stt = _interval_stats("stt_candidate")
    vad = _interval_stats("vad_discarded")
    short = _interval_stats("short_discard")
    produced_values = [sample.produced_count or 0 for sample in samples if sample.produced_count is not None]
    dropped_energy_values = [
        sample.dropped_energy_count or 0 for sample in samples if sample.dropped_energy_count is not None
    ]
    dropped_full_values = [
        sample.dropped_full_count or 0 for sample in samples if sample.dropped_full_count is not None
    ]
    decision_kinds = {interval.kind for interval in intervals}
    return DecisionGraphStats(
        stt_candidate_count=int(stt["count"]),
        stt_candidate_seconds=float(stt["seconds"]),
        stt_candidate_average_seconds=float(stt["average"]),
        stt_candidate_min_seconds=float(stt["min"]),
        stt_candidate_max_seconds=float(stt["max"]),
        vad_discarded_count=int(vad["count"]),
        vad_discarded_seconds=float(vad["seconds"]),
        short_discard_count=int(short["count"]),
        short_discard_seconds=float(short["seconds"]),
        queue_dropped_count=sum(1 for interval in intervals if interval.kind == "queue_dropped"),
        clipped_count=sum(1 for interval in intervals if interval.kind == "clipped"),
        guard_discard_count=sum(1 for interval in intervals if interval.kind == "guard_discard"),
        produced_max=max(produced_values, default=0),
        dropped_energy_max=max(dropped_energy_values, default=0),
        dropped_full_max=max(dropped_full_values, default=0),
        has_energy_samples=any(sample.rms > 0 or sample.peak > 0 for sample in samples),
        has_decision_intervals=bool(decision_kinds - {"idle", "unknown"}),
    )


def _build_decision_graph(
    trace: AudioDecisionTrace,
    *,
    title: str,
    time_start: float,
    time_end: float,
    scale_max: float,
) -> DecisionGraphViewModel:
    events = tuple(trace.events)
    samples = _sample_bins(events)
    intervals = _event_intervals(samples)
    stats = _stats_from_graph_parts(samples, intervals)
    short_intervals = [interval for interval in intervals if interval.kind == "short_discard"]
    short_durations = [interval.duration for interval in short_intervals]
    return DecisionGraphViewModel(
        title=title,
        note=trace.note,
        estimated=trace.estimated,
        time_start=time_start,
        time_end=time_end,
        duration=max(0.0, time_end - time_start),
        scale_max=scale_max,
        samples=samples,
        intervals=intervals,
        threshold_lines=_trace_threshold_lines(events),
        stats=stats,
        short_discard_count=len(short_intervals),
        shortest_short_discard_seconds=min(short_durations, default=0.0),
        longest_short_discard_seconds=max(short_durations, default=0.0),
    )


def build_before_after_decision_graphs(
    before_trace: AudioDecisionTrace,
    after_trace: AudioDecisionTrace,
    *,
    before_title: str = "before 現設定",
    after_title: str = "after 変更候補",
) -> BeforeAfterDecisionGraphViewModel:
    events = [*before_trace.events, *after_trace.events]
    if events:
        time_start = min(float(event.t0) for event in events)
        time_end = max(float(event.t1) for event in events)
    else:
        time_start = 0.0
        time_end = 0.0
    scale_max = _trace_scale_max((before_trace, after_trace))
    before = _build_decision_graph(before_trace, title=before_title, time_start=time_start, time_end=time_end, scale_max=scale_max)
    after = _build_decision_graph(after_trace, title=after_title, time_start=time_start, time_end=time_end, scale_max=scale_max)
    bs = before.stats
    af = after.stats
    summary_lines = (
        f"STT送信候補数: {bs.stt_candidate_count} -> {af.stt_candidate_count}",
        f"STT送信候補の合計時間: {bs.stt_candidate_seconds:.1f}秒 -> {af.stt_candidate_seconds:.1f}秒",
        f"平均送信候補長: {bs.stt_candidate_average_seconds:.1f}秒 -> {af.stt_candidate_average_seconds:.1f}秒",
        (
            "最短/最長送信候補長: "
            f"{bs.stt_candidate_min_seconds:.1f}/{bs.stt_candidate_max_seconds:.1f}秒"
            f" -> {af.stt_candidate_min_seconds:.1f}/{af.stt_candidate_max_seconds:.1f}秒"
        ),
        f"VAD破棄数: {bs.vad_discarded_count} -> {af.vad_discarded_count}",
        f"VAD破棄の合計時間: {bs.vad_discarded_seconds:.1f}秒 -> {af.vad_discarded_seconds:.1f}秒",
        f"短すぎて破棄された区間数: {bs.short_discard_count} -> {af.short_discard_count}",
        f"queue破棄数: {bs.queue_dropped_count} -> {af.queue_dropped_count}",
        f"clip数: {bs.clipped_count} -> {af.clipped_count}",
    )
    candidate_delta = af.stt_candidate_seconds - bs.stt_candidate_seconds
    short_delta = af.short_discard_count - bs.short_discard_count
    vad_delta = af.vad_discarded_seconds - bs.vad_discarded_seconds
    if af.clipped_count or bs.clipped_count:
        explanation = "clip区間があります。AgendaSnap設定より先にWindows、マイク、Teams/Zoom側の入力音量を下げてください。"
    elif candidate_delta > 0 and short_delta <= 0 and vad_delta <= 0:
        explanation = "STT送信候補が増え、短すぎる破棄やVAD破棄は増えていません。改善の見込みがありますが、ノイズも拾いやすくなる可能性があります。"
    elif short_delta > 0:
        explanation = "短すぎて破棄される区間が増えています。語頭切れ防止を戻すか、min_voice_chunksを確認してください。"
    elif vad_delta > 0:
        explanation = "VAD破棄時間が増えています。小さい声や語尾を捨てる可能性があります。"
    elif candidate_delta < 0:
        explanation = "STT送信候補が減っています。ノイズ対策としては有効でも、発話の取りこぼしに注意してください。"
    else:
        explanation = "同じ15秒診断メタデータでは大きな変化は推定されません。必要なら保存後に再診断してください。"
    return BeforeAfterDecisionGraphViewModel(
        before=before,
        after=after,
        summary_lines=summary_lines,
        explanation=explanation,
    )

def should_show_no_candidate_help(graph: DecisionGraphViewModel) -> bool:
    return graph.stats.stt_candidate_count == 0


def candidate_visibility_from_graph(graph: DecisionGraphViewModel) -> GraphInterpretation:
    """Interpret the same graph model used for drawing."""
    stats = graph.stats
    if stats.stt_candidate_count > 0:
        return GraphInterpretation(
            title="STT送信候補区間があります",
            severity="ok",
            message=(
                f"緑のSTT送信候補区間が {stats.stt_candidate_count} 件、"
                f"合計 {stats.stt_candidate_seconds:.1f} 秒あります。送信済みではなく候補区間です。"
            ),
            action="この状態を基準に、before/after差分とclip有無を確認してください。",
            reason="描画に使うDecisionGraphViewModelのinterval集計から判定しています。",
        )
    if stats.produced_max > 0:
        return GraphInterpretation(
            title="producedは増えていますが緑区間がありません",
            severity="warning",
            message="producer統計上は送信候補が作られていますが、グラフ上のSTT送信候補区間に変換できていません。",
            action="telemetryの変換経路と表示側のdecision生成を確認してください。",
            reason="produced_max > 0 かつ stt_candidate interval が0件です。",
        )
    if stats.vad_discarded_count or stats.short_discard_count or stats.guard_discard_count:
        return GraphInterpretation(
            title="VADで破棄されています",
            severity="warning",
            message=(
                f"STT送信候補は0件です。VAD破棄 {stats.vad_discarded_count} 件、"
                f"短すぎる破棄 {stats.short_discard_count} 件があります。"
            ),
            action="「声を拾いやすくする」か「声の頭切れを防ぐ」を1段階だけ試して再診断してください。",
            reason="緑区間はなく、破棄区間のintervalが存在します。",
        )
    if stats.has_energy_samples and not stats.has_decision_intervals:
        return GraphInterpretation(
            title="RMS/Peakはありますが判定区間がありません",
            severity="warning",
            message="音量サンプルはありますが、STT候補/VAD破棄などの判定区間が生成されていません。",
            action="15秒診断を再実行し、続く場合はtelemetry経路を確認してください。",
            reason="energy sampleあり、decision intervalなしです。",
        )
    return GraphInterpretation(
        title="判定用telemetryが不足しています",
        severity="info",
        message="STT送信候補区間もVAD破棄区間もありません。telemetry欠落または無音の可能性があります。",
        action="入力ソースを確認して15秒診断を再実行してください。",
        reason="graph sample/interval集計で候補・破棄・energyが不足しています。",
    )


def line_top(line: ThresholdLine, *, graph_height: int, scale_max: float) -> int:
    if line.id == "clip":
        return 0
    value = min(max(float(line.value), 0.0), max(scale_max, 1.0))
    return max(0, graph_height - int(graph_height * value / max(scale_max, 1.0)))


def sample_bar_heights(sample: dict, *, graph_height: int, scale_max: float) -> tuple[int, int]:
    rms = float(sample.get("rms", 0.0) or 0.0)
    peak = float(sample.get("peak", 0.0) or 0.0)
    capped_peak = min(peak, max(scale_max, 1.0))
    rms_height = max(2, int(graph_height * min(rms, scale_max) / max(scale_max, 1.0)))
    peak_height = max(rms_height, int(graph_height * capped_peak / max(scale_max, 1.0)))
    return rms_height, peak_height


def threshold_line_text(lines: Iterable[ThresholdLine], *, expert: bool = False) -> list[str]:
    if expert:
        return threshold_line_labels(lines, expert=True)
    labels: list[str] = []
    for line in lines:
        if line.id == "clip":
            labels.append("クリップ警告: 入力過大")
        else:
            labels.append(f"{line.label}: {line.value:.0f}")
    return labels


def split_cards(cards: Iterable[DiagnosisCard], *, limit: int = 3) -> tuple[list[DiagnosisCard], list[DiagnosisCard]]:
    items = list(cards)
    return items[:limit], items[limit:]


def change_display(change: ConfigChange) -> ChangeDisplay:
    summary = f"{change.effect}: {change.before} -> {change.after}"
    side_effect = change.side_effect or "大きな副作用は想定していません。"
    return ChangeDisplay(
        summary=summary,
        effect=change.effect,
        side_effect=side_effect,
        timing=change.timing,
        expert=f"{change.key}: {change.before} -> {change.after}",
    )


def recommendation_display(action: TuningRecommendation | None) -> RecommendationDisplay | None:
    if action is None:
        return None
    expert_lines = tuple(change_display(change).expert for change in action.changes)
    return RecommendationDisplay(
        title=action.title,
        what_changes=action.what_changes,
        effect=action.effect,
        side_effect=action.side_effect,
        timing=action.timing,
        reversible="元に戻せます" if action.reversible else "元に戻せません",
        expert_lines=expert_lines,
    )


def basic_change_label(key: str) -> str:
    return CHANGE_LABELS.get(key, "調整値")


def change_chip(change: ConfigChange) -> ChangeChip:
    before = "" if change.before is None else str(change.before)
    after = "" if change.after is None else str(change.after)
    direction = "変更"
    try:
        before_f = float(change.before)
        after_f = float(change.after)
        if after_f > before_f:
            direction = "上げる"
        elif after_f < before_f:
            direction = "下げる"
    except (TypeError, ValueError):
        if change.before != change.after:
            direction = "切替"
    return ChangeChip(
        label=basic_change_label(change.key),
        before=before,
        after=after,
        direction=direction,
    )


def compact_change_summary(
    changes: Iterable[ConfigChange],
    *,
    title: str,
    what_changes: str,
    effect: str,
    side_effect: str,
    timing: str,
    reversible: bool = True,
) -> ChangeSummaryDisplay:
    items = list(changes)
    return ChangeSummaryDisplay(
        title=title,
        what_changes=what_changes,
        effect=effect,
        side_effect=side_effect,
        timing=timing,
        reversible="元に戻せます" if reversible else "元に戻せません",
        chips=tuple(change_chip(change) for change in items),
        expert_lines=tuple(change_display(change).expert for change in items),
    )


def adjustment_step(current: int, direction: int) -> int:
    return max(-2, min(2, int(current) + (1 if int(direction) > 0 else -1)))


def reset_adjustment_levels(keys: Iterable[str]) -> dict[str, int]:
    return {str(key): 0 for key in keys}


def adjustment_axis_display(key: str, level: int, *, before: int = 0) -> AdjustmentAxis:
    template = next((axis for axis in ADJUSTMENT_AXES if axis.key == key), None)
    if template is None:
        template = AdjustmentAxis(key, key, "弱める", "強める", before, level)
    return AdjustmentAxis(
        template.key,
        template.label,
        template.negative_label,
        template.positive_label,
        max(-2, min(2, int(before))),
        max(-2, min(2, int(level))),
    )


def adjustment_marker_text(axis: AdjustmentAxis) -> str:
    return f"▲変更前 Lv.{axis.before}  /  ●変更後 Lv.{axis.after}"


def live_status_display(mode: str, observed_at: float | None) -> LiveStatusDisplay:
    mode_value = str(mode or "idle")
    if mode_value == "running":
        return LiveStatusDisplay("ライブ状態: 診断中", "現在のライブ値", "診断結果はまだ固定されていません。")
    if mode_value == "final":
        label = "最終観測値"
        if observed_at:
            try:
                import time

                label = f"最終観測値: {time.strftime('%H:%M:%S', time.localtime(float(observed_at)))} 時点"
            except (OSError, ValueError):
                label = "最終観測値"
        return LiveStatusDisplay("ライブ状態: 停止中", label, "診断結果は直近15秒の固定結果です。")
    if mode_value == "insufficient":
        return LiveStatusDisplay("ライブ状態: 停止中", "最終観測値: データ不足", "まず15秒診断を再実行してください。")
    return LiveStatusDisplay("ライブ状態: 未診断", "現在のライブ値なし", "15秒診断を開始してください。")


def graph_interpretation_text(items: Iterable[GraphInterpretation]) -> list[str]:
    return [f"{item.title}: {item.message} 次にすること: {item.action}" for item in items]


def stable_diagnosis_display(diagnosis: StableDiagnosis | None) -> StableDiagnosisDisplay | None:
    if diagnosis is None:
        return None
    return StableDiagnosisDisplay(
        title=diagnosis.title,
        message=diagnosis.message,
        reason=diagnosis.reason,
        confidence=diagnosis.confidence,
        observed=f"直近{diagnosis.observed_seconds:.0f}秒 / {diagnosis.sample_count}サンプル",
        primary_action=recommendation_display(diagnosis.recommended_action),
    )


def graph_sample_color(sample: dict) -> str:
    return GRAPH_SAMPLE_COLORS.get(graph_sample_label(sample), GRAPH_SAMPLE_COLORS["待機"])


def graph_peak_color(sample: dict) -> str:
    return GRAPH_SAMPLE_PEAK_COLORS.get(graph_sample_label(sample), GRAPH_SAMPLE_PEAK_COLORS["待機"])
