from __future__ import annotations

from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any


APP_PACK_REQUIRED_APP_FILES = ("app.yaml", "README.md", "requirements.txt")


def normalize_yaml_scalar(value: str) -> str | None:
    text = value.strip()
    if " #" in text:
        text = text.split(" #", 1)[0].strip()
    if len(text) >= 2 and ((text[0] == text[-1] == '"') or (text[0] == text[-1] == "'")):
        text = text[1:-1]
    if text in {"", "null", "~"}:
        return None
    return text


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


def normalize_policy_value(value: str | None) -> str:
    return (value or "").strip().lower()


def is_frozen_folder_app(app_yaml_text: str) -> bool:
    distribution_mode = normalize_policy_value(yaml_section_scalar(app_yaml_text, "runtime", "distribution_mode"))
    build_mode = normalize_policy_value(yaml_section_scalar(app_yaml_text, "build", "build_mode"))
    return distribution_mode in {"frozen_folder", "frozen-folder"} or build_mode in {"frozen_folder", "frozen-folder"}


def app_studio_frozen_folder_manifest(text: str) -> bool:
    return is_frozen_folder_app(text)


def normalize_app_relative_path(
    value: str | None,
    app_dir: Path | None = None,
    label: str = "app path",
) -> str:
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


def normalize_app_relative_entry(
    value: str | None,
    app_dir: Path | None = None,
    label: str = "app path",
) -> str:
    return normalize_app_relative_path(value, app_dir=app_dir, label=label)


def app_relative_path(app_dir: Path, relative: str) -> Path:
    root = app_dir.resolve()
    path = (app_dir / Path(*relative.split("/"))).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"app path must stay inside the app directory: {relative}") from exc
    return path


def app_yaml_run_entry(app_yaml_text: str, app_dir: Path | None = None) -> str | None:
    value = yaml_section_scalar(app_yaml_text, "run", "entry")
    if value is None:
        return None
    return normalize_app_relative_path(value, app_dir=app_dir, label="run.entry")


def app_yaml_display_icon_entry(app_yaml_text: str, app_dir: Path | None = None) -> str | None:
    value = yaml_section_scalar(app_yaml_text, "display", "icon")
    if value is None:
        return None
    return normalize_app_relative_path(value, app_dir=app_dir, label="display.icon")


def runtime_requirements_lock_entry(app_yaml_text: str, app_dir: Path | None = None) -> str | None:
    declared = yaml_section_scalar(app_yaml_text, "runtime", "requirements_lock")
    if declared:
        return normalize_app_relative_path(declared, app_dir=app_dir, label="runtime.requirements_lock")
    if is_frozen_folder_app(app_yaml_text):
        return "requirements.lock"
    return None


def app_pack_requirements_lock_entry(app_dir: Path) -> str | None:
    app_yaml = app_dir / "app.yaml"
    text = app_yaml.read_text(encoding="utf-8")
    return runtime_requirements_lock_entry(text, app_dir=app_dir)


def app_pack_required_entries(
    app_id: str,
    *,
    run_entry: str,
    display_icon: str,
    requirements_lock: str | None = None,
    include_pack_manifest: bool = True,
) -> set[str]:
    entries = {
        f"{app_id}/app.yaml",
        f"{app_id}/README.md",
        f"{app_id}/requirements.txt",
        f"{app_id}/{display_icon}",
        f"{app_id}/{run_entry}",
    }
    if include_pack_manifest:
        entries.add(f"{app_id}/pack_manifest.json")
    if requirements_lock:
        entries.add(f"{app_id}/{requirements_lock}")
    return entries


def app_pack_contract_summary(app_id: str, app_yaml_text: str, app_dir: Path | None = None) -> dict[str, Any]:
    run_entry = app_yaml_run_entry(app_yaml_text, app_dir=app_dir)
    display_icon = app_yaml_display_icon_entry(app_yaml_text, app_dir=app_dir)
    requirements_lock = runtime_requirements_lock_entry(app_yaml_text, app_dir=app_dir)
    required_entries: list[str] = []
    if run_entry and display_icon:
        required_entries = sorted(
            app_pack_required_entries(
                app_id,
                run_entry=run_entry,
                display_icon=display_icon,
                requirements_lock=requirements_lock,
            )
        )
    return {
        "app_id": app_id,
        "run_entry": run_entry,
        "display_icon": display_icon,
        "requirements_lock": requirements_lock,
        "is_frozen_folder": is_frozen_folder_app(app_yaml_text),
        "required_entries": required_entries,
    }
