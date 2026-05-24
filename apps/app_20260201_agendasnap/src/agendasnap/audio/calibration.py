"""Audio calibration utilities (noise floor -> VAD threshold)."""
from __future__ import annotations

from typing import Any, Dict, Iterable, Optional, Tuple

import numpy as np

from agendasnap.audio.resample import resample_pcm16


def resolve_calibration_config(audio_cfg: Dict[str, Any]) -> Dict[str, Any]:
    cal = audio_cfg.get("calibration")
    if not isinstance(cal, dict):
        return {"enable": False}

    return {
        "enable": bool(cal.get("enable", False)),
        "seconds": float(cal.get("seconds", 3.0)),
        "percentile": float(cal.get("percentile", 20.0)),
        "multiplier": float(cal.get("multiplier", 2.5)),
        "min_threshold_sys": cal.get("min_threshold_sys"),
        "min_threshold_mic": cal.get("min_threshold_mic"),
        "max_threshold_sys": cal.get("max_threshold_sys"),
        "max_threshold_mic": cal.get("max_threshold_mic"),
        "recalibration_interval_seconds": float(cal.get("recalibration_interval_seconds", 0.0) or 0.0),
        "recalibration_window_seconds": float(cal.get("recalibration_window_seconds", 0.0) or 0.0),
        "recalibration_min_samples": int(cal.get("recalibration_min_samples", 0) or 0),
        "recalibration_min_change_ratio": float(cal.get("recalibration_min_change_ratio", 0.0) or 0.0),
    }


def build_source_calibration(
    cal_cfg: Dict[str, Any],
    *,
    source: str,
    fallback_threshold: float,
) -> Dict[str, Any]:
    if not cal_cfg.get("enable", False):
        return {"enable": False}

    min_key = f"min_threshold_{source}"
    max_key = f"max_threshold_{source}"

    min_thr = cal_cfg.get(min_key)
    max_thr = cal_cfg.get(max_key)

    return {
        "enable": True,
        "seconds": float(cal_cfg.get("seconds", 3.0)),
        "percentile": float(cal_cfg.get("percentile", 20.0)),
        "multiplier": float(cal_cfg.get("multiplier", 2.5)),
        "min_threshold": float(min_thr) if min_thr is not None else float(fallback_threshold),
        "max_threshold": float(max_thr) if max_thr is not None else 0.0,
        "recalibration_interval_seconds": float(cal_cfg.get("recalibration_interval_seconds", 0.0) or 0.0),
        "recalibration_window_seconds": float(cal_cfg.get("recalibration_window_seconds", 0.0) or 0.0),
        "recalibration_min_samples": int(cal_cfg.get("recalibration_min_samples", 0) or 0),
        "recalibration_min_change_ratio": float(cal_cfg.get("recalibration_min_change_ratio", 0.0) or 0.0),
    }


def compute_threshold_from_rms(
    rms_values: Iterable[float],
    *,
    percentile: float,
    multiplier: float,
    min_threshold: float,
    max_threshold: float,
) -> Tuple[Optional[float], Optional[float]]:
    vals = [v for v in rms_values if v is not None]
    if not vals:
        return None, None

    noise_rms = float(np.percentile(np.array(vals, dtype=np.float32), percentile))
    threshold = noise_rms * float(multiplier)

    if min_threshold and threshold < min_threshold:
        threshold = min_threshold
    if max_threshold and threshold > max_threshold:
        threshold = max_threshold

    return float(threshold), float(noise_rms)


def estimate_threshold_from_frames(
    *,
    frames: Iterable[bytes],
    capture_rate: int,
    capture_channels: int,
    target_rate: int,
    calibration: Dict[str, Any],
    fallback_threshold: float,
    frame_ms: int = 30,
) -> Tuple[float, Optional[float]]:
    if not calibration.get("enable") or not frames:
        return float(fallback_threshold), None

    pcm = b"".join(frames)
    if not pcm:
        return float(fallback_threshold), None

    resampled, _frames_cnt, used_rate, _used_ch = resample_pcm16(
        pcm,
        src_rate=int(capture_rate),
        dst_rate=int(target_rate),
        src_channels=int(capture_channels),
        target_channels=1,
    )
    if not resampled:
        return float(fallback_threshold), None

    bytes_per_sample = 2
    total_samples = len(resampled) // bytes_per_sample
    seconds = float(calibration.get("seconds", 3.0))
    if seconds > 0 and used_rate > 0:
        max_samples = int(seconds * used_rate)
        total_samples = min(total_samples, max_samples)

    if total_samples <= 0:
        return float(fallback_threshold), None

    resampled = resampled[: total_samples * bytes_per_sample]
    samples = np.frombuffer(resampled, dtype=np.int16)

    frame_len = max(1, int(used_rate * frame_ms / 1000))
    rms_values = []
    for i in range(0, samples.size, frame_len):
        frame = samples[i : i + frame_len]
        if frame.size == 0:
            break
        rms = float(np.sqrt(np.mean(frame.astype(np.float32) ** 2)))
        rms_values.append(rms)

    threshold, noise_rms = compute_threshold_from_rms(
        rms_values,
        percentile=float(calibration.get("percentile", 20.0)),
        multiplier=float(calibration.get("multiplier", 2.5)),
        min_threshold=float(calibration.get("min_threshold", 0.0)),
        max_threshold=float(calibration.get("max_threshold", 0.0)),
    )

    if threshold is None:
        return float(fallback_threshold), noise_rms

    return float(threshold), noise_rms
