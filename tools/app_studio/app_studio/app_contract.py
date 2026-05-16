from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

from .models import StudioContext


EXCLUDED_SCAN_DIRS = {
    ".git",
    ".gitup",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "env",
    "node_modules",
    "site-packages",
    "toolhub_appstudio_output",
    "venv",
}
GUI_SIGNALS = (
    "ft.app(",
    "flet.app(",
    "import flet",
    "from flet",
    "tkinter",
    "customtkinter",
    "pyqt",
    "pyside",
    "wx.",
    "streamlit",
    "gradio",
)
CLI_SIGNALS = ("argparse", "click.", "typer.", "sys.argv")
SMOKE_FLAGS = ("--toolhub-smoke", "--smoke")


@dataclass(frozen=True)
class FrozenSubprocessRisk:
    path: Path
    line: int
    module: str

    def display(self, source_root: Path) -> str:
        try:
            relative = self.path.relative_to(source_root).as_posix()
        except ValueError:
            relative = str(self.path)
        return f"{relative}:{self.line} uses sys.executable -m {self.module}"


def infer_run_mode_from_source(context: StudioContext) -> str:
    if context.entry.suffix.lower() == ".exe":
        return "gui"

    entry_text = read_text(context.entry)
    if source_has_gui_signal(context):
        return "gui"

    if any(signal in entry_text for signal in CLI_SIGNALS):
        return "cli"
    return "gui"


def source_has_gui_signal(context: StudioContext) -> bool:
    lowered_source = "\n".join(read_text(path) for path in iter_source_python_files(context)).lower()
    return any(signal in lowered_source for signal in GUI_SIGNALS)


def smoke_flags_in_source(context: StudioContext) -> list[str]:
    text = "\n".join(read_text(path) for path in iter_source_python_files(context))
    return [flag for flag in SMOKE_FLAGS if flag in text]


def detect_frozen_subprocess_module_risks(context: StudioContext) -> list[FrozenSubprocessRisk]:
    local_roots = local_module_roots(context)
    risks: list[FrozenSubprocessRisk] = []
    for path in iter_source_python_files(context):
        text = read_text(path)
        if "sys.executable" not in text or '"-m"' not in text and "'-m'" not in text:
            continue
        try:
            tree = ast.parse(text, filename=str(path))
        except SyntaxError:
            risks.extend(text_fallback_subprocess_risks(context, path, text, local_roots))
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            module = sys_executable_module_from_call(node)
            if module and module_is_local(module, local_roots):
                risks.append(FrozenSubprocessRisk(path=path, line=getattr(node, "lineno", 0) or 0, module=module))
    return risks


def sys_executable_module_from_call(node: ast.Call) -> str | None:
    if not node.args:
        return None
    sequence = literal_sequence(node.args[0])
    if not sequence or len(sequence) < 3:
        return None
    if not is_sys_executable(sequence[0]):
        return None
    for index, item in enumerate(sequence[:-1]):
        if literal_string(item) == "-m":
            return literal_string(sequence[index + 1])
    return None


def literal_sequence(node: ast.AST) -> list[ast.AST]:
    if isinstance(node, (ast.List, ast.Tuple)):
        return list(node.elts)
    return []


def is_sys_executable(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Attribute)
        and node.attr == "executable"
        and isinstance(node.value, ast.Name)
        and node.value.id == "sys"
    )


def literal_string(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def text_fallback_subprocess_risks(
    context: StudioContext,
    path: Path,
    text: str,
    local_roots: set[str],
) -> list[FrozenSubprocessRisk]:
    risks: list[FrozenSubprocessRisk] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        if "sys.executable" not in line or "-m" not in line:
            continue
        for root in local_roots:
            if root and root in line:
                risks.append(FrozenSubprocessRisk(path=path, line=line_no, module=root))
                break
    return risks


def module_is_local(module: str | None, local_roots: set[str]) -> bool:
    if not module:
        return False
    root = module.split(".", 1)[0]
    return root in local_roots


def local_module_roots(context: StudioContext) -> set[str]:
    roots = {context.entry.stem}
    try:
        for path in context.source_root.iterdir():
            if path.is_file() and path.suffix == ".py":
                roots.add(path.stem)
            elif path.is_dir() and (path / "__init__.py").is_file():
                roots.add(path.name)
    except OSError:
        pass
    return {root for root in roots if root}


def iter_source_python_files(context: StudioContext, max_files: int = 500) -> list[Path]:
    if context.entry.is_file():
        files = [context.entry]
    else:
        files = []
    try:
        candidates = sorted(context.source_root.rglob("*.py"), key=lambda path: path.as_posix().lower())
    except OSError:
        return files
    seen = {path.resolve() for path in files}
    for path in candidates:
        if len(files) >= max_files:
            break
        try:
            resolved = path.resolve()
        except OSError:
            continue
        if resolved in seen:
            continue
        if should_skip_source_path(path, context.source_root):
            continue
        files.append(path)
        seen.add(resolved)
    return files


def should_skip_source_path(path: Path, source_root: Path) -> bool:
    try:
        relative = path.relative_to(source_root)
    except ValueError:
        return True
    return any(part.lower() in EXCLUDED_SCAN_DIRS for part in relative.parts)


def read_text(path: Path, max_bytes: int = 1024 * 1024) -> str:
    try:
        if path.stat().st_size > max_bytes:
            return ""
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
