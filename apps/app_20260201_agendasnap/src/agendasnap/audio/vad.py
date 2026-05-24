"""Energy-based voice activity detection (VAD) utilities.

Design goals for this project:
- Simple, deterministic, dependency-light.
- Avoid tiny "turns" (e.g., 30ms) that cause excessive commits / errors / cost.
- Return merged speech *segments* rather than raw frames.

All inputs/outputs are PCM16 little-endian bytes.
"""
from __future__ import annotations

from typing import List, Tuple

import numpy as np


def energy_vad_segments(
    pcm: bytes,
    sample_rate: int,
    channels: int,
    *,
    frame_ms: int = 30,
    energy_threshold: float = 500.0,
    max_gap_ms: int = 120,
    min_segment_ms: int = 250,
) -> List[Tuple[float, float, bytes]]:
    """Return merged speech segments using a simple energy threshold.

    Parameters
    ----------
    pcm:
        Interleaved PCM16 bytes.
    sample_rate:
        Sample rate in Hz.
    channels:
        Number of channels in pcm.
    frame_ms:
        Analysis frame size in milliseconds.
    energy_threshold:
        RMS threshold to treat a frame as "speech".
    max_gap_ms:
        If silence lasts longer than this, close the current segment.
        Shorter silence gaps are bridged (segment merging).
    min_segment_ms:
        Discard segments shorter than this duration.

    Returns
    -------
    List of (start_sec, end_sec, segment_pcm_bytes).
    """
    if not pcm:
        return []

    if sample_rate <= 0:
        raise ValueError(f"sample_rate must be > 0 (got {sample_rate})")
    if channels <= 0:
        raise ValueError(f"channels must be > 0 (got {channels})")

    samples = np.frombuffer(pcm, dtype=np.int16)
    if samples.size == 0:
        return []

    # Convert to mono for energy calculation and output segments
    if channels > 1:
        n = (samples.size // channels) * channels
        if n == 0:
            return []
        mono = samples[:n].reshape(-1, channels).mean(axis=1).astype(np.int16)
    else:
        mono = samples

    frame_len = max(1, int(sample_rate * frame_ms / 1000))
    max_gap_frames = max(0, int(max_gap_ms / frame_ms))

    segments: List[Tuple[float, float, bytes]] = []
    in_seg = False
    seg_start = 0
    last_voice_end = 0
    gap = 0

    for i in range(0, mono.size, frame_len):
        frame = mono[i : i + frame_len]
        if frame.size == 0:
            break

        # RMS energy
        rms = float(np.sqrt(np.mean(frame.astype(np.float32) ** 2)))
        voiced = rms >= energy_threshold

        if voiced:
            if not in_seg:
                in_seg = True
                seg_start = i
            last_voice_end = i + frame.size
            gap = 0
        else:
            if in_seg:
                gap += 1
                if gap > max_gap_frames:
                    seg_end = last_voice_end
                    dur_ms = (seg_end - seg_start) * 1000.0 / sample_rate
                    if dur_ms >= min_segment_ms:
                        seg_pcm = mono[seg_start:seg_end].astype(np.int16).tobytes()
                        segments.append((seg_start / sample_rate, seg_end / sample_rate, seg_pcm))
                    in_seg = False
                    gap = 0

    if in_seg:
        seg_end = last_voice_end
        dur_ms = (seg_end - seg_start) * 1000.0 / sample_rate
        if dur_ms >= min_segment_ms:
            seg_pcm = mono[seg_start:seg_end].astype(np.int16).tobytes()
            segments.append((seg_start / sample_rate, seg_end / sample_rate, seg_pcm))

    return segments


def energy_vad_segments_hysteresis(
    pcm: bytes,
    sample_rate: int,
    channels: int,
    *,
    frame_ms: int = 30,
    start_threshold: float,
    stop_threshold: float,
    max_gap_ms: int = 120,
    min_segment_ms: int = 250,
) -> List[Tuple[float, float, bytes]]:
    """Return merged speech segments using hysteresis thresholds.

    - start_threshold: RMS level to start a segment.
    - stop_threshold: RMS level to keep a segment alive.
    """
    if not pcm:
        return []

    if sample_rate <= 0:
        raise ValueError(f"sample_rate must be > 0 (got {sample_rate})")
    if channels <= 0:
        raise ValueError(f"channels must be > 0 (got {channels})")

    samples = np.frombuffer(pcm, dtype=np.int16)
    if samples.size == 0:
        return []

    if channels > 1:
        n = (samples.size // channels) * channels
        if n == 0:
            return []
        mono = samples[:n].reshape(-1, channels).mean(axis=1).astype(np.int16)
    else:
        mono = samples

    frame_len = max(1, int(sample_rate * frame_ms / 1000))
    max_gap_frames = max(0, int(max_gap_ms / frame_ms))

    segments: List[Tuple[float, float, bytes]] = []
    in_seg = False
    seg_start = 0
    last_voice_end = 0
    gap = 0

    for i in range(0, mono.size, frame_len):
        frame = mono[i : i + frame_len]
        if frame.size == 0:
            break

        rms = float(np.sqrt(np.mean(frame.astype(np.float32) ** 2)))

        if not in_seg:
            if rms >= start_threshold:
                in_seg = True
                seg_start = i
                last_voice_end = i + frame.size
                gap = 0
            continue

        # in segment
        if rms >= stop_threshold:
            last_voice_end = i + frame.size
            gap = 0
        else:
            gap += 1
            if gap > max_gap_frames:
                seg_end = last_voice_end
                dur_ms = (seg_end - seg_start) * 1000.0 / sample_rate
                if dur_ms >= min_segment_ms:
                    seg_pcm = mono[seg_start:seg_end].astype(np.int16).tobytes()
                    segments.append((seg_start / sample_rate, seg_end / sample_rate, seg_pcm))
                in_seg = False
                gap = 0

    if in_seg:
        seg_end = last_voice_end
        dur_ms = (seg_end - seg_start) * 1000.0 / sample_rate
        if dur_ms >= min_segment_ms:
            seg_pcm = mono[seg_start:seg_end].astype(np.int16).tobytes()
            segments.append((seg_start / sample_rate, seg_end / sample_rate, seg_pcm))

    return segments
