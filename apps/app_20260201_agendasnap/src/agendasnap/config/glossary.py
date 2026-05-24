"""Meeting glossary normalization and prompt helpers.

The glossary can contain user-specific names and terms. Keep this module free of
project defaults that would encourage committing real meeting vocabulary.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping


GLOSSARY_CATEGORIES = (
    "general",
    "technical",
    "product",
    "person",
    "place",
    "department",
)

ROLLING_CONTEXT_UPDATE_POLICIES = (
    "session_start",
    "rolling_session",
    "manual_only",
    "session_update_experimental",
)
ROLLING_CONTEXT_GUARD_STYLES = (
    "current",
    "minimal",
    "sentence_end_only",
    "no_repetition_only",
    "none",
)

DEFAULT_ROLLING_CONTEXT_SETTINGS: dict[str, Any] = {
    "enable": True,
    "use_recent_final_transcript": False,
    "use_topic": False,
    "use_glossary": False,
    "use_summary": False,
    "max_recent_segments": 1,
    "max_recent_chars": 200,
    "max_glossary_terms": 20,
    "max_prompt_chars": 1200,
    "update_policy": "rolling_session",
    "guard_style": "current",
    "include_partial": False,
    "include_low_confidence": False,
    "repetition_guard": True,
}


@dataclass(frozen=True)
class GlossaryTerm:
    surface: str
    readings: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()
    category: str = "general"
    note: str = ""
    enabled: bool = True


def split_glossary_values(value: Any) -> tuple[str, ...]:
    """Split UI text like "けんしょう / kenshou, 検証" into clean values."""
    if value is None:
        return ()
    if isinstance(value, (list, tuple)):
        raw_parts = [str(item) for item in value]
    else:
        text = str(value)
        for delimiter in ("、", "，", ",", "/", "\n", "\t"):
            text = text.replace(delimiter, "\n")
        raw_parts = text.splitlines()
    seen: set[str] = set()
    result: list[str] = []
    for raw in raw_parts:
        item = str(raw).strip()
        if not item or item in seen:
            continue
        seen.add(item)
        result.append(item)
    return tuple(result)


def _normalize_category(value: Any) -> str:
    category = str(value or "general").strip().lower() or "general"
    return category if category in GLOSSARY_CATEGORIES else "general"


def normalize_glossary(raw: Any) -> list[GlossaryTerm]:
    """Accept legacy list[str] and the structured dict form."""
    if raw is None:
        return []
    if isinstance(raw, Mapping):
        raw_items = raw.get("items") or raw.get("terms") or []
    else:
        raw_items = raw
    if not isinstance(raw_items, list):
        return []

    terms: list[GlossaryTerm] = []
    for item in raw_items:
        if isinstance(item, str):
            surface = item.strip()
            if surface:
                terms.append(GlossaryTerm(surface=surface))
            continue
        if not isinstance(item, Mapping):
            continue
        surface = str(item.get("surface") or item.get("term") or item.get("word") or "").strip()
        if not surface:
            continue
        enabled_raw = item.get("enabled", True)
        enabled = enabled_raw if isinstance(enabled_raw, bool) else str(enabled_raw).strip().lower() not in {
            "0",
            "false",
            "off",
            "disabled",
            "no",
        }
        terms.append(
            GlossaryTerm(
                surface=surface,
                readings=split_glossary_values(item.get("readings") or item.get("reading")),
                aliases=split_glossary_values(item.get("aliases") or item.get("alias")),
                category=_normalize_category(item.get("category")),
                note=str(item.get("note") or "").strip(),
                enabled=enabled,
            )
        )
    return terms


def glossary_to_config(terms: Iterable[GlossaryTerm]) -> list[dict[str, Any]]:
    """Serialize the structured glossary while omitting empty optional fields."""
    payload: list[dict[str, Any]] = []
    for term in terms:
        surface = str(term.surface or "").strip()
        if not surface:
            continue
        item: dict[str, Any] = {"surface": surface, "enabled": bool(term.enabled)}
        if term.readings:
            item["readings"] = list(term.readings)
        if term.aliases:
            item["aliases"] = list(term.aliases)
        if term.category and term.category != "general":
            item["category"] = term.category
        if term.note:
            item["note"] = term.note
        payload.append(item)
    return payload


def glossary_preview_text(terms: Iterable[GlossaryTerm]) -> str:
    lines: list[str] = []
    for term in terms:
        status = "ON" if term.enabled else "OFF"
        extras: list[str] = []
        if term.readings:
            extras.append("読み: " + " / ".join(term.readings))
        if term.aliases:
            extras.append("誤変換候補: " + " / ".join(term.aliases))
        if term.note:
            extras.append("文脈: " + term.note)
        detail = " / ".join(extras)
        lines.append(f"[{status}] {term.surface}" + (f" ({detail})" if detail else ""))
    return "\n".join(lines)


def enabled_glossary_terms(raw: Any) -> list[GlossaryTerm]:
    return [term for term in normalize_glossary(raw) if term.enabled and term.surface.strip()]


def _term_stt_line(term: GlossaryTerm) -> str:
    reads = "」「".join(term.readings)
    aliases = "」「".join(term.aliases)
    parts: list[str] = []
    if term.readings:
        parts.append(f"「{reads}」と聞こえる語は、文脈上「{term.surface}」と表記する。")
    else:
        parts.append(f"専門用語・固有名詞「{term.surface}」を正しい表記として優先する。")
    if term.aliases:
        parts.append(f"誤変換候補「{aliases}」が文脈に合う場合は「{term.surface}」を優先する。")
    if term.category and term.category != "general":
        parts.append(f"カテゴリ: {term.category}。")
    if term.note:
        parts.append(f"文脈: {term.note}。")
    return " ".join(parts)


def _as_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"1", "true", "yes", "on", "enabled"}:
            return True
        if text in {"0", "false", "no", "off", "disabled"}:
            return False
    return bool(value)


def _as_positive_int(value: Any, default: int, *, minimum: int = 0) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = int(default)
    return max(int(minimum), parsed)


def normalize_stt_guard_style(value: Any) -> str:
    """Return a supported guard prompt style, preserving current behavior by default."""
    style = str(value or "current").strip().lower()
    return style if style in ROLLING_CONTEXT_GUARD_STYLES else "current"


def normalize_rolling_context_settings(settings: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Return safe Rolling STT Context settings with defaults for missing keys."""
    raw = settings if isinstance(settings, Mapping) else {}
    result = dict(DEFAULT_ROLLING_CONTEXT_SETTINGS)
    for key in (
        "enable",
        "use_recent_final_transcript",
        "use_topic",
        "use_glossary",
        "use_summary",
        "include_low_confidence",
        "repetition_guard",
    ):
        result[key] = _as_bool(raw.get(key, result[key]), bool(result[key]))
    # Partial hypotheses are intentionally excluded from Rolling STT Context.
    result["include_partial"] = False
    result["max_recent_segments"] = _as_positive_int(
        raw.get("max_recent_segments", result["max_recent_segments"]),
        int(result["max_recent_segments"]),
        minimum=0,
    )
    result["max_recent_chars"] = _as_positive_int(
        raw.get("max_recent_chars", result["max_recent_chars"]),
        int(result["max_recent_chars"]),
        minimum=0,
    )
    result["max_glossary_terms"] = _as_positive_int(
        raw.get("max_glossary_terms", result["max_glossary_terms"]),
        int(result["max_glossary_terms"]),
        minimum=0,
    )
    result["max_prompt_chars"] = _as_positive_int(
        raw.get("max_prompt_chars", result["max_prompt_chars"]),
        int(result["max_prompt_chars"]),
        minimum=1,
    )
    policy = str(raw.get("update_policy", result["update_policy"]) or "").strip()
    result["update_policy"] = (
        policy if policy in ROLLING_CONTEXT_UPDATE_POLICIES else "rolling_session"
    )
    result["guard_style"] = normalize_stt_guard_style(raw.get("guard_style", result["guard_style"]))
    return result


