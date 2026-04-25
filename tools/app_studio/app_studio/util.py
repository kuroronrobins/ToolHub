from __future__ import annotations

import hashlib
import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any


def find_repo_root(start: Path) -> Path:
    current = start.resolve()
    if current.is_file():
        current = current.parent
    for candidate in (current, *current.parents):
        if (candidate / "apps").is_dir() and (candidate / "release").is_dir() and (candidate / "runner").is_dir():
            return candidate
    raise FileNotFoundError("ToolHub repository root was not found.")


def slugify_app_id(value: str) -> str:
    text = value.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    if not text:
        text = "imported_app"
    if text[0].isdigit():
        text = f"app_{text}"
    return text


def display_name_from_app_id(app_id: str) -> str:
    return " ".join(part.capitalize() for part in app_id.split("_") if part) or app_id


def default_app_id_for_entry(entry: Path) -> str:
    parent_name = entry.parent.name
    stem = entry.stem
    generic_names = {"main", "app", "run", "start", "__main__"}
    base = parent_name if stem.lower() in generic_names and parent_name else stem
    return slugify_app_id(base)


def resolve_existing_file(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"Entry file was not found: {resolved}")
    return resolved


def is_relative_to(path: Path, base: Path) -> bool:
    try:
        path.resolve().relative_to(base.resolve())
        return True
    except ValueError:
        return False


def assert_within(path: Path, base: Path, label: str) -> Path:
    resolved_path = path.resolve()
    resolved_base = base.resolve()
    if not is_relative_to(resolved_path, resolved_base):
        raise ValueError(f"Refusing {label} outside expected directory: {resolved_path}")
    return resolved_path


def output_dir_for_entry(entry: Path, app_id: str) -> Path:
    safe_app_id = slugify_app_id(app_id)
    return entry.parent / "ToolHub_AppStudio_Output" / safe_app_id


def reset_output_dir(entry: Path, app_id: str) -> Path:
    base = (entry.parent / "ToolHub_AppStudio_Output").resolve()
    output_dir = output_dir_for_entry(entry, app_id).resolve()
    assert_within(output_dir, base, "output directory")
    assert_within(base, entry.parent, "output base")
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def reset_directory(path: Path, allowed_base: Path) -> None:
    resolved = assert_within(path, allowed_base, "directory reset")
    if resolved.exists():
        shutil.rmtree(resolved)
    resolved.mkdir(parents=True, exist_ok=True)


def read_text_if_exists(path: Path) -> str:
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def write_json(path: Path, payload: Any) -> None:
    write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def copy_file_preserving_root(source: Path, source_root: Path, destination_root: Path) -> Path:
    relative = source.relative_to(source_root)
    destination = destination_root / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return destination


def yaml_scalar(value: str | None) -> str:
    if value is None:
        return "null"
    text = str(value)
    if text == "":
        return '""'
    if re.fullmatch(r"[A-Za-z0-9_./\\:>=<+\- ]+", text) and not text.startswith((" ", "-", "?", "@", "&", "*", "!", "%")):
        return text
    return json.dumps(text, ensure_ascii=False)


def markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(cell.replace("\n", " ") for cell in row) + " |")
    return "\n".join(lines)

