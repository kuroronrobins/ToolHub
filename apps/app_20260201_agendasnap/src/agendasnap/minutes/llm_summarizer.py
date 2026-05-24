"""LLM-based minutes generator and incremental updater."""
from __future__ import annotations

import asyncio
import difflib
import json
import logging
import re
import time
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

from agendasnap.bus.events import TranscriptSegment
from agendasnap.config.ai_providers import resolve_text_runtime
from agendasnap.llm.cost import LlmCostRecord, append_cost_record_jsonl
from agendasnap.llm.openai_responses import (
    OpenAIResponsesClient,
    extract_output_json,
    extract_output_text,
)
from agendasnap.minutes.profiles import apply_minutes_profile, describe_minutes_profile
from agendasnap.minutes.render_md import render as render_minutes
from agendasnap.minutes.schema import (
    ActionItem,
    AgendaItem,
    Decision,
    Evidence,
    MinutesDocument,
    NoteItem,
    OpenQuestion,
    RiskItem,
    SummaryItem,
)
from agendasnap.minutes.ssot import init_minutes_doc, load_minutes_json, save_minutes_json_atomic
from agendasnap.store.atomic import write_text_atomic

logger = logging.getLogger(__name__)

MINUTES_BUILDER_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "meeting_info": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "title": {"type": "string"},
                "date": {"type": "string", "description": "YYYY-MM-DD または '未記載'"},
                "participants": {"type": "array", "items": {"type": "string"}},
                "location": {"type": "string"},
            },
            "required": ["title", "date", "participants", "location"],
        },
        "summary": {"type": "string"},
        "decisions": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "decision": {"type": "string"},
                    "owner": {"type": "string"},
                    "due": {"type": "string"},
                },
                "required": ["decision", "owner", "due"],
            },
        },
        "action_items": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "task": {"type": "string"},
                    "owner": {"type": "string"},
                    "due": {"type": "string"},
                    "priority": {"type": "string", "enum": ["H", "M", "L"]},
                },
                "required": ["task", "owner", "due", "priority"],
            },
        },
        "sections": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "heading": {"type": "string"},
                    "bullets": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["heading", "bullets"],
            },
        },
        "next_agenda": {"type": "array", "items": {"type": "string"}},
        "risks": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "meeting_info",
        "summary",
        "decisions",
        "action_items",
        "sections",
        "next_agenda",
        "risks",
    ],
}

MINUTES_BUILDER_SYSTEM_PROMPT_JA = """あなたは日本語の議事録作成者です。
入力は文字起こしであり、誤記・聞き間違いが含まれます。

ルール:
- 根拠のない推測・捏造は禁止。不明な情報は '未記載' と書く。
- 文字起こしから合理的に推定できる情報は補完してよいが、その値には必ず「（推定）」を付与する。
- meeting_info は必ず埋める。title/date/location が不明なら '未記載'。participants が不明なら空配列。
- decisions と action_items は重要。存在しない場合は空配列で返す（勝手に作らない）。
- action_items.priority は H/M/L を付与（緊急/重要そうならH、通常M、軽微L。確信が無ければM）。
- sections は「背景」「論点」「合意の方向性」「教育テーマ」「今後の進め方」など、会話に即して適切に作る（見出しと箇条書き）。
- 簡潔に。重複は統合する。
- 出力は JSON のみ（説明文や Markdown は禁止）。
"""

MINUTES_MERGE_SYSTEM_PROMPT_JA = """あなたは複数の部分議事録を統合する編集者です。
入力は部分ごとの議事録JSONです。重複や言い換えは統合し、矛盾がある場合はより具体的・根拠が強い内容を優先してください。
推定で補完した値には必ず「（推定）」を付与してください。
必須セクション（summary/decisions/action_items）は必ず出力してください。
出力は指定スキーマに従うJSONのみです（説明文やMarkdownは禁止）。
"""


@dataclass
class LlmMinutesConfig:
    enable: bool
    incremental_enable: bool
    incremental_mode: str
    model: str
    final_model: str
    reasoning_effort: Optional[str]
    temperature: float
    max_output_tokens: int
    incremental_max_output_tokens: int
    final_max_output_tokens: int
    store: bool
    structured_output: bool
    min_interval_seconds: float
    min_new_segments: int
    max_segments_per_call: int
    request_timeout_seconds: float
    confidence_threshold: float
    dedupe_similarity: float
    prompt_version: str
    language: str
    category_hints: dict
    system_prompt: Optional[str]
    filter_enable: bool
    filter_min_chars: int
    filter_allowlist: List[str]


@dataclass
class FinalizeChunkingConfig:
    mode: str
    min_chars: int
    max_chars: int
    overlap_chars: int
    max_segments: int


@dataclass
class FinalizeConfig:
    request_timeout_seconds: float
    retries: int
    retry_backoff_seconds: float
    fallback_model: str
    fallback_request_timeout_seconds: float
    chunking: FinalizeChunkingConfig


def _load_llm_cfg(minutes_cfg: dict) -> LlmMinutesConfig:
    llm = minutes_cfg.get("llm") or {}
    filt = minutes_cfg.get("filter") or {}
    return LlmMinutesConfig(
        enable=bool(llm.get("enable", False)),
        incremental_enable=bool(llm.get("incremental_enable", True)),
        incremental_mode=str(llm.get("incremental_mode", "llm")).strip().lower() or "llm",
        model=str(llm.get("model", "gpt-4o-mini")),
        final_model=str(llm.get("final_model", llm.get("model", "gpt-4o-mini"))),
        reasoning_effort=str(llm.get("reasoning_effort")).strip().lower()
        if llm.get("reasoning_effort") is not None
        else None,
        temperature=float(llm.get("temperature", 0.2)),
        max_output_tokens=int(llm.get("max_output_tokens", 800)),
        incremental_max_output_tokens=int(
            llm.get("incremental_max_output_tokens", llm.get("max_output_tokens", 800))
        ),
        final_max_output_tokens=int(llm.get("final_max_output_tokens", llm.get("max_output_tokens", 800))),
        store=bool(llm.get("store", False)),
        structured_output=bool(llm.get("structured_output", False)),
        min_interval_seconds=float(llm.get("min_interval_seconds", 60)),
        min_new_segments=int(llm.get("min_new_segments", 6)),
        max_segments_per_call=int(llm.get("max_segments_per_call", 12)),
        request_timeout_seconds=float(llm.get("request_timeout_seconds", 30)),
        confidence_threshold=float(llm.get("confidence_threshold", 0.45)),
        dedupe_similarity=float(llm.get("dedupe_similarity", 0.9)),
        prompt_version=str(llm.get("prompt_version", "v1")),
        language=str(llm.get("language", "ja")),
        category_hints=llm.get("category_hints") or {},
        system_prompt=llm.get("system_prompt"),
        filter_enable=bool(filt.get("enable", False)),
        filter_min_chars=int(filt.get("min_chars", 0) or 0),
        filter_allowlist=[str(x) for x in (filt.get("allowlist") or [])],
    )


