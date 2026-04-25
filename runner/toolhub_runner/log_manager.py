from __future__ import annotations

import datetime as dt
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from .event_protocol import RunnerEvent


@dataclass
class RunLogPaths:
    log_dir: Path
    json_log: Path
    text_log: Path
    latest_log: Path


def create_run_log_paths(project_root: Path, app_id: str) -> RunLogPaths:
    log_dir = user_data_root(project_root) / "data" / "logs" / app_id
    log_dir.mkdir(parents=True, exist_ok=True)
    timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    return RunLogPaths(
        log_dir=log_dir,
        json_log=log_dir / f"run_{timestamp}.json",
        text_log=log_dir / f"run_{timestamp}.log",
        latest_log=log_dir / "latest.log",
    )


def user_data_root(project_root: Path) -> Path:
    configured = os.environ.get("TOOLHUB_USER_DATA_ROOT")
    if configured:
        return Path(configured)
    return project_root


def save_run_log(
    paths: RunLogPaths,
    *,
    app_id: str,
    app_name: str,
    start_time: str,
    end_time: str,
    exit_code: Optional[int],
    stdout: str,
    stderr: str,
    events: list[RunnerEvent],
    user_message: str,
    admin_error: str = "",
    command: list[str] | None = None,
    pid: int | None = None,
) -> None:
    payload: dict[str, Any] = {
        "app_id": app_id,
        "app_name": app_name,
        "start_time": start_time,
        "end_time": end_time,
        "exit_code": exit_code,
        "pid": pid,
        "command": command or [],
        "stdout": stdout,
        "stderr": stderr,
        "events": [event.to_dict() for event in events],
        "user_message": user_message,
        "admin_error": admin_error,
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    paths.json_log.write_text(text, encoding="utf-8")

    log_text = "\n".join(
        [
            f"app_id: {app_id}",
            f"app_name: {app_name}",
            f"start_time: {start_time}",
            f"end_time: {end_time}",
            f"exit_code: {exit_code}",
            f"pid: {pid}",
            f"user_message: {user_message}",
            f"admin_error: {admin_error}",
            "",
            "[stdout]",
            stdout,
            "",
            "[stderr]",
            stderr,
            "",
            "[events]",
            json.dumps([event.to_dict() for event in events], ensure_ascii=False, indent=2),
        ]
    )
    paths.text_log.write_text(log_text, encoding="utf-8")
    paths.latest_log.write_text(log_text, encoding="utf-8")


def now_iso() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")

