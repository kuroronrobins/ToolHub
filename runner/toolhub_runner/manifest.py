from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Tuple


SUPPORTED_RUNNERS = {"python", "cli", "exe", "playwright_python", "python_app_env", "python_shared_env"}
SUPPORTED_MODES = {"gui", "cli", "background"}


class ManifestError(ValueError):
    pass


@dataclass
class Display:
    icon: str
    short_description: str
    categories: List[str]


@dataclass
class Detail:
    description: str
    use_cases: List[str] = field(default_factory=list)
    inputs: List[str] = field(default_factory=list)
    outputs: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)


@dataclass
class Search:
    keywords: List[str] = field(default_factory=list)
    examples: List[str] = field(default_factory=list)


@dataclass
class Run:
    runner: str
    entry: str
    mode: str
    env_id: str = ""
    show_terminal: bool = False


@dataclass
class Admin:
    version: str = ""
    owner: str = ""
    requirements: str = ""
    log_dir: str = "logs"


@dataclass
class AppManifest:
    id: str
    name: str
    app_dir: Path
    display: Display
    detail: Detail
    search: Search
    run: Run
    admin: Admin


def load_app_manifest(project_root: Path, app_id: str) -> AppManifest:
    app_dir = project_root / "apps" / app_id
    manifest_path = app_dir / "app.yaml"
    if not manifest_path.is_file():
        raise ManifestError(f"app.yaml not found: {manifest_path}")
    data = load_yaml_mapping(manifest_path)
    return manifest_from_dict(data, app_dir)


def load_yaml_mapping(path: Path) -> Dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore
    except Exception:
        data = parse_basic_yaml(text)
    else:
        data = yaml.safe_load(text)

    if not isinstance(data, dict):
        raise ManifestError("app.yaml root must be a mapping")
    return data


def manifest_from_dict(data: Dict[str, Any], app_dir: Path) -> AppManifest:
    try:
        app_id = require_str(data, "id")
        name = require_str(data, "name")
        display_data = require_map(data, "display")
        detail_data = require_map(data, "detail")
        run_data = require_map(data, "run")
    except ManifestError:
        raise
    except Exception as exc:
        raise ManifestError(str(exc)) from exc

    display = Display(
        icon=require_str(display_data, "icon"),
        short_description=require_str(display_data, "short_description"),
        categories=require_str_list(display_data, "categories"),
    )
    detail = Detail(
        description=require_str(detail_data, "description"),
        use_cases=optional_str_list(detail_data, "use_cases"),
        inputs=optional_str_list(detail_data, "inputs"),
        outputs=optional_str_list(detail_data, "outputs"),
        notes=optional_str_list(detail_data, "notes"),
    )
    search_data = data.get("search") or {}
    if not isinstance(search_data, dict):
        raise ManifestError("search must be a mapping")
    search = Search(
        keywords=optional_str_list(search_data, "keywords"),
        examples=optional_str_list(search_data, "examples"),
    )
    run = Run(
        runner=require_str(run_data, "runner"),
        entry=require_str(run_data, "entry"),
        mode=require_str(run_data, "mode"),
        env_id=str(run_data.get("env_id") or ""),
        show_terminal=optional_bool(run_data, "show_terminal"),
    )
    validate_run(run)

    admin_data = data.get("admin") or {}
    if not isinstance(admin_data, dict):
        raise ManifestError("admin must be a mapping")
    admin = Admin(
        version=str(admin_data.get("version", "")),
        owner=str(admin_data.get("owner", "")),
        requirements=str(admin_data.get("requirements", "")),
        log_dir=str(admin_data.get("log_dir", "logs")),
    )

    return AppManifest(
        id=app_id,
        name=name,
        app_dir=app_dir,
        display=display,
        detail=detail,
        search=search,
        run=run,
        admin=admin,
    )


def require_map(data: Dict[str, Any], key: str) -> Dict[str, Any]:
    value = data.get(key)
    if not isinstance(value, dict):
        raise ManifestError(f"{key} is required and must be a mapping")
    return value


def require_str(data: Dict[str, Any], key: str) -> str:
    value = data.get(key)
    if value is None or str(value).strip() == "":
        raise ManifestError(f"{key} is required")
    return str(value)


def require_str_list(data: Dict[str, Any], key: str) -> List[str]:
    value = data.get(key)
    if not isinstance(value, list) or not value:
        raise ManifestError(f"{key} is required and must be a non-empty list")
    return [str(item) for item in value]


