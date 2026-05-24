"""Abstract interface for STT engines."""
from abc import ABC, abstractmethod
from typing import Iterable

from agendasnap.bus.events import AudioChunk, TranscriptSegment


class ISttEngine(ABC):
    @abstractmethod
    async def start(self) -> None:
        """Prepare connections/resources."""

    @abstractmethod
    async def stop(self) -> None:
        """Tear down resources."""

    @abstractmethod
    async def push_audio(self, chunks: Iterable[AudioChunk]) -> Iterable[TranscriptSegment]:
        """Send audio and yield transcript segments."""
