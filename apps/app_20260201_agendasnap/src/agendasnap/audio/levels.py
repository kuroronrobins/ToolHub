"""Live audio level telemetry helpers."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import math
import time
from typing import Any

import numpy as np


PCM16_FULL_SCALE = 32768.0
PCM16_CLIP_LEVEL = 32700


@dataclass(frozen=True)
class LiveAudioLevel:
    source: str
    enabled: bool
    timestamp: float
    rms: float
    peak: float
    dbfs: float
    threshold: float
    vad_active: bool
    clipped: bool
    error: str | None = None
    device_index: int | None = None
    device_name: str | None = None
    noise_rms: float | None = None
    energy_threshold: float | None = None
    produced: int | None = None
    dropped_energy: int | None = None
    dropped_full: int | None = None
    queue_size: int | None = None
    queue_max: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def compute_pcm16_level(
    pcm: bytes,
    *,
    source: str,
    threshold: float = 0.0,
    enabled: bool = True,
    timestamp: float | None = None,
    error: str | None = None,
    device_index: int | None = None,
    device_name: str | None = None,
) -> LiveAudioLevel:
    """Compute lightweight level telemetry from PCM16 bytes."""
    ts = time.time() if timestamp is None else float(timestamp)
    if not enabled or not pcm:
        return LiveAudioLevel(
            source=source,
            enabled=bool(enabled),
            timestamp=ts,
            rms=0.0,
            peak=0.0,
            dbfs=-120.0,
            threshold=float(threshold or 0.0),
            vad_active=False,
            clipped=False,
            error=error,
            device_index=device_index,
            device_name=device_name,
        )

    arr = np.frombuffer(pcm, dtype=np.int16)
    if arr.size == 0:
        rms = 0.0
        peak = 0.0
    else:
        abs_arr = np.abs(arr.astype(np.int32))
        peak = float(abs_arr.max(initial=0))
        rms = float(np.sqrt(np.mean(arr.astype(np.float64) ** 2)))

    dbfs = 20.0 * math.log10(max(rms, 1.0) / PCM16_FULL_SCALE)
    threshold_f = float(threshold or 0.0)
    vad_active = bool(enabled and rms >= threshold_f) if threshold_f > 0 else bool(enabled and rms > 0)
    clipped = bool(peak >= PCM16_CLIP_LEVEL)
    return LiveAudioLevel(
        source=source,
        enabled=bool(enabled),
        timestamp=ts,
        rms=rms,
        peak=peak,
        dbfs=max(-120.0, dbfs),
        threshold=threshold_f,
        vad_active=vad_active,
        clipped=clipped,
        error=error,
        device_index=device_index,
        device_name=device_name,
    )


def inactive_level(
    *,
    source: str,
    threshold: float = 0.0,
    error: str | None = None,
    device_index: int | None = None,
    device_name: str | None = None,
) -> LiveAudioLevel:
    return compute_pcm16_level(
        b"",
        source=source,
        threshold=threshold,
        enabled=False,
        error=error,
        device_index=device_index,
        device_name=device_name,
    )


def level_state_label(level: LiveAudioLevel | dict[str, Any]) -> str:
    data = level.to_dict() if isinstance(level, LiveAudioLevel) else level
    if data.get("error"):
        return "デバイスエラー"
    if not bool(data.get("enabled", False)):
        return "OFF"
    if bool(data.get("clipped", False)):
        return "クリップ"
    if bool(data.get("vad_active", False)):
        return "音声検出中"
    rms = float(data.get("rms", 0.0) or 0.0)
    threshold = float(data.get("threshold", 0.0) or 0.0)
    if rms <= 0:
        return "無音"
    if threshold > 0 and rms < threshold * 0.6:
        return "小さすぎる"
    return "無音"
