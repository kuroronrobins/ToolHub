from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from toolhub_runner.base_runner import RunnerResult, USER_FAILURE_MESSAGE
from toolhub_runner.cli_runner import CliRunner
from toolhub_runner.exe_runner import ExeRunner
from toolhub_runner.event_protocol import RunnerEvent
from toolhub_runner.log_manager import create_run_log_paths, now_iso, save_run_log
from toolhub_runner.manifest import AppManifest, ManifestError, load_app_manifest
from toolhub_runner.playwright_runner import PlaywrightPythonRunner
from toolhub_runner.python_app_env_runner import PythonAppEnvRunner
from toolhub_runner.python_runner import PythonRunner
from toolhub_runner.python_shared_env_runner import PythonSharedEnvRunner


def select_runner(project_root: Path, manifest: AppManifest):
    if manifest.run.runner == "python":
        return PythonRunner(project_root, manifest)
    if manifest.run.runner == "python_app_env":
        return PythonAppEnvRunner(project_root, manifest)
    if manifest.run.runner == "python_shared_env":
        return PythonSharedEnvRunner(project_root, manifest)
    if manifest.run.runner == "cli":
        return CliRunner(project_root, manifest)
    if manifest.run.runner == "exe":
        return ExeRunner(project_root, manifest)
    if manifest.run.runner == "playwright_python":
        return PlaywrightPythonRunner(project_root, manifest)
    raise ManifestError(f"unsupported runner: {manifest.run.runner}")


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ToolHub Python App Runner")
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--app-id", required=True)
    parser.add_argument("--result-json")
    return parser.parse_args(argv)


def manifest_failure(project_root: Path, app_id: str, error: Exception) -> RunnerResult:
    paths = create_run_log_paths(project_root, app_id)
    events = [RunnerEvent(type="error", message=USER_FAILURE_MESSAGE)]
    save_run_log(
        paths,
        app_id=app_id,
        app_name=app_id,
        start_time=now_iso(),
        end_time=now_iso(),
        exit_code=None,
        stdout="",
        stderr="",
        events=events,
        user_message=USER_FAILURE_MESSAGE,
        admin_error=repr(error),
        command=[],
    )
    return RunnerResult(
        ok=False,
        app_id=app_id,
        user_message=USER_FAILURE_MESSAGE,
        log_path=str(paths.json_log),
        events=events,
    )


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    project_root = Path(args.project_root).resolve()
    app_id = args.app_id

    try:
        manifest = load_app_manifest(project_root, app_id)
        result = select_runner(project_root, manifest).run()
    except Exception as exc:
        result = manifest_failure(project_root, app_id, exc)

    payload = result.to_dict()
    if args.result_json:
        result_path = Path(args.result_json)
        result_path.parent.mkdir(parents=True, exist_ok=True)
        result_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        print(json.dumps(payload, ensure_ascii=False))

    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

