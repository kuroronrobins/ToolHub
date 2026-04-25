from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from .models import BuildPlan, StudioContext
from .util import now_iso, write_text


SUPPORTED_RUNNERS = {"python", "cli", "exe", "playwright_python", "python_app_env"}


def run_execution_checks(context: StudioContext, plan: BuildPlan, output_dir: Path) -> Path:
    report = build_execution_report(context, plan)
    output_report = output_dir / "execution_test_report.md"
    write_text(output_report, report)

    log_dir = context.repo_root / "data" / "logs" / "app_studio"
    log_report = log_dir / f"{context.app_id}_execution_test_report.md"
    write_text(log_report, report)
    return output_report


def build_execution_report(context: StudioContext, plan: BuildPlan) -> str:
    checks: list[tuple[str, str, str]] = []
    app_yaml = context.repo_root / "apps" / context.app_id / "app.yaml"
    app_entry = context.repo_root / "apps" / context.app_id / plan.entry

    checks.append(("OK" if app_yaml.is_file() else "NG", "app.yaml", str(app_yaml)))
    checks.append(parse_manifest_check(context))
    checks.append(("OK" if plan.runner in SUPPORTED_RUNNERS else "NG", "runner", plan.runner))
    checks.append(("OK" if app_entry.is_file() else "WARN", "entry", str(app_entry)))

    if plan.runner == "python_app_env":
        app_env_python = context.repo_root / "runtime" / "app_envs" / context.app_id / "Scripts" / "python.exe"
        runtime_python = context.repo_root / "runtime" / "python" / "python.exe"
        if app_env_python.is_file():
            checks.append(("OK", "python_app_env runtime", str(app_env_python)))
        elif runtime_python.is_file():
            checks.append(("OK", "python runtime fallback", str(runtime_python)))
        else:
            checks.append(("WARN", "python runtime", f"Missing {app_env_python} and {runtime_python}. Runtime may be provided during installation."))

    runner_attempt = attempt_runner(context, plan, app_entry)
    if runner_attempt:
        checks.append(runner_attempt)

    lines = [
        "# Execution Test Report",
        "",
        f"- app_id: `{context.app_id}`",
        f"- generated_at: `{now_iso()}`",
        "",
        "| Status | Check | Detail |",
        "| --- | --- | --- |",
    ]
    lines.extend(f"| {status} | {name} | {detail} |" for status, name, detail in checks)
    lines.append("")
    lines.append("Human approval is required before enabling this app in release/app_manifest.json.")
    return "\n".join(lines) + "\n"


def parse_manifest_check(context: StudioContext) -> tuple[str, str, str]:
    runner_path = context.repo_root / "runner"
    if str(runner_path) not in sys.path:
        sys.path.insert(0, str(runner_path))
    try:
        from toolhub_runner.manifest import load_app_manifest

        manifest = load_app_manifest(context.repo_root, context.app_id)
    except Exception as exc:
        return ("NG", "app.yaml parse", repr(exc))
    return ("OK", "app.yaml parse", f"runner={manifest.run.runner}, entry={manifest.run.entry}")


def attempt_runner(context: StudioContext, plan: BuildPlan, app_entry: Path) -> tuple[str, str, str] | None:
    if not app_entry.is_file():
        return ("WARN", "runner dry execution", "Skipped because entry file is not present.")
    if plan.runner == "exe" or plan.mode == "frozen-folder":
        return ("WARN", "runner dry execution", "Skipped for exe/frozen-folder mode in MVP.")
    if plan.runner == "python_app_env":
        app_env_python = context.repo_root / "runtime" / "app_envs" / context.app_id / "Scripts" / "python.exe"
        runtime_python = context.repo_root / "runtime" / "python" / "python.exe"
        if not app_env_python.is_file() and not runtime_python.is_file():
            return ("WARN", "runner dry execution", "Skipped because ToolHub Python runtime is not present in this checkout.")
    if plan.runner not in {"python_app_env", "cli"}:
        return ("WARN", "runner dry execution", "Skipped because automatic GUI execution could be disruptive.")

    result_json = context.repo_root / "data" / "logs" / "app_studio" / f"{context.app_id}_runner_result.json"
    command = [
        sys.executable,
        str(context.repo_root / "runner" / "toolhub_runner" / "main.py"),
        "--project-root",
        str(context.repo_root),
        "--app-id",
        context.app_id,
        "--result-json",
        str(result_json),
    ]
    try:
        completed = subprocess.run(command, cwd=str(context.repo_root), text=True, capture_output=True, timeout=20, check=False)
    except Exception as exc:
        return ("WARN", "runner dry execution", f"Could not run runner: {exc!r}")
    detail: Any = {"exit_code": completed.returncode}
    if result_json.is_file():
        try:
            detail["result"] = json.loads(result_json.read_text(encoding="utf-8"))
        except Exception:
            detail["result"] = "result json could not be parsed"
    status = "OK" if completed.returncode == 0 else "WARN"
    return (status, "runner dry execution", json.dumps(detail, ensure_ascii=False))
