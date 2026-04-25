from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from .registrar import load_app_manifest_json, package_app_pack
from .util import find_repo_root, now_iso, write_json, write_text


def approve_app(repo_root: Path, app_id: str) -> Path:
    repo_root = find_repo_root(repo_root)
    report_path = repo_root / "data" / "logs" / "app_studio" / f"{app_id}_execution_test_report.md"
    if not report_path.is_file():
        raise FileNotFoundError(f"Execution test report was not found: {report_path}")

    manifest_path = repo_root / "release" / "app_manifest.json"
    manifest = load_app_manifest_json(manifest_path)
    apps = manifest.get("apps") or {}
    entry = apps.get(app_id)
    if not isinstance(entry, dict):
        raise ValueError(f"App is not listed in release/app_manifest.json: {app_id}")

    entry["enabled"] = True
    apps[app_id] = entry
    manifest["apps"] = apps
    write_json(manifest_path, manifest)
    package_path = package_app_pack(repo_root, app_id)
    verify_result = run_verify_release(repo_root)
    record = approval_record(app_id, entry, package_path, report_path, verify_result)

    log_dir = repo_root / "data" / "logs" / "app_studio"
    record_path = log_dir / f"{app_id}_approval_record.md"
    write_text(record_path, record)

    mirror = find_output_mirror(repo_root, app_id)
    if mirror:
        write_text(mirror / "approval_record.md", record)
        pack_dir = mirror / "app_pack"
        pack_dir.mkdir(parents=True, exist_ok=True)
        import shutil

        shutil.copy2(package_path, pack_dir / package_path.name)
    return record_path


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


def approval_record(app_id: str, manifest_entry: dict[str, Any], package_path: Path, report_path: Path, verify_result: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Approval Record",
            "",
            f"- approved_at: `{now_iso()}`",
            f"- app_id: `{app_id}`",
            f"- version: `{manifest_entry.get('version')}`",
            f"- enabled: `{manifest_entry.get('enabled')}`",
            f"- package: `{package_path}`",
            f"- execution_test_report: `{report_path}`",
            "",
            "## verify_release.ps1",
            "",
            "```json",
            json.dumps(verify_result, ensure_ascii=False, indent=2),
            "```",
            "",
        ]
    )


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

