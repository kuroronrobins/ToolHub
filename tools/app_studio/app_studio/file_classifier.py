from __future__ import annotations

import ast
import fnmatch
import os
from dataclasses import dataclass
from pathlib import Path

from .models import FileRecord, SourceInventory, StudioContext
from .util import markdown_table


GENERATED_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    ".mypy_cache",
    "venv",
    "env",
    "__pycache__",
    ".pytest_cache",
    "node_modules",
    "dist",
    "build",
    "output",
    "outputs",
    "release",
    "result",
    "results",
    "runtime",
    "target",
    ".pytest_tmp",
    "toolhub_appstudio_output",
    "work",
    "works",
}
EXCLUDED_DIRS = {"logs", "log", "screenshots", "sessions", "tmp", "temp"}
BLOCKED_DIRS = {".auth"}
BLOCKED_EXACT_NAMES = {
    "auth_state.json",
    "client_secret.json",
    "client-secrets.json",
    "client_secrets.json",
    "cookie.json",
    "cookies.json",
    "credential.json",
    "credentials.json",
    "session.json",
    "sessions.json",
    "storage_state.json",
    "token.json",
    "tokens.json",
}
SENSITIVE_NAME_MARKERS = {"credential", "credentials", "token", "secret", "password", "api_key", "apikey", "storage_state", "cookie", "session"}
SENSITIVE_NAME_SUFFIXES = {".json", ".yaml", ".yml", ".toml", ".ini", ".txt"}
BLOCKED_PATTERNS = {"*.pem", "*.key", ".env", ".env.*"}
EXCLUDED_PATTERNS = {"*.pyc", "*.pyo", "*.log", "*.tmp"}
INCLUDE_FILENAMES = {
    "requirements.txt",
    "requirements.lock",
    "pyproject.toml",
    "README.md",
    "readme.md",
}
RUNTIME_CONFIG_FILENAMES = {"config.yaml", "config.yml"}
RESOURCE_DIRS = {"assets", "templates", "static", "config", "config.default", "icons", "images", "flows"}
RESOURCE_SUFFIXES = {
    ".csv",
    ".flow",
    ".ini",
    ".json",
    ".md",
    ".toml",
    ".txt",
    ".xlsx",
    ".yaml",
    ".yml",
}
PATH_REFERENCE_SUFFIXES = RESOURCE_SUFFIXES | {".xls", ".xml"}
PATH_FACTORY_NAMES = {"Path", "pathlib.Path"}
PATH_READ_METHODS = {"read_text", "read_bytes"}
FILE_READER_NAMES = {
    "open",
    "pandas.read_csv",
    "pd.read_csv",
    "pandas.read_excel",
    "pd.read_excel",
    "json.load",
    "yaml.safe_load",
    "tomllib.load",
    "configparser.ConfigParser.read",
}


@dataclass(frozen=True)
class CodeReference:
    raw_path: str
    source_file: Path
    pattern: str
    base: str = "ambiguous"


@dataclass(frozen=True)
class ToolHubIgnoreRule:
    pattern: str
    directory_only: bool = False
    negated: bool = False


@dataclass
class SourceWalkResult:
    files: list[Path]
    excluded_directories: list[dict[str, str]]


def classify_files(context: StudioContext) -> SourceInventory:
    ignore_rules = load_toolhubignore(context.source_root)
    walk_result = collect_source_files(context.source_root, ignore_rules)
    allowed_file_set = {path.resolve() for path in walk_result.files}
    allowed_file_set.add(context.entry.resolve())
    local_imports, import_roots = resolve_local_imports(context.entry, context.source_root, allowed_file_set)
    local_import_set = {path.resolve() for path in local_imports}
    references, manual_checks = collect_code_path_references(context.entry, local_import_set, context.source_root)
    referenced_files = referenced_files_by_path(references, context.source_root, allowed_file_set)
    records: list[FileRecord] = []

    for path in walk_result.files:
        if not path.is_file():
            continue
        relative = path.relative_to(context.source_root).as_posix()
        size = path.stat().st_size
        ignored, ignore_reason = ignore_match_reason(path, context.source_root, False, ignore_rules)
        if ignored:
            excluded, status, reason, secret_scan = True, "exclude", ignore_reason, "not_scanned"
        else:
            excluded, status, reason, secret_scan = exclusion_reason(path, context.source_root)
        include = False
        category = "other"
        include_reason = reason
        detected_from = ""
        code_reference_file = ""
        detection_pattern = ""

        if not excluded:
            reference = referenced_files.get(path.resolve())
            include, include_reason, category, detected_from, code_reference_file, detection_pattern = inclusion_reason(
                path,
                context,
                local_import_set,
                reference,
            )
            status = "include" if include else "exclude"

        records.append(
            FileRecord(
                path=path.resolve(),
                relative_path=relative,
                size=size,
                include=include,
                reason=include_reason,
                category=category,
                status=status,
                detected_from=detected_from,
                code_reference_file=code_reference_file,
                detection_pattern=detection_pattern,
                secret_scan=secret_scan,
            )
        )

    return SourceInventory(
        records=records,
        local_import_files=sorted(local_import_set),
        import_roots=sorted(import_roots),
        manual_checks=manual_checks,
        source_root=str(context.source_root),
        source_root_origin=context.source_root_origin,
        entry_relative=context.entry_relative.as_posix(),
        source_root_warnings=context.source_root_warnings,
        excluded_directories=walk_result.excluded_directories,
        toolhubignore_patterns=[rule.pattern for rule in ignore_rules],
    )


