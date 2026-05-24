"""Safe STT error classification helpers."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping


PERMANENT = "permanent"
TRANSIENT = "transient"
UNKNOWN = "unknown"

_MAX_TEXT = 180
_SECRET_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"(?i)(api[_\- ]?key|authorization|bearer)\s*[:=]\s*[^\s,;]+"),
)
_TRANSIENT_KEYWORDS = (
    "timeout",
    "timed out",
    "websocket closed",
    "connection closed",
    "connection reset",
    "connection refused",
    "connection aborted",
    "network",
    "temporarily unavailable",
    "temporary",
    "try again",
    "server error",
    "internal server error",
    "service unavailable",
    "bad gateway",
    "gateway timeout",
    "rate_limit",
    "rate limit",
    "too many requests",
    "429",
    " 500",
    " 502",
    " 503",
    " 504",
)
_PERMANENT_KEYWORDS = (
    "invalid_api_key",
    "invalid api key",
    "incorrect api key",
    "authentication",
    "unauthorized",
    "authorization",
    "forbidden",
    "permission",
    "insufficient_permissions",
    "insufficient_quota",
    "quota exceeded",
    "billing",
    "payment",
    "model_not_found",
    "model not found",
    "does not exist",
    "does not have access",
    "unsupported configuration",
    "unsupported_configuration",
    "unsupported parameter",
    "unsupported_value",
)


@dataclass(frozen=True)
class SttErrorInfo:
    classification: str
    code: str | None = None
    message: str = ""
    event_type: str | None = None

    @property
    def safe_message(self) -> str:
        parts: list[str] = []
        if self.classification:
            parts.append(f"classification={self.classification}")
        if self.code:
            parts.append(f"code={self.code}")
        detail = _safe_detail_label(self.classification, f"{self.code or ''} {self.message}")
        if detail:
            parts.append(f"detail={detail}")
        return "; ".join(parts) or f"classification={UNKNOWN}"


class PermanentSttError(RuntimeError):
    """Raised when the current STT session should not retry with the same settings."""

    def __init__(self, info: SttErrorInfo):
        self.info = info
        super().__init__(info.safe_message)


def redact_sensitive_text(value: Any, *, max_length: int = _MAX_TEXT) -> str:
    """Return a bounded string with common secret shapes removed."""
    text = str(value or "").replace("\r", " ").replace("\n", " ").strip()
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    if len(text) > max_length:
        text = text[: max(0, max_length - 3)].rstrip() + "..."
    return text


def stt_error_safe_category(value: Any) -> str:
    """Return a compact non-sensitive STT error category for UI and diagnostics."""
    if value is None:
        return "unknown"
    if isinstance(value, SttErrorInfo):
        text = f"{value.classification} {value.code or ''} {value.message} {value.safe_message}".lower()
    else:
        text = str(value).lower()

    if "classification=transient" in text or "transient" in text:
        return "transient"
    if "missing_api_key" in text:
        return "missing_api_key"
    if "invalid_api_key" in text or "authentication" in text or "unauthorized" in text:
        return "authentication"
    if "authorization" in text or "permission" in text or "forbidden" in text:
        return "permission"
    if "insufficient_quota" in text or "quota" in text or "billing" in text or "payment" in text:
        return "quota_or_billing"
    if (
        "model_not_found" in text
        or "model or configuration" in text
        or "unsupported" in text
        or "configuration" in text
        or "invalid_request_error" in text
    ):
        return "model_or_configuration"
    if "classification=permanent" in text or "permanent" in text:
        return "permanent"
    return "unknown"


def summarize_realtime_error_event(event: Mapping[str, Any] | BaseException | str) -> SttErrorInfo:
    """Create a safe summary from a Realtime error payload or exception."""
    if isinstance(event, SttErrorInfo):
        return event
    if isinstance(event, PermanentSttError):
        return event.info
    if isinstance(event, BaseException):
        return classify_stt_error_text(type(event).__name__, str(event))
    if isinstance(event, Mapping):
        event_type = _safe_value(event.get("type"))
        raw_error = event.get("error")
        error = raw_error if isinstance(raw_error, Mapping) else event
        code = _first_text(error, "code", "type", "error_code")
        message = _first_text(error, "message", "detail", "error")
        if not message and raw_error is not None and not isinstance(raw_error, Mapping):
            message = _safe_value(raw_error)
        classification = classify_stt_error_text(code, message).classification
        return SttErrorInfo(
            classification=classification,
            code=code or None,
            message=message,
            event_type=event_type or None,
        )
    return classify_stt_error_text("", str(event))


def classify_stt_error(error: Mapping[str, Any] | BaseException | str) -> SttErrorInfo:
    """Classify an STT error as permanent, transient, or unknown."""
    return summarize_realtime_error_event(error)


def classify_stt_error_text(code: Any = "", message: Any = "") -> SttErrorInfo:
    code_text = _safe_value(code)
    message_text = _safe_value(message)
    haystack = f"{code_text} {message_text}".lower()
    if any(keyword in haystack for keyword in _TRANSIENT_KEYWORDS):
        classification = TRANSIENT
    elif any(keyword in haystack for keyword in _PERMANENT_KEYWORDS):
        classification = PERMANENT
    elif not haystack.strip():
        classification = UNKNOWN
    else:
        classification = UNKNOWN
    return SttErrorInfo(
        classification=classification,
        code=code_text or None,
        message=message_text,
    )


def make_stt_exception(info: SttErrorInfo) -> RuntimeError:
    if info.classification == PERMANENT:
        return PermanentSttError(info)
    return RuntimeError(info.safe_message)


def _first_text(mapping: Mapping[str, Any], *keys: str) -> str:
    for key in keys:
        value = mapping.get(key)
        if value is not None:
            text = _safe_value(value)
            if text:
                return text
    return ""


def _safe_value(value: Any) -> str:
    if isinstance(value, (dict, list, tuple, set)):
        return redact_sensitive_text(type(value).__name__)
    return redact_sensitive_text(value)


def _safe_detail_label(classification: str, haystack: str) -> str:
    text = str(haystack or "").lower()
    if classification == PERMANENT:
        if any(keyword in text for keyword in ("invalid_api_key", "api key", "authentication", "unauthorized")):
            return "authentication error"
        if any(keyword in text for keyword in ("authorization", "permission", "forbidden")):
            return "permission error"
        if any(keyword in text for keyword in ("quota", "billing", "payment")):
            return "quota or billing error"
        if any(keyword in text for keyword in ("model", "unsupported")):
            return "model or configuration error"
        return "permanent STT error"
    if classification == TRANSIENT:
        return "transient STT error"
    if classification == UNKNOWN:
        return "unclassified STT error"
    return ""