def _load_finalize_cfg(minutes_cfg: dict, llm_cfg: LlmMinutesConfig) -> FinalizeConfig:
    fin = minutes_cfg.get("finalize") if isinstance(minutes_cfg, dict) else {}
    if not isinstance(fin, dict):
        fin = {}
    chunk = fin.get("chunking") if isinstance(fin.get("chunking"), dict) else {}
    if not isinstance(chunk, dict):
        chunk = {}

    mode = str(chunk.get("mode", "auto")).strip().lower() or "auto"
    if mode not in {"auto", "always", "off"}:
        mode = "auto"

    return FinalizeConfig(
        request_timeout_seconds=float(fin.get("request_timeout_seconds", llm_cfg.request_timeout_seconds)),
        retries=int(fin.get("retries", 0) or 0),
        retry_backoff_seconds=float(fin.get("retry_backoff_seconds", 5.0)),
        fallback_model=str(fin.get("fallback_model", llm_cfg.final_model or llm_cfg.model)),
        fallback_request_timeout_seconds=float(
            fin.get("fallback_request_timeout_seconds", llm_cfg.request_timeout_seconds)
        ),
        chunking=FinalizeChunkingConfig(
            mode=mode,
            min_chars=int(chunk.get("min_chars", 12000) or 0),
            max_chars=int(chunk.get("max_chars", 12000) or 12000),
            overlap_chars=int(chunk.get("overlap_chars", 400) or 0),
            max_segments=int(chunk.get("max_segments", 200) or 200),
        ),
    )


def _text_similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def _build_hints_text(hints: dict) -> str:
    if not hints:
        return ""
    lines = ["Category hints (optional):"]
    for key, vals in hints.items():
        if not vals:
            continue
        if isinstance(vals, list):
            joined = " / ".join(str(x) for x in vals)
        else:
            joined = str(vals)
        lines.append(f"- {key}: {joined}")
    return "\n".join(lines)


def _default_system_prompt(language: str, hints: dict) -> str:
    hint_text = _build_hints_text(hints)
    return "\n".join(
        [
            "You are a meeting minutes assistant.",
            f"Use {language} for all output text.",
            "Classify each transcript segment into exactly one of:",
            "agenda_items, decisions, action_items, open_questions, risks, notes.",
            "Write concise, minutes-friendly phrasing suitable for bullet lists.",
            "agenda_items: short topic titles (noun phrases).",
            "decisions: state the conclusion (e.g., '〜と決定').",
            "action_items: start with an action verb (e.g., '〜する').",
            "Also produce a short summary (summary) of key points (max 5 items).",
            "Always include header with all fields; if unknown, leave empty string or empty list.",
            "Header fields: title, date, time, location, facilitator, recorder, attendees, absentees, purpose.",
            "Fill header only when explicitly stated in the provided transcript segments.",
            "You may infer fields only if the transcript strongly implies them, and then append '（推定）' to the value.",
            "If header info is partial, only fill the known fields and leave the rest empty.",
            "Attendees/absentees must be explicit lists (do not include speakers unless explicitly listed).",
            "Only use the provided transcript segments. Do not invent facts.",
            "If meaning is unclear or confidence is low, put it in notes.",
            "For action_items, include owner/due only when explicitly stated; otherwise leave empty.",
            "Each item must include text, t0, t1, source, confidence (0-1).",
            "If an item already exists in existing_items, omit it.",
            "Return JSON strictly following the provided schema.",
            "Output JSON only. Do not wrap in markdown or add commentary.",
            hint_text,
        ]
    ).strip()


def _build_response_schema() -> dict:
    header_schema = {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "date": {"type": "string"},
            "time": {"type": "string"},
            "location": {"type": "string"},
            "facilitator": {"type": "string"},
            "recorder": {"type": "string"},
            "attendees": {"type": "array", "items": {"type": "string"}},
            "absentees": {"type": "array", "items": {"type": "string"}},
            "purpose": {"type": "string"},
        },
        "required": [
            "title",
            "date",
            "time",
            "location",
            "facilitator",
            "recorder",
            "attendees",
            "absentees",
            "purpose",
        ],
        "additionalProperties": False,
    }
    base_item = {
        "type": "object",
        "properties": {
            "text": {"type": "string"},
            "t0": {"type": "number"},
            "t1": {"type": "number"},
            "source": {"type": "string"},
            "confidence": {"type": "number"},
        },
        "required": ["text", "t0", "t1", "source", "confidence"],
        "additionalProperties": False,
    }
    action_item = {
        "type": "object",
        "properties": {
            "text": {"type": "string"},
            "owner": {"type": "string"},
            "due": {"type": "string"},
            "t0": {"type": "number"},
            "t1": {"type": "number"},
            "source": {"type": "string"},
            "confidence": {"type": "number"},
        },
        "required": ["text", "owner", "due", "t0", "t1", "source", "confidence"],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {
            "header": header_schema,
            "summary": {"type": "array", "items": base_item},
            "agenda_items": {"type": "array", "items": base_item},
            "decisions": {"type": "array", "items": base_item},
            "action_items": {"type": "array", "items": action_item},
            "open_questions": {"type": "array", "items": base_item},
            "risks": {"type": "array", "items": base_item},
            "notes": {"type": "array", "items": base_item},
        },
        "required": [
            "header",
            "summary",
            "agenda_items",
            "decisions",
            "action_items",
            "open_questions",
            "risks",
            "notes",
        ],
        "additionalProperties": False,
    }


