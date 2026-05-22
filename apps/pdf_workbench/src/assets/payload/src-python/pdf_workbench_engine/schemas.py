from __future__ import annotations

from pathlib import Path
from typing import Any


JsonDict = dict[str, Any]


def as_path(value: Any, field: str) -> Path:
    if not isinstance(value, str) or not value:
        from .errors import user_error

        raise user_error(f"{field} を指定してください。", target=field)
    return Path(value)


def result(job_id: str | None, data: JsonDict | None = None, logs: list[JsonDict] | None = None) -> JsonDict:
    payload: JsonDict = {
        "type": "result",
        "data": data or {},
    }
    if job_id:
        payload["jobId"] = job_id
    if logs:
        payload["logs"] = logs
    return payload


def error(job_id: str | None, payload: JsonDict) -> JsonDict:
    event: JsonDict = {
        "type": "error",
        **payload,
    }
    if job_id:
        event["jobId"] = job_id
    return event


def log(level: str, message: str, step: str | None = None, target: str | None = None) -> JsonDict:
    payload: JsonDict = {
        "type": "log",
        "level": level,
        "message": message,
    }
    if step:
        payload["step"] = step
    if target:
        payload["target"] = target
    return payload
