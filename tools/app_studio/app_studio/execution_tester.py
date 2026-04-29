from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from .models import BuildPlan, ExecutionCheck, ExecutionTestResult, RuntimeCheckResult, SecretScanReport, StudioContext
from .runtime_checker import is_forbidden_payload_path, required_data_findings
from .trace import trace_with_import_plan
from .util import now_iso, write_json, write_text

APPROVAL_BLOCKING_WARNING = "approval_blocking_warning"
NON_BLOCKING_WARNING = "non_blocking_warning"
INFO = "info"
FAIL = "fail"


SUPPORTED_RUNNERS = {"python", "cli", "exe", "playwright_python", "python_app_env"}


def run_execution_checks(
    context: StudioContext,
    plan: BuildPlan,
    output_dir: Path,
    secret_report: SecretScanReport | None = None,
    runtime_result: RuntimeCheckResult | None = None,
) -> ExecutionTestResult:
    result = build_execution_result(context, plan, output_dir, secret_report, runtime_result)
    write_execution_result(context, output_dir, result)
    return result


def record_blocked_execution(context: StudioContext, output_dir: Path, check_name: str, detail: str, plan: BuildPlan | None = None) -> ExecutionTestResult:
    result = ExecutionTestResult(
        app_id=context.app_id,
        generated_at=now_iso(),
        overall_status="fail",
        approval_allowed=False,
        checks=[check(check_name, "fail", detail, approval_category=FAIL, approval_blocking=True)],
        evidence=execution_evidence(context, output_dir, plan),
    )
    apply_approval_summary(result)
    write_execution_result(context, output_dir, result)
    return result


def write_execution_result(context: StudioContext, output_dir: Path, result: ExecutionTestResult) -> None:
    report = execution_report_markdown(result)
    write_text(output_dir / "execution_test_report.md", report)
    write_json(output_dir / "execution_test_result.json", result.to_dict())

    log_dir = context.repo_root / "data" / "logs" / "app_studio"
    write_text(log_dir / f"{context.app_id}_execution_test_report.md", report)
    write_json(log_dir / f"{context.app_id}_execution_test_result.json", result.to_dict())


def build_execution_result(
    context: StudioContext,
    plan: BuildPlan,
    output_dir: Path | None = None,
    secret_report: SecretScanReport | None = None,
    runtime_result: RuntimeCheckResult | None = None,
) -> ExecutionTestResult:
    output_dir = output_dir or context.output_dir
    checks: list[ExecutionCheck] = []
    app_yaml = context.repo_root / "apps" / context.app_id / "app.yaml"
    app_entry = context.repo_root / "apps" / context.app_id / plan.entry

    checks.append(check("app.yaml exists", "pass" if app_yaml.is_file() else "fail", str(app_yaml)))
    checks.append(parse_manifest_check(context))
    checks.append(check("runner supported", "pass" if plan.runner in SUPPORTED_RUNNERS else "fail", plan.runner))

    if plan.mode == "frozen-folder":
        checks.append(check("frozen-folder executable", "pass" if app_entry.is_file() else "fail", str(app_entry)))
        checks.append(check(".py run.entry blocked", "fail" if plan.entry.lower().endswith(".py") else "pass", plan.entry))
        checks.append(registered_build_required_check(context))
        checks.extend(frozen_profile_checks(context))
        checks.append(forbidden_registered_payload_check(context))
    else:
        checks.append(check("run.entry exists", "pass" if app_entry.is_file() else "fail", str(app_entry)))

    if secret_report and secret_report.blocks_apply:
        checks.append(check("secret scan", "fail", f"{len(secret_report.blocking_findings)} secret finding(s) block approval."))
    elif secret_report:
        detail = f"No Apply-blocking secret findings. warnings={len(secret_report.warning_findings)}, manual_checks={len(secret_report.manual_check_findings)}"
        checks.append(check("secret scan", "warn" if secret_report.findings else "pass", detail, approval_category=NON_BLOCKING_WARNING))

    if runtime_result:
        checks.extend(runtime_distribution_summary_checks(runtime_result))

    if plan.runner == "python_app_env":
        checks.append(python_runtime_check(context))

    runner_attempt = attempt_runner(context, plan, app_entry)
    if runner_attempt:
        checks.append(runner_attempt)

    overall = overall_status(checks)
    result = ExecutionTestResult(
        app_id=context.app_id,
        generated_at=now_iso(),
        overall_status=overall,
        approval_allowed=True,
        checks=checks,
        evidence=execution_evidence(context, output_dir, plan),
    )
    apply_approval_summary(result)
    return result


