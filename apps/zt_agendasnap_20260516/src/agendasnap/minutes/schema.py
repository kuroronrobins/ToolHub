"""Schema for structured minutes (SSOT)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Optional


@dataclass
class MinutesMeta:
    version: int = 1
    generated_at: Optional[str] = None
    model: Optional[str] = None
    mode: Optional[str] = None  # "incremental" | "final"
    last_segment_index: int = 0
    prompt_version: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "version": int(self.version),
            "generated_at": self.generated_at,
            "model": self.model,
            "mode": self.mode,
            "last_segment_index": int(self.last_segment_index),
            "prompt_version": self.prompt_version,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MinutesMeta":
        return cls(
            version=int(data.get("version", 1)),
            generated_at=data.get("generated_at"),
            model=data.get("model"),
            mode=data.get("mode"),
            last_segment_index=int(data.get("last_segment_index", 0) or 0),
            prompt_version=data.get("prompt_version"),
        )


@dataclass
class MinutesHeader:
    title: Optional[str] = None
    date: Optional[str] = None
    time: Optional[str] = None
    location: Optional[str] = None
    facilitator: Optional[str] = None
    recorder: Optional[str] = None
    attendees: List[str] = field(default_factory=list)
    absentees: List[str] = field(default_factory=list)
    purpose: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "date": self.date,
            "time": self.time,
            "location": self.location,
            "facilitator": self.facilitator,
            "recorder": self.recorder,
            "attendees": list(self.attendees),
            "absentees": list(self.absentees),
            "purpose": self.purpose,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MinutesHeader":
        return cls(
            title=data.get("title"),
            date=data.get("date"),
            time=data.get("time"),
            location=data.get("location"),
            facilitator=data.get("facilitator"),
            recorder=data.get("recorder"),
            attendees=[str(x) for x in (data.get("attendees") or []) if str(x).strip()],
            absentees=[str(x) for x in (data.get("absentees") or []) if str(x).strip()],
            purpose=data.get("purpose"),
        )


@dataclass
class Evidence:
    text: str
    t0: float
    t1: float
    source: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "t0": float(self.t0),
            "t1": float(self.t1),
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Evidence":
        return cls(
            text=str(data.get("text", "")),
            t0=float(data.get("t0", 0.0) or 0.0),
            t1=float(data.get("t1", 0.0) or 0.0),
            source=data.get("source"),
        )


@dataclass
class AgendaItem:
    text: str
    evidence: List[Evidence] = field(default_factory=list)
    confidence: Optional[float] = None


@dataclass
class Decision:
    text: str
    evidence: List[Evidence] = field(default_factory=list)
    confidence: Optional[float] = None


@dataclass
class ActionItem:
    text: str
    owner: Optional[str] = None
    due: Optional[str] = None
    status: Optional[str] = None
    evidence: List[Evidence] = field(default_factory=list)
    confidence: Optional[float] = None


@dataclass
class OpenQuestion:
    text: str
    evidence: List[Evidence] = field(default_factory=list)
    confidence: Optional[float] = None


@dataclass
class RiskItem:
    text: str
    evidence: List[Evidence] = field(default_factory=list)
    confidence: Optional[float] = None


@dataclass
class NoteItem:
    text: str
    evidence: List[Evidence] = field(default_factory=list)
    confidence: Optional[float] = None


@dataclass
class SummaryItem:
    text: str
    evidence: List[Evidence] = field(default_factory=list)
    confidence: Optional[float] = None


@dataclass
class MinutesDocument:
    meta: MinutesMeta = field(default_factory=MinutesMeta)
    header: MinutesHeader = field(default_factory=MinutesHeader)
    summary: List[SummaryItem] = field(default_factory=list)
    agenda_items: List[AgendaItem] = field(default_factory=list)
    decisions: List[Decision] = field(default_factory=list)
    action_items: List[ActionItem] = field(default_factory=list)
    open_questions: List[OpenQuestion] = field(default_factory=list)
    risks: List[RiskItem] = field(default_factory=list)
    notes: List[NoteItem] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "meta": self.meta.to_dict(),
            "header": self.header.to_dict(),
            "summary": [_item_to_dict(x) for x in self.summary],
            "agenda_items": [_item_to_dict(x) for x in self.agenda_items],
            "decisions": [_item_to_dict(x) for x in self.decisions],
            "action_items": [_action_to_dict(x) for x in self.action_items],
            "open_questions": [_item_to_dict(x) for x in self.open_questions],
            "risks": [_item_to_dict(x) for x in self.risks],
            "notes": [_item_to_dict(x) for x in self.notes],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MinutesDocument":
        meta = MinutesMeta.from_dict(data.get("meta") or {})
        header = MinutesHeader.from_dict(data.get("header") or {})
        return cls(
            meta=meta,
            header=header,
            summary=[_item_from_dict(SummaryItem, x) for x in data.get("summary", [])],
            agenda_items=[_item_from_dict(AgendaItem, x) for x in data.get("agenda_items", [])],
            decisions=[_item_from_dict(Decision, x) for x in data.get("decisions", [])],
            action_items=[_action_from_dict(x) for x in data.get("action_items", [])],
            open_questions=[_item_from_dict(OpenQuestion, x) for x in data.get("open_questions", [])],
            risks=[_item_from_dict(RiskItem, x) for x in data.get("risks", [])],
            notes=[_item_from_dict(NoteItem, x) for x in data.get("notes", [])],
        )


def _item_to_dict(item: Any) -> dict:
    return {
        "text": item.text,
        "evidence": [ev.to_dict() for ev in item.evidence],
        "confidence": item.confidence,
    }


def _item_from_dict(cls, data: dict):
    return cls(
        text=str(data.get("text", "")),
        evidence=[Evidence.from_dict(x) for x in data.get("evidence", [])],
        confidence=_to_float_optional(data.get("confidence")),
    )


def _action_to_dict(item: ActionItem) -> dict:
    return {
        "text": item.text,
        "owner": item.owner,
        "due": item.due,
        "status": item.status,
        "evidence": [ev.to_dict() for ev in item.evidence],
        "confidence": item.confidence,
    }


def _action_from_dict(data: dict) -> ActionItem:
    return ActionItem(
        text=str(data.get("text", "")),
        owner=data.get("owner"),
        due=data.get("due"),
        status=data.get("status"),
        evidence=[Evidence.from_dict(x) for x in data.get("evidence", [])],
        confidence=_to_float_optional(data.get("confidence")),
    )


def _to_float_optional(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None
