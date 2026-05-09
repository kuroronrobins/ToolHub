from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Any

from .registrar import (
    app_pack_requirements_lock_entry,
    app_relative_path,
    load_app_manifest_json,
    normalize_app_relative_entry,
    package_app_pack,
    require_app_yaml_file,
)
from .util import find_repo_root, now_iso, write_json, write_text


def approve_app(repo_root: Path, app_id: str, strict: bool = False, allow_warnings: bool = True) -> Path:
    repo_root = find_repo_root(repo_root)
    manifest_path = repo_root / "release" / "app_manifest.json"
    original_manifest = load_app_manifest_json(manifest_path)
    manifest = copy.deepcopy(original_manifest)

    record_path = repo_root / "data" / "logs" / "app_studio" / f"{app_id}_approval_record.md"
    record_written = False
    verify_before = run_verify_release(repo_root)
    try:
        entry, result = validate_approval_inputs(repo_root, manifest, app_id, strict, allow_warnings)
        entry = copy.deepcopy(entry)
        entry["enabled"] = True
        manifest["apps"][app_id] = entry
        write_json(manifest_path, manifest)

        package_path = package_app_pack(repo_root, app_id)
        updated_manifest = load_app_manifest_json(manifest_path)
        updated_entry = updated_manifest.get("apps", {}).get(app_id, entry)
        targeted_result = targeted_approval_verification(repo_root, app_id, updated_entry, package_path)
        verify_result = run_verify_release(repo_root)
        verify_gate = verify_release_gate(app_id, verify_before, verify_result)

        if targeted_result.get("status") == "failed" or verify_gate.get("rollback_required"):
            write_json(manifest_path, original_manifest)
            failures = []
            if targeted_result.get("status") == "failed":
                failures.extend(targeted_result.get("failures") or ["targeted approval verification failed"])
            if verify_gate.get("rollback_required"):
                failures.extend(verify_gate.get("rollback_failures") or ["verify_release.ps1 failed for this app or introduced new failures"])
            record = approval_record(
                "rolled_back",
                app_id,
                updated_entry if isinstance(updated_entry, dict) else entry,
                package_path,
                result,
                verify_result,
                failures,
                verify_before=verify_before,
                targeted_result=targeted_result,
                verify_gate=verify_gate,
                manifest_enabled_after=False,
            )
            write_text(record_path, record)
            record_written = True
            write_mirror_record(repo_root, app_id, record, package_path)
            raise RuntimeError("Approval verification failed; enabled=true was rolled back. " + "; ".join(failures[:3]))

        status = "approved_with_global_warnings" if verify_gate.get("global_warning") else "approved"
        record = approval_record(
            status,
            app_id,
            updated_entry if isinstance(updated_entry, dict) else entry,
            package_path,
            result,
            verify_result,
            [],
            verify_before=verify_before,
            targeted_result=targeted_result,
            verify_gate=verify_gate,
            manifest_enabled_after=True,
        )
        write_text(record_path, record)
        record_written = True
        write_mirror_record(repo_root, app_id, record, package_path)
        return record_path
    except Exception as exc:
        write_json(manifest_path, original_manifest)
        if not record_written:
            record = approval_record(
                "failed",
                app_id,
                {},
                None,
                None,
                {"status": "not_run"},
                [str(exc)],
                verify_before=verify_before,
                targeted_result={"status": "not_run"},
                verify_gate={"rollback_required": True, "rollback_reason": str(exc)},
                manifest_enabled_after=False,
            )
            write_text(record_path, record)
        raise