def runtime_distribution_summary_checks(runtime_result: RuntimeCheckResult) -> list[ExecutionCheck]:
    checks: list[ExecutionCheck] = []
    if runtime_result.overall_status == "fail":
        failed = [item for item in runtime_result.checks if item.status == "fail"]
        detail = "Distribution check failed: " + "; ".join(f"{item.name}: {item.detail}" for item in failed[:5])
        checks.append(check("distribution check", "fail", detail))
        return checks
    if runtime_result.approval_blocking_warnings_count:
        detail = "; ".join(runtime_result.approval_blocking_reasons[:5]) or "Distribution check has approval-blocking warnings."
        checks.append(check("distribution check", "warn", detail, approval_category=APPROVAL_BLOCKING_WARNING))
    elif runtime_result.non_blocking_warnings_count:
        detail = "; ".join(runtime_result.non_blocking_warning_summaries[:5]) or "Distribution check has non-blocking warnings."
        checks.append(check("distribution check", "warn", detail, approval_category=NON_BLOCKING_WARNING))
    else:
        checks.append(check("distribution check", "pass", "Distribution checks passed."))
    return checks


def check(
    name: str,
    status: str,
    detail: str,
    approval_category: str = "",
    approval_blocking: bool | None = None,
    resolved: bool = False,
) -> ExecutionCheck:
    category = approval_category or default_approval_category(status)
    blocking = status == "fail" if approval_blocking is None else approval_blocking
    if category == APPROVAL_BLOCKING_WARNING:
        blocking = True
    return ExecutionCheck(name=name, status=status, detail=detail, approval_category=category, approval_blocking=blocking, resolved=resolved)


def default_approval_category(status: str) -> str:
    if status == "fail":
        return FAIL
    if status == "warn":
        return NON_BLOCKING_WARNING
    return INFO


def overall_status(checks: list[ExecutionCheck]) -> str:
    statuses = {item.status for item in checks}
    if "fail" in statuses:
        return "fail"
    if "warn" in statuses:
        return "warn"
    return "pass"


def parse_manifest_check(context: StudioContext) -> ExecutionCheck:
    runner_path = context.repo_root / "runner"
    if str(runner_path) not in sys.path:
        sys.path.insert(0, str(runner_path))
    try:
        from toolhub_runner.manifest import load_app_manifest

        manifest = load_app_manifest(context.repo_root, context.app_id)
    except Exception as exc:
        return check("app.yaml parse", "fail", repr(exc))
    return check("app.yaml parse", "pass", f"runner={manifest.run.runner}, entry={manifest.run.entry}")


def python_runtime_check(context: StudioContext) -> ExecutionCheck:
    app_env_python = context.repo_root / "runtime" / "app_envs" / context.app_id / "Scripts" / "python.exe"
    runtime_python = context.repo_root / "runtime" / "python" / "python.exe"
    if app_env_python.is_file():
        return check("python_app_env runtime", "pass", str(app_env_python))
    if runtime_python.is_file():
        return check("python runtime fallback", "pass", str(runtime_python))
    return check("python runtime", "warn", f"Missing {app_env_python} and {runtime_python}. StrictApproval will reject this.")


