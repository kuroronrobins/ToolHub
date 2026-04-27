from __future__ import annotations

import sys
from pathlib import Path

from .models import DependencyReport, SourceInventory, StudioContext


FALLBACK_STDLIB = {
    "argparse",
    "ast",
    "collections",
    "csv",
    "dataclasses",
    "datetime",
    "functools",
    "hashlib",
    "io",
    "itertools",
    "json",
    "logging",
    "math",
    "os",
    "pathlib",
    "re",
    "shutil",
    "sqlite3",
    "subprocess",
    "sys",
    "tempfile",
    "threading",
    "time",
    "tkinter",
    "typing",
    "unittest",
    "uuid",
    "zipfile",
}


def analyze_dependencies(context: StudioContext, inventory: SourceInventory) -> tuple[DependencyReport, str]:
    pyproject = context.source_root / "pyproject.toml"
    requirements = context.source_root / "requirements.txt"
    lock = context.source_root / "requirements.lock"

    if pyproject.is_file():
        parsed = parse_pyproject_dependencies(pyproject)
        if parsed:
            report = DependencyReport("pyproject.toml", parsed, inventory.import_roots, third_party_candidates=[], notes=["pyproject.toml dependencies were used."])
            return report, "\n".join(parsed) + "\n"

    if requirements.is_file():
        lines = normalize_requirement_lines(requirements.read_text(encoding="utf-8", errors="replace").splitlines())
        report = DependencyReport("requirements.txt", lines, inventory.import_roots, third_party_candidates=[], notes=["requirements.txt was copied as the proposed requirements file."])
        return report, requirements.read_text(encoding="utf-8", errors="replace")

    if lock.is_file():
        lines = normalize_requirement_lines(lock.read_text(encoding="utf-8", errors="replace").splitlines())
        report = DependencyReport("requirements.lock", lines, inventory.import_roots, third_party_candidates=[], notes=["requirements.lock was used as a reference because requirements.txt was not found."])
        return report, "\n".join(lines) + "\n"

    nested_requirements = included_requirements_files(context, inventory)
    if nested_requirements:
        lines = merged_requirement_lines(nested_requirements)
        source_list = ", ".join(path.relative_to(context.source_root).as_posix() for path in nested_requirements)
        report = DependencyReport(
            "nested-requirements.txt",
            lines,
            inventory.import_roots,
            third_party_candidates=[],
            notes=[
                "Nested requirements.txt files were found in included project files.",
                f"Sources: {source_list}",
            ],
        )
        return report, "\n".join(lines).rstrip() + "\n"

    stdlib = set(getattr(sys, "stdlib_module_names", FALLBACK_STDLIB)) | FALLBACK_STDLIB
    local_roots = local_module_roots(context)
    candidates = sorted(root for root in inventory.import_roots if root not in stdlib and root not in local_roots)
    proposed = ["# Review these import-derived candidates before installing.", "# App Studio did not find requirements.txt or pyproject.toml."]
    proposed.extend(f"# {candidate}" for candidate in candidates)
    proposed_text = "\n".join(proposed).rstrip() + "\n"
    report = DependencyReport(
        "import-analysis",
        [],
        inventory.import_roots,
        candidates,
        notes=["pip freeze is intentionally not used. Import roots are listed for human review."],
    )
    return report, proposed_text


def parse_pyproject_dependencies(path: Path) -> list[str]:
    try:
        import tomllib
    except Exception:
        return []
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return []
    project = data.get("project") or {}
    dependencies = project.get("dependencies") or []
    if isinstance(dependencies, list):
        return [str(item) for item in dependencies if str(item).strip()]
    return []


def normalize_requirement_lines(lines: list[str]) -> list[str]:
    normalized: list[str] = []
    for line in lines:
        stripped = line.strip().lstrip("\ufeff")
        if not stripped or stripped.startswith("#"):
            continue
        normalized.append(stripped)
    return normalized


def included_requirements_files(context: StudioContext, inventory: SourceInventory) -> list[Path]:
    root_requirements = (context.source_root / "requirements.txt").resolve()
    paths = []
    for record in inventory.records:
        if not record.include:
            continue
        if record.path.name.lower() != "requirements.txt":
            continue
        resolved = record.path.resolve()
        if resolved == root_requirements:
            continue
        paths.append(resolved)
    return sorted(paths)


def merged_requirement_lines(paths: list[Path]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for path in paths:
        for line in normalize_requirement_lines(path.read_text(encoding="utf-8", errors="replace").splitlines()):
            key = line.lower()
            if key in seen:
                continue
            seen.add(key)
            merged.append(line)
    return merged


def local_module_roots(context: StudioContext) -> set[str]:
    roots = {context.entry.stem}
    for path in context.source_root.iterdir():
        if path.is_file() and path.suffix == ".py":
            roots.add(path.stem)
        elif path.is_dir() and (path / "__init__.py").is_file():
            roots.add(path.name)
    return roots