def collect_source_files(source_root: Path, ignore_rules: list[ToolHubIgnoreRule] | None = None) -> SourceWalkResult:
    ignore_rules = ignore_rules or []
    files: list[Path] = []
    excluded_directories: list[dict[str, str]] = []
    for root, dirnames, filenames in os.walk(source_root):
        current = Path(root)
        kept_dirnames: list[str] = []
        for dirname in dirnames:
            directory = current / dirname
            relative = directory.relative_to(source_root).as_posix()
            lower = dirname.lower()
            excluded = False
            reason = ""
            pattern = ""
            if lower in GENERATED_DIRS or lower.startswith("pytest-cache-files-"):
                excluded = True
                reason = "excluded generated or external-work directory"
            elif lower in EXCLUDED_DIRS:
                excluded = True
                reason = "excluded runtime/user-output directory"
            else:
                excluded, reason = ignore_match_reason(directory, source_root, True, ignore_rules)
                if excluded:
                    pattern = reason.removeprefix("excluded by .toolhubignore: ")
            if excluded:
                excluded_directories.append(
                    {
                        "path": str(directory.resolve()),
                        "relative_path": relative,
                        "reason": reason,
                        "pattern": pattern,
                    }
                )
            else:
                kept_dirnames.append(dirname)
        dirnames[:] = kept_dirnames
        files.extend(current / filename for filename in filenames)
    return SourceWalkResult(
        files=sorted(files, key=lambda path: path.as_posix().lower()),
        excluded_directories=sorted(excluded_directories, key=lambda item: item["relative_path"].lower()),
    )


def iter_source_files(source_root: Path) -> list[Path]:
    return collect_source_files(source_root).files


def load_toolhubignore(source_root: Path) -> list[ToolHubIgnoreRule]:
    path = source_root / ".toolhubignore"
    if not path.is_file():
        return []
    rules: list[ToolHubIgnoreRule] = []
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        negated = line.startswith("!")
        if negated:
            line = line[1:].strip()
        if not line:
            continue
        directory_only = line.endswith("/")
        pattern = line.rstrip("/").lstrip("/").replace("\\", "/")
        if pattern:
            rules.append(ToolHubIgnoreRule(pattern=pattern, directory_only=directory_only, negated=negated))
    return rules


def ignore_match_reason(path: Path, source_root: Path, is_dir: bool, rules: list[ToolHubIgnoreRule]) -> tuple[bool, str]:
    if not rules:
        return False, ""
    relative = path.relative_to(source_root).as_posix()
    ignored = False
    matched_pattern = ""
    for rule in rules:
        if ignore_rule_matches(rule, relative, is_dir):
            ignored = not rule.negated
            matched_pattern = ("!" if rule.negated else "") + rule.pattern + ("/" if rule.directory_only else "")
    if ignored:
        return True, f"excluded by .toolhubignore: {matched_pattern}"
    return False, ""


def ignore_rule_matches(rule: ToolHubIgnoreRule, relative: str, is_dir: bool) -> bool:
    if rule.directory_only and not is_dir:
        return False
    pattern = rule.pattern
    parts = relative.split("/")
    if "/" not in pattern:
        return any(fnmatch.fnmatch(part, pattern) for part in parts)
    if fnmatch.fnmatch(relative, pattern):
        return True
    if is_dir and fnmatch.fnmatch(relative + "/", pattern.rstrip("/") + "/"):
        return True
    return False