def validate_approval_inputs(repo_root: Path, manifest: dict[str, Any], app_id: str, strict: bool, allow_warnings: bool) -> tuple[dict[str, Any], dict[str, Any]]:
    apps = manifest.get("apps") or {}
    entry = apps.get(app_id)
    if not isinstance(entry, dict):
        raise ValueError(f"App is not listed in release/app_manifest.json: {app_id}")
    app_yaml = repo_root / "apps" / app_id / "app.yaml"
    if not app_yaml.is_file():
        raise FileNotFoundError(f"app.yaml was not found: {app_yaml}")

    result_path = repo_root / "data" / "logs" / "app_studio" / f"{app_id}_execution_test_result.json"
    if not result_path.is_file():
        raise FileNotFoundError(f"Execution test result JSON was not found: {result_path}")
    result = json.loads(result_path.read_text(encoding="utf-8"))

    validate_result_identity_and_output_dir(repo_root, app_id, app_yaml, result, result_path, "Execution test result")
    checks = result.get("checks") or []
    fail_checks = [item for item in checks if item.get("status") == "fail"]
    warn_checks = [item for item in checks if item.get("status") == "warn"]
    approval_blocking_warn_checks = [
        item
        for item in warn_checks
        if item.get("approval_blocking") is True or item.get("approval_category") == "approval_blocking_warning"
    ]
    stale_signals = stale_execution_result_signals(repo_root, app_id, app_yaml, result_path)
    if stale_signals:
        raise ValueError(
            "Execution test result is stale. "
            f"result_path={result_path}; stale_against={'; '.join(stale_signals)}"
        )
    if result.get("approval_allowed") is not True:
        raise ValueError(
            "Execution test result does not allow approval. "
            f"result_path={result_path}; generated_at={result.get('generated_at')}; overall_status={result.get('overall_status')}; "
            f"fail_checks={format_check_summaries(fail_checks)}; warn_checks={format_check_summaries(warn_checks)}"
        )
    if fail_checks:
        raise ValueError(f"Execution test result contains fail checks. result_path={result_path}; fail_checks={format_check_summaries(fail_checks)}")
    if result.get("overall_status") == "fail":
        raise ValueError(f"Execution test result overall_status=fail. result_path={result_path}; fail_checks={format_check_summaries(fail_checks)}")
    if strict and approval_blocking_warn_checks:
        raise ValueError(
            "StrictApproval rejects approval-blocking warning checks. "
            f"result_path={result_path}; warn_checks={format_check_summaries(approval_blocking_warn_checks)}"
        )
    if not allow_warnings and approval_blocking_warn_checks:
        raise ValueError(
            "Approval-blocking warnings are not allowed for this approval. "
            f"result_path={result_path}; warn_checks={format_check_summaries(approval_blocking_warn_checks)}"
        )
    validate_runtime_check_for_approval(repo_root, app_id, app_yaml)
    return entry, result


def validate_runtime_check_for_approval(repo_root: Path, app_id: str, app_yaml: Path) -> None:
    result_path = repo_root / "data" / "logs" / "app_studio" / f"{app_id}_runtime_check_result.json"
    if not result_path.is_file():
        return
    result = json.loads(result_path.read_text(encoding="utf-8"))
    validate_result_identity_and_output_dir(repo_root, app_id, app_yaml, result, result_path, "Runtime check result")
    stale_signals = stale_runtime_result_signals(result, result_path)
    if stale_signals:
        raise ValueError(
            "Runtime check result is stale. "
            f"result_path={result_path}; stale_against={'; '.join(stale_signals)}"
        )
    checks = result.get("checks") if isinstance(result.get("checks"), list) else []
    fail_checks = [item for item in checks if isinstance(item, dict) and item.get("status") == "fail"]
    if result.get("overall_status") == "fail" or fail_checks:
        raise ValueError(
            "Runtime check result blocks approval. "
            f"result_path={result_path}; overall_status={result.get('overall_status')}; "
            f"fail_checks={format_check_summaries(fail_checks)}"
        )
    if int(result.get("approval_blocking_warnings_count") or 0) > 0:
        raise ValueError(
            "Runtime check result contains approval-blocking warnings. "
            f"result_path={result_path}; approval_blocking_reasons={result.get('approval_blocking_reasons') or []}"
        )


def validate_result_identity_and_output_dir(
    repo_root: Path,
    app_id: str,
    app_yaml: Path,
    result: dict[str, Any],
    result_path: Path,
    label: str,
) -> None:
    actual_app_id = result.get("app_id")
    if isinstance(actual_app_id, str) and actual_app_id and actual_app_id != app_id:
        raise ValueError(
            f"{label} app_id mismatch. "
            f"result_path={result_path}; expected_app_id={app_id}; result_app_id={actual_app_id}"
        )
    if actual_app_id is not None and not isinstance(actual_app_id, str):
        raise ValueError(
            f"{label} app_id is invalid. "
            f"result_path={result_path}; expected_app_id={app_id}; result_app_id={actual_app_id!r}"
        )

    expected_output = find_output_mirror(repo_root, app_id)
    actual_output = result_output_dir(result)
    if expected_output and actual_output and not same_path(repo_root, expected_output, actual_output):
        raise ValueError(
            f"{label} output_dir mismatch. "
            f"result_path={result_path}; app_yaml={app_yaml}; "
            f"app_yaml_output_mirror={expected_output}; result_output_dir={actual_output}"
        )