_DELTA_SCHEMA_DESC = """JSON object with keys:
- header: object {title,date,time,location,facilitator,recorder,attendees,absentees,purpose}
  - title/date/time/location/facilitator/recorder/purpose are strings ("" if unknown)
  - attendees/absentees are arrays of strings (empty array if unknown)
- summary: array of items {text,t0,t1,source,confidence}
- agenda_items: array of items {text,t0,t1,source,confidence}
- decisions: array of items {text,t0,t1,source,confidence}
- action_items: array of items {text,owner,due,t0,t1,source,confidence}
- open_questions: array of items {text,t0,t1,source,confidence}
- risks: array of items {text,t0,t1,source,confidence}
- notes: array of items {text,t0,t1,source,confidence}
All arrays must exist (use empty arrays when none)."""

_FINAL_SCHEMA_DESC = """JSON object with keys:
- meeting_info: object {title,date,participants,location}
  - title/date/location are strings (use '未記載' if unknown; append '（推定）' if inferred)
  - participants is array of strings (empty array if unknown)
- summary: string (empty if none)
- decisions: array of {decision,owner,due}
- action_items: array of {task,owner,due,priority} where priority is H/M/L
- sections: array of {heading,bullets} where bullets is array of strings
- next_agenda: array of strings
- risks: array of strings
All arrays must exist (use empty arrays when none)."""


def _extract_json_block(text: str) -> str | None:
    if not text:
        return None
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        return fence.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return text[start : end + 1].strip()
    return None


def _safe_json_load(text: str) -> dict | None:
    if not text:
        return None
    candidates = [text]
    extracted = _extract_json_block(text)
    if extracted and extracted not in candidates:
        candidates.append(extracted)
    for cand in candidates:
        try:
            obj = json.loads(cand)
        except Exception:
            continue
        if isinstance(obj, dict):
            return obj
    return None


def _is_retryable_exception(exc: Exception) -> bool:
    msg = str(exc).lower()
    if "timed out" in msg or "timeout" in msg:
        return True
    if "connection error" in msg:
        return True
    if "http error" in msg and " 5" in msg:
        return True
    return False


def _chunk_segments(
    segments: List[TranscriptSegment],
    *,
    max_chars: int,
    overlap_chars: int,
    max_segments: int,
) -> List[List[TranscriptSegment]]:
    chunks: List[List[TranscriptSegment]] = []
    current: List[TranscriptSegment] = []
    current_chars = 0

    def _segment_len(seg: TranscriptSegment) -> int:
        text = (seg.text or "").strip()
        if not text:
            return 0
        return len(text) + 1

    def _flush() -> None:
        nonlocal current, current_chars
        if not current:
            return
        chunks.append(current)
        if overlap_chars <= 0:
            current = []
            current_chars = 0
            return
        overlap: List[TranscriptSegment] = []
        count = 0
        for seg in reversed(current):
            seg_len = _segment_len(seg)
            if seg_len == 0:
                continue
            overlap.append(seg)
            count += seg_len
            if count >= overlap_chars:
                break
        overlap = list(reversed(overlap))
        current = overlap
        current_chars = sum(_segment_len(s) for s in current)

    for seg in segments:
        seg_len = _segment_len(seg)
        if seg_len == 0:
            continue
        if current and (
            (max_chars > 0 and current_chars + seg_len > max_chars)
            or (max_segments > 0 and len(current) >= max_segments)
        ):
            _flush()
        current.append(seg)
        current_chars += seg_len
    if current:
        chunks.append(current)
    return chunks


def _validate_delta_shape(data: dict | None) -> bool:
    if not isinstance(data, dict):
        return False
    required = [
        "header",
        "summary",
        "agenda_items",
        "decisions",
        "action_items",
        "open_questions",
        "risks",
        "notes",
    ]
    for key in required:
        if key not in data:
            return False
    if not isinstance(data.get("header"), dict):
        return False
    for key in required[1:]:
        if not isinstance(data.get(key), list):
            return False
    return True


def _validate_final_shape(data: dict | None) -> bool:
    if not isinstance(data, dict):
        return False
    required = ["meeting_info", "summary", "decisions", "action_items", "sections", "next_agenda", "risks"]
    for key in required:
        if key not in data:
            return False
    if not isinstance(data.get("meeting_info"), dict):
        return False
    if not isinstance(data.get("summary"), str):
        return False
    for key in required[2:]:
        if not isinstance(data.get(key), list):
            return False
    return True


def _empty_delta_payload() -> dict:
    return {
        "header": {
            "title": "",
            "date": "",
            "time": "",
            "location": "",
            "facilitator": "",
            "recorder": "",
            "attendees": [],
            "absentees": [],
            "purpose": "",
        },
        "summary": [],
        "agenda_items": [],
        "decisions": [],
        "action_items": [],
        "open_questions": [],
        "risks": [],
        "notes": [],
    }


def _empty_final_payload() -> dict:
    return {
        "meeting_info": {
            "title": "未記載",
            "date": "未記載",
            "participants": [],
            "location": "未記載",
        },
        "summary": "",
        "decisions": [],
        "action_items": [],
        "sections": [],
        "next_agenda": [],
        "risks": [],
    }


def _build_user_prompt(segments: list[dict], existing: dict, header: dict, summary: list) -> str:
    payload = {
        "segments": segments,
        "existing_items": existing,
        "existing_header": header,
        "existing_summary": summary,
    }
    return json.dumps(payload, ensure_ascii=False)


def _is_gpt5_1_or_5_2(model: str) -> bool:
    m = (model or "").strip()
    return m == "gpt-5.2" or m.startswith("gpt-5.2-") or m == "gpt-5.1" or m.startswith("gpt-5.1-")


def _build_minutes_builder_user_prompt(transcript: str) -> str:
    return (
        "以下の文字起こしから、統一フォーマットの議事録データを作成してください。\n"
        "誤記・言い淀み・重複・途中で切れた文が含まれている前提で、意味が通るように補正してください。\n"
        "固有名詞や数値は、根拠が不十分な場合は推測せず、曖昧さを残してください。\n"
        "推定で補完した値には必ず「（推定）」を付与してください。\n"
        "必ず指定スキーマに従って JSON のみを出力してください。\n\n"
        "---\n"
        f"{transcript}\n"
        "---"
    )


def _build_minutes_merge_user_prompt(partials: List[Dict[str, Any]]) -> str:
    payload = {"partials": partials}
    return json.dumps(payload, ensure_ascii=False)