def optional_str_list(data: Dict[str, Any], key: str) -> List[str]:
    value = data.get(key, [])
    if value is None:
        return []
    if not isinstance(value, list):
        raise ManifestError(f"{key} must be a list")
    return [str(item) for item in value]


def optional_bool(data: Dict[str, Any], key: str) -> bool:
    value = data.get(key, False)
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "yes", "1", "on"}:
            return True
        if normalized in {"false", "no", "0", "off", ""}:
            return False
    raise ManifestError(f"{key} must be a boolean")


def validate_run(run: Run) -> None:
    if run.runner not in SUPPORTED_RUNNERS:
        raise ManifestError(f"unsupported runner: {run.runner}")
    if run.mode not in SUPPORTED_MODES:
        raise ManifestError(f"unsupported mode: {run.mode}")


def parse_basic_yaml(text: str) -> Dict[str, Any]:
    lines = text.splitlines()
    parsed, index = _parse_block(lines, 0, 0)
    _ = index
    if not isinstance(parsed, dict):
        raise ManifestError("basic YAML parser expected a mapping")
    return parsed


def _next_content_line(lines: List[str], start: int) -> Tuple[int, str] | None:
    for index in range(start, len(lines)):
        stripped = lines[index].strip()
        if stripped and not stripped.startswith("#"):
            return index, lines[index]
    return None


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _parse_block(lines: List[str], start: int, indent: int) -> Tuple[Any, int]:
    next_line = _next_content_line(lines, start)
    if next_line is None:
        return {}, start
    _, first = next_line
    is_list = _indent(first) == indent and first.lstrip().startswith("- ")
    return _parse_list(lines, start, indent) if is_list else _parse_mapping(lines, start, indent)


def _parse_mapping(lines: List[str], start: int, indent: int) -> Tuple[Dict[str, Any], int]:
    result: Dict[str, Any] = {}
    index = start
    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            index += 1
            continue

        current_indent = _indent(line)
        if current_indent < indent:
            break
        if current_indent > indent:
            raise ManifestError(f"unexpected indentation near line {index + 1}")
        if stripped.startswith("- "):
            break
        if ":" not in stripped:
            raise ManifestError(f"expected key near line {index + 1}")

        key, raw_value = stripped.split(":", 1)
        key = key.strip()
        raw_value = raw_value.strip()
        if raw_value in {">", "|"}:
            value, index = _parse_block_scalar(lines, index + 1, current_indent, raw_value)
        elif raw_value == "":
            next_line = _next_content_line(lines, index + 1)
            if next_line is None or _indent(next_line[1]) <= current_indent:
                value = {}
                index += 1
            else:
                value, index = _parse_block(lines, index + 1, _indent(next_line[1]))
        else:
            value = _parse_scalar(raw_value)
            index += 1
        result[key] = value
    return result, index


def _parse_list(lines: List[str], start: int, indent: int) -> Tuple[List[Any], int]:
    result: List[Any] = []
    index = start
    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            index += 1
            continue

        current_indent = _indent(line)
        if current_indent < indent:
            break
        if current_indent > indent:
            raise ManifestError(f"unexpected indentation near line {index + 1}")
        if not stripped.startswith("- "):
            break

        raw_value = stripped[2:].strip()
        if raw_value == "":
            next_line = _next_content_line(lines, index + 1)
            if next_line is None or _indent(next_line[1]) <= current_indent:
                result.append({})
                index += 1
            else:
                value, index = _parse_block(lines, index + 1, _indent(next_line[1]))
                result.append(value)
        else:
            result.append(_parse_scalar(raw_value))
            index += 1
    return result, index


def _parse_block_scalar(lines: List[str], start: int, parent_indent: int, marker: str) -> Tuple[str, int]:
    collected: List[str] = []
    index = start
    while index < len(lines):
        line = lines[index]
        if not line.strip():
            collected.append("")
            index += 1
            continue
        current_indent = _indent(line)
        if current_indent <= parent_indent:
            break
        collected.append(line[parent_indent + 2 :])
        index += 1
    if marker == "|":
        return "\n".join(collected).strip(), index
    return " ".join(part.strip() for part in collected if part.strip()).strip(), index


def _parse_scalar(value: str) -> Any:
    if value in {"[]", ""}:
        return []
    if value in {"{}", "null", "~"}:
        return None
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    return value

