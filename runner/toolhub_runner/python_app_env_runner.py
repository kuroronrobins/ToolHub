from __future__ import annotations

import os
from pathlib import Path

from .base_runner import BaseRunner, RunnerResult, USER_FAILURE_MESSAGE
from .env_manager import build_app_env
from .event_protocol import RunnerEvent
from .log_manager import create_run_log_paths, now_iso, save_run_log


RUNTIME_FAILURE_MESSAGE = "アプリの実行環境が見つかりません。管理者に連絡してください。"


class PythonAppEnvRunner(BaseRunner):
    def run(self) -> RunnerResult:
        entry = self.app_entry()
        if not entry.is_file():
            return self._failure(USER_FAILURE_MESSAGE, f"entry file not found: {entry}", [])

        python = self.find_python()
        if python is None:
            searched = [
                self.app_env_python(),
                self.project_root / "runtime" / "python" / "python.exe",
            ]
            return self._failure(
                RUNTIME_FAILURE_MESSAGE,
                "python runtime not found. searched=" + ", ".join(str(path) for path in searched),
                [],
            )

        command = [str(python), str(entry)]
        env = build_app_env(self.project_root, self.manifest)
        self.apply_app_env_path(env)
        if self.manifest.run.show_terminal:
            return self.start_visible_terminal(command, env)
        if self.manifest.run.mode == "gui":
            return self.start_detached(command, env)
        return self.run_blocking(command, env)

    def find_python(self) -> Path | None:
        app_env = self.app_env_python()
        if app_env.is_file():
            return app_env
        fallback = self.project_root / "runtime" / "python" / "python.exe"
        if fallback.is_file():
            return fallback
        return None

    def app_env_python(self) -> Path:
        return self.project_root / "runtime" / "app_envs" / self.manifest.id / "Scripts" / "python.exe"

    def apply_app_env_path(self, env: dict[str, str]) -> None:
        scripts = self.project_root / "runtime" / "app_envs" / self.manifest.id / "Scripts"
        if scripts.is_dir():
            env["VIRTUAL_ENV"] = str(scripts.parent)
            env["PATH"] = str(scripts) + os.pathsep + env.get("PATH", "")

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