def _build_transcription_parts(
    base_prompt: Any,
    topic: Any = "",
    glossary: Any = None,
    *,
    include_topic: bool = True,
    include_glossary: bool = True,
    max_glossary_terms: int = 80,
) -> list[str]:
    parts: list[str] = []
    base = str(base_prompt or "").strip()
    if base:
        parts.append(base)
    topic_text = str(topic or "").strip()
    if include_topic and topic_text:
        parts.append(f"今日の会議テーマ: {topic_text}")
    terms = enabled_glossary_terms(glossary) if include_glossary else []
    if terms and max_glossary_terms > 0:
        parts.append(
            "専門用語辞書: 読み・聞こえ方と表記を照合し、文脈に合う場合だけ正しい表記を優先する。"
        )
        parts.extend(f"- {_term_stt_line(term)}" for term in terms[:max_glossary_terms])
    return parts


def build_transcription_prompt(
    base_prompt: Any,
    topic: Any = "",
    glossary: Any = None,
    *,
    include_topic: bool = True,
    include_glossary: bool = True,
    max_glossary_terms: int = 80,
) -> str:
    """Build a conservative STT prompt from base text, topic and glossary.

    This function only creates model instructions. It does not perform automatic
    transcript replacement.
    """
    return "\n".join(
        _build_transcription_parts(
            base_prompt,
            topic,
            glossary,
            include_topic=include_topic,
            include_glossary=include_glossary,
            max_glossary_terms=max_glossary_terms,
        )
    ).strip()


