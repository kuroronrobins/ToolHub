from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .event_protocol import RunnerEvent, parse_stdout
from .log_manager import create_run_log_paths, now_iso, save_run_log
from .manifest import AppManifest


USER_FAILURE_MESSAGE = "アプリの起動に失敗しました。時間をおいて再実行するか、管理者に連絡してください。"
STARTUP_EXIT_MESSAGE = "アプリは起動直後に終了しました。管理者にログ確認を依頼してください。"
STARTUP_PROBE_SECONDS = 2.0
DETACHED_OUTPUT_TAIL_CHARS = 12000


@dataclass
class RunnerResult:
    ok: bool
    app_id: str
    user_message: str
    log_path: Optional[str]
    events: list[RunnerEvent] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "appId": self.app_id,
            "userMessage": self.user_message,
            "logPath": self.log_path,
            "events": [event.to_dict() for event in self.events],
        }


class BaseRunner:
    def __init__(self, project_root: Path, manifest: AppManifest) -> None:
        self.project_root = project_root
        self.manifest = manifest

    def run(self) -> RunnerResult:
        raise NotImplementedError

    def app_entry(self) -> Path:
        return self.manifest.app_dir / self.manifest.run.entry

    def success_result(self, message: str, events: list[RunnerEvent], log_path: Path) -> RunnerResult:
        return RunnerResult(
            ok=True,
            app_id=self.manifest.id,
            user_message=message,
            log_path=str(log_path),
            events=events,
        )

    def failure_result(self, events: list[RunnerEvent], log_path: Optional[Path], message: str = USER_FAILURE_MESSAGE) -> RunnerResult:
        if not events or events[-1].type != "error":
            events.append(RunnerEvent(type="error", message=message))
        return RunnerResult(
            ok=False,
            app_id=self.manifest.id,
            user_message=message,
            log_path=str(log_path) if log_path else None,
            events=events,
        )

    def run_blocking(self, command: list[str], env: dict[str, str]) -> RunnerResult:
        paths = create_run_log_paths(self.project_root, self.manifest.id)
        start = now_iso()
        stdout = ""
        stderr = ""
        exit_code: Optional[int] = None
        admin_error = ""
        events: list[RunnerEvent] = [RunnerEvent(type="status", message="起動準備をしています", progress=10)]

        try:
            completed = subprocess.run(
                command,
                cwd=str(self.manifest.app_dir),
                env=env,
                text=True,
                encoding="utf-8",
                errors="replace",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            stdout = completed.stdout
            stderr = completed.stderr
            exit_code = completed.returncode
            events.extend(parse_stdout(stdout))
        except Exception as exc:
            admin_error = repr(exc)
            exit_code = None

        ok = exit_code == 0
        if ok and not any(event.type == "success" for event in events):
            events.append(RunnerEvent(type="success", message="完了しました", progress=100))
        if not ok:
            events.append(RunnerEvent(type="error", message=USER_FAILURE_MESSAGE))

        end = now_iso()
        user_message = "完了しました。" if ok else USER_FAILURE_MESSAGE
        save_run_log(
            paths,
            app_id=self.manifest.id,
            app_name=self.manifest.name,
            start_time=start,
            end_time=end,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            events=events,
            user_message=user_message,
            admin_error=admin_error,
            command=command,
        )

        if ok:
            return self.success_result(user_message, events, paths.json_log)
        return self.failure_result(events, paths.json_log)

    def start_detached(self, command: list[str], env: dict[str, str]) -> RunnerResult:
        paths = create_run_log_paths(self.project_root, self.manifest.id)
        start = now_iso()
        events = [RunnerEvent(type="status", message="起動準備をしています", progress=10)]
        stdout = ""
        stderr = ""
        admin_error = ""
        pid: int | None = None
        exit_code: Optional[int] = None
        ok = False

        try:
            stdout_file = paths.stdout_log.open("wb")
            stderr_file = paths.stderr_log.open("wb")
            try:
                process = subprocess.Popen(
                    command,
                    cwd=str(self.manifest.app_dir),
                    env=env,
                    stdout=stdout_file,
                    stderr=stderr_file,
                    close_fds=True,
                )
            finally:
                stdout_file.close()
                stderr_file.close()
            pid = process.pid
            exit_code = wait_for_startup_exit(process, STARTUP_PROBE_SECONDS)
            if exit_code is None:
                ok = True
                release_detached_process(process)
                events.append(RunnerEvent(type="success", message="起動しました", progress=100))
            else:
                stdout = read_text_tail(paths.stdout_log)
                stderr = read_text_tail(paths.stderr_log)
                admin_error = f"process exited during startup probe with exit_code={exit_code}"
                events.append(RunnerEvent(type="error", message=STARTUP_EXIT_MESSAGE, progress=100))
        except Exception as exc:
            admin_error = repr(exc)
            events.append(RunnerEvent(type="error", message=USER_FAILURE_MESSAGE))

        end = now_iso()
        user_message = "起動しました。" if ok else STARTUP_EXIT_MESSAGE if exit_code is not None else USER_FAILURE_MESSAGE
        save_run_log(
            paths,
            app_id=self.manifest.id,
            app_name=self.manifest.name,
            start_time=start,
            end_time=end,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            events=events,
            user_message=user_message,
            admin_error=admin_error,
            command=command,
            pid=pid,
            stdout_log_path=str(paths.stdout_log) if paths.stdout_log.exists() else None,
            stderr_log_path=str(paths.stderr_log) if paths.stderr_log.exists() else None,
        )

        if ok:
            return self.success_result(user_message, events, paths.json_log)
        return self.failure_result(events, paths.json_log, user_message)


def wait_for_startup_exit(process: subprocess.Popen[bytes], seconds: float) -> Optional[int]:
    deadline = time.monotonic() + max(0.0, seconds)
    while True:
        exit_code = process.poll()
        if exit_code is not None:
            return exit_code
        if time.monotonic() >= deadline:
            return None
        time.sleep(0.05)


def release_detached_process(process: subprocess.Popen[bytes]) -> None:
    handle = getattr(process, "_handle", None)
    if handle is not None and hasattr(handle, "Close"):
        handle.Close()
        if hasattr(process, "_child_created"):
            process._child_created = False


def read_text_tail(path: Path, limit: int = DETACHED_OUTPUT_TAIL_CHARS) -> str:
    if not path.is_file():
        return ""
    data = path.read_bytes()
    if len(data) > limit:
        data = data[-limit:]
    return data.decode("utf-8", errors="replace")

