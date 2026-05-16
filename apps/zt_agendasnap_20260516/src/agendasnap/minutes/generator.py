"""Simple rule-based minutes generator (placeholder)."""
from __future__ import annotations

import difflib
import re
from typing import Iterable, List, Optional

from agendasnap.bus.events import TranscriptSegment
from agendasnap.minutes.schema import Decision, Evidence, MinutesDocument, NoteItem, SummaryItem


def _normalize_text(text: str) -> str:
    cleaned = re.sub(r"[\s\.,!！\?？、。・]", "", text.strip().lower())
    return cleaned


def _text_similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def _dedupe_segments(
    segments: List[TranscriptSegment],
    *,
    window_seconds: float,
    similarity_threshold: float,
) -> tuple[List[TranscriptSegment], List[TranscriptSegment]]:
    if not segments:
        return [], []
    if window_seconds <= 0 or similarity_threshold <= 0:
        return list(segments), []

    filtered: List[TranscriptSegment] = []
    removed: List[TranscriptSegment] = []
    recent: List[TranscriptSegment] = []

    for seg in segments:
        t0 = float(seg.start or 0.0)
        recent = [s for s in recent if (t0 - float(s.start or 0.0)) <= window_seconds]
        norm_text = _normalize_text(seg.text or "")
        is_dup = False
        for other in recent:
            if other.source == seg.source:
                continue
            other_norm = _normalize_text(other.text or "")
            if _text_similarity(norm_text, other_norm) >= similarity_threshold:
                is_dup = True
                break
        if not is_dup:
            filtered.append(seg)
            recent.append(seg)
        else:
            removed.append(seg)

    return filtered, removed


def _merge_segments_for_minutes(
    segments: Iterable[TranscriptSegment],
    *,
    merge_enable: bool = True,
    merge_min_seconds: float = 2.0,
    merge_max_seconds: float = 5.0,
    merge_gap_seconds: float = 0.8,
    merge_by_source: bool = True,
    dedupe_enable: bool = False,
    dedupe_window_seconds: float = 1.0,
    dedupe_similarity: float = 0.9,
) -> tuple[List[TranscriptSegment], List[TranscriptSegment]]:
    if not merge_enable:
        return list(segments), []

    min_s = float(merge_min_seconds)
    max_s = float(merge_max_seconds)
    gap_s = float(merge_gap_seconds)
    if max_s < min_s:
        max_s = min_s

    finals = [s for s in segments if s.state == "final" and s.text and s.text.strip()]
    finals.sort(key=lambda s: float(getattr(s, "start", 0.0) or 0.0))
    deduped: List[TranscriptSegment] = []
    if dedupe_enable:
        finals, deduped = _dedupe_segments(
            finals,
            window_seconds=float(dedupe_window_seconds),
            similarity_threshold=float(dedupe_similarity),
        )

    merged: List[TranscriptSegment] = []
    current: Optional[TranscriptSegment] = None

    for seg in finals:
        t0 = float(seg.start or 0.0)
        t1 = float(seg.end or t0)

        if current is None:
            current = TranscriptSegment(
                text=seg.text.strip(),
                start=t0,
                end=t1,
                source=seg.source,
                state="final",
                confidence=seg.confidence,
            )
            continue

        same_source = (seg.source == current.source) if merge_by_source else True
        gap = t0 - float(current.end or 0.0)
        cur_duration = float(current.end or 0.0) - float(current.start or 0.0)
        new_duration = max(float(current.end or 0.0), t1) - float(current.start or 0.0)

        if same_source and gap <= gap_s:
            if cur_duration < min_s or new_duration <= max_s:
                current.text = f"{current.text} {seg.text.strip()}".strip()
                current.end = max(float(current.end or 0.0), t1)
                continue

        merged.append(current)
        current = TranscriptSegment(
            text=seg.text.strip(),
            start=t0,
            end=t1,
            source=seg.source,
            state="final",
            confidence=seg.confidence,
        )

    if current is not None:
        merged.append(current)

    return merged, deduped


def generate_minutes(segments: Iterable[TranscriptSegment], minutes_cfg: Optional[dict] = None) -> MinutesDocument:
    """
    Extremely naive summarizer:
    - Collect final segments only
    - Use first sentence as a "decision" placeholder with timestamp evidence
    """
    doc = MinutesDocument()
    cfg = minutes_cfg or {}
    filter_cfg = cfg.get("filter") if isinstance(cfg, dict) else None
    filter_enable = bool(filter_cfg.get("enable", False)) if isinstance(filter_cfg, dict) else False
    filter_min_chars = int(filter_cfg.get("min_chars", 0) or 0) if isinstance(filter_cfg, dict) else 0
    filter_allowlist = [str(x) for x in (filter_cfg.get("allowlist") or [])] if isinstance(filter_cfg, dict) else []
    merged, deduped = _merge_segments_for_minutes(
        segments,
        merge_enable=bool(cfg.get("merge_enable", True)),
        merge_min_seconds=float(cfg.get("merge_min_seconds", 2.0)),
        merge_max_seconds=float(cfg.get("merge_max_seconds", 5.0)),
        merge_gap_seconds=float(cfg.get("merge_gap_seconds", 0.8)),
        merge_by_source=bool(cfg.get("merge_by_source", True)),
        dedupe_enable=bool(cfg.get("dedupe_enable", False)),
        dedupe_window_seconds=float(cfg.get("dedupe_window_seconds", 1.0)),
        dedupe_similarity=float(cfg.get("dedupe_similarity", 0.9)),
    )
    if deduped:
        for seg in deduped:
            t0 = float(seg.start or 0.0)
            t1 = float(seg.end or t0)
            text = seg.text.strip()
            if not text:
                continue
            ev = Evidence(text=text, t0=t0, t1=t1, source=seg.source)
            doc.notes.append(NoteItem(text=f"[deduped:{seg.source}] {text}", evidence=[ev]))
    for seg in merged:
        text = seg.text.strip()
        if not text:
            continue
        if filter_enable:
            if text not in filter_allowlist and len(text) < filter_min_chars:
                continue
        ev = Evidence(text=text, t0=seg.start, t1=seg.end, source=seg.source)
        doc.decisions.append(Decision(text=text[:60], evidence=[ev]))
        if len(doc.summary) < 3:
            doc.summary.append(SummaryItem(text=text[:60], evidence=[ev], confidence=seg.confidence))
    return doc
