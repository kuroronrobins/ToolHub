"""Realtime WebSocket client for transcription sessions.

Notes
-----
- WebSocket URL `model=...` must be a Realtime-capable model (e.g. `gpt-realtime`).
- The speech-to-text model is configured via `session.update` under
  `session.audio.input.transcription.model`.

This client assumes **client-side turn segmentation**. Therefore:
- Server turn detection is disabled (`turn_detection=None`).
- Each "turn" is committed via `input_audio_buffer.commit` and then cleared.

Design goals:
- Strict and explicit failure (no silent fallback).
- Upstream code decides retry/stop strategy.
"""
from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import logging
import time
from collections import deque
from dataclasses import dataclass
from typing import Any, Deque, Dict, Iterable, List, Mapping, Optional

import websockets

from agendasnap.apikeys.provider import resolve_api_key
from agendasnap.apikeys.service import api_key_missing_message
from agendasnap.bus.events import AudioChunk, TranscriptSegment
from agendasnap.stt.errors import (
    PERMANENT,
    PermanentSttError,
    SttErrorInfo,
    make_stt_exception,
    redact_sensitive_text,
    summarize_realtime_error_event,
)

logger = logging.getLogger(__name__)


_PROMPT_METADATA_BOOL_KEYS = (
    "rolling_context_enabled",
    "topic_used",
    "summary_used",
    "include_partial",
    "include_low_confidence",
)
_PROMPT_METADATA_INT_KEYS = (
    "glossary_terms_count",
    "recent_segments_count",
    "recent_chars",
)


def _safe_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() not in {"", "0", "false", "no", "off", "disabled", "null"}
    return bool(value)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return max(0, int(value))
    except Exception:
        return default


def sanitize_realtime_prompt_metadata(metadata: Mapping[str, Any] | None) -> dict[str, Any]:
    """Return prompt diagnostics that are safe to log.

    This deliberately excludes the prompt body, glossary text, topic text,
    transcript snippets, API keys, and any meeting content.
    """
    if not isinstance(metadata, Mapping):
        return {}

    safe: dict[str, Any] = {}
    for key in _PROMPT_METADATA_BOOL_KEYS:
        if key in metadata:
            safe[key] = _safe_bool(metadata.get(key))
    for key in _PROMPT_METADATA_INT_KEYS:
        if key in metadata:
            safe[key] = _safe_int(metadata.get(key))
    if "update_policy" in metadata:
        safe["update_policy"] = str(metadata.get("update_policy") or "").strip()
    if "guard_style" in metadata:
        safe["guard_style"] = str(metadata.get("guard_style") or "current").strip()
    return safe


@dataclass(frozen=True)
class TurnMeta:
    start: float
    end: float
    source: str  # "sys" or "mic"


@dataclass
class PendingTurn:
    meta: TurnMeta
    future: asyncio.Future[str]


def normalize_noise_reduction(value: Any) -> dict[str, str] | None:
    """Normalize Realtime noise reduction config.

    Disabled values are represented by omitting the field. The Realtime API
    must not receive {"type": "none"}.
    """
    if value is None:
        return None
    if isinstance(value, Mapping):
        value = value.get("type")
    text = str(value).strip().lower()
    if text in {"", "none", "off", "disabled", "disable", "false", "0", "null"}:
        return None
    if text in {"near_field", "far_field"}:
        return {"type": text}
    raise ValueError(f"Unsupported noise_reduction value: {value!r}")


