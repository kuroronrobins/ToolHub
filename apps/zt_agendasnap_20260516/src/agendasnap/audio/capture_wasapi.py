"""WASAPI loopback capture (system output)."""
from __future__ import annotations

import logging
from typing import Iterable, Tuple

import pyaudiowpatch as pyaudio

logger = logging.getLogger(__name__)

FORMAT = pyaudio.paInt16


def open_loopback_stream(
    pa: pyaudio.PyAudio,
    requested_rate: int,
    requested_channels: int,
    frames_per_buffer: int,
    *,
    follow_default: bool = True,
    select_each_time: bool = False,
    device_index: int | None = None,
) -> Tuple[pyaudio.Stream, int, int, int]:
    """Open a WASAPI loopback input stream.

    Strict behavior:
    - Use requested_rate / requested_channels as-is (no silent fallback).
    - If config is incompatible with the default loopback device, raise clearly.

    Returns (stream, loopback_device_index, rate_used, channels_used).
    """
    loopback_devices = list(_iter_loopback_devices(pa))
    if not loopback_devices:
        raise RuntimeError("WASAPI loopback device not found. (Windows/WASAPI required)")

    loopback_info = _select_loopback_device(
        pa,
        loopback_devices,
        follow_default=follow_default,
        select_each_time=select_each_time,
        device_index=device_index,
    )

    loopback_index = int(loopback_info["index"])
    name = loopback_info.get("name")
    max_in = int(loopback_info.get("maxInputChannels", 0) or 0)
    default_rate = int(loopback_info.get("defaultSampleRate", 0) or 0)

    if requested_channels <= 0:
        raise ValueError(f"channels_system must be > 0 (got {requested_channels})")
    if max_in and requested_channels > max_in:
        raise RuntimeError(
            "System(loopback) channel configuration is not supported: "
            f"requested_channels={requested_channels} > device_max_input_channels={max_in}. "
            f"device={loopback_index} name={name!r}"
        )

    if default_rate and int(requested_rate) != default_rate:
        logger.info(
            "Loopback device default sample rate differs from requested: requested=%sHz default=%sHz (will try requested)",
            requested_rate,
            default_rate,
        )

    try:
        stream_info = pyaudio.WasapiLoopbackInfo()
    except Exception:
        stream_info = None

    try:
        stream = pa.open(
            format=FORMAT,
            channels=int(requested_channels),
            rate=int(requested_rate),
            frames_per_buffer=int(frames_per_buffer),
            input=True,
            input_device_index=loopback_index,
            input_host_api_specific_stream_info=stream_info,
        )
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            "Failed to open WASAPI loopback stream with requested config: "
            f"device={loopback_index} name={name!r} "
            f"requested_rate={requested_rate}Hz requested_channels={requested_channels} "
            f"(device_default_rate={default_rate}Hz device_max_input_channels={max_in}). "
            f"Error: {exc}"
        ) from exc

    logger.info("Opened WASAPI loopback: device=%s rate=%s ch=%s name=%s", loopback_index, requested_rate, requested_channels, name)
    return stream, loopback_index, int(requested_rate), int(requested_channels)


def _iter_loopback_devices(pa: pyaudio.PyAudio) -> Iterable[dict]:
    try:
        return list(pa.get_loopback_device_info_generator())
    except Exception:
        return []


def _normalize_device_name(name: str | None) -> str:
    if not name:
        return ""
    normalized = name.replace("[Loopback]", "").strip().lower()
    return normalized


def _resolve_default_output_name(pa: pyaudio.PyAudio) -> str | None:
    try:
        info = pa.get_default_output_device_info()
        return info.get("name")
    except Exception:
        return None


def _select_loopback_device(
    pa: pyaudio.PyAudio,
    loopback_devices: list[dict],
    *,
    follow_default: bool,
    select_each_time: bool,
    device_index: int | None,
) -> dict:
    if device_index is not None:
        for dev in loopback_devices:
            if int(dev.get("index", -1)) == int(device_index):
                logger.info("Using specified loopback device index: %s", dev.get("name"))
                return dev
        raise RuntimeError(f"Specified loopback device index not found: {device_index}")
    if select_each_time:
        _print_loopback_devices(loopback_devices)
        default_name = _resolve_default_output_name(pa) if follow_default else None
        selected = _prompt_loopback_device(loopback_devices, default_name)
        if selected is not None:
            return selected

    if follow_default:
        default_name = _resolve_default_output_name(pa)
        if default_name:
            match = _match_loopback_by_name(loopback_devices, default_name)
            if match is not None:
                logger.info("Using default output loopback: %s", match.get("name"))
                return match
            logger.warning(
                "Default output loopback not found for %r. Falling back to first loopback device.",
                default_name,
            )

    return loopback_devices[0]


def _print_loopback_devices(loopbacks: list[dict]) -> None:
    logger.info("Available loopback devices:")
    for dev in loopbacks:
        logger.info("  index=%s name=%s", dev.get("index"), dev.get("name"))


def _prompt_loopback_device(loopbacks: list[dict], default_name: str | None) -> dict | None:
    default_label = f" (default: {default_name})" if default_name else ""
    try:
        choice = input(f"Select loopback device index{default_label} (blank=default): ").strip()
    except Exception:
        return None

    if not choice:
        if default_name:
            return _match_loopback_by_name(loopbacks, default_name)
        return None

    try:
        idx = int(choice)
    except ValueError:
        logger.warning("Invalid device index input: %r", choice)
        return None

    for dev in loopbacks:
        if int(dev.get("index", -1)) == idx:
            logger.info("Selected loopback device: %s", dev.get("name"))
            return dev

    logger.warning("Loopback device index not found: %s", idx)
    return None


def _match_loopback_by_name(loopbacks: list[dict], default_name: str) -> dict | None:
    norm_default = _normalize_device_name(default_name)
    if not norm_default:
        return None
    # First try exact normalized match.
    for dev in loopbacks:
        if _normalize_device_name(dev.get("name")) == norm_default:
            return dev
    # Then try substring match (e.g., extra suffix/prefix).
    for dev in loopbacks:
        if norm_default and norm_default in _normalize_device_name(dev.get("name")):
            return dev
    return None