def _build_transcript_text(segments: List[TranscriptSegment]) -> str:
    lines: list[str] = []
    for seg in segments:
        text = (seg.text or "").strip()
        if text:
            lines.append(text)
    return "\n".join(lines).strip()


def _minutes_builder_to_markdown(minutes: Dict[str, Any]) -> str:
    mi = minutes["meeting_info"]
    title = mi.get("title", "未記載")
    date = mi.get("date", "未記載")
    location = mi.get("location", "未記載")
    participants = mi.get("participants") or []

    summary = minutes.get("summary", "").strip()
    decisions = minutes.get("decisions") or []
    action_items = minutes.get("action_items") or []
    sections = minutes.get("sections") or []
    next_agenda = minutes.get("next_agenda") or []
    risks = minutes.get("risks") or []

    lines: list[str] = []
    lines.append(f"# 議事録：{title}")
    lines.append("")
    lines.append("## 会議情報")
    lines.append(f"- 日付: {date}")
    lines.append(f"- 場所: {location}")
    if participants:
        lines.append(f"- 参加者: {', '.join(participants)}")
    else:
        lines.append("- 参加者: 未記載")
    lines.append("")

    lines.append("## サマリー")
    lines.append(summary if summary else "（未記載）")
    lines.append("")

    lines.append("## 決定事項")
    if decisions:
        for d in decisions:
            lines.append(
                f"- {d.get('decision','')}（Owner: {d.get('owner','未記載')} / Due: {d.get('due','未記載')}）"
            )
    else:
        lines.append("- （なし）")
    lines.append("")

    lines.append("## アクションアイテム")
    if action_items:
        for a in action_items:
            pr = a.get("priority", "M")
            lines.append(
                f"- [{pr}] {a.get('task','')}（Owner: {a.get('owner','未記載')} / Due: {a.get('due','未記載')}）"
            )
    else:
        lines.append("- （なし）")
    lines.append("")

    lines.append("## 本文")
    if sections:
        for s in sections:
            heading = s.get("heading", "").strip() or "（無題）"
            bullets = s.get("bullets") or []
            lines.append(f"### {heading}")
            if bullets:
                for b in bullets:
                    lines.append(f"- {b}")
            else:
                lines.append("- （なし）")
            lines.append("")
    else:
        lines.append("（本文なし）")
        lines.append("")

    lines.append("## リスク・懸念")
    if risks:
        for r in risks:
            lines.append(f"- {r}")
    else:
        lines.append("- （なし）")
    lines.append("")

    lines.append("## 次回議題案")
    if next_agenda:
        for n in next_agenda:
            lines.append(f"- {n}")
    else:
        lines.append("- （なし）")
    lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _extract_existing_titles(doc: MinutesDocument, limit: int = 50) -> dict:
    def _take(items: Iterable) -> list[str]:
        out = []
        for item in items:
            if item.text:
                out.append(item.text)
            if len(out) >= limit:
                break
        return out

    return {
        "agenda_items": _take(doc.agenda_items),
        "decisions": _take(doc.decisions),
        "action_items": _take(doc.action_items),
        "open_questions": _take(doc.open_questions),
        "risks": _take(doc.risks),
        "notes": _take(doc.notes),
        "summary": _take(doc.summary),
    }


def _evidence_from_item(item: dict) -> Evidence:
    return Evidence(
        text=str(item.get("text", "")),
        t0=float(item.get("t0", 0.0) or 0.0),
        t1=float(item.get("t1", 0.0) or 0.0),
        source=item.get("source"),
    )


def _append_item(
    items: list,
    text: str,
    evidence: Evidence,
    confidence: float,
    *,
    dedupe_similarity: float,
    existing_texts: list[str],
    filter_enable: bool,
    filter_min_chars: int,
    filter_allowlist: list[str],
) -> None:
    if not text:
        return
    cleaned = text.strip()
    if not cleaned:
        return
    if filter_enable:
        if cleaned in filter_allowlist:
            pass
        elif len(cleaned) < int(filter_min_chars):
            return
    for existing in existing_texts:
        if _text_similarity(cleaned, existing) >= dedupe_similarity:
            return
    items.append((cleaned, evidence, confidence))
    existing_texts.append(cleaned)


