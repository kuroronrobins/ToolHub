"""
Event definitions used across the pipeline.

Only minimal placeholders are provided for the audio capture MVP.
"""
from dataclasses import dataclass
from typing import Optional


@dataclass
class AudioChunk:
    """PCM audio chunk with timing metadata."""

    pcm: bytes
    sample_rate: int
    channels: int
    source: str  # "sys" or "mic"
    t0: Optional[float] = None
    t1: Optional[float] = None


@dataclass
class TranscriptSegment:
    """Transcribed text segment (hypothesis/final)."""

    text: str
    start: float
    end: float
    source: str
    state: str  # "hyp" or "final"
    confidence: Optional[float] = None
