"""Adaptive VAD threshold controller (stable, bounded, slow-changing)."""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass
class AdaptiveVadConfig:
    enable: bool = False
    update_interval_seconds: float = 30.0
    target_drop_rate: float = 0.4
    deadband: float = 0.1
    max_step_ratio: float = 0.15
    smoothing: float = 0.7
    min_samples: int = 40
    min_change_ratio: float = 0.03
    min_threshold: Optional[float] = None
    max_threshold: Optional[float] = None


class AdaptiveVadController:
    """Thread-safe adaptive VAD controller.

    The controller adjusts threshold slowly based on recent drop rate,
    with deadband, step limits, and clamps to avoid instability.
    """

    def __init__(
        self,
        *,
        base_threshold: float,
        start_threshold: Optional[float],
        stop_threshold: Optional[float],
        cfg: AdaptiveVadConfig,
    ) -> None:
        self.cfg = cfg
        self._lock = threading.Lock()
        self._threshold = float(max(0.0, base_threshold))
        self._last_update = time.monotonic()

        self._start_ratio: Optional[float] = None
        self._stop_ratio: Optional[float] = None
        if start_threshold is not None and self._threshold > 0:
            self._start_ratio = float(start_threshold) / self._threshold
        if stop_threshold is not None and self._threshold > 0:
            self._stop_ratio = float(stop_threshold) / self._threshold

        self._clamp_threshold()

    def _clamp_threshold(self) -> None:
        if self.cfg.min_threshold is not None:
            self._threshold = max(self._threshold, float(self.cfg.min_threshold))
        if self.cfg.max_threshold is not None:
            self._threshold = min(self._threshold, float(self.cfg.max_threshold))

    def set_threshold(
        self,
        *,
        threshold: float,
        start_threshold: Optional[float] = None,
        stop_threshold: Optional[float] = None,
        reset_timer: bool = True,
    ) -> None:
        with self._lock:
            self._threshold = float(max(0.0, threshold))
            if start_threshold is not None and self._threshold > 0:
                self._start_ratio = float(start_threshold) / self._threshold
            if stop_threshold is not None and self._threshold > 0:
                self._stop_ratio = float(stop_threshold) / self._threshold
            self._clamp_threshold()
            if reset_timer:
                self._last_update = time.monotonic()

    def current_thresholds(self) -> Tuple[float, Optional[float], Optional[float]]:
        with self._lock:
            thr = float(self._threshold)
            start = float(self._start_ratio * thr) if self._start_ratio is not None else None
            stop = float(self._stop_ratio * thr) if self._stop_ratio is not None else None
            return thr, start, stop

    def maybe_update(
        self,
        *,
        drop_rate: float,
        sample_count: int,
        now: Optional[float] = None,
    ) -> Optional[Tuple[float, float]]:
        if not self.cfg.enable:
            return None

        if sample_count < int(self.cfg.min_samples):
            return None

        now = now or time.monotonic()

        with self._lock:
            if (now - self._last_update) < float(self.cfg.update_interval_seconds):
                return None

            dr = float(drop_rate)
            if dr < 0.0 or dr > 1.0:
                return None

            error = dr - float(self.cfg.target_drop_rate)
            if abs(error) <= float(self.cfg.deadband):
                return None

            # Step size scales with error but is capped.
            step = max(0.0, abs(error) - float(self.cfg.deadband)) * 0.5
            step = min(step, float(self.cfg.max_step_ratio))

            old = float(self._threshold)
            if error > 0:
                # Drop too high -> lower threshold.
                new = old * (1.0 - step)
            else:
                # Drop too low -> raise threshold.
                new = old * (1.0 + step)

            # Exponential smoothing for stability.
            smooth = float(self.cfg.smoothing)
            smooth = min(max(smooth, 0.0), 0.95)
            new = (old * smooth) + (new * (1.0 - smooth))

            self._threshold = max(0.0, float(new))
            self._clamp_threshold()
            self._last_update = now

            if old <= 0:
                return None

            change_ratio = abs(self._threshold - old) / old
            if change_ratio < float(self.cfg.min_change_ratio):
                return None

            return old, float(self._threshold)
