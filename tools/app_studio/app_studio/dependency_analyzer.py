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
    return [line.strip() for line in lines if line.strip() and not line.strip().startswith("#")]


def local_module_roots(context: StudioContext) -> set[str]:
    roots = {context.entry.stem}
    for path in context.source_root.iterdir():
        if path.is_file() and path.suffix == ".py":
            roots.add(path.stem)
        elif path.is_dir() and (path / "__init__.py").is_file():
            roots.add(path.name)
    return roots

