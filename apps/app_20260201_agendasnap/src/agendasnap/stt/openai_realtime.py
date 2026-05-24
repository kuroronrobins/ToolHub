"""OpenAI Realtime STT engine (transcription session)."""
from __future__ import annotations

from typing import Any, Iterable, List, Mapping, Optional

from agendasnap.bus.events import AudioChunk, TranscriptSegment
from agendasnap.stt.base import ISttEngine
from agendasnap.stt.realtime_client import RealtimeSttClient


class OpenAIRealtime(ISttEngine):
    def __init__(
        self,
        *,
        url: str,
        api_key_priority,
        api_key_service: str = "openai",
        language: Optional[str] = None,
        transcription_model: str = "gpt-4o-transcribe",
        source: str = "sys",
        noise_reduction: Optional[str] = None,
        transcription_prompt: Optional[str] = None,
        prompt_metadata: Optional[Mapping[str, Any]] = None,
        request_timeout_seconds: float = 30.0,
    ):
        self.client = RealtimeSttClient(
            url=url,
            api_key_priority=api_key_priority,
            api_key_service=api_key_service,
            language=language,
            transcription_model=transcription_model,
            source=source,
            noise_reduction=noise_reduction,
            transcription_prompt=transcription_prompt,
            prompt_metadata=prompt_metadata,
            request_timeout_seconds=request_timeout_seconds,
        )

    async def start(self) -> None:
        await self.client.start()

    async def stop(self) -> None:
        await self.client.stop()

    def set_transcription_prompt(self, prompt: Optional[str]) -> None:
        self.client.set_transcription_prompt(prompt)

    def set_transcription_prompt_metadata(self, metadata: Optional[Mapping[str, Any]]) -> None:
        self.client.set_transcription_prompt_metadata(metadata)

    async def push_audio(self, chunks: Iterable[AudioChunk]) -> List[TranscriptSegment]:
        return await self.client.push_audio(chunks)
