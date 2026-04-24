from __future__ import annotations

import shutil
import sys

from .base_runner import BaseRunner, RunnerResult, USER_FAILURE_MESSAGE
from .env_manager import build_app_env
from .event_protocol import RunnerEvent
from .log_manager import create_run_log_paths, now_iso, save_run_log


class PythonRunner(BaseRunner):
    def run(self) -> RunnerResult:
        entry = self.app_entry()
        if not entry.is_file():
            return self._missing_entry_result(str(entry))

        command = [sys.executable, str(entry)]
        env = build_app_env(self.project_root, self.manifest)
        if self.manifest.run.mode == "gui":
            return self.start_detached(command, env)
        return self.run_blocking(command, env)

    def _missing_entry_result(self, entry: str) -> RunnerResult:
        paths = create_run_log_paths(self.project_root, self.manifest.id)
        events = [RunnerEvent(type="error", message=USER_FAILURE_MESSAGE)]
        save_run_log(
            paths,
            app_id=self.manifest.id,
            app_name=self.manifest.name,
            start_time=now_iso(),
            end_time=now_iso(),
            exit_code=None,
            stdout="",
            stderr="",
            events=events,
            user_message=USER_FAILURE_MESSAGE,
            admin_error=f"entry file not found: {entry}",
            command=[shutil.which("python") or sys.executable, entry],
        )
        return self.failure_result(events, paths.json_log)

