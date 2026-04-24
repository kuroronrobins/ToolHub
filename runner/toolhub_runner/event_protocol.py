from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, Optional


VALID_EVENT_TYPES = {"status", "progress", "success", "warning", "error", "output"}


@dataclass
class RunnerEvent:
    type: str
    message: str
    progress: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {"type": self.type, "message": self.message}
        if self.progress is not None:
            data["progress"] = max(0, min(100, int(self.progress)))
        return data


def parse_event_line(line: str) -> RunnerEvent:
    text = line.rstrip("\r\n")
    if not text.strip():
        return RunnerEvent(type="output", message="")

    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return RunnerEvent(type="output", message=text)

    if not isinstance(payload, dict):
        return RunnerEvent(type="output", message=text)

    event_type = str(payload.get("type", "output"))
    if event_type not in VALID_EVENT_TYPES:
        event_type = "output"

    message = payload.get("message")
    if message is None:
        message = text if event_type == "output" else ""

    progress = payload.get("progress")
    parsed_progress: Optional[int]
    try:
        parsed_progress = int(progress) if progress is not None else None
    except (TypeError, ValueError):
        parsed_progress = None

    return RunnerEvent(type=event_type, message=str(message), progress=parsed_progress)


def parse_stdout(stdout: str) -> list[RunnerEvent]:
    return [parse_event_line(line) for line in stdout.splitlines()]