def _apply_delta(doc: MinutesDocument, delta: dict, cfg: LlmMinutesConfig) -> None:
    thr = float(cfg.confidence_threshold)
    sim = float(cfg.dedupe_similarity)
    filter_enable = bool(cfg.filter_enable)
    filter_min_chars = int(cfg.filter_min_chars)
    filter_allowlist = list(cfg.filter_allowlist)

    existing_agenda = [x.text for x in doc.agenda_items]
    existing_decisions = [x.text for x in doc.decisions]
    existing_actions = [x.text for x in doc.action_items]
    existing_questions = [x.text for x in doc.open_questions]
    existing_risks = [x.text for x in doc.risks]
    existing_notes = [x.text for x in doc.notes]
    existing_summary = [x.text for x in doc.summary]

    new_agenda: list = []
    new_decisions: list = []
    new_actions: list = []
    new_questions: list = []
    new_risks: list = []
    new_notes: list = []
    new_summary: list = []

    header_delta = delta.get("header") if isinstance(delta, dict) else None
    if isinstance(header_delta, dict):
        def _set_header(attr: str, key: str) -> None:
            val = header_delta.get(key)
            if isinstance(val, str):
                val = val.strip()
                if val:
                    setattr(doc.header, attr, val)

        _set_header("title", "title")
        _set_header("date", "date")
        _set_header("time", "time")
        _set_header("location", "location")
        _set_header("facilitator", "facilitator")
        _set_header("recorder", "recorder")
        _set_header("purpose", "purpose")

        def _merge_list(attr: str, key: str) -> None:
            vals = header_delta.get(key)
            if not isinstance(vals, list):
                return
            current = getattr(doc.header, attr) or []
            merged = list(current)
            for v in vals:
                if not isinstance(v, str):
                    continue
                s = v.strip()
                if not s:
                    continue
                if s not in merged:
                    merged.append(s)
            setattr(doc.header, attr, merged)

        _merge_list("attendees", "attendees")
        _merge_list("absentees", "absentees")

    for item in delta.get("agenda_items", []):
        ev = _evidence_from_item(item)
        conf = float(item.get("confidence", 0.5))
        if conf < thr:
            _append_item(
                new_notes,
                item.get("text", ""),
                ev,
                conf,
                dedupe_similarity=sim,
                existing_texts=existing_notes,
                filter_enable=filter_enable,
                filter_min_chars=filter_min_chars,
                filter_allowlist=filter_allowlist,
            )
        else:
            _append_item(
                new_agenda,
                item.get("text", ""),
                ev,
                conf,
                dedupe_similarity=sim,
                existing_texts=existing_agenda,
                filter_enable=filter_enable,
                filter_min_chars=filter_min_chars,
                filter_allowlist=filter_allowlist,
            )

    for item in delta.get("decisions", []):
        ev = _evidence_from_item(item)
        conf = float(item.get("confidence", 0.5))
        if conf < thr:
            _append_item(
                new_notes,
                item.get("text", ""),
                ev,
                conf,
                dedupe_similarity=sim,
                existing_texts=existing_notes,
                filter_enable=filter_enable,
                filter_min_chars=filter_min_chars,
                filter_allowlist=filter_allowlist,
            )
        else:
            _append_item(
                new_decisions,
                item.get("text", ""),
                ev,
                conf,
                dedupe_similarity=sim,
                existing_texts=existing_decisions,
                filter_enable=filter_enable,
                filter_min_chars=filter_min_chars,
                filter_allowlist=filter_allowlist,
            )

    for item in delta.get("action_items", []):
        ev = _evidence_from_item(item)
        conf = float(item.get("confidence", 0.5))
        text = str(item.get("text", "")).strip()
        if conf < thr:
            _append_item(
                new_notes,
                text,
                ev,
                conf,
                dedupe_similarity=sim,
                existing_texts=existing_notes,
                filter_enable=filter_enable,
                filter_min_chars=filter_min_chars,
                filter_allowlist=filter_allowlist,
            )
        else:
            _append_item(
                new_actions,
                text,
                ev,
                conf,
                dedupe_similarity=sim,
                existing_texts=existing_actions,
                filter_enable=filter_enable,
                filter_min_chars=filter_min_chars,
                filter_allowlist=filter_allowlist,
            )

    for item in delta.get("open_questions", []):
        ev = _evidence_from_item(item)
        conf = float(item.get("confidence", 0.5))
        if conf < thr:
            _append_item(
                new_notes,
                item.get("text", ""),
                ev,
                conf,
                dedupe_similarity=sim,
                existing_texts=existing_notes,
                filter_enable=filter_enable,
                filter_min_chars=filter_min_chars,
                filter_allowlist=filter_allowlist,
            )
        else:
            _append_item(
                new_questions,
                item.get("text", ""),
                ev,
                conf,
                dedupe_similarity=sim,
                existing_texts=existing_questions,
                filter_enable=filter_enable,
                filter_min_chars=filter_min_chars,
                filter_allowlist=filter_allowlist,
            )

    for item in delta.get("risks", []):
        ev = _evidence_from_item(item)
        conf = float(item.get("confidence", 0.5))
        if conf < thr:
            _append_item(
                new_notes,
                item.get("text", ""),
                ev,
                conf,
                dedupe_similarity=sim,
                existing_texts=existing_notes,
                filter_enable=filter_enable,
                filter_min_chars=filter_min_chars,
                filter_allowlist=filter_allowlist,
            )
        else:
            _append_item(
                new_risks,
                item.get("text", ""),
                ev,
                conf,
                dedupe_similarity=sim,
                existing_texts=existing_risks,
                filter_enable=filter_enable,
                filter_min_chars=filter_min_chars,
                filter_allowlist=filter_allowlist,
            )

    for item in delta.get("notes", []):
        ev = _evidence_from_item(item)
        conf = float(item.get("confidence", 0.5))
        _append_item(
            new_notes,
            item.get("text", ""),
            ev,
            conf,
            dedupe_similarity=sim,
            existing_texts=existing_notes,
            filter_enable=filter_enable,
            filter_min_chars=filter_min_chars,
            filter_allowlist=filter_allowlist,
        )

    for item in delta.get("summary", []):
        ev = _evidence_from_item(item)
        conf = float(item.get("confidence", 0.5))
        _append_item(
            new_summary,
            item.get("text", ""),
            ev,
            conf,
            dedupe_similarity=sim,
            existing_texts=existing_summary,
            filter_enable=filter_enable,
            filter_min_chars=filter_min_chars,
            filter_allowlist=filter_allowlist,
        )

    for text, ev, conf in new_agenda:
        doc.agenda_items.append(AgendaItem(text=text, evidence=[ev], confidence=conf))
    for text, ev, conf in new_decisions:
        doc.decisions.append(Decision(text=text, evidence=[ev], confidence=conf))
    for text, ev, conf in new_actions:
        owner = None
        due = None
        # try to preserve owner/due when present in delta
        for item in delta.get("action_items", []):
            if str(item.get("text", "")).strip() == text:
                owner = item.get("owner") or None
                due = item.get("due") or None
                break
        doc.action_items.append(ActionItem(text=text, owner=owner, due=due, evidence=[ev], confidence=conf))
    for text, ev, conf in new_questions:
        doc.open_questions.append(OpenQuestion(text=text, evidence=[ev], confidence=conf))
    for text, ev, conf in new_risks:
        doc.risks.append(RiskItem(text=text, evidence=[ev], confidence=conf))
    for text, ev, conf in new_notes:
        doc.notes.append(NoteItem(text=text, evidence=[ev], confidence=conf))
    for text, ev, conf in new_summary:
        doc.summary.append(SummaryItem(text=text, evidence=[ev], confidence=conf))


