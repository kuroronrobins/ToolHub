from __future__ import annotations

import json
import shutil
import zipfile
from pathlib import Path
from typing import Any

from .exporter import copy_pack_to_output
from .models import BuildPlan, StudioContext
from .util import assert_within, file_sha256, reset_directory, timestamp, write_json, write_text


def apply_registration(context: StudioContext, plan: BuildPlan, final_app_dir: Path, output_dir: Path) -> Path:
    backup_existing(context.repo_root, context.app_id)
    apps_dir = context.repo_root / "apps"
    target = apps_dir / context.app_id
    assert_within(target, apps_dir, "app registration target")
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(final_app_dir, target)

    manifest_path = context.repo_root / "release" / "app_manifest.json"
    manifest = load_app_manifest_json(manifest_path)
    manifest.setdefault("schema_version", 1)
    manifest.setdefault("channel", "stable")
    manifest.setdefault("apps", {})
    manifest["apps"][context.app_id] = {
        "version": context.version,
        "package": f"app_packs/{context.app_id}-{context.version}.zip",
        "sha256": "",
        "required_core": ">=0.1.0",
        "required_runner": ">=0.1.0",
        "required_runtime": plan.required_runtime,
        "enabled": False,
    }
    write_json(manifest_path, manifest)
    package_path = package_app_pack(context.repo_root, context.app_id)
    copy_pack_to_output(package_path, output_dir)
    return package_path


def backup_existing(repo_root: Path, app_id: str) -> Path | None:
    app_dir = repo_root / "apps" / app_id
    manifest_path = repo_root / "release" / "app_manifest.json"
    manifest = load_app_manifest_json(manifest_path) if manifest_path.is_file() else {"apps": {}}
    app_exists = app_dir.exists()
    manifest_exists = app_id in (manifest.get("apps") or {})
    if not app_exists and not manifest_exists:
        return None

    backup_root = repo_root / "backups" / "app_studio" / timestamp() / app_id
    assert_within(backup_root, repo_root / "backups", "backup target")
    backup_root.mkdir(parents=True, exist_ok=True)
    if app_exists:
        shutil.copytree(app_dir, backup_root / "app")
    if manifest_path.is_file():
        shutil.copy2(manifest_path, backup_root / "app_manifest.json")
    return backup_root


def load_app_manifest_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"schema_version": 1, "channel": "stable", "apps": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def package_app_pack(repo_root: Path, app_id: str) -> Path:
    manifest_path = repo_root / "release" / "app_manifest.json"
    manifest = load_app_manifest_json(manifest_path)
    app_entry = manifest.get("apps", {}).get(app_id)
    if not isinstance(app_entry, dict):
        raise ValueError(f"App is not listed in release/app_manifest.json: {app_id}")

    version = str(app_entry.get("version") or "0.1.0")
    app_dir = repo_root / "apps" / app_id
    if not app_dir.is_dir():
        raise FileNotFoundError(f"App directory is missing: {app_dir}")
    for required in ("app.yaml", "README.md", "requirements.txt", "icon.svg"):
        if not (app_dir / required).is_file():
            raise FileNotFoundError(f"Required app file is missing: {app_dir / required}")

    staging_base = repo_root / "release" / "staging" / "app_studio_pack"
    reset_directory(staging_base, repo_root / "release" / "staging")
    stage_app_dir = staging_base / app_id
    shutil.copytree(app_dir, stage_app_dir)
    remove_generated_cache(stage_app_dir)

    pack_manifest = {
        "schema_version": 1,
        "app_id": app_id,
        "version": version,
        "required_core": app_entry.get("required_core"),
        "required_runner": app_entry.get("required_runner"),
        "required_runtime": app_entry.get("required_runtime"),
        "package_sha256": "",
    }
    write_json(stage_app_dir / "pack_manifest.json", pack_manifest)

    app_packs_dir = repo_root / "release" / "app_packs"
    app_packs_dir.mkdir(parents=True, exist_ok=True)
    package_path = app_packs_dir / f"{app_id}-{version}.zip"
    assert_within(package_path, app_packs_dir, "app pack")
    if package_path.exists():
        package_path.unlink()

    with zipfile.ZipFile(package_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for file in sorted(stage_app_dir.rglob("*")):
            if file.is_file():
                archive.write(file, file.relative_to(staging_base).as_posix())

    app_entry["package"] = f"app_packs/{app_id}-{version}.zip"
    app_entry["sha256"] = file_sha256(package_path)
    manifest["apps"][app_id] = app_entry
    write_json(manifest_path, manifest)
    return package_path


def remove_generated_cache(path: Path) -> None:
    for cache_dir in path.rglob("__pycache__"):
        if cache_dir.is_dir():
            shutil.rmtree(cache_dir)
    for file in path.rglob("*"):
        if file.is_file() and file.suffix.lower() in {".pyc", ".pyo"}:
            file.unlink()

