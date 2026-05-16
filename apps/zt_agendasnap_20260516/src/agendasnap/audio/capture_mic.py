"""Microphone capture (default input)."""
from __future__ import annotations

import logging
from typing import Tuple

import pyaudiowpatch as pyaudio

from agendasnap.audio.devices import get_default_input_device_index

logger = logging.getLogger(__name__)

FORMAT = pyaudio.paInt16


def open_mic_stream(
    pa: pyaudio.PyAudio,
    requested_rate: int,
    requested_channels: int,
    frames_per_buffer: int,
    device_index: int | None = None,
) -> Tuple[pyaudio.Stream, int, int, int]:
    """Open a microphone input stream.

    Strict behavior:
    - No channel fallback.
    - No silent rate changes.
    - If config is incompatible with the device, raise with actionable details.

    Returns (stream, device_index, rate_used, channels_used).
    """
    if device_index is None:
        device_index = get_default_input_device_index(pa)
    if device_index is None:
        raise RuntimeError("Input (microphone) device not found.")

    info = pa.get_device_info_by_index(device_index)
    name = info.get("name")
    max_in = int(info.get("maxInputChannels", 0) or 0)
    default_rate = int(info.get("defaultSampleRate", 0) or 0)

    if requested_channels <= 0:
        raise ValueError(f"channels_mic must be > 0 (got {requested_channels})")
    if max_in and requested_channels > max_in:
        raise RuntimeError(
            "Microphone channel configuration is not supported: "
            f"requested_channels={requested_channels} > device_max_input_channels={max_in}. "
            f"device={device_index} name={name!r}"
        )

    try:
        stream = pa.open(
            format=FORMAT,
            channels=int(requested_channels),
            rate=int(requested_rate),
            frames_per_buffer=int(frames_per_buffer),
            input=True,
            input_device_index=device_index,
        )
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            "Failed to open microphone stream with requested config: "
            f"device={device_index} name={name!r} "
            f"requested_rate={requested_rate}Hz requested_channels={requested_channels} "
            f"(device_default_rate={default_rate}Hz device_max_input_channels={max_in}). "
            f"Error: {exc}"
        ) from exc

    logger.info("Opened microphone: device=%s rate=%s ch=%s name=%s", device_index, requested_rate, requested_channels, name)
    return stream, device_index, int(requested_rate), int(requested_channels)
