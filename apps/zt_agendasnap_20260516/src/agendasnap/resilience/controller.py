"""Resilience controller for delay mode and status reporting."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass
class DelayModeThresholds:
    queue_ratio: float = 0.7
    delay_seconds: float = 10.0
    drop_rate: float = 0.5
    recover_queue_ratio: float = 0.4
    recover_delay_seconds: float = 5.0
    recover_drop_rate: float = 0.2


@dataclass
class DelayModeActions:
    segment_max_seconds_boost: float = 20.0
    minutes_interval_boost: float = 180.0


@dataclass
class ResilienceConfig:
    enable: bool = True
    thresholds: DelayModeThresholds = field(default_factory=DelayModeThresholds)
    actions: DelayModeActions = field(default_factory=DelayModeActions)


class ResilienceController:
    def __init__(
        self,
        *,
        cfg: dict,
        base_segment_max_seconds: float,
        base_minutes_interval: float,
        queue_max: int,
    ) -> None:
        self.cfg = ResilienceConfig(
            enable=bool(cfg.get("enable", True)),
            thresholds=DelayModeThresholds(
                queue_ratio=float(cfg.get("delay_mode", {}).get("queue_ratio", 0.7)),
                delay_seconds=float(cfg.get("delay_mode", {}).get("delay_seconds", 10.0)),
                drop_rate=float(cfg.get("delay_mode", {}).get("drop_rate", 0.5)),
                recover_queue_ratio=float(cfg.get("delay_mode", {}).get("recover_queue_ratio", 0.4)),
                recover_delay_seconds=float(cfg.get("delay_mode", {}).get("recover_delay_seconds", 5.0)),
                recover_drop_rate=float(cfg.get("delay_mode", {}).get("recover_drop_rate", 0.2)),
            ),
            actions=DelayModeActions(
                segment_max_seconds_boost=float(cfg.get("actions", {}).get("segment_max_seconds_boost", 20.0)),
                minutes_interval_boost=float(cfg.get("actions", {}).get("minutes_interval_boost", 180.0)),
            ),
        )
        self.base_segment_max_seconds = float(base_segment_max_seconds)
        self.base_minutes_interval = float(base_minutes_interval)
        self.queue_max = int(queue_max) if queue_max > 0 else 1

        self.mode = "normal"  # normal | delay
        self.delay_mode_triggered = False
        self.metrics: Dict[str, dict] = {"sys": {}, "mic": {}}
        self.last_errors: Dict[str, Optional[str]] = {"sys": None, "mic": None}
        self.reconnect_counts: Dict[str, int] = {"sys": 0, "mic": 0}
        self.stt_state: Dict[str, str] = {"sys": "healthy", "mic": "healthy"}

    def update_metrics(self, source: str, *, queue_size: int, delay_seconds: Optional[float], drop_rate: float) -> None:
        if source not in self.metrics:
            self.metrics[source] = {}
        self.metrics[source].update(
            {
                "queue_size": int(queue_size),
                "queue_ratio": float(queue_size) / float(self.queue_max),
                "delay_seconds": delay_seconds,
                "drop_rate": float(drop_rate),
            }
        )

    def record_stt_error(self, source: str, message: str) -> None:
        self.last_errors[source] = message
        self.stt_state[source] = "reconnecting"

    def record_stt_permanent_error(self, source: str, message: str) -> None:
        self.last_errors[source] = message
        self.stt_state[source] = "permanent_error"

    def record_stt_reconnect(self, source: str) -> None:
        self.reconnect_counts[source] = int(self.reconnect_counts.get(source, 0)) + 1
        self.stt_state[source] = "healthy"

    def evaluate_mode(self) -> bool:
        """Return True if mode changed."""
        if not self.cfg.enable:
            return False
        thresholds = self.cfg.thresholds

        def _overloaded(source: str) -> bool:
            m = self.metrics.get(source, {})
            queue_ratio = float(m.get("queue_ratio", 0.0))
            delay_seconds = m.get("delay_seconds")
            drop_rate = float(m.get("drop_rate", 0.0))

            if queue_ratio >= thresholds.queue_ratio:
                return True
            if queue_ratio > 0 and delay_seconds is not None and delay_seconds >= thresholds.delay_seconds:
                return True
            if queue_ratio > 0 and drop_rate >= thresholds.drop_rate:
                return True
            return False

        def _recovered(source: str) -> bool:
            m = self.metrics.get(source, {})
            queue_ratio = float(m.get("queue_ratio", 0.0))
            delay_seconds = m.get("delay_seconds")
            drop_rate = float(m.get("drop_rate", 0.0))

            if queue_ratio > thresholds.recover_queue_ratio:
                return False
            if queue_ratio > 0 and delay_seconds is not None and delay_seconds > thresholds.recover_delay_seconds:
                return False
            if queue_ratio > 0 and drop_rate > thresholds.recover_drop_rate:
                return False
            return True

        if self.mode == "normal":
            if _overloaded("sys") or _overloaded("mic"):
                self.mode = "delay"
                self.delay_mode_triggered = True
                return True
        else:
            if _recovered("sys") and _recovered("mic"):
                self.mode = "normal"
                return True
        return False

    def current_segment_max_seconds(self) -> float:
        if self.mode != "delay":
            return self.base_segment_max_seconds
        return max(self.base_segment_max_seconds, float(self.cfg.actions.segment_max_seconds_boost))

    def current_minutes_interval(self) -> float:
        if self.mode != "delay":
            return self.base_minutes_interval
        return max(self.base_minutes_interval, float(self.cfg.actions.minutes_interval_boost))

    def status_payload(self) -> dict:
        return {
            "mode": self.mode,
            "metrics": self.metrics,
            "stt": {
                "reconnect_counts": self.reconnect_counts,
                "last_errors": self.last_errors,
                "state": self.stt_state,
            },
            "actions": {
                "segment_max_seconds": self.current_segment_max_seconds(),
                "minutes_interval_seconds": self.current_minutes_interval(),
            },
            "flags": {
                "delay_mode_triggered": self.delay_mode_triggered,
            },
        }