def _segment_state(segment: Any) -> str:
    if isinstance(segment, Mapping):
        return str(segment.get("state") or segment.get("status") or "").strip().lower()
    return str(getattr(segment, "state", "") or getattr(segment, "status", "") or "").strip().lower()


def _segment_confidence(segment: Any) -> float | None:
    value = segment.get("confidence") if isinstance(segment, Mapping) else getattr(segment, "confidence", None)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _segment_text(segment: Any) -> str:
    if isinstance(segment, str):
        return segment
    if isinstance(segment, Mapping):
        return str(segment.get("text") or segment.get("transcript") or "")
    return str(getattr(segment, "text", "") or getattr(segment, "transcript", "") or "")


def _clean_segment_text(text: Any) -> str:
    return " ".join(str(text or "").split())


def recent_final_transcript_texts(
    segments: Iterable[Any],
    *,
    max_segments: int = 6,
    max_chars: int = 600,
    include_partial: bool = False,
    include_low_confidence: bool = False,
    low_confidence_threshold: float = 0.45,
) -> list[str]:
    """Collect recent final transcript texts for STT context without changing storage.

    Strings are treated as already-final text. Transcript-like mappings/objects
    must have state="final"; include_partial is retained for config compatibility
    but partial hypotheses are never included.
    """
    _ = include_partial
    if max_segments <= 0 or max_chars <= 0:
        return []
    collected: list[str] = []
    seen: set[str] = set()
    used_chars = 0

    for segment in reversed(list(segments or [])):
        state = _segment_state(segment)
        if state and state != "final":
            continue
        confidence = _segment_confidence(segment)
        if (
            confidence is not None
            and not include_low_confidence
            and 0.0 <= confidence < float(low_confidence_threshold)
        ):
            continue
        text = _clean_segment_text(_segment_text(segment))
        if not text or text in seen:
            continue
        remaining = max_chars - used_chars
        if remaining <= 0:
            break
        if len(text) > remaining:
            text = text[-remaining:].lstrip()
        if not text:
            break
        collected.append(text)
        seen.add(text)
        used_chars += len(text)
        if len(collected) >= max_segments:
            break
    collected.reverse()
    return collected


def _trim_to_limit(text: str, limit: int) -> str:
    if limit <= 0:
        return ""
    if len(text) <= limit:
        return text
    return text[:limit].rstrip()


def _fit_prompt_sections(sections: Iterable[str], max_chars: int) -> str:
    prompt = ""
    for section in sections:
        text = str(section or "").strip()
        if not text:
            continue
        separator = "\n\n" if prompt else ""
        candidate = f"{prompt}{separator}{text}"
        if len(candidate) <= max_chars:
            prompt = candidate
            continue
        remaining = max_chars - len(prompt) - len(separator)
        if remaining <= 0:
            break
        trimmed = _trim_to_limit(text, remaining)
        if trimmed:
            prompt = f"{prompt}{separator}{trimmed}" if prompt else trimmed
        break
    return _trim_to_limit(prompt, max_chars).strip()