class LlmMinutesUpdater:
    def __init__(self, *, session_dir, minutes_cfg: dict, api_key_priority: Iterable[str]) -> None:
        self.session_dir = session_dir
        self.raw_minutes_cfg = minutes_cfg
        self.minutes_cfg = apply_minutes_profile(minutes_cfg)
        self.minutes_profile = describe_minutes_profile(self.minutes_cfg)
        self.llm_cfg = _load_llm_cfg(self.minutes_cfg)
        self.finalize_cfg = _load_finalize_cfg(self.minutes_cfg, self.llm_cfg)
        self.api_key_priority = list(api_key_priority)
        llm_raw = self.minutes_cfg.get("llm") if isinstance(self.minutes_cfg.get("llm"), dict) else {}
        runtime = resolve_text_runtime(
            llm_raw,
            fallback_priority=self.api_key_priority,
            purpose="minutes",
        )
        self.runtime_provider = str(runtime.get("provider") or "openai")
        self.runtime_api_key_priority = list(runtime.get("api_key_priority") or self.api_key_priority)
        self.runtime_api_key_service = str(runtime.get("api_key_service") or "openai")
        self.runtime_base_url = str(runtime.get("base_url") or "")
        self.runtime_model = str(runtime.get("model") or self.llm_cfg.model)
        self.runtime_final_model = str(runtime.get("final_model") or self.llm_cfg.final_model)

        fin_cfg = self.minutes_cfg.get("finalize") if isinstance(self.minutes_cfg.get("finalize"), dict) else {}
        low_cost_fallback_model = str(fin_cfg.get("low_cost_fallback_model", "")).strip()
        if str(runtime.get("cost_profile") or "standard") == "low_cost" and low_cost_fallback_model:
            self.runtime_fallback_model = low_cost_fallback_model
        else:
            self.runtime_fallback_model = self.finalize_cfg.fallback_model

        cost_tracking = llm_raw.get("cost_tracking") if isinstance(llm_raw.get("cost_tracking"), dict) else {}
        self.cost_tracking_enabled = bool(cost_tracking.get("enable", False))
        cost_filename = str(cost_tracking.get("filename") or "llm_costs.jsonl").strip()
        if not cost_filename:
            cost_filename = "llm_costs.jsonl"
        self.cost_log_path = self.session_dir / cost_filename
        self.cost_session_id = getattr(self.session_dir, "name", "") or str(self.session_dir)

        self.client = OpenAIResponsesClient(
            provider=self.runtime_provider,
            api_key_priority=self.runtime_api_key_priority,
            api_key_service=self.runtime_api_key_service,
            base_url=self.runtime_base_url,
            timeout_seconds=self.llm_cfg.request_timeout_seconds,
        )
        self.minutes_path = self.session_dir / "minutes.json"
        self.doc = load_minutes_json(self.minutes_path)
        if self.doc.meta.version == 0:
            self.doc = init_minutes_doc(
                model=self.runtime_model,
                mode="incremental",
                prompt_version=self.llm_cfg.prompt_version,
            )
        self.last_index = int(self.doc.meta.last_segment_index or 0)
        self.last_call_time = 0.0

    def _make_client(self, timeout_seconds: float) -> OpenAIResponsesClient:
        return OpenAIResponsesClient(
            provider=self.runtime_provider,
            api_key_priority=self.runtime_api_key_priority,
            api_key_service=self.runtime_api_key_service,
            base_url=self.runtime_base_url,
            timeout_seconds=float(timeout_seconds),
        )

    def _write_cost_record(self, record: LlmCostRecord) -> None:
        if not self.cost_tracking_enabled:
            return
        try:
            append_cost_record_jsonl(self.cost_log_path, record)
        except Exception as exc:  # noqa: BLE001
            logger.debug("Failed to write LLM cost record: %s", exc)

    async def _request_json(
        self,
        payload: dict,
        *,
        client: OpenAIResponsesClient | None = None,
        component: str = "other",
        model: str = "",
        source: str = "",
        retry_count: int = 0,
    ) -> dict:
        req_client = client or self.client
        started_at = time.time()
        started_mono = time.monotonic()
        record_model = str(model or payload.get("model") or "")
        try:
            resp = await asyncio.to_thread(req_client.request_json, payload)
        except Exception as exc:  # noqa: BLE001
            elapsed = time.monotonic() - started_mono
            self._write_cost_record(
                LlmCostRecord.from_payload_response(
                    component=component,
                    model=record_model,
                    session_id=self.cost_session_id,
                    source=source,
                    payload=payload,
                    response=None,
                    started_at=started_at,
                    elapsed_seconds=elapsed,
                    success=False,
                    failure=type(exc).__name__,
                    retry_count=retry_count,
                )
            )
            raise

        elapsed = time.monotonic() - started_mono
        self._write_cost_record(
            LlmCostRecord.from_payload_response(
                component=component,
                model=record_model,
                session_id=self.cost_session_id,
                source=source,
                payload=payload,
                response=resp,
                started_at=started_at,
                elapsed_seconds=elapsed,
                success=True,
                retry_count=retry_count,
            )
        )
        return resp

    async def _request_with_retries(
        self,
        fn,
        *,
        retries: int,
        backoff_seconds: float,
    ):
        attempt = 0
        while True:
            try:
                return await fn()
            except Exception as exc:  # noqa: BLE001
                if attempt >= retries or not _is_retryable_exception(exc):
                    raise
                wait_s = float(backoff_seconds) * (2**attempt)
                logger.warning("Retryable LLM error: %s (retrying in %.1fs)", exc, wait_s)
                attempt += 1
                await asyncio.sleep(wait_s)

    def _apply_common_controls(
        self,
        payload: dict,
        *,
        temperature: float,
        max_output_tokens: int,
        model: str,
    ) -> dict:
        payload["temperature"] = float(temperature)
        payload["max_output_tokens"] = int(max_output_tokens)
        payload["store"] = bool(self.llm_cfg.store)
        if self.llm_cfg.reasoning_effort and _is_gpt5_1_or_5_2(model):
            payload["reasoning"] = {"effort": self.llm_cfg.reasoning_effort}
        if _is_gpt5_1_or_5_2(model):
            text_obj = payload.get("text") if isinstance(payload.get("text"), dict) else {}
            text_obj["verbosity"] = "low"
            payload["text"] = text_obj
        return payload

    def _build_payload(self, *, segments: list[TranscriptSegment], model: str) -> dict:
        sys_prompt = self.llm_cfg.system_prompt or _default_system_prompt(
            self.llm_cfg.language, self.llm_cfg.category_hints
        )
        if not self.llm_cfg.structured_output:
            sys_prompt = "\n".join([sys_prompt, "Schema:", _DELTA_SCHEMA_DESC, "Output JSON only."])
        segment_payload = [
            {
                "text": s.text,
                "t0": float(s.start or 0.0),
                "t1": float(s.end or 0.0),
                "source": s.source,
            }
            for s in segments
            if s and s.text and s.text.strip()
        ]
        existing = _extract_existing_titles(self.doc, limit=50)
        header = self.doc.header.to_dict() if self.doc.header else {}
        existing_summary = existing.get("summary", [])

        user_prompt = _build_user_prompt(segment_payload, existing, header, existing_summary)
        payload: dict = {
            "model": model,
            "input": [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        if self.llm_cfg.structured_output:
            schema = _build_response_schema()
            payload["text"] = {
                "format": {
                    "type": "json_schema",
                    "name": "minutes_delta",
                    "schema": schema,
                    "strict": True,
                }
            }
        return self._apply_common_controls(
            payload,
            temperature=self.llm_cfg.temperature,
            max_output_tokens=self.llm_cfg.incremental_max_output_tokens,
            model=model,
        )

    def _build_payload_minutes_builder(self, *, transcript: str, model: str) -> dict:
        user_prompt = _build_minutes_builder_user_prompt(transcript)
        sys_prompt = MINUTES_BUILDER_SYSTEM_PROMPT_JA
        if not self.llm_cfg.structured_output:
            sys_prompt = "\n".join([sys_prompt, "スキーマ:", _FINAL_SCHEMA_DESC, "JSONのみを出力してください。"])
        payload: dict = {
            "model": model,
            "input": [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "truncation": "auto",
        }

        if self.llm_cfg.structured_output:
            payload["text"] = {
                "format": {
                    "type": "json_schema",
                    "name": "meeting_minutes",
                    "schema": MINUTES_BUILDER_SCHEMA,
                    "strict": True,
                }
            }
        return self._apply_common_controls(
            payload,
            temperature=self.llm_cfg.temperature,
            max_output_tokens=self.llm_cfg.final_max_output_tokens,
            model=model,
        )

    async def _repair_json(
        self,
        *,
        bad_text: str,
        schema_desc: str,
        model: str,
        client: OpenAIResponsesClient | None = None,
    ) -> dict | None:
        system_prompt = (
            "You are a JSON repair tool. Fix the provided output to exactly match the schema. "
            "Return JSON only."
        )
        user_prompt = "\n".join(
            [
                "Schema:",
                schema_desc,
                "",
                "Invalid output:",
                bad_text.strip(),
                "",
                "Return corrected JSON only.",
            ]
        )
        payload: dict = {
            "model": model,
            "input": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        payload = self._apply_common_controls(
            payload,
            temperature=0.0,
            max_output_tokens=self.llm_cfg.final_max_output_tokens,
            model=model,
        )
        resp = await self._request_json(
            payload,
            client=client,
            component="minutes_final",
            model=model,
            source="json_repair",
        )
        text = extract_output_text(resp)
        return _safe_json_load(text)

    async def _decode_json_response(
        self,
        *,
        resp: dict,
        schema_desc: str,
        validate_fn,
        fallback: dict,
        model: str,
        client: OpenAIResponsesClient | None = None,
    ) -> dict:
        data: dict | None
        if self.llm_cfg.structured_output:
            data = extract_output_json(resp)
        else:
            text = extract_output_text(resp)
            data = _safe_json_load(text)
        if validate_fn(data):
            return data  # type: ignore[return-value]

        logger.warning("Minutes JSON invalid; attempting repair.")
        bad_text = json.dumps(data, ensure_ascii=False) if data is not None else extract_output_text(resp)
        repaired = await self._repair_json(
            bad_text=bad_text,
            schema_desc=schema_desc,
            model=model,
            client=client,
        )
        if validate_fn(repaired):
            return repaired  # type: ignore[return-value]

        logger.error("Minutes JSON repair failed; using fallback payload.")
        return fallback

    async def _call_llm_delta(
        self,
        *,
        segments: list[TranscriptSegment],
        model: str,
        client: OpenAIResponsesClient | None = None,
    ) -> dict:
        payload = self._build_payload(segments=segments, model=model)
        resp = await self._request_json(
            payload,
            client=client,
            component="minutes_incremental",
            model=model,
            source="incremental_delta",
        )
        return await self._decode_json_response(
            resp=resp,
            schema_desc=_DELTA_SCHEMA_DESC,
            validate_fn=_validate_delta_shape,
            fallback=_empty_delta_payload(),
            model=model,
            client=client,
        )

    async def _call_llm_minutes_builder(
        self,
        *,
        transcript: str,
        model: str,
        client: OpenAIResponsesClient | None = None,
    ) -> dict:
        payload = self._build_payload_minutes_builder(transcript=transcript, model=model)
        resp = await self._request_json(
            payload,
            client=client,
            component="minutes_final",
            model=model,
            source="final_builder",
        )
        return await self._decode_json_response(
            resp=resp,
            schema_desc=_FINAL_SCHEMA_DESC,
            validate_fn=_validate_final_shape,
            fallback=_empty_final_payload(),
            model=model,
            client=client,
        )

    async def _call_llm_minutes_merge(
        self,
        *,
        partials: List[Dict[str, Any]],
        model: str,
        client: OpenAIResponsesClient | None = None,
    ) -> dict:
        user_prompt = _build_minutes_merge_user_prompt(partials)
        sys_prompt = MINUTES_MERGE_SYSTEM_PROMPT_JA
        if not self.llm_cfg.structured_output:
            sys_prompt = "\n".join([sys_prompt, "スキーマ:", _FINAL_SCHEMA_DESC, "JSONのみを出力してください。"])
        payload: dict = {
            "model": model,
            "input": [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "truncation": "auto",
        }
        if self.llm_cfg.structured_output:
            payload["text"] = {
                "format": {
                    "type": "json_schema",
                    "name": "meeting_minutes_merge",
                    "schema": MINUTES_BUILDER_SCHEMA,
                    "strict": True,
                }
            }
        payload = self._apply_common_controls(
            payload,
            temperature=self.llm_cfg.temperature,
            max_output_tokens=self.llm_cfg.final_max_output_tokens,
            model=model,
        )
        resp = await self._request_json(
            payload,
            client=client,
            component="minutes_final",
            model=model,
            source="final_merge",
        )
        return await self._decode_json_response(
            resp=resp,
            schema_desc=_FINAL_SCHEMA_DESC,
            validate_fn=_validate_final_shape,
            fallback=_empty_final_payload(),
            model=model,
            client=client,
        )

    def _should_call(self, *, new_count: int) -> bool:
        if new_count <= 0:
            return False
        if not self.last_call_time:
            return new_count >= self.llm_cfg.min_new_segments
        elapsed = time.monotonic() - self.last_call_time
        if elapsed >= self.llm_cfg.min_interval_seconds:
            return True
        return new_count >= self.llm_cfg.min_new_segments

    async def update_incremental(self, segments: List[TranscriptSegment]) -> bool:
        if not self.llm_cfg.enable:
            return False
        if not self.llm_cfg.incremental_enable or self.llm_cfg.incremental_mode != "llm":
            return False
        if self.last_index >= len(segments):
            return False

        slice_segments = list(segments[self.last_index :])
        final_segments = [s for s in slice_segments if s.state == "final"]
        if not self._should_call(new_count=len(final_segments)):
            return False

        batch_slice = slice_segments[: self.llm_cfg.max_segments_per_call]
        batch = [s for s in batch_slice if s.state == "final"]
        if not batch:
            self.last_index += len(batch_slice)
            self.doc.meta.last_segment_index = int(self.last_index)
            return False

        try:
            delta = await self._call_llm_delta(segments=batch, model=self.runtime_model)
        except Exception as exc:  # noqa: BLE001
            logger.error("LLM minutes update failed: %s", exc)
            return False

        _apply_delta(self.doc, delta, self.llm_cfg)
        self.last_index += len(batch_slice)
        self.doc.meta.last_segment_index = int(self.last_index)
        self.doc.meta.model = self.runtime_model
        self.doc.meta.mode = "incremental"
        self.doc.meta.prompt_version = self.llm_cfg.prompt_version
        save_minutes_json_atomic(self.minutes_path, self.doc)

        md = render_minutes(self.doc)
        write_text_atomic(self.session_dir / "minutes.md", md, encoding="utf-8")

        self.last_call_time = time.monotonic()
        return True

    async def finalize(self, segments: List[TranscriptSegment]) -> bool:
        if not self.llm_cfg.enable:
            return False
        finals = [s for s in segments if s.state == "final"]
        if not finals:
            logger.warning("Finalize skipped: no final transcript segments.")
            if not self.minutes_path.exists():
                minutes = _empty_final_payload()
                write_text_atomic(
                    self.minutes_path,
                    json.dumps(minutes, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                md = _minutes_builder_to_markdown(minutes)
                write_text_atomic(self.session_dir / "minutes.md", md, encoding="utf-8")
            return False

        transcript = _build_transcript_text(finals)
        if not transcript:
            logger.warning("Finalize skipped: empty transcript.")
            if not self.minutes_path.exists():
                minutes = _empty_final_payload()
                write_text_atomic(
                    self.minutes_path,
                    json.dumps(minutes, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                md = _minutes_builder_to_markdown(minutes)
                write_text_atomic(self.session_dir / "minutes.md", md, encoding="utf-8")
            return False

        fin = self.finalize_cfg
        chunk_cfg = fin.chunking

        def _should_chunk() -> bool:
            if chunk_cfg.mode == "off":
                return False
            if chunk_cfg.mode == "always":
                return True
            if chunk_cfg.min_chars and len(transcript) >= chunk_cfg.min_chars:
                return True
            if chunk_cfg.max_segments and len(finals) >= chunk_cfg.max_segments:
                return True
            return False

        async def _finalize_with_model(model: str, timeout_seconds: float) -> dict:
            client = self._make_client(timeout_seconds)

            async def _single_pass(text: str) -> dict:
                async def _call():
                    return await self._call_llm_minutes_builder(
                        transcript=text,
                        model=model,
                        client=client,
                    )

                return await self._request_with_retries(
                    _call,
                    retries=fin.retries,
                    backoff_seconds=fin.retry_backoff_seconds,
                )

            async def _merge_pass(partials: List[Dict[str, Any]]) -> dict:
                async def _call():
                    return await self._call_llm_minutes_merge(
                        partials=partials,
                        model=model,
                        client=client,
                    )

                return await self._request_with_retries(
                    _call,
                    retries=fin.retries,
                    backoff_seconds=fin.retry_backoff_seconds,
                )

            if not _should_chunk():
                return await _single_pass(transcript)

            chunks = _chunk_segments(
                finals,
                max_chars=chunk_cfg.max_chars,
                overlap_chars=chunk_cfg.overlap_chars,
                max_segments=chunk_cfg.max_segments,
            )
            if len(chunks) <= 1:
                return await _single_pass(transcript)

            partials: List[Dict[str, Any]] = []
            for idx, chunk in enumerate(chunks):
                chunk_text = _build_transcript_text(chunk)
                if not chunk_text:
                    continue
                logger.info("Finalize chunk %d/%d: %d chars", idx + 1, len(chunks), len(chunk_text))
                partials.append(await _single_pass(chunk_text))

            if not partials:
                raise RuntimeError("Finalize chunking produced no partials")

            if len(partials) == 1:
                return partials[0]
            return await _merge_pass(partials)

        minutes: dict | None = None
        try:
            minutes = await _finalize_with_model(self.runtime_final_model, fin.request_timeout_seconds)
        except Exception as exc:  # noqa: BLE001
            logger.error("LLM minutes finalization failed: %s", exc)
            if self.runtime_fallback_model and self.runtime_fallback_model != self.runtime_final_model:
                try:
                    logger.warning("Finalize fallback to model=%s", self.runtime_fallback_model)
                    minutes = await _finalize_with_model(
                        self.runtime_fallback_model,
                        fin.fallback_request_timeout_seconds,
                    )
                except Exception as exc2:  # noqa: BLE001
                    logger.error("Finalize fallback failed: %s", exc2)
                    minutes = None
            else:
                minutes = None

        if minutes is None:
            logger.error("Finalize failed; keeping realtime minutes without overwrite.")
            if not self.minutes_path.exists():
                minutes = _empty_final_payload()
                write_text_atomic(
                    self.minutes_path,
                    json.dumps(minutes, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                md = _minutes_builder_to_markdown(minutes)
                write_text_atomic(self.session_dir / "minutes.md", md, encoding="utf-8")
            return False

        write_text_atomic(
            self.minutes_path,
            json.dumps(minutes, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        md = _minutes_builder_to_markdown(minutes)
        write_text_atomic(self.session_dir / "minutes.md", md, encoding="utf-8")

        self.last_index = len(finals)
        return True