def result_output_dir(result: dict[str, Any]) -> str:
    value = result.get("output_dir")
    if isinstance(value, str) and value.strip():
        return value.strip()
    evidence = result.get("evidence")
    if isinstance(evidence, dict):
        value = evidence.get("output_dir")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def same_path(repo_root: Path, expected: Path, actual: str) -> bool:
    expected_path = resolve_for_compare(repo_root, expected)
    actual_path = resolve_for_compare(repo_root, Path(actual))
    return os.path.normcase(str(expected_path)) == os.path.normcase(str(actual_path))


def resolve_for_compare(repo_root: Path, path: Path) -> Path:
    base = path.expanduser()
    if not base.is_absolute():
        base = repo_root / base
    try:
        return base.resolve()
    except Exception:
        return base.absolute()


def stale_execution_result_signals(repo_root: Path, app_id: str, app_yaml: Path, result_path: Path) -> list[str]:
    result_mtime = result_path.stat().st_mtime
    signals: list[str] = []
    compare_target(result_mtime, app_yaml, "app.yaml", signals)
    compare_target(result_mtime, repo_root / "apps" / app_id / "build_profile.json", "build_profile.json", signals)
    compare_target(result_mtime, repo_root / "data" / "logs" / "app_studio" / f"{app_id}_frozen_folder_build_report.md", "frozen_folder_build_report.md", signals)

    entry = app_yaml_run_entry(app_yaml) or f"bin/{app_id}/{app_id}.exe"
    compare_target(result_mtime, repo_root / "apps" / app_id / entry, "frozen exe", signals)
    return signals


def stale_runtime_result_signals(result: dict[str, Any], result_path: Path) -> list[str]:
    output = result_output_dir(result)
    if not output:
        return []
    output_dir = Path(output)
    result_mtime = result_path.stat().st_mtime
    signals: list[str] = []
    final_app = output_dir / "final_app"
    compare_target(result_mtime, final_app / "app.yaml", "final_app/app.yaml", signals)
    entry = app_yaml_run_entry(final_app / "app.yaml")
    if entry:
        compare_target(result_mtime, final_app / entry, "final_app run.entry", signals)
    return signals


def compare_target(result_mtime: float, path: Path, label: str, signals: list[str]) -> None:
    if not path.is_file():
        return
    if path.stat().st_mtime > result_mtime:
        signals.append(f"{label} is newer than execution_test_result.json ({path})")


def app_yaml_run_entry(path: Path) -> str | None:
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.strip().startswith("entry:"):
                return line.split(":", 1)[1].strip().strip('"').strip("'")
    except Exception:
        return None
    return None


def format_check_summaries(checks: list[dict[str, Any]]) -> str:
    if not checks:
        return "none"
    summaries = []
    for item in checks[:5]:
        name = str(item.get("name") or "-")
        status = str(item.get("status") or "-")
        detail = str(item.get("detail") or "-")
        summaries.append(f"[{status}] {name}: {detail}")
    if len(checks) > 5:
        summaries.append(f"... +{len(checks) - 5} more")
    return " | ".join(summaries)


def run_verify_release(repo_root: Path) -> dict[str, Any]:
    script = repo_root / "scripts" / "verify_release.ps1"
    if not script.is_file():
        return {"status": "skipped", "reason": "scripts/verify_release.ps1 was not found."}
    command = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)]
    try:
        completed = subprocess.run(command, cwd=str(repo_root), text=True, capture_output=True, timeout=60, check=False)
    except Exception as exc:
        return {"status": "skipped", "reason": repr(exc)}
    return {
        "status": "ok" if completed.returncode == 0 else "failed",
        "exit_code": completed.returncode,
        "stdout": completed.stdout[-4000:],
        "stderr": completed.stderr[-4000:],
        "failures": verify_failure_lines(completed.stdout),
        "warnings": verify_warning_lines(completed.stdout),
    }


