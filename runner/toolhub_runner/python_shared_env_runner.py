from __future__ import annotations

import os
from pathlib import Path

from .base_runner import BaseRunner, RunnerResult, USER_FAILURE_MESSAGE
from .env_manager import build_app_env
from .event_protocol import RunnerEvent
from .log_manager import create_run_log_paths, now_iso, save_run_log


RUNTIME_FAILURE_MESSAGE = "アプリの実行環境が見つかりません。管理者に連絡してください。"


class PythonSharedEnvRunner(BaseRunner):
    def run(self) -> RunnerResult:
        entry = self.app_entry()
        if not entry.is_file():
            return self._failure(USER_FAILURE_MESSAGE, f"entry file not found: {entry}", [])

        python = self.shared_env_python()
        if not python.is_file():
            return self._failure(
                RUNTIME_FAILURE_MESSAGE,
                f"shared env python not found: env_id={self.manifest.run.env_id}, path={python}",
                [],
            )

        command = [str(python), str(entry)]
        env = build_app_env(self.project_root, self.manifest)
        self.apply_shared_env_path(env, python)
        cwd = entry.parent
        if self.manifest.run.mode == "gui":
            return self.start_detached(command, env, cwd=cwd)
        return self.run_blocking(command, env, cwd=cwd)

    def shared_env_python(self) -> Path:
        env_id = self.manifest.run.env_id
        if not env_id:
            return Path("__missing_env_id__")
        env_root = self.project_root / "runtime" / "envs" / env_id
        return env_root / ("Scripts/python.exe" if os.name == "nt" else "bin/python")

    def apply_shared_env_path(self, env: dict[str, str], python: Path) -> None:
        scripts = python.parent
        env_root = scripts.parent
        env["VIRTUAL_ENV"] = str(env_root)
        env["PATH"] = str(scripts) + os.pathsep + env.get("PATH", "")
        env["PYTHONNOUSERSITE"] = "1"
        env["TOOLHUB_SHARED_ENV_ID"] = self.manifest.run.env_id

    def _failure(self, user_message: str, admin_error: str, command: list[str]) -> RunnerResult:
        paths = create_run_log_paths(self.project_root, self.manifest.id)
        events = [RunnerEvent(type="error", message=user_message)]
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
            user_message=user_message,
            admin_error=admin_error,
            command=command,
        )
        return RunnerResult(
            ok=False,
            app_id=self.manifest.id,
            user_message=user_message,
            log_path=str(paths.json_log),
            events=events,
        )