def exclusion_reason(path: Path, source_root: Path) -> tuple[bool, str, str, str]:
    relative_parts = [part.lower() for part in path.relative_to(source_root).parts]
    name = path.name.lower()
    if any(part.startswith("pytest-cache-files-") for part in relative_parts[:-1]):
        return True, "exclude", "excluded generated directory", "not_scanned"
    if any(part in BLOCKED_DIRS for part in relative_parts[:-1]):
        return True, "blocked", "blocked sensitive directory", "high"
    if any(part in GENERATED_DIRS for part in relative_parts[:-1]):
        return True, "exclude", "excluded generated directory", "not_scanned"
    if any(part in EXCLUDED_DIRS for part in relative_parts[:-1]):
        return True, "exclude", "excluded runtime/user-output directory", "medium"
    if any(fnmatch.fnmatch(name, pattern.lower()) for pattern in BLOCKED_PATTERNS):
        return True, "blocked", "blocked unsafe credential file", "high"
    if name in BLOCKED_EXACT_NAMES:
        return True, "blocked", "blocked credential/session state file", "high"
    if path.suffix.lower() in SENSITIVE_NAME_SUFFIXES and any(marker in name for marker in SENSITIVE_NAME_MARKERS):
        return True, "manual_check", "sensitive-looking config filename requires review", "medium"
    if any(fnmatch.fnmatch(name, pattern.lower()) for pattern in EXCLUDED_PATTERNS):
        return True, "exclude", "excluded unsafe or generated file", "medium"
    return False, "exclude", "", "not_scanned"


def inclusion_reason(
    path: Path,
    context: StudioContext,
    local_import_set: set[Path],
    reference: CodeReference | None,
) -> tuple[bool, str, str, str, str, str]:
    relative = path.relative_to(context.source_root)
    name = path.name
    lower_name = name.lower()
    lower_parts = {part.lower() for part in relative.parts}

    if path.resolve() == context.entry.resolve():
        return True, "entry file", "entry", "entry", "", ""
    if path.resolve() in local_import_set:
        return True, "local import dependency", "source", "import", "", ""
    if reference:
        return (
            True,
            "code-referenced runtime file",
            "asset",
            "code_reference",
            reference.source_file.relative_to(context.source_root).as_posix(),
            reference.pattern,
        )
    if lower_name in RUNTIME_CONFIG_FILENAMES:
        return True, "runtime config file", "asset", "well_known_config", "", ""
    if lower_name in INCLUDE_FILENAMES:
        return True, "project metadata", "metadata", "metadata", "", ""
    if path.suffix.lower() == ".py" and ("src" in lower_parts or has_package_marker(path.parent, context.source_root)):
        return True, "project source package", "source", "package_source", "", ""
    if lower_parts & RESOURCE_DIRS and path.suffix.lower() in RESOURCE_SUFFIXES:
        return True, "asset/config directory", "asset", "resource_directory", "", ""
    if lower_name in {"icon.svg", "icon.png", "app.ico"}:
        return True, "icon candidate", "asset", "well_known_icon", "", ""
    return False, "not selected for App Studio package", "other", "", "", ""


def collect_code_path_references(entry: Path, local_import_set: set[Path], source_root: Path) -> tuple[list[CodeReference], list[dict[str, str]]]:
    references: list[CodeReference] = []
    manual_checks: list[dict[str, str]] = []
    for file in sorted({entry.resolve(), *local_import_set}):
        try:
            tree = ast.parse(file.read_text(encoding="utf-8", errors="replace"), filename=str(file))
        except SyntaxError:
            manual_checks.append(
                {
                    "status": "manual_check",
                    "reason": "Python source could not be parsed for data-file references.",
                    "source_file": safe_relative(file, source_root),
                    "pattern": "syntax_error",
                }
            )
            continue
        visitor = PathReferenceVisitor(file, source_root)
        visitor.visit(tree)
        references.extend(visitor.references)
        manual_checks.extend(visitor.manual_checks)
    return unique_references(references), manual_checks


