"""PCM16 resampling utilities (down to STT target format) without scipy dependency."""
from __future__ import annotations

from typing import Tuple

import numpy as np


def _linear_resample(audio: np.ndarray, src_rate: int, dst_rate: int) -> np.ndarray:
    """
    Simple linear resampler (per channel) to avoid scipy dependency.
    Good enough for speech (48k -> 24k/16k).
    """
    if src_rate == dst_rate or audio.size == 0:
        return audio
    ratio = dst_rate / src_rate
    src_len = audio.shape[0]
    dst_len = int(src_len * ratio)
    # time positions
    src_positions = np.arange(src_len)
    dst_positions = np.arange(dst_len) / ratio
    # interpolate per channel
    return np.stack(
        [
            np.interp(dst_positions, src_positions, audio[:, ch])
            for ch in range(audio.shape[1])
        ],
        axis=1,
    )


def resample_pcm16(
    data: bytes,
    src_rate: int,
    dst_rate: int,
    src_channels: int,
    target_channels: int = 1,
) -> Tuple[bytes, int, int, int]:
    """
    Resample interleaved PCM16 bytes to the desired rate/channels.

    Returns (resampled_bytes, frames, used_rate, used_channels).
    """
    if not data:
        return b"", 0, dst_rate, target_channels

    audio = np.frombuffer(data, dtype=np.int16).reshape(-1, src_channels).astype(np.float64)

    # Channel conversion
    if target_channels == 1 and src_channels > 1:
        audio = audio.mean(axis=1, keepdims=True)
    elif target_channels > 1 and src_channels == 1:
        audio = np.repeat(audio, target_channels, axis=1)
    else:
        target_channels = src_channels

    # Resample
    audio = _linear_resample(audio, src_rate, dst_rate)

    audio = np.clip(audio, -32768, 32767).astype(np.int16)
    frames = audio.shape[0]
    return audio.tobytes(), frames, dst_rate, target_channels