def attempt_runner(context: StudioContext, plan: BuildPlan, app_entry: Path) -> ExecutionCheck | None:
    if not app_entry.is_file():
        return check("runner dry execution", "fail", "Skipped because entry file is not present.")
    if plan.runner == "exe" or plan.mode == "frozen-folder":
        return check(
            "runner dry execution",
            "warn",
            "Skipped for exe/frozen-folder mode. Browser, login, and GUI flows require human launch verification.",
            approval_category=NON_BLOCKING_WARNING,
        )
    if plan.runner == "python_app_env":
        app_env_python = context.repo_root / "runtime" / "app_envs" / context.app_id / "Scripts" / "python.exe"
        runtime_python = context.repo_root / "runtime" / "python" / "python.exe"
        if not app_env_python.is_file() and not runtime_python.is_file():
            return check("runner dry execution", "warn", "Skipped because ToolHub Python runtime/app_env is not present.", approval_category=NON_BLOCKING_WARNING)
    if plan.runner not in {"python_app_env", "cli"}:
        return check("runner dry execution", "warn", "Skipped because automatic GUI execution could be disruptive.", approval_category=NON_BLOCKING_WARNING)

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
        return check("runner dry execution", "warn", f"Could not run runner: {exc!r}")
    detail: Any = {"exit_code": completed.returncode}
    if result_json.is_file():
        try:
            detail["result"] = json.loads(result_json.read_text(encoding="utf-8"))
        except Exception:
            detail["result"] = "result json could not be parsed"
    if completed.returncode == 0:
        return check("runner dry execution", "pass", json.dumps(detail, ensure_ascii=False))
    status = "fail" if plan.runner == "cli" or plan.runner == "python_app_env" and plan.entry.endswith(".py") else "warn"
    return check("runner dry execution", status, json.dumps(detail, ensure_ascii=False))


def frozen_profile_checks(context: StudioContext) -> list[ExecutionCheck]:
    profile_path = context.repo_root / "apps" / context.app_id / "build_profile.json"
    if not profile_path.is_file():
        return [
            check(
                "frozen build profile",
                "warn",
                "build_profile.json was not found; data-file gate was skipped.",
                approval_category=APPROVAL_BLOCKING_WARNING,
            )
        ]
    try:
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return [check("frozen build profile", "fail", f"build_profile.json could not be parsed: {exc!r}")]

    findings = required_data_findings(context.repo_root / "apps" / context.app_id / "bin" / context.app_id, profile, context.source_root)
    if findings["status"] == "no_data":
        return [check("frozen data files", "warn", "No add_data entries are listed in build_profile.json.", approval_category=NON_BLOCKING_WARNING)]
    if findings["missing"]:
        return [check("frozen data files", "fail", "Missing packaged data files: " + ", ".join(item["relative"] for item in findings["missing"][:10]))]
    if findings["internal_only"]:
        return [
            check(
                "frozen data files",
                "warn",
                f"{findings['found_count']} packaged data file(s) were found, but {len(findings['internal_only'])} are only under _internal. Rebuild with --contents-directory . to normalize layout.",
                approval_category=NON_BLOCKING_WARNING,
            )
        ]
    return [check("frozen data files", "pass", f"{findings['found_count']} packaged data file(s) were found.")]


def forbidden_registered_payload_check(context: StudioContext) -> ExecutionCheck:
    app_dir = context.repo_root / "apps" / context.app_id
    if not app_dir.is_dir():
        return check("forbidden registered payload", "fail", f"App directory is missing: {app_dir}")
    findings: list[str] = []
    for path in sorted(app_dir.rglob("*")):
        if is_forbidden_payload_path(path, app_dir):
            findings.append(path.relative_to(app_dir).as_posix())
    if findings:
        return check("forbidden registered payload", "fail", "Forbidden files were registered: " + ", ".join(findings[:10]))
    return check("forbidden registered payload", "pass", "No forbidden credential, log, cache, temp, or build_env files were registered.")


def registered_build_required_check(context: StudioContext) -> ExecutionCheck:
    marker = context.repo_root / "apps" / context.app_id / "bin" / "BUILD_REQUIRED.txt"
    if marker.exists():
        return check("registered BUILD_REQUIRED marker", "fail", f"BUILD_REQUIRED.txt remains after registration: {marker}")
    return check("registered BUILD_REQUIRED marker", "pass", "BUILD_REQUIRED.txt is not present in apps/<app_id>/bin.")


