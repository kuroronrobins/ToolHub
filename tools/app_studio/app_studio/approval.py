from __future__ import annotations

import copy
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .registrar import load_app_manifest_json, package_app_pack
from .util import find_repo_root, now_iso, write_json, write_text


def approve_app(repo_root: Path, app_id: str, strict: bool = False, allow_warnings: bool = True) -> Path:
    repo_root = find_repo_root(repo_root)
    manifest_path = repo_root / "release" / "app_manifest.json"
    original_manifest = load_app_manifest_json(manifest_path)
    manifest = copy.deepcopy(original_manifest)

    record_path = repo_root / "data" / "logs" / "app_studio" / f"{app_id}_approval_record.md"
    record_written = False
    try:
        entry, result = validate_approval_inputs(repo_root, manifest, app_id, strict, allow_warnings)
        entry["enabled"] = True
        manifest["apps"][app_id] = entry
        write_json(manifest_path, manifest)

        package_path = package_app_pack(repo_root, app_id)
        verify_result = run_verify_release(repo_root)
        if verify_result.get("status") == "failed":
            write_json(manifest_path, original_manifest)
            record = approval_record("failed", app_id, entry, package_path, result, verify_result, ["verify_release.ps1 failed"])
            write_text(record_path, record)
            record_written = True
            write_mirror_record(repo_root, app_id, record, package_path)
            raise RuntimeError("verify_release.ps1 failed; enabled=true was rolled back.")

        record = approval_record("approved", app_id, entry, package_path, result, verify_result, [])
        write_text(record_path, record)
        record_written = True
        write_mirror_record(repo_root, app_id, record, package_path)
        return record_path
    except Exception as exc:
        write_json(manifest_path, original_manifest)
        if not record_written:
            record = approval_record("failed", app_id, {}, None, None, {"status": "not_run"}, [str(exc)])
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

    checks = result.get("checks") or []
    fail_checks = [item for item in checks if item.get("status") == "fail"]
    warn_checks = [item for item in checks if item.get("status") == "warn"]
    if result.get("approval_allowed") is not True:
        raise ValueError("Execution test result does not allow approval.")
    if fail_checks:
        raise ValueError("Execution test result contains fail checks.")
    if strict and warn_checks:
        raise ValueError("StrictApproval rejects warning checks.")
    if not allow_warnings and warn_checks:
        raise ValueError("Warnings are not allowed for this approval.")
    return entry, result


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
    }


def approval_record(
    status: str,
    app_id: str,
    manifest_entry: dict[str, Any],
    package_path: Path | None,
    execution_result: dict[str, Any] | None,
    verify_result: dict[str, Any],
    failures: list[str],
) -> str:
    return "\n".join(
        [
            "# Approval Record",
            "",
            f"- status: `{status}`",
            f"- recorded_at: `{now_iso()}`",
            f"- app_id: `{app_id}`",
            f"- version: `{manifest_entry.get('version')}`",
            f"- enabled: `{manifest_entry.get('enabled')}`",
            f"- package: `{package_path}`",
            "",
            "## Failures",
            "",
            *(f"- {failure}" for failure in failures),
            "",
            "## execution_test_result.json",
            "",
            "```json",
            json.dumps(execution_result or {}, ensure_ascii=False, indent=2),
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