def verify_failure_lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip().startswith("[NG]")]


def verify_warning_lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip().startswith("[WARN]")]


def verify_release_gate(app_id: str, before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    before_failures = set(str(item) for item in before.get("failures") or [])
    after_failures = set(str(item) for item in after.get("failures") or [])
    new_failures = sorted(after_failures - before_failures)
    app_failures = sorted(item for item in after_failures if verify_line_mentions_app(item, app_id))
    rollback_failures = sorted(set(new_failures + app_failures))
    pre_existing_failures = sorted(after_failures & before_failures)
    rollback_required = bool(rollback_failures)
    return {
        "rollback_required": rollback_required,
        "global_warning": after.get("status") == "failed" and not rollback_required,
        "verify_release_before": before.get("status", "unknown"),
        "verify_release_after": after.get("status", "unknown"),
        "new_failures": new_failures,
        "pre_existing_failures": pre_existing_failures,
        "app_failures": app_failures,
        "rollback_failures": rollback_failures,
        "rollback_reason": "; ".join(rollback_failures[:5]) if rollback_required else "",
    }


def verify_line_mentions_app(line: str, app_id: str) -> bool:
    text = line.strip()
    prefix = f"[NG] {app_id} "
    return text == f"[NG] {app_id}" or text.startswith(prefix)


def targeted_approval_verification(repo_root: Path, app_id: str, manifest_entry: dict[str, Any], package_path: Path | None) -> dict[str, Any]:
    failures: list[str] = []
    checks: list[str] = []
    app_dir = repo_root / "apps" / app_id
    app_yaml = app_dir / "app.yaml"
    if manifest_entry.get("enabled") is True:
        checks.append("manifest enabled=true")
    else:
        failures.append("release/app_manifest.json did not keep enabled=true for this app")
    if app_yaml.is_file():
        checks.append("app.yaml exists")
    else:
        failures.append(f"app.yaml is missing: {app_yaml}")

    run_entry = ""
    if app_yaml.is_file():
        try:
            run_entry = normalize_app_relative_entry(load_run_entry(repo_root, app_id), app_dir, "run.entry")
            checks.append(f"app.yaml parses; run.entry={run_entry}")
        except Exception as exc:
            failures.append(f"app.yaml parse failed: {exc}")
    if run_entry:
        entry_path = app_relative_path(app_dir, run_entry)
        if entry_path.is_file():
            checks.append("run.entry exists")
        else:
            failures.append(f"run.entry is missing: {entry_path}")

    display_icon = ""
    requirements_lock = ""
    if app_yaml.is_file():
        try:
            display_icon = require_app_yaml_file(app_dir, "display", "icon", "display.icon")
            checks.append(f"display.icon exists: {display_icon}")
        except Exception as exc:
            failures.append(f"display.icon validation failed: {exc}")
        try:
            requirements_lock = app_pack_requirements_lock_entry(app_dir) or ""
            if requirements_lock:
                lock_path = app_relative_path(app_dir, requirements_lock)
                if lock_path.is_file():
                    checks.append(f"runtime.requirements_lock exists: {requirements_lock}")
                else:
                    failures.append(f"runtime.requirements_lock is missing: {lock_path}")
        except Exception as exc:
            failures.append(f"runtime.requirements_lock validation failed: {exc}")

    marker = app_dir / "bin" / "BUILD_REQUIRED.txt"
    if marker.exists():
        failures.append(f"BUILD_REQUIRED.txt remains: {marker}")
    else:
        checks.append("BUILD_REQUIRED.txt absent")

    if package_path and package_path.is_file():
        checks.append(f"app pack exists: {package_path}")
        try:
            with zipfile.ZipFile(package_path) as archive:
                names = {name.replace("\\", "/") for name in archive.namelist()}
            if f"{app_id}/app.yaml" in names and f"{app_id}/pack_manifest.json" in names:
                checks.append("app pack contains app.yaml and pack_manifest.json")
            else:
                failures.append("app pack does not contain expected app.yaml and pack_manifest.json")
            if run_entry:
                expected_run_entry = f"{app_id}/{run_entry}"
                if expected_run_entry in names:
                    checks.append("app pack contains run.entry")
                else:
                    failures.append(f"app pack does not contain run.entry: {expected_run_entry}")
            if display_icon:
                expected_icon = f"{app_id}/{display_icon}"
                if expected_icon in names:
                    checks.append("app pack contains display.icon")
                else:
                    failures.append(f"app pack does not contain display.icon: {expected_icon}")
            if requirements_lock:
                expected_lock = f"{app_id}/{requirements_lock}"
                if expected_lock in names:
                    checks.append("app pack contains runtime.requirements_lock")
                else:
                    failures.append(f"app pack does not contain runtime.requirements_lock: {expected_lock}")
        except Exception as exc:
            failures.append(f"app pack could not be inspected: {exc}")
    else:
        failures.append(f"app pack is missing: {package_path}")

    return {
        "status": "failed" if failures else "ok",
        "checks": checks,
        "failures": failures,
    }


def load_run_entry(repo_root: Path, app_id: str) -> str:
    runner_path = repo_root / "runner"
    if runner_path.is_dir() and str(runner_path) not in sys.path:
        sys.path.insert(0, str(runner_path))
    try:
        from toolhub_runner.manifest import load_app_manifest

        manifest = load_app_manifest(repo_root, app_id)
        return manifest.run.entry
    except ModuleNotFoundError:
        entry = app_yaml_run_entry(repo_root / "apps" / app_id / "app.yaml")
        if entry:
            return entry
        raise


def approval_record(
    status: str,
    app_id: str,
    manifest_entry: dict[str, Any],
    package_path: Path | None,
    execution_result: dict[str, Any] | None,
    verify_result: dict[str, Any],
    failures: list[str],
    verify_before: dict[str, Any] | None = None,
    targeted_result: dict[str, Any] | None = None,
    verify_gate: dict[str, Any] | None = None,
    manifest_enabled_after: bool | None = None,
) -> str:
    verify_before = verify_before or {"status": "not_run"}
    targeted_result = targeted_result or {"status": "not_run"}
    verify_gate = verify_gate or {}
    return "\n".join(
        [
            "# Approval Record",
            "",
            f"- status: `{status}`",
            f"- recorded_at: `{now_iso()}`",
            f"- app_id: `{app_id}`",
            f"- version: `{manifest_entry.get('version')}`",
            f"- enabled: `{manifest_entry.get('enabled')}`",
            f"- manifest_enabled_after: `{manifest_enabled_after}`",
            f"- package: `{package_path}`",
            f"- targeted_verification_status: `{targeted_result.get('status')}`",
            f"- verify_release_before: `{verify_before.get('status')}`",
            f"- verify_release_after: `{verify_result.get('status')}`",
            f"- rollback_reason: `{verify_gate.get('rollback_reason') or ''}`",
            "",
            "## Failures",
            "",
            *(f"- {failure}" for failure in failures),
            "",
            "## Targeted Verification",
            "",
            "```json",
            json.dumps(targeted_result, ensure_ascii=False, indent=2),
            "```",
            "",
            "## Verify Release Gate",
            "",
            "```json",
            json.dumps(verify_gate, ensure_ascii=False, indent=2),
            "```",
            "",
            "## execution_test_result.json",
            "",
            "```json",
            json.dumps(execution_result or {}, ensure_ascii=False, indent=2),
            "```",
            "",
            "## verify_release.ps1 before",
            "",
            "```json",
            json.dumps(verify_before, ensure_ascii=False, indent=2),
            "```",
            "",
            "## verify_release.ps1",
            "",
            "```json",
            json.dumps(verify_result, ensure_ascii=False, indent=2),
            "```",
            "",
        ]
    )


def write_mirror_record(repo_root: Path, app_id: str, record: str, package_path: Path | None) -> None:
    mirror = find_output_mirror(repo_root, app_id)
    if not mirror:
        return
    write_text(mirror / "approval_record.md", record)
    if package_path and package_path.is_file():
        pack_dir = mirror / "app_pack"
        pack_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(package_path, pack_dir / package_path.name)


def find_output_mirror(repo_root: Path, app_id: str) -> Path | None:
    app_yaml = repo_root / "apps" / app_id / "app.yaml"
    if not app_yaml.is_file():
        return None
    for line in app_yaml.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.strip().startswith("output_mirror:"):
            value = line.split(":", 1)[1].strip().strip('"').strip("'")
            if value:
                return Path(value)
    return None