def _fit_sections_with_required_tail(
    priority_sections: Iterable[str],
    required_tail: str,
    max_chars: int,
) -> str:
    """Fit priority content while reserving room for required safety guidance."""
    tail = str(required_tail or "").strip()
    if not tail:
        return _fit_prompt_sections(priority_sections, max_chars)
    separator_len = 2
    content_budget = max(0, int(max_chars) - len(tail) - separator_len)
    if content_budget <= 0:
        return _fit_prompt_sections([tail], max_chars)
    body = _fit_prompt_sections(priority_sections, content_budget)
    return _fit_prompt_sections([body, tail], max_chars)


def _current_guard_section(*, repetition_guard: bool = True) -> str:
    lines = [
        "Rolling STT Context 指示:",
        "- 日本語の会議音声を正確に文字起こしする。",
        "- 音声にない内容を追加・推測・創作しない。",
        "- 直前文脈は用語、話題、句読点、疑問形判断の参考にだけ使う。",
        "- 文末の「です」「ですか」「ます」「ますか」などを落とさない。",
        "- 疑問形に聞こえる場合だけ疑問符を使い、音声にない疑問符は勝手に足さない。",
    ]
    if repetition_guard:
        lines.append("- 直前文脈を新しい文字起こしとして繰り返さない。同じ発話を重複出力しない。")
    return "\n".join(lines)


def build_stt_guard_prompt(style: str = "current", *, repetition_guard: bool = True) -> str:
    """Build only the guard wording used by Rolling STT Context."""
    normalized_style = normalize_stt_guard_style(style)
    if normalized_style == "none":
        return ""
    if normalized_style == "minimal":
        return "日本語会議音声を正確に文字起こししてください。音声にない内容を追加しないでください。"
    if normalized_style == "sentence_end_only":
        return (
            "文末の「です」「ですか」「ます」「ますか」を落とさないでください。"
            "疑問形に聞こえる場合のみ疑問符を使い、音声にない疑問符は追加しないでください。"
        )
    if normalized_style == "no_repetition_only":
        return "直前文脈を新しい文字起こしとして繰り返さないでください。同じ発話を重複出力しないでください。"
    return _current_guard_section(repetition_guard=repetition_guard)


def _rolling_guard_section(settings: Mapping[str, Any]) -> str:
    return build_stt_guard_prompt(
        str(settings.get("guard_style", "current")),
        repetition_guard=bool(settings.get("repetition_guard", True)),
    )


def build_rolling_transcription_prompt(
    base_prompt: Any,
    topic: Any = "",
    glossary: Any = None,
    recent_final_segments: Iterable[Any] | None = None,
    rolling_summary: Any = "",
    settings: Mapping[str, Any] | None = None,
) -> str:
    """Build STT prompt with bounded recent final context.

    This is a prompt-context improvement for Realtime STT. It does not rewrite
    transcript output and it deliberately excludes partial/non-final context by
    default.
    """
    normalized = normalize_rolling_context_settings(settings)
    if not normalized["enable"]:
        return build_transcription_prompt(base_prompt, topic, glossary)

    max_prompt_chars = int(normalized["max_prompt_chars"])
    sections: list[str] = []

    base = str(base_prompt or "").strip()
    if base:
        sections.append(base)

    topic_text = str(topic or "").strip()
    if normalized["use_topic"] and topic_text:
        sections.append(f"今日の会議テーマ: {topic_text}")

    terms = enabled_glossary_terms(glossary) if normalized["use_glossary"] else []
    max_glossary_terms = int(normalized["max_glossary_terms"])
    if terms and max_glossary_terms > 0:
        glossary_lines = [
            "専門用語辞書: 読み・聞こえ方と表記を照合し、文脈に合う場合だけ正しい表記を優先する。"
        ]
        glossary_lines.extend(f"- {_term_stt_line(term)}" for term in terms[:max_glossary_terms])
        sections.append("\n".join(glossary_lines))

    if normalized["use_recent_final_transcript"]:
        recent = recent_final_transcript_texts(
            recent_final_segments or [],
            max_segments=int(normalized["max_recent_segments"]),
            max_chars=int(normalized["max_recent_chars"]),
            include_partial=bool(normalized["include_partial"]),
            include_low_confidence=bool(normalized["include_low_confidence"]),
        )
        if recent:
            sections.append(
                "直近のfinal確定発話 (参考のみ、繰り返し禁止):\n"
                + "\n".join(f"- {line}" for line in recent)
            )

    summary_text = str(rolling_summary or "").strip()
    if normalized["use_summary"] and summary_text:
        sections.append(f"直近の会話文脈要約 (参考のみ):\n{summary_text}")

    return _fit_sections_with_required_tail(sections, _rolling_guard_section(normalized), max_prompt_chars)