class PathReferenceVisitor(ast.NodeVisitor):
    def __init__(self, source_file: Path, source_root: Path) -> None:
        self.source_file = source_file
        self.source_root = source_root
        self.references: list[CodeReference] = []
        self.manual_checks: list[dict[str, str]] = []

    def visit_Call(self, node: ast.Call) -> None:
        name = call_name(node.func)
        if name in FILE_READER_NAMES:
            if node.args:
                self.record_call_arg(node.args[0], name)
            else:
                self.record_manual(name, "reader call has no static path argument")
        elif name in PATH_FACTORY_NAMES:
            if node.args:
                self.record_call_arg(node.args[0], name)
        elif isinstance(node.func, ast.Attribute) and node.func.attr in PATH_READ_METHODS:
            reference = evaluate_path_expr(node.func.value, self.source_file)
            if reference:
                self.add_reference(reference, node.func.attr)
            else:
                self.record_manual(node.func.attr, "Path read call uses a dynamic path expression")
        self.generic_visit(node)

    def visit_BinOp(self, node: ast.BinOp) -> None:
        if isinstance(node.op, ast.Div):
            reference = evaluate_path_expr(node, self.source_file)
            if reference:
                self.add_reference(reference, "pathlib /")
        self.generic_visit(node)

    def record_call_arg(self, node: ast.AST, pattern: str) -> None:
        reference = evaluate_path_expr(node, self.source_file)
        if reference:
            self.add_reference(reference, pattern)
        else:
            self.record_manual(pattern, "call uses a dynamic path expression")

    def add_reference(self, reference: tuple[str, str], pattern: str) -> None:
        raw_path, base = reference
        if is_probable_runtime_reference(raw_path):
            self.references.append(CodeReference(raw_path=raw_path, source_file=self.source_file, pattern=pattern, base=base))

    def record_manual(self, pattern: str, reason: str) -> None:
        self.manual_checks.append(
            {
                "status": "manual_check",
                "reason": reason,
                "source_file": safe_relative(self.source_file, self.source_root),
                "pattern": pattern,
            }
        )


def evaluate_path_expr(node: ast.AST, source_file: Path) -> tuple[str, str] | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value, "ambiguous"
    if isinstance(node, ast.JoinedStr):
        return None
    if isinstance(node, ast.Name) and node.id == "__file__":
        return source_file.name, "file_parent"
    if isinstance(node, ast.Call):
        name = call_name(node.func)
        if name in PATH_FACTORY_NAMES and node.args:
            if isinstance(node.args[0], ast.Name) and node.args[0].id == "__file__":
                return "", "file_parent"
            return evaluate_path_expr(node.args[0], source_file)
        if name == "os.path.join" and node.args:
            parts: list[str] = []
            base = "ambiguous"
            for arg in node.args:
                value = evaluate_path_expr(arg, source_file)
                if not value:
                    return None
                raw, value_base = value
                if value_base == "file_parent":
                    base = "file_parent"
                parts.append(raw)
            return os.path.join(*[part for part in parts if part]), base
        if isinstance(node.func, ast.Attribute) and node.func.attr == "resolve":
            return evaluate_path_expr(node.func.value, source_file)
        return None
    if isinstance(node, ast.Attribute):
        value = evaluate_path_expr(node.value, source_file)
        if node.attr == "parent" and value:
            raw, base = value
            if base == "file_parent":
                return str(Path(raw).parent) if raw else "", "file_parent"
            return str(Path(raw).parent), base
        return value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        left = evaluate_path_expr(node.left, source_file)
        right = evaluate_path_expr(node.right, source_file)
        if not left or not right:
            return None
        left_raw, left_base = left
        right_raw, right_base = right
        base = "file_parent" if "file_parent" in {left_base, right_base} else "ambiguous"
        return str(Path(left_raw) / right_raw) if left_raw else right_raw, base
    return None


def referenced_files_by_path(references: list[CodeReference], source_root: Path, allowed_files: set[Path] | None = None) -> dict[Path, CodeReference]:
    result: dict[Path, CodeReference] = {}
    for reference in references:
        for candidate in resolve_reference_candidates(reference, source_root):
            if candidate.is_file():
                resolved = candidate.resolve()
                if allowed_files is None or resolved in allowed_files:
                    result.setdefault(resolved, reference)
            elif candidate.is_dir():
                if allowed_files is None:
                    for child in sorted(candidate.rglob("*")):
                        if child.is_file():
                            result.setdefault(child.resolve(), reference)
                else:
                    candidate_root = candidate.resolve()
                    for child in sorted(allowed_files, key=lambda path: path.as_posix().lower()):
                        try:
                            child.relative_to(candidate_root)
                        except ValueError:
                            continue
                        if child.is_file():
                            result.setdefault(child.resolve(), reference)
    return result


def resolve_reference_candidates(reference: CodeReference, source_root: Path) -> list[Path]:
    raw = reference.raw_path.strip().strip("\"'")
    if not raw:
        return []
    path = Path(raw)
    if path.is_absolute():
        return [path] if path.resolve().is_relative_to(source_root.resolve()) else []
    candidates: list[Path] = []
    if reference.base == "file_parent":
        candidates.append(reference.source_file.parent / path)
    candidates.append(source_root / path)
    if reference.source_file.parent.resolve() != source_root.resolve():
        candidates.append(reference.source_file.parent / path)
    unique: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved in seen or not resolved.is_relative_to(source_root.resolve()):
            continue
        seen.add(resolved)
        unique.append(resolved)
    return unique


