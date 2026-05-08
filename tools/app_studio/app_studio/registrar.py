from __future__ import annotations

import json
import shutil
import zipfile
from pathlib import Path
from pathlib import PurePosixPath, PureWindowsPath
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
    manifest["apps"][context.app_id] = manifest_entry_from_app_source(target, context, plan)
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


def manifest_entry_from_app_source(app_dir: Path, context: StudioContext, plan: BuildPlan) -> dict[str, Any]:
    app_yaml = app_dir / "app.yaml"
    text = app_yaml.read_text(encoding="utf-8") if app_yaml.is_file() else ""
    version = yaml_section_scalar(text, "admin", "version") or context.version
    required_runtime = yaml_section_scalar(text, "runtime", "required_runtime")
    if required_runtime is None:
        required_runtime = plan.required_runtime
    return {
        "version": version,
        "package": f"app_packs/{context.app_id}-{version}.zip",
        "sha256": "",
        "required_core": ">=0.1.0",
        "required_runner": ">=0.1.0",
        "required_runtime": required_runtime,
        "enabled": False,
    }


def yaml_section_scalar(text: str, section: str, key: str) -> str | None:
    in_section = False
    section_indent = -1
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(line) - len(line.lstrip(" "))
        if not in_section:
            if indent == 0 and stripped == f"{section}:":
                in_section = True
                section_indent = indent
            continue
        if indent <= section_indent:
            break
        if stripped.startswith(f"{key}:"):
            value = stripped.split(":", 1)[1].strip()
            return normalize_yaml_scalar(value)
    return None


def normalize_yaml_scalar(value: str) -> str | None:
    text = value.strip()
    if " #" in text:
        text = text.split(" #", 1)[0].strip()
    if len(text) >= 2 and ((text[0] == text[-1] == '"') or (text[0] == text[-1] == "'")):
        text = text[1:-1]
    if text in {"", "null", "~"}:
        return None
    return text


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
    for required in ("app.yaml", "README.md", "requirements.txt"):
        if not (app_dir / required).is_file():
            raise FileNotFoundError(f"Required app file is missing: {app_dir / required}")
    if not (app_dir / "icon.png").is_file() and not (app_dir / "icon.svg").is_file():
        raise FileNotFoundError(f"Required app icon is missing: {app_dir / 'icon.png'} or {app_dir / 'icon.svg'}")
    run_entry = require_app_yaml_file(app_dir, "run", "entry", "run.entry")
    display_icon = require_app_yaml_file(app_dir, "display", "icon", "display.icon")

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

    with zipfile.ZipFile(package_path) as archive:
        names = {name.replace("\\", "/") for name in archive.namelist()}
    required_entries = {
        f"{app_id}/app.yaml",
        f"{app_id}/pack_manifest.json",
        f"{app_id}/README.md",
        f"{app_id}/requirements.txt",
        f"{app_id}/{display_icon}",
        f"{app_id}/{run_entry}",
    }
    missing_entries = sorted(required_entries - names)
    if missing_entries:
        raise FileNotFoundError(f"App Pack is missing required entries: {', '.join(missing_entries)}")

    app_entry["package"] = f"app_packs/{app_id}-{version}.zip"
    app_entry["sha256"] = file_sha256(package_path)
    manifest["apps"][app_id] = app_entry
    write_json(manifest_path, manifest)
    return package_path


def require_app_yaml_file(app_dir: Path, section: str, key: str, label: str) -> str:
    app_yaml = app_dir / "app.yaml"
    text = app_yaml.read_text(encoding="utf-8")
    value = yaml_section_scalar(text, section, key)
    relative = normalize_app_relative_entry(value, app_dir, label)
    path = app_relative_path(app_dir, relative)
    if not path.is_file():
        raise FileNotFoundError(f"Required app {label} file is missing: {path}")
    return relative


def normalize_app_relative_entry(value: str | None, app_dir: Path | None = None, label: str = "app path") -> str:
    if value is None or not str(value).strip():
        raise ValueError(f"{label} is missing.")
    raw = str(value).strip().replace("\\", "/")
    if PurePosixPath(raw).is_absolute() or PureWindowsPath(raw).is_absolute():
        raise ValueError(f"{label} must be a relative path inside the app directory: {value}")

    parts: list[str] = []
    for part in raw.split("/"):
        if part in {"", "."}:
            continue
        if part == "..":
            raise ValueError(f"{label} must stay inside the app directory: {value}")
        parts.append(part)
    if not parts:
        raise ValueError(f"{label} is missing.")

    relative = "/".join(parts)
    if app_dir is not None:
        app_relative_path(app_dir, relative)
    return relative


def app_relative_path(app_dir: Path, relative: str) -> Path:
    root = app_dir.resolve()
    path = (app_dir / Path(*relative.split("/"))).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"app path must stay inside the app directory: {relative}") from exc
    return path


def remove_generated_cache(path: Path) -> None:
    for cache_dir in path.rglob("__pycache__"):
        if cache_dir.is_dir():
            shutil.rmtree(cache_dir)
    for file in path.rglob("*"):
        if file.is_file() and file.suffix.lower() in {".pyc", ".pyo"}:
            file.unlink()
