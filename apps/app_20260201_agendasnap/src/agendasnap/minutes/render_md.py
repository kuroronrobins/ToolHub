"""Render minutes to Markdown (readable meeting notes format)."""
from __future__ import annotations

from datetime import datetime

from agendasnap.minutes.schema import MinutesDocument


def _clean_text(text: str) -> str:
    return (text or "").strip()


def _escape_table(text: str) -> str:
    if text is None:
        return ""
    return text.replace("|", "\\|")


def _render_list(items, *, empty_text: str = "（なし）") -> list[str]:
    lines: list[str] = []
    for item in items or []:
        text = _clean_text(getattr(item, "text", "") or "")
        if text:
            lines.append(f"- {text}")
    if not lines:
        lines.append(f"- {empty_text}")
    return lines


def _render_action_items(items) -> list[str]:
    if not items:
        return ["（なし）"]

    rows: list[str] = []
    idx = 1
    for item in items:
        text = _clean_text(getattr(item, "text", "") or "")
        if not text:
            continue
        owner = _clean_text(getattr(item, "owner", "") or "")
        due = _clean_text(getattr(item, "due", "") or "")
        status = _clean_text(getattr(item, "status", "") or "")
        rows.append(
            f"| {idx} | {_escape_table(text)} | {_escape_table(owner) or '未設定'} | "
            f"{_escape_table(due) or '未設定'} | {_escape_table(status)} |"
        )
        idx += 1

    if not rows:
        return ["（なし）"]

    return [
        "| # | 内容 | 担当 | 期限 | 状態 |",
        "| - | - | - | - | - |",
        *rows,
    ]


def _is_japanese_char(ch: str) -> bool:
    code = ord(ch)
    return (
        0x3040 <= code <= 0x309F  # Hiragana
        or 0x30A0 <= code <= 0x30FF  # Katakana
        or 0x4E00 <= code <= 0x9FFF  # CJK Unified Ideographs
        or 0xFF66 <= code <= 0xFF9D  # Half-width Katakana
    )


def _max_run_length(text: str) -> int:
    if not text:
        return 0
    max_run = 1
    run = 1
    prev = text[0]
    for ch in text[1:]:
        if ch == prev:
            run += 1
            if run > max_run:
                max_run = run
        else:
            run = 1
            prev = ch
    return max_run


def _note_is_noise(
    text: str,
    confidence: float | None,
    *,
    core_char_sets: list[set[str]] | None = None,
) -> bool:
    cleaned = _clean_text(text)
    if not cleaned:
        return True
    if confidence is not None and confidence < 0.45:
        return True
    if len(cleaned) < 4:
        return True

    valid = 0
    for ch in cleaned:
        if ch.isalnum() or _is_japanese_char(ch):
            valid += 1
    if valid / max(1, len(cleaned)) < 0.5:
        return True

    if _max_run_length(cleaned) >= max(6, int(len(cleaned) * 0.6)):
        return True

    if core_char_sets:
        note_chars = {ch for ch in cleaned if _is_japanese_char(ch)}
        if len(note_chars) >= 3:
            max_sim = 0.0
            for core in core_char_sets:
                if not core:
                    continue
                inter = len(note_chars & core)
                union = len(note_chars | core)
                if union:
                    sim = inter / union
                    if sim > max_sim:
                        max_sim = sim
            if len(cleaned) < 6 and max_sim < 0.25:
                return True
            if max_sim < 0.2:
                return True
    return False


def _render_notes(items, *, core_char_sets: list[set[str]] | None = None) -> tuple[list[str], int]:
    lines: list[str] = []
    for item in items or []:
        text = _clean_text(getattr(item, "text", "") or "")
        conf = getattr(item, "confidence", None)
        if not text:
            continue
        if _note_is_noise(text, conf, core_char_sets=core_char_sets):
            continue
        lines.append(f"- {text}")
    count = len(lines)
    if not lines:
        lines.append("- （なし）")
    return lines, count


def _top_texts(items, *, limit: int = 3) -> list[str]:
    out: list[str] = []
    for item in items or []:
        text = _clean_text(getattr(item, "text", "") or "")
        if text:
            out.append(text)
        if len(out) >= limit:
            break
    return out


def _format_generated_at(value: str | None) -> str:
    if not value:
        return "（未設定）"
    try:
        dt = datetime.fromisoformat(value)
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return value