def is_probable_runtime_reference(raw_path: str) -> bool:
    text = raw_path.strip()
    if not text or "{" in text or "}" in text:
        return False
    path = Path(text)
    lower_parts = {part.lower() for part in path.parts}
    if lower_parts & RESOURCE_DIRS:
        return True
    suffix = path.suffix.lower()
    return suffix in PATH_REFERENCE_SUFFIXES


def unique_references(references: list[CodeReference]) -> list[CodeReference]:
    result: list[CodeReference] = []
    seen: set[tuple[str, str, str]] = set()
    for reference in references:
        key = (reference.raw_path, str(reference.source_file), reference.pattern)
        if key in seen:
            continue
        seen.add(key)
        result.append(reference)
    return result


def call_name(func: ast.AST) -> str:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        parent = call_name(func.value)
        return f"{parent}.{func.attr}" if parent else func.attr
    if isinstance(func, ast.Call):
        return call_name(func.func)
    return ""


def has_package_marker(directory: Path, source_root: Path) -> bool:
    current = directory
    while current != source_root and current.is_relative_to(source_root):
        if (current / "__init__.py").is_file():
            return True
        current = current.parent
    return (directory / "__init__.py").is_file()


def resolve_local_imports(entry: Path, source_root: Path, allowed_files: set[Path] | None = None) -> tuple[list[Path], set[str]]:
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
                    candidates.extend(resolve_absolute_module(alias.name, source_root))
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    import_roots.add(node.module.split(".")[0])
                candidates.extend(resolve_from_import(node, current, source_root))

            for candidate in candidates:
                resolved = candidate.resolve()
                if (
                    resolved.is_file()
                    and resolved.is_relative_to(source_root.resolve())
                    and resolved not in discovered
                    and (allowed_files is None or resolved in allowed_files)
                ):
                    queue.append(resolved)

    return [path for path in discovered if path != entry.resolve()], import_roots


def resolve_absolute_module(module_name: str, source_root: Path) -> list[Path]:
    module_path = source_root.joinpath(*module_name.split("."))
    candidates = [module_path.with_suffix(".py"), module_path / "__init__.py"]
    root_path = source_root / module_name.split(".")[0]
    candidates.extend([root_path.with_suffix(".py"), root_path / "__init__.py"])
    return candidates


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
    summary = inventory.summary()
    text = "\n".join(
        [
            "# File Inventory",
            "",
            "## Source Scope",
            "",
            f"- source_root: `{summary.get('source_root')}`",
            f"- source_root_origin: `{summary.get('source_root_origin')}`",
            f"- entry_relative: `{summary.get('entry_relative')}`",
            f"- included_count: {summary.get('included_count')}",
            f"- excluded_count: {summary.get('excluded_count')}",
            f"- blocked_count: {summary.get('blocked_count')}",
            f"- manual_check_count: {summary.get('manual_check_count')}",
            f"- excluded_directory_count: {summary.get('excluded_directory_count')}",
            f"- toolhubignore_pattern_count: {summary.get('toolhubignore_pattern_count')}",
            "",
        ]
    )
    if inventory.source_root_warnings:
        text += "## Source Scope Warnings\n\n"
        for warning in inventory.source_root_warnings:
            text += f"- {warning}\n"
        text += "\n"
    if inventory.excluded_directories:
        text += "## Excluded Directories\n\n"
        text += markdown_table(
            ["Path", "Reason", "Pattern"],
            [
                [
                    item.get("relative_path", "-"),
                    item.get("reason", "-"),
                    item.get("pattern", "-") or "-",
                ]
                for item in inventory.excluded_directories[:100]
            ],
        )
        text += "\n"
        if len(inventory.excluded_directories) > 100:
            text += f"\n... {len(inventory.excluded_directories) - 100} more excluded directories\n"
        text += "\n"
    rows = [
        [
            record.status or ("include" if record.include else "exclude"),
            record.category,
            record.relative_path,
            str(record.size),
            record.reason,
            record.detected_from or "-",
            record.secret_scan,
        ]
        for record in inventory.records
    ]
    text += "## Files\n\n" + markdown_table(["Status", "Category", "Path", "Bytes", "Reason", "Detected From", "Secret Scan"], rows) + "\n"
    if inventory.manual_checks:
        text += "\n## Manual Checks\n\n"
        for item in inventory.manual_checks:
            text += f"- {item.get('source_file', '-')}: {item.get('pattern', '-')} - {item.get('reason', '-')}\n"
    return text


def safe_relative(path: Path, source_root: Path) -> str:
    try:
        return path.relative_to(source_root).as_posix()
    except ValueError:
        return str(path)
