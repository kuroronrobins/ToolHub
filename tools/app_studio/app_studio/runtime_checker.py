from __future__ import annotations

import subprocess
from pathlib import Path

from .models import RuntimeCheck, RuntimeCheckResult, StudioContext
from .util import write_json, write_text


def verify_runtime(context: StudioContext, output_dir: Path) -> RuntimeCheckResult:
    runtime_python = context.repo_root / "runtime" / "python" / "python.exe"
    app_env_python = context.repo_root / "runtime" / "app_envs" / context.app_id / "Scripts" / "python.exe"
    checks = [
        file_check("runtime/python/python.exe exists", runtime_python, missing_status="warn"),
        command_check("runtime python --version", runtime_python, ["--version"]),
        command_check("runtime python pip --version", runtime_python, ["-m", "pip", "--version"]),
        file_check("app_env python exists", app_env_python, missing_status="warn"),
        command_check("app_env python --version", app_env_python, ["--version"]),
        command_check("app_env python pip --version", app_env_python, ["-m", "pip", "--version"]),
    ]
    if not runtime_python.is_file() and not app_env_python.is_file():
        checks.append(RuntimeCheck("app-env runnable runtime", "fail", "Neither runtime/python/python.exe nor runtime/app_envs/<app_id>/Scripts/python.exe exists."))
    result = RuntimeCheckResult(context.app_id, overall_status(checks), checks)
    write_runtime_reports(context, output_dir, result)
    return result


def file_check(name: str, path: Path, missing_status: str = "fail") -> RuntimeCheck:
    if path.is_file():
        return RuntimeCheck(name, "pass", str(path))
    return RuntimeCheck(name, missing_status, f"Missing: {path}")


def command_check(name: str, python_path: Path, args: list[str]) -> RuntimeCheck:
    if not python_path.is_file():
        return RuntimeCheck(name, "warn", f"Skipped because executable is missing: {python_path}")
    try:
        completed = subprocess.run([str(python_path), *args], text=True, encoding="utf-8", errors="replace", stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20, check=False)
    except Exception as exc:
        return RuntimeCheck(name, "fail", repr(exc))
    detail = (completed.stdout or completed.stderr).strip()
    status = "pass" if completed.returncode == 0 else "fail"
    return RuntimeCheck(name, status, detail or f"exit_code={completed.returncode}")


def overall_status(checks: list[RuntimeCheck]) -> str:
    statuses = {check.status for check in checks}
    if "fail" in statuses:
        return "fail"
    if "warn" in statuses:
        return "warn"
    return "pass"


def runtime_report_markdown(result: RuntimeCheckResult) -> str:
    lines = [
        "# Runtime Check Report",
        "",
        f"- app_id: `{result.app_id}`",
        f"- overall_status: `{result.overall_status}`",
        "",
        "| Status | Check | Detail |",
        "| --- | --- | --- |",
    ]
    lines.extend(f"| {check.status} | {check.name} | {check.detail} |" for check in result.checks)
    lines.extend(
        [
            "",
            "Development Python fallback is acceptable while developing, but release validation should pass with ToolHub bundled `runtime/python/python.exe` and the generated app_env.",
        ]
    )
    return "\n".join(lines) + "\n"


def write_runtime_reports(context: StudioContext, output_dir: Path, result: RuntimeCheckResult) -> None:
    report = runtime_report_markdown(result)
    write_text(output_dir / "runtime_check_report.md", report)
    write_json(output_dir / "runtime_check_result.json", result.to_dict())
    log_dir = context.repo_root / "data" / "logs" / "app_studio"
    write_text(log_dir / f"{context.app_id}_runtime_check_report.md", report)
    write_json(log_dir / f"{context.app_id}_runtime_check_result.json", result.to_dict())