class RealtimeSttClient:
    """Realtime transcription client (WebSocket)."""

    def __init__(
        self,
        *,
        url: str,
        api_key_priority: Iterable[str],
        api_key_service: str = "openai",
        language: Optional[str] = None,
        transcription_model: str = "gpt-4o-transcribe",
        source: str = "sys",
        noise_reduction: Optional[Any] = None,
        transcription_prompt: Optional[str] = None,
        prompt_metadata: Optional[Mapping[str, Any]] = None,
        request_timeout_seconds: float = 30.0,
    ):
        self.url = url
        self.api_key_priority = list(api_key_priority)
        self.api_key_service = str(api_key_service or "openai")
        self.language = (language or "ja")
        self.transcription_model = transcription_model
        self.source = source
        self.noise_reduction = normalize_noise_reduction(noise_reduction)
        self.transcription_prompt = str(transcription_prompt or "").strip()
        self.prompt_metadata = sanitize_realtime_prompt_metadata(prompt_metadata)
        self.request_timeout_seconds = float(request_timeout_seconds)

        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self._listen_task: Optional[asyncio.Task] = None
        self._send_lock = asyncio.Lock()

        self._pending_turns: Deque[PendingTurn] = deque()
        self._turns_by_item: Dict[str, PendingTurn] = {}

        self.session_id: Optional[str] = None

    def set_transcription_prompt(self, prompt: Optional[str]) -> None:
        """Update the prompt that will be sent on the next Realtime session start."""
        self.transcription_prompt = str(prompt or "").strip()

    def set_transcription_prompt_metadata(self, metadata: Mapping[str, Any] | None) -> None:
        """Update safe prompt metadata for the next Realtime session diagnostics."""
        self.prompt_metadata = sanitize_realtime_prompt_metadata(metadata)

    def session_diagnostics(self) -> dict[str, Any]:
        """Return safe Realtime session metadata without prompt or secret values."""
        metadata = self.prompt_metadata
        noise_reduction_type = self.noise_reduction.get("type") if self.noise_reduction else "disabled"
        return {
            "rolling_context_enabled": _safe_bool(metadata.get("rolling_context_enabled")),
            "update_policy": str(metadata.get("update_policy") or ""),
            "guard_style": str(metadata.get("guard_style") or "current"),
            "prompt_present": bool(self.transcription_prompt),
            "prompt_chars": len(self.transcription_prompt),
            "topic_used": _safe_bool(metadata.get("topic_used")),
            "glossary_terms_count": _safe_int(metadata.get("glossary_terms_count")),
            "recent_segments_count": _safe_int(metadata.get("recent_segments_count")),
            "noise_reduction": noise_reduction_type,
            "turn_detection_mode": "client_manual",
            "transcription_model": self.transcription_model,
            "language": self.language,
        }

    # --------------------------
    # lifecycle
    # --------------------------
    async def start(self) -> None:
        auth_value = self._get_api_key()
        headers = {"Authorization": f"Bearer {auth_value}"}

        # websockets v14+ renamed `extra_headers` -> `additional_headers`.
        try:
            self.ws = await websockets.connect(self.url, additional_headers=headers)
        except TypeError:
            self.ws = await websockets.connect(self.url, extra_headers=headers)

        logger.info("Realtime STT connected. url=%s", self.url)

        # Configure session before starting listener (so we can wait for ack synchronously).
        await self._configure_transcription_session()

        self._listen_task = asyncio.create_task(self._listen())

    async def stop(self) -> None:
        self._fail_all_pending(RuntimeError("Realtime STT stopped"))

        if self._listen_task:
            self._listen_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._listen_task
            self._listen_task = None

        if self.ws is not None:
            with contextlib.suppress(Exception):
                await self.ws.close()
            self.ws = None

    # --------------------------
    # main API
    # --------------------------
    async def push_audio(self, chunks: Iterable[AudioChunk]) -> List[TranscriptSegment]:
        """Send one (already segmented) audio turn and wait for its final transcript.

        Raises
        ------
        TimeoutError:
            If the server does not respond within request_timeout_seconds.
        RuntimeError:
            If connection/session is invalid.
        """
        chunk_list = [c for c in chunks if c and getattr(c, "pcm", None)]
        if not chunk_list:
            return []

        pcm = b"".join(c.pcm for c in chunk_list if c.pcm)
        if not pcm:
            return []

        start = float(next((c.t0 for c in chunk_list if c.t0 is not None), 0.0) or 0.0)
        end = float(next((c.t1 for c in reversed(chunk_list) if c.t1 is not None), start) or start)
        meta = TurnMeta(start=start, end=end, source=self.source)

        if self.ws is None:
            raise RuntimeError("RealtimeSttClient.start() must be called before push_audio().")

        loop = asyncio.get_running_loop()
        fut: asyncio.Future[str] = loop.create_future()
        pending = PendingTurn(meta=meta, future=fut)
        self._pending_turns.append(pending)

        audio_b64 = base64.b64encode(pcm).decode("ascii")
        await self._send({"type": "input_audio_buffer.append", "audio": audio_b64})
        await self._send({"type": "input_audio_buffer.commit"})
        await self._send({"type": "input_audio_buffer.clear"})

        transcript = await asyncio.wait_for(fut, timeout=self.request_timeout_seconds)
        transcript = (transcript or "").strip()
        if not transcript:
            return []

        return [TranscriptSegment(text=transcript, start=meta.start, end=meta.end, source=self.source, state="final")]

    # --------------------------
    # internals
    # --------------------------
    async def _configure_transcription_session(self) -> None:
        if self.ws is None:
            raise RuntimeError("WebSocket is not connected")

        payload = self._build_session_update_payload()
        diagnostics = self.session_diagnostics()

        logger.info(
            "Configuring Realtime session: transcription_model=%s language=%s noise_reduction=%s "
            "prompt_present=%s prompt_chars=%d",
            diagnostics["transcription_model"],
            diagnostics["language"],
            diagnostics["noise_reduction"],
            diagnostics["prompt_present"],
            diagnostics["prompt_chars"],
        )
        logger.debug("Realtime session diagnostics: %s", diagnostics)
        await self._send(payload)

        ok = await self._wait_session_updated_or_error(timeout_s=8.0)
        if not ok:
            raise RuntimeError("Realtime session.update was not acknowledged (session.updated missing).")

    def _build_session_update_payload(self) -> dict[str, Any]:
        transcription: dict[str, Any] = {
            "model": self.transcription_model,
            "language": self.language,
        }
        if self.transcription_prompt:
            transcription["prompt"] = self.transcription_prompt

        audio_input: dict[str, Any] = {
            "format": {"type": "audio/pcm", "rate": 24000},
            "transcription": transcription,
            "turn_detection": None,
        }
        if self.noise_reduction is not None:
            audio_input["noise_reduction"] = self.noise_reduction

        return {
            "type": "session.update",
            "session": {
                "type": "realtime",
                "audio": {
                    "input": audio_input,
                },
            },
        }

    async def _wait_session_updated_or_error(self, timeout_s: float) -> bool:
        assert self.ws is not None
        end_time = time.monotonic() + float(timeout_s)

        got_updated = False
        while time.monotonic() < end_time:
            try:
                msg = await asyncio.wait_for(self.ws.recv(), timeout=max(0.1, end_time - time.monotonic()))
            except asyncio.TimeoutError:
                break

            try:
                event = json.loads(msg)
            except Exception:
                continue

            etype = event.get("type")
            if etype == "session.created":
                self.session_id = (event.get("session") or {}).get("id")
                continue
            if etype == "session.updated":
                got_updated = True
                break
            if etype == "error":
                info = summarize_realtime_error_event(event)
                logger.error("Realtime server error during session.update: %s", info.safe_message)
                raise make_stt_exception(info)

        # Some servers may not emit session.updated reliably; treat as soft-success with warning.
        if not got_updated:
            logger.warning("No session.updated received during setup (continuing).")
            return True
        return True

    async def _listen(self) -> None:
        assert self.ws is not None
        try:
            async for message in self.ws:
                try:
                    event = json.loads(message)
                except Exception:
                    logger.debug("Non-JSON message from server: %r", message)
                    continue

                etype = event.get("type")

                if etype == "error":
                    info = summarize_realtime_error_event(event)
                    logger.error("Realtime server error event: %s", info.safe_message)
                    self._fail_all_pending(make_stt_exception(info))
                    continue

                if etype == "input_audio_buffer.committed":
                    item_id = event.get("item_id")
                    if not item_id:
                        continue
                    if self._pending_turns:
                        pending = self._pending_turns.popleft()
                        self._turns_by_item[item_id] = pending
                    continue

                if etype == "conversation.item.input_audio_transcription.completed":
                    item_id = event.get("item_id")
                    transcript = event.get("transcript") or ""
                    if not item_id:
                        continue
                    pending = self._turns_by_item.pop(item_id, None)
                    if pending and not pending.future.done():
                        pending.future.set_result(transcript)
                    continue

                if etype == "conversation.item.input_audio_transcription.failed":
                    item_id = event.get("item_id")
                    info = summarize_realtime_error_event(event)
                    if not item_id:
                        continue
                    pending = self._turns_by_item.pop(item_id, None)
                    if pending and not pending.future.done():
                        pending.future.set_exception(make_stt_exception(info))
                    continue

                # other events ignored
                continue

        except asyncio.CancelledError:
            pass
        except websockets.ConnectionClosed as exc:
            reason = redact_sensitive_text(getattr(exc, "reason", "") or "")
            logger.error(
                "Realtime WebSocket closed: code=%s reason=%s",
                getattr(exc, "code", None),
                reason,
            )
            self._fail_all_pending(
                RuntimeError(f"WebSocket closed: {getattr(exc, 'code', None)} {reason}")
            )

    async def _send(self, data: Dict[str, Any]) -> None:
        if self.ws is None:
            raise RuntimeError("WebSocket is not connected")
        async with self._send_lock:
            await self.ws.send(json.dumps(data))

    def _fail_all_pending(self, exc: Exception) -> None:
        for pending in list(self._pending_turns):
            if not pending.future.done():
                pending.future.set_exception(exc)
        self._pending_turns.clear()

        for pending in list(self._turns_by_item.values()):
            if not pending.future.done():
                pending.future.set_exception(exc)
        self._turns_by_item.clear()

    def _get_api_key(self) -> str:
        key = resolve_api_key(self.api_key_priority, service=self.api_key_service)
        if not key:
            raise PermanentSttError(
                SttErrorInfo(
                    classification=PERMANENT,
                    code="missing_api_key",
                    message=api_key_missing_message(self.api_key_service),
                )
            )
        return key