def execution_report_markdown(result: ExecutionTestResult) -> str:
    lines = [
        "# Execution Test Report",
        "",
        f"- app_id: `{result.app_id}`",
        f"- generated_at: `{result.generated_at}`",
        f"- overall_status: `{result.overall_status}`",
        f"- approval_allowed: `{str(result.approval_allowed).lower()}`",
        f"- approval_blocking_warnings_count: `{result.approval_blocking_warnings_count}`",
        f"- non_blocking_warnings_count: `{result.non_blocking_warnings_count}`",
        f"- info_count: `{result.info_count}`",
        f"- unresolved_distribution_risks_count: `{result.unresolved_distribution_risks_count}`",
        "",
        "| Status | Category | Blocking | Check | Detail |",
        "| --- | --- | --- | --- | --- |",
    ]
    lines.extend(
        f"| {item.status} | {item.approval_category or default_approval_category(item.status)} | {str(item.approval_blocking or item.status == 'fail').lower()} | {item.name} | {item.detail} |"
        for item in result.checks
    )
    if result.evidence:
        lines.extend(["", "## Evidence", "", "```json", json.dumps(result.evidence, ensure_ascii=False, indent=2), "```"])
    lines.append("")
    lines.append("Human approval is required before enabling this app in release/app_manifest.json.")
    return "\n".join(lines) + "\n"


def execution_evidence(context: StudioContext, output_dir: Path, plan: BuildPlan | None) -> dict[str, Any]:
    app_dir = context.repo_root / "apps" / context.app_id
    app_yaml = app_dir / "app.yaml"
    build_profile = app_dir / "build_profile.json"
    output_build_profile = output_dir / "build_profile.json"
    entry = plan.entry if plan else f"bin/{context.app_id}/{context.app_id}.exe"
    frozen_exe = app_dir / entry
    output_frozen_exe = output_dir / "final_app" / entry
    return {
        **trace_with_import_plan(context, output_dir),
        "output_dir": str(output_dir),
        "frozen_build_report": file_evidence(output_dir / "frozen_folder_build_report.md"),
        "frozen_exe": file_evidence(frozen_exe),
        "output_frozen_exe": file_evidence(output_frozen_exe),
        "app_yaml": file_evidence(app_yaml),
        "build_profile": file_evidence(build_profile if build_profile.is_file() else output_build_profile),
        "timing_report": file_evidence(output_dir / "timing_report.json"),
    }


def file_evidence(path: Path) -> dict[str, Any]:
    exists = path.exists()
    stat = path.stat() if exists else None
    return {
        "path": str(path),
        "exists": exists,
        "last_write_time": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds") if stat else None,
        "size": stat.st_size if stat and path.is_file() else None,
    }


def apply_approval_summary(result: ExecutionTestResult) -> None:
    summary = approval_summary(result.checks)
    result.approval_blocking_warnings_count = summary["approval_blocking_warnings_count"]
    result.non_blocking_warnings_count = summary["non_blocking_warnings_count"]
    result.info_count = summary["info_count"]
    result.unresolved_distribution_risks_count = summary["unresolved_distribution_risks_count"]
    result.approval_blocking_reasons = summary["approval_blocking_reasons"]
    result.non_blocking_warning_summaries = summary["non_blocking_warning_summaries"]
    result.approval_allowed = not has_fail(result.checks) and result.approval_blocking_warnings_count == 0


def approval_summary(checks: list[ExecutionCheck]) -> dict[str, Any]:
    blocking_warnings = [
        item
        for item in checks
        if item.status == "warn" and (item.approval_blocking or item.approval_category == APPROVAL_BLOCKING_WARNING)
    ]
    non_blocking_warnings = [
        item
        for item in checks
        if item.status == "warn" and not (item.approval_blocking or item.approval_category == APPROVAL_BLOCKING_WARNING)
    ]
    info_checks = [item for item in checks if (item.approval_category or default_approval_category(item.status)) == INFO]
    return {
        "approval_blocking_warnings_count": len(blocking_warnings),
        "non_blocking_warnings_count": len(non_blocking_warnings),
        "info_count": len(info_checks),
        "unresolved_distribution_risks_count": len(blocking_warnings) + sum(1 for item in checks if item.status == "fail"),
        "approval_blocking_reasons": [f"{item.name}: {item.detail}" for item in blocking_warnings[:10]],
        "non_blocking_warning_summaries": [f"{item.name}: {item.detail}" for item in non_blocking_warnings[:10]],
    }


def has_fail(checks: list[ExecutionCheck]) -> bool:
    return any(item.status == "fail" for item in checks)
