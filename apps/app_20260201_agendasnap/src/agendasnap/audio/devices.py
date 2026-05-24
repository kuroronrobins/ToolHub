"""Device helpers for PyAudioWPatch (Windows/WASAPI).

Keep this module minimal and *strict*:
- Do not guess or fall back silently. If a required device is missing, raise clearly.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import pyaudiowpatch as pyaudio

logger = logging.getLogger(__name__)


def get_default_input_device_index(pa: pyaudio.PyAudio) -> Optional[int]:
    """Return the default input (microphone) device index, or None if unavailable."""
    try:
        dev = pa.get_default_input_device_info()
        return int(dev.get("index"))
    except OSError:
        logger.error("No default input (microphone) device available.")
        return None


def describe_device(pa: pyaudio.PyAudio, device_index: int) -> Dict[str, Any]:
    """Return a structured device description for session logging."""
    info = pa.get_device_info_by_index(int(device_index))
    host_api_name = None
    host_api_index = info.get("hostApi")
    if host_api_index is not None:
        try:
            host_api_name = pa.get_host_api_info_by_index(int(host_api_index)).get("name")
        except Exception:
            host_api_name = None

    return {
        "index": int(info.get("index", device_index)),
        "name": info.get("name"),
        "host_api": host_api_name,
        "max_input_channels": int(info.get("maxInputChannels", 0) or 0),
        "max_output_channels": int(info.get("maxOutputChannels", 0) or 0),
        "default_sample_rate": int(info.get("defaultSampleRate", 0) or 0),
    }


def build_capture_device_info(
    pa: pyaudio.PyAudio,
    device_index: int,
    *,
    capture_rate: int,
    channels: int,
    frames_per_buffer: int,
) -> Dict[str, Any]:
    """Augment device description with capture settings."""
    info = describe_device(pa, device_index)
    info.update(
        {
            "capture_rate": int(capture_rate),
            "channels": int(channels),
            "frames_per_buffer": int(frames_per_buffer),
            "format": "int16",
        }
    )
    return info
