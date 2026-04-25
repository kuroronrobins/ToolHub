from __future__ import annotations

import ast
import fnmatch
from pathlib import Path

from .models import FileRecord, SourceInventory, StudioContext
from .util import markdown_table


EXCLUDED_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    ".pytest_cache",
    "node_modules",
    "dist",
    "build",
    "toolhub_appstudio_output",
}
EXCLUDED_NAME_PARTS = {"secrets", "secret", "token", "credentials", "personal_data"}
EXCLUDED_PATTERNS = {"*.pyc", "*.pyo", "*.log", ".env", "*.pem", "*.key"}
INCLUDE_FILENAMES = {
    "requirements.txt",
    "requirements.lock",
    "pyproject.toml",
    "README.md",
    "readme.md",
}
INCLUDE_DIRS = {"assets", "templates", "static", "config", "config.default", "icons", "images"}


def classify_files(context: StudioContext) -> SourceInventory:
    local_imports, import_roots = resolve_local_imports(context.entry, context.source_root)
    local_import_set = {path.resolve() for path in local_imports}
    records: list[FileRecord] = []

    for path in sorted(context.source_root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(context.source_root).as_posix()
        size = path.stat().st_size
        excluded, reason = exclusion_reason(path, context.source_root)
        include = False
        category = "other"
        include_reason = reason

        if not excluded:
            include, include_reason, category = inclusion_reason(path, context, local_import_set)

        records.append(
            FileRecord(
                path=path.resolve(),
                relative_path=relative,
                size=size,
                include=include,
                reason=include_reason,
                category=category,
            )
        )

    return SourceInventory(records=records, local_import_files=sorted(local_import_set), import_roots=sorted(import_roots))


def exclusion_reason(path: Path, source_root: Path) -> tuple[bool, str]:
    relative_parts = [part.lower() for part in path.relative_to(source_root).parts]
    if any(part in EXCLUDED_DIRS for part in relative_parts[:-1]):
        return True, "excluded directory"
    name = path.name.lower()
    if any(part in name for part in EXCLUDED_NAME_PARTS):
        return True, "excluded sensitive filename"
    if any(fnmatch.fnmatch(name, pattern.lower()) for pattern in EXCLUDED_PATTERNS):
        return True, "excluded unsafe or generated file"
    return False, ""


def inclusion_reason(path: Path, context: StudioContext, local_import_set: set[Path]) -> tuple[bool, str, str]:
    relative = path.relative_to(context.source_root)
    name = path.name
    lower_name = name.lower()
    parts = set(relative.parts)
    lower_parts = {part.lower() for part in relative.parts}

    if path.resolve() == context.entry.resolve():
        return True, "entry file", "entry"
    if path.resolve() in local_import_set:
        return True, "local import dependency", "source"
    if lower_name in INCLUDE_FILENAMES:
        return True, "project metadata", "metadata"
    if path.suffix.lower() == ".py" and ("src" in lower_parts or has_package_marker(path.parent, context.source_root)):
        return True, "project source package", "source"
    if lower_parts & INCLUDE_DIRS:
        return True, "asset/config directory", "asset"
    if lower_name in {"icon.svg", "icon.png", "app.ico"}:
        return True, "icon candidate", "asset"
    if parts and relative.parts[0].lower() in INCLUDE_DIRS:
        return True, "asset/config directory", "asset"
    return False, "not selected for App Studio package", "other"


def has_package_marker(directory: Path, source_root: Path) -> bool:
    current = directory
    while current != source_root and current.is_relative_to(source_root):
        if (current / "__init__.py").is_file():
            return True
        current = current.parent
    return (directory / "__init__.py").is_file()


def resolve_local_imports(entry: Path, source_root: Path) -> tuple[list[Path], set[str]]:
    discovered: set[Path] = set()
    import_roots: set[str] = set()
    queue = [entry.resolve()]

    while queue:
        current = queue.pop(0)
        if current in discovered or not current.is_file():
            continue
        discovered.add(current)
        try:
            tree = ast.parse(current.read_text(encoding="utf-8", errors="replace"), filename=str(current))
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            candidates: list[Path] = []
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".")[0]
                    import_roots.add(root)
                    candidates.extend(resolve_absolute_module(root, source_root))
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    import_roots.add(node.module.split(".")[0])
                candidates.extend(resolve_from_import(node, current, source_root))

            for candidate in candidates:
                resolved = candidate.resolve()
                if resolved.is_file() and resolved.is_relative_to(source_root.resolve()) and resolved not in discovered:
                    queue.append(resolved)

    return [path for path in discovered if path != entry.resolve()], import_roots


def resolve_absolute_module(module_name: str, source_root: Path) -> list[Path]:
    module_path = source_root.joinpath(*module_name.split("."))
    return [module_path.with_suffix(".py"), module_path / "__init__.py"]


def resolve_from_import(node: ast.ImportFrom, current_file: Path, source_root: Path) -> list[Path]:
    candidates: list[Path] = []
    if node.level and node.level > 0:
        base = current_file.parent
        for _ in range(node.level - 1):
            base = base.parent
        if node.module:
            base = base.joinpath(*node.module.split("."))
        candidates.append(base.with_suffix(".py"))
        candidates.append(base / "__init__.py")
        for alias in node.names:
            candidates.append(base / f"{alias.name}.py")
            candidates.append(base / alias.name / "__init__.py")
        return candidates

    if node.module:
        module_path = source_root.joinpath(*node.module.split("."))
        candidates.append(module_path.with_suffix(".py"))
        candidates.append(module_path / "__init__.py")
        for alias in node.names:
            candidates.append(module_path / f"{alias.name}.py")
            candidates.append(module_path / alias.name / "__init__.py")
    return candidates


def inventory_markdown(inventory: SourceInventory) -> str:
    rows = [
        [
            "include" if record.include else "exclude",
            record.category,
            record.relative_path,
            str(record.size),
            record.reason,
        ]
        for record in inventory.records
    ]
    return "# File Inventory\n\n" + markdown_table(["Status", "Category", "Path", "Bytes", "Reason"], rows) + "\n"