def rolling_transcription_prompt_metadata(
    base_prompt: Any,
    topic: Any = "",
    glossary: Any = None,
    recent_final_segments: Iterable[Any] | None = None,
    rolling_summary: Any = "",
    settings: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return safe diagnostics for Rolling STT Context without exposing prompt text."""
    normalized = normalize_rolling_context_settings(settings)
    prompt = build_rolling_transcription_prompt(
        base_prompt,
        topic,
        glossary,
        recent_final_segments,
        rolling_summary,
        normalized,
    )
    recent = recent_final_transcript_texts(
        recent_final_segments or [],
        max_segments=int(normalized["max_recent_segments"]),
        max_chars=int(normalized["max_recent_chars"]),
        include_partial=False,
        include_low_confidence=bool(normalized["include_low_confidence"]),
    )
    glossary_terms = (
        enabled_glossary_terms(glossary)[: int(normalized["max_glossary_terms"])]
        if normalized["use_glossary"]
        else []
    )
    summary_text = str(rolling_summary or "").strip()
    return {
        "rolling_context_enabled": bool(normalized["enable"]),
        "update_policy": str(normalized["update_policy"]),
        "guard_style": str(normalized["guard_style"]),
        "prompt_chars": len(prompt),
        "max_prompt_chars": int(normalized["max_prompt_chars"]),
        "recent_segments_count": len(recent) if normalized["use_recent_final_transcript"] else 0,
        "recent_chars": sum(len(item) for item in recent) if normalized["use_recent_final_transcript"] else 0,
        "glossary_terms_count": len(glossary_terms),
        "topic_used": bool(normalized["use_topic"] and str(topic or "").strip()),
        "summary_used": bool(normalized["use_summary"] and summary_text),
        "include_partial": False,
        "include_low_confidence": bool(normalized["include_low_confidence"]),
    }


def build_minutes_context_prompt(topic: Any = "", glossary: Any = None) -> str:
    """Build context appended to minutes prompts."""
    lines: list[str] = []
    topic_text = str(topic or "").strip()
    if topic_text:
        lines.append(f"会議テーマ: {topic_text}")
    terms = enabled_glossary_terms(glossary)
    if terms:
        lines.append("専門用語・固有名詞は以下の表記を維持する。無条件置換はせず、文脈で判断する。")
        for term in terms[:80]:
            detail: list[str] = [f"表記: {term.surface}"]
            if term.readings:
                detail.append("読み/聞こえ方: " + " / ".join(term.readings))
            if term.aliases:
                detail.append("誤変換候補: " + " / ".join(term.aliases))
            if term.category and term.category != "general":
                detail.append(f"カテゴリ: {term.category}")
            if term.note:
                detail.append(f"文脈: {term.note}")
            lines.append("- " + "、".join(detail))
    return "\n".join(lines).strip()


def apply_explicit_alias_corrections(text: str, glossary: Any) -> str:
    """Conservatively replace only explicitly registered aliases.

    This helper is intentionally not wired into the live transcript path yet;
    callers must opt in because even alias replacement can be unsafe without
    confidence/context checks.
    """
    result = str(text or "")
    for term in enabled_glossary_terms(glossary):
        for alias in term.aliases:
            if alias:
                result = result.replace(alias, term.surface)
    return result