def render(doc: MinutesDocument) -> str:
    has_any = any(
        [
            doc.agenda_items,
            doc.decisions,
            doc.action_items,
            doc.open_questions,
            doc.risks,
            doc.notes,
        ]
    )
    lines: list[str] = ["# 議事録", ""]
    if not has_any:
        lines.append("（記録なし）")
        return "\n".join(lines)

    generated_at = _format_generated_at(getattr(doc.meta, "generated_at", None))
    header = getattr(doc, "header", None)
    title = _clean_text(getattr(header, "title", "") or "")
    date = _clean_text(getattr(header, "date", "") or "")
    time = _clean_text(getattr(header, "time", "") or "")
    location = _clean_text(getattr(header, "location", "") or "")
    recorder = _clean_text(getattr(header, "recorder", "") or "")
    attendees = ", ".join([x for x in (getattr(header, "attendees", None) or []) if _clean_text(x)])
    absentees = ", ".join([x for x in (getattr(header, "absentees", None) or []) if _clean_text(x)])

    # Meeting header (placeholders for now)
    lines.append("## 会議情報")
    lines.extend(
        [
            "| 項目 | 内容 |",
            "| - | - |",
            f"| 会議名 | {title or '（未設定）'} |",
            f"| 会議日時 | {(date + ' ' + time).strip() or '（未設定）'} |",
            f"| 場所 | {location or '（未設定）'} |",
            f"| 記録者 | {recorder or '（未設定）'} |",
            f"| 出席者 | {attendees or '（未設定）'} |",
            f"| 欠席者 | {absentees or '（未設定）'} |",
            f"| 記録作成 | {generated_at} |",
        ]
    )
    lines.append("")

    # Summary
    lines.append("## サマリー")
    summary_items = _top_texts(getattr(doc, "summary", []) or [], limit=5)
    if summary_items:
        lines.extend([f"- {x}" for x in summary_items])
    else:
        summary_lines = []
        decisions = _top_texts(doc.decisions, limit=3)
        actions = _top_texts(doc.action_items, limit=3)
        agenda = _top_texts(doc.agenda_items, limit=3)
        pending = _top_texts(doc.open_questions, limit=3)
        risks = _top_texts(doc.risks, limit=3)

        summary_lines.append(
            "- 決定事項: " + (" / ".join(decisions) if decisions else "（なし）")
        )
        summary_lines.append(
            "- アクション: " + (" / ".join(actions) if actions else "（なし）")
        )
        summary_lines.append(
            "- 議題: " + (" / ".join(agenda) if agenda else "（なし）")
        )
        summary_lines.append(
            "- 保留: " + (" / ".join(pending) if pending else "（なし）")
        )
        summary_lines.append(
            "- リスク: " + (" / ".join(risks) if risks else "（なし）")
        )
        lines.extend(summary_lines)
    lines.append("")

    # 1) Decisions (most actionable)
    lines.append(f"## 決定事項（{len(doc.decisions)}件）")
    lines.extend(_render_list(doc.decisions))
    lines.append("")

    # 2) Action items
    lines.append(f"## アクションアイテム（{len(doc.action_items)}件）")
    lines.extend(_render_action_items(doc.action_items))
    lines.append("")

    # 3) Agenda / Discussion topics
    lines.append(f"## 議題・論点（{len(doc.agenda_items)}件）")
    lines.extend(_render_list(doc.agenda_items))
    lines.append("")

    # 4) Open questions / Pending
    lines.append(f"## 保留・未決事項（{len(doc.open_questions)}件）")
    lines.extend(_render_list(doc.open_questions))
    lines.append("")

    # 5) Risks / Concerns
    lines.append(f"## リスク・懸念（{len(doc.risks)}件）")
    lines.extend(_render_list(doc.risks))
    lines.append("")

    # 6) Notes
    core_texts: list[str] = []
    core_texts.extend(_top_texts(doc.summary, limit=10))
    core_texts.extend(_top_texts(doc.agenda_items, limit=10))
    core_texts.extend(_top_texts(doc.decisions, limit=10))
    core_texts.extend(_top_texts(doc.action_items, limit=10))
    core_texts.extend(_top_texts(doc.open_questions, limit=10))
    core_texts.extend(_top_texts(doc.risks, limit=10))
    core_sets = [
        {ch for ch in _clean_text(text) if _is_japanese_char(ch)} for text in core_texts if _clean_text(text)
    ]
    note_lines, note_count = _render_notes(doc.notes, core_char_sets=core_sets if core_sets else None)
    lines.append(f"## メモ（{note_count}件）")
    lines.extend(note_lines)

    return "\n".join(lines)
