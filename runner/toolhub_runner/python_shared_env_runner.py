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

        env_root = self.shared_env_root()
        if not env_root.is_dir():
            return self._failure(
                RUNTIME_FAILURE_MESSAGE,
                f"shared env root not found: env_id={self.manifest.run.env_id}, path={env_root}",
                [],
            )

        site_packages = self.shared_env_site_packages(env_root)
        if not site_packages.is_dir():
            return self._failure(
                RUNTIME_FAILURE_MESSAGE,
                f"shared env site-packages not found: env_id={self.manifest.run.env_id}, path={site_packages}",
                [],
            )

        python = self.bundled_python()
        if not python.is_file():
            return self._failure(
                RUNTIME_FAILURE_MESSAGE,
                f"bundled python not found: env_id={self.manifest.run.env_id}, path={python}",
                [],
            )

        bootstrap = self.shared_env_bootstrap()
        if not bootstrap.is_file():
            return self._failure(
                RUNTIME_FAILURE_MESSAGE,
                f"shared env bootstrap not found: {bootstrap}",
                [],
            )

        command = [str(python), str(bootstrap), str(env_root), str(entry)]
        env = build_app_env(self.project_root, self.manifest)
        self.apply_shared_env_path(env, python, env_root, site_packages)
        cwd = entry.parent
        if self.manifest.run.show_terminal:
            return self.start_visible_terminal(command, env, cwd=cwd)
        if self.manifest.run.mode == "gui":
            return self.start_detached(command, env, cwd=cwd)
        return self.run_blocking(command, env, cwd=cwd)

    def shared_env_root(self) -> Path:
        env_id = self.manifest.run.env_id
        if not env_id:
            return Path("__missing_env_id__")
        return self.project_root / "runtime" / "envs" / env_id

    def bundled_python(self) -> Path:
        runtime_root = self.project_root / "runtime" / "python"
        return runtime_root / ("python.exe" if os.name == "nt" else "bin/python")

    def shared_env_bootstrap(self) -> Path:
        return Path(__file__).resolve().with_name("shared_env_bootstrap.py")

    def shared_env_site_packages(self, env_root: Path) -> Path:
        windows_site_packages = env_root / "Lib" / "site-packages"
        if windows_site_packages.is_dir() or os.name == "nt":
            return windows_site_packages
        matches = sorted((env_root / "lib").glob("python*/site-packages"))
        if matches:
            return matches[0]
        return env_root / "lib" / "site-packages"

    def apply_shared_env_path(self, env: dict[str, str], python: Path, env_root: Path, site_packages: Path) -> None:
        scripts = env_root / ("Scripts" if os.name == "nt" else "bin")
        path_entries = [
            str(python.parent),
            str(scripts),
        ]
        pywin32_system32 = site_packages / "pywin32_system32"
        if pywin32_system32.is_dir():
            path_entries.append(str(pywin32_system32))
        env["VIRTUAL_ENV"] = str(env_root)
        env["PATH"] = os.pathsep.join(path_entries + [env.get("PATH", "")])
        env["PYTHONNOUSERSITE"] = "1"
        env["TOOLHUB_SHARED_ENV_ID"] = self.manifest.run.env_id
        env["TOOLHUB_SHARED_ENV_ROOT"] = str(env_root)
        env["TOOLHUB_SHARED_ENV_SITE_PACKAGES"] = str(site_packages)

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
