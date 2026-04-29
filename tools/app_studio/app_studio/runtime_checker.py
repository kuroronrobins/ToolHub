from __future__ import annotations

import fnmatch
import json
from pathlib import Path
from typing import Any

from .models import BuildPlan, RuntimeCheck, RuntimeCheckResult, StudioContext
from .trace import trace_with_import_plan
from .util import write_json, write_text


FORBIDDEN_DIRS = {
    ".auth",
    ".git",
    ".pytest_cache",
    ".venv",
    "__pycache__",
    "build",
    "build_env",
    "dist",
    "env",
    "log",
    "logs",
    "node_modules",
    "screenshots",
    "temp",
    "tmp",
    "venv",
}
FORBIDDEN_PATTERNS = {
    ".env",
    ".env.*",
    "*.key",
    "*.log",
    "*.pem",
    "*.pyc",
    "*.pyo",
    "*.tmp",
}
FORBIDDEN_EXACT_NAMES = {
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
FORBIDDEN_CONFIG_SUFFIXES = {".json", ".yaml", ".yml", ".toml", ".ini", ".txt"}
FORBIDDEN_CONFIG_MARKERS = {
    "api_key",
    "apikey",
    "auth_state",
    "client_secret",
    "credential",
    "credentials",
    "password",
    "passwd",
    "secret",
    "storage_state",
}
FORBIDDEN_AUTH_MARKERS = {"cookie", "session", "token"}


def verify_runtime(
    context: StudioContext,
    output_dir: Path,
    plan: BuildPlan | None = None,
    build_profile: dict[str, Any] | None = None,
) -> RuntimeCheckResult:
    if plan and plan.mode == "frozen-folder":
        result = verify_frozen_folder_distribution(context, output_dir, plan, build_profile or {})
    else:
        result = verify_legacy_runtime(context, output_dir)
    write_runtime_reports(context, output_dir, result)
    return result


def verify_frozen_folder_distribution(
    context: StudioContext,
    output_dir: Path,
    plan: BuildPlan,
    build_profile: dict[str, Any],
) -> RuntimeCheckResult:
    final_app = output_dir / "final_app"
    bin_root = final_app / "bin" / context.app_id
    exe_path = final_app / plan.entry
    checks: list[RuntimeCheck] = [
        file_check("frozen-folder executable exists", exe_path),
        app_yaml_entry_check(final_app / "app.yaml", plan.entry),
        run_entry_policy_check(plan.entry),
        build_required_removed_check(final_app),
        pyinstaller_layout_check(output_dir),
        required_data_files_check(bin_root, build_profile, context.source_root),
        forbidden_payload_check(final_app),
        build_env_separation_check(context, final_app),
        size_check("frozen-folder size", bin_root),
        add_data_size_check(context, build_profile),
        RuntimeCheck(
            "frozen smoke execution",
            "warn",
            "Skipped automatically for exe/frozen-folder mode. GUI, browser, login, and file-picker flows require manual launch verification.",
        ),
    ]
    if uses_playwright(build_profile):
        checks.append(
            RuntimeCheck(
                "playwright manual check",
                "warn",
                "Playwright was collected for the build. Browser binaries and login state must be verified manually; authenticated storage state is not packaged.",
            )
        )
    return RuntimeCheckResult(context.app_id, overall_status(checks), checks, trace_with_import_plan(context, output_dir))


def verify_legacy_runtime(context: StudioContext, output_dir: Path) -> RuntimeCheckResult:
    checks = [
        RuntimeCheck(
            "legacy runtime check",
            "warn",
            "Normal App Studio registration now verifies frozen-folder distribution output. Legacy app_env runtime probing is skipped for this path.",
        )
    ]
    return RuntimeCheckResult(context.app_id, overall_status(checks), checks, trace_with_import_plan(context, output_dir))


def file_check(name: str, path: Path, missing_status: str = "fail") -> RuntimeCheck:
    if path.is_file():
        return RuntimeCheck(name, "pass", str(path))
    return RuntimeCheck(name, missing_status, f"Missing: {path}")


def app_yaml_entry_check(path: Path, expected_entry: str) -> RuntimeCheck:
    if not path.is_file():
        return RuntimeCheck("app.yaml run.entry", "fail", f"Missing: {path}")
    text = path.read_text(encoding="utf-8", errors="replace")
    if f"entry: {expected_entry}" in text or f"entry: \"{expected_entry}\"" in text or f"entry: '{expected_entry}'" in text:
        return RuntimeCheck("app.yaml run.entry", "pass", expected_entry)
    return RuntimeCheck("app.yaml run.entry", "fail", f"run.entry does not point to generated exe: {expected_entry}")


def run_entry_policy_check(entry: str) -> RuntimeCheck:
    if entry.lower().endswith(".py"):
        return RuntimeCheck("distribution run.entry policy", "fail", ".py run.entry is not allowed for normal user distribution.")
    if entry.lower().endswith(".exe") or "." not in Path(entry).name:
        return RuntimeCheck("distribution run.entry policy", "pass", entry)
    return RuntimeCheck("distribution run.entry policy", "warn", f"Entry is not a .py file, but review unusual executable name: {entry}")


def build_required_removed_check(final_app: Path) -> RuntimeCheck:
    marker = final_app / "bin" / "BUILD_REQUIRED.txt"
    if marker.exists():
        return RuntimeCheck("BUILD_REQUIRED marker removed", "fail", f"BUILD_REQUIRED.txt remains after frozen build: {marker}")
    return RuntimeCheck("BUILD_REQUIRED marker removed", "pass", "BUILD_REQUIRED.txt is not present in final_app/bin.")


def pyinstaller_layout_check(output_dir: Path) -> RuntimeCheck:
    report_path = output_dir / "frozen_folder_build_report.md"
    if not report_path.is_file():
        return RuntimeCheck("pyinstaller layout command", "warn", f"Build report was not found: {report_path}")
    text = report_path.read_text(encoding="utf-8", errors="replace")
    if command_uses_contents_directory_dot(text):
        return RuntimeCheck("pyinstaller layout command", "pass", "PyInstaller command includes --contents-directory . for old-style onedir layout.")
    if "--contents-directory" in text:
        return RuntimeCheck("pyinstaller layout command", "warn", "PyInstaller command uses --contents-directory but not with '.'. Review onedir data placement.")
    return RuntimeCheck("pyinstaller layout command", "warn", "PyInstaller command does not show --contents-directory .; _internal data placement may be from an old build.")


def command_uses_contents_directory_dot(text: str) -> bool:
    tokens = text.replace("`", "").replace('"', "").replace("'", "").split()
    for index, token in enumerate(tokens[:-1]):
        if token == "--contents-directory" and tokens[index + 1] == ".":
            return True
    return False


def required_data_files_check(bin_root: Path, build_profile: dict[str, Any], source_root: Path | None = None) -> RuntimeCheck:
    findings = required_data_findings(bin_root, build_profile, source_root)
    if findings["status"] == "no_data":
        return RuntimeCheck("required add-data files", "warn", "No add_data entries are listed in build_profile.json.")
    if findings["missing"]:
        return RuntimeCheck("required add-data files", "fail", "Missing packaged data files: " + ", ".join(item["relative"] for item in findings["missing"][:10]))
    if findings["internal_only"]:
        detail = (
            f"{findings['found_count']} packaged data item(s) were found, but "
            f"{len(findings['internal_only'])} item(s) are only under _internal. "
            "This is acceptable for existing PyInstaller 6 onedir artifacts, but with --contents-directory . new builds should place them beside the exe."
        )
        return RuntimeCheck("required add-data files", "warn", detail)
    return RuntimeCheck("required add-data files", "pass", f"{findings['found_count']} packaged data item(s) were found.")


def required_data_findings(bin_root: Path, build_profile: dict[str, Any], source_root: Path | None = None) -> dict[str, Any]:
    add_data = build_profile.get("add_data") if isinstance(build_profile, dict) else None
    required_files = build_profile.get("required_files") if isinstance(build_profile, dict) else None
    mappings = [item for item in add_data if isinstance(item, dict)] if isinstance(add_data, list) else []
    required = [str(item) for item in required_files if str(item).strip()] if isinstance(required_files, list) else []
    if not mappings and not required:
        return {"status": "no_data", "expected": [], "found": [], "missing": [], "internal_only": [], "found_count": 0}

    expected = expected_data_relatives(mappings, required, source_root)
    found: list[dict[str, str]] = []
    missing: list[dict[str, str]] = []
    internal_only: list[dict[str, str]] = []
    for relative in expected:
        primary = bin_root / relative
        internal = bin_root / "_internal" / relative
        item = {"relative": relative.as_posix(), "primary": primary.as_posix(), "internal": internal.as_posix()}
        if primary.exists():
            found.append({**item, "location": "primary"})
        elif internal.exists():
            found.append({**item, "location": "internal"})
            internal_only.append(item)
        else:
            missing.append(item)
    return {
        "status": "ok",
        "expected": [item.as_posix() for item in expected],
        "found": found,
        "missing": missing,
        "internal_only": internal_only,
        "found_count": len(found),
    }


def expected_data_relatives(mappings: list[dict[str, Any]], required_files: list[str], source_root: Path | None) -> list[Path]:
    expected: list[Path] = []
    if required_files:
        for required in required_files:
            relative = expected_relative_for_required_file(required, mappings, source_root)
            if relative is not None:
                expected.append(relative)
        return unique_paths(expected)

    for mapping in mappings:
        source = str(mapping.get("source") or "").strip()
        destination = str(mapping.get("destination") or ".").strip() or "."
        if not source:
            continue
        source_path = resolve_source(source_root, source)
        if source_path and source_path.is_dir():
            files = sorted(path for path in source_path.rglob("*") if path.is_file())
            if not files:
                expected.append(clean_relative(destination))
                continue
            for file in files:
                expected.append(clean_relative(destination) / file.relative_to(source_path))
        else:
            expected.append(clean_relative(destination) / Path(source).name)
    return unique_paths(expected)


def expected_relative_for_required_file(required: str, mappings: list[dict[str, Any]], source_root: Path | None) -> Path | None:
    required_relative = clean_relative(required)
    for mapping in mappings:
        source = str(mapping.get("source") or "").strip()
        destination = str(mapping.get("destination") or ".").strip() or "."
        if not source:
            continue
        source_relative = clean_relative(source)
        source_path = resolve_source(source_root, source)
        if source_relative == required_relative:
            if source_path and source_path.is_dir():
                return clean_relative(destination)
            return clean_relative(destination) / source_relative.name
        nested = relative_to_or_none(required_relative, source_relative)
        if nested is not None:
            return clean_relative(destination) / nested
    return required_relative


def resolve_source(source_root: Path | None, source: str) -> Path | None:
    if not source_root:
        return None
    path = Path(source)
    return path if path.is_absolute() else source_root / path


def clean_relative(value: str) -> Path:
    normalized = str(value).replace("\\", "/").strip()
    if not normalized or normalized == ".":
        return Path(".")
    return Path(normalized)


def relative_to_or_none(path: Path, base: Path) -> Path | None:
    path_parts = path.parts
    base_parts = base.parts
    if len(base_parts) > len(path_parts):
        return None
    if tuple(part.lower() for part in path_parts[: len(base_parts)]) != tuple(part.lower() for part in base_parts):
        return None
    rest = path_parts[len(base_parts) :]
    return Path(*rest) if rest else Path(".")


def unique_paths(paths: list[Path]) -> list[Path]:
    result: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        key = path.as_posix().lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(path)
    return result


def forbidden_payload_check(final_app: Path) -> RuntimeCheck:
    findings: list[str] = []
    if not final_app.exists():
        return RuntimeCheck("forbidden payload files", "fail", f"Missing final_app: {final_app}")
    for path in sorted(final_app.rglob("*")):
        if is_forbidden_payload_path(path, final_app):
            findings.append(path.relative_to(final_app).as_posix())
    if findings:
        return RuntimeCheck("forbidden payload files", "fail", "Forbidden files were packaged: " + ", ".join(findings[:10]))
    return RuntimeCheck("forbidden payload files", "pass", "No forbidden credential, log, cache, temp, or build_env files were found.")


def is_forbidden_payload_path(path: Path, root: Path) -> bool:
    relative_parts = [part.lower() for part in path.relative_to(root).parts]
    if any(part in FORBIDDEN_DIRS for part in relative_parts):
        return True
    if not path.is_file():
        return False

    name = path.name.lower()
    if is_allowed_runtime_certificate(relative_parts, name):
        return False
    if any(fnmatch.fnmatch(name, pattern.lower()) for pattern in FORBIDDEN_PATTERNS):
        return True
    if name in FORBIDDEN_EXACT_NAMES:
        return True
    if name.startswith(".env"):
        return True

    suffix = path.suffix.lower()
    stem = path.stem.lower()
    if suffix in FORBIDDEN_CONFIG_SUFFIXES:
        if any(marker in stem for marker in FORBIDDEN_CONFIG_MARKERS):
            return True
        if any(marker in stem for marker in FORBIDDEN_AUTH_MARKERS):
            return True
    return False


def is_allowed_runtime_certificate(relative_parts: list[str], name: str) -> bool:
    return name == "cacert.pem" and "certifi" in relative_parts


def build_env_separation_check(context: StudioContext, final_app: Path) -> RuntimeCheck:
    build_env = context.output_dir / "build_env"
    if build_env.exists() and not build_env.is_relative_to(final_app):
        return RuntimeCheck("build_env separation", "pass", f"build_env is outside final_app: {build_env}")
    if not build_env.exists():
        return RuntimeCheck("build_env separation", "warn", "build_env was not found when verification ran.")
    return RuntimeCheck("build_env separation", "fail", f"build_env is inside final_app: {build_env}")


def size_check(name: str, path: Path) -> RuntimeCheck:
    if not path.exists():
        return RuntimeCheck(name, "fail", f"Missing: {path}")
    size = directory_size(path)
    mb = size / 1024 / 1024
    status = "warn" if size >= 250 * 1024 * 1024 else "pass"
    detail = f"{size} bytes ({mb:.1f} MB)"
    if status == "warn":
        detail += "; large frozen-folder output, review bundled dependencies and data files."
    return RuntimeCheck(name, status, detail)


def add_data_size_check(context: StudioContext, build_profile: dict[str, Any]) -> RuntimeCheck:
    add_data = build_profile.get("add_data") if isinstance(build_profile, dict) else None
    if not isinstance(add_data, list) or not add_data:
        return RuntimeCheck("add-data source size", "warn", "No add_data entries are listed.")
    total = 0
    large: list[str] = []
    for item in add_data:
        if not isinstance(item, dict):
            continue
        source = context.source_root / str(item.get("source") or "")
        size = directory_size(source) if source.is_dir() else source.stat().st_size if source.is_file() else 0
        total += size
        if size >= 25 * 1024 * 1024:
            large.append(f"{source.name}={size} bytes")
    mb = total / 1024 / 1024
    status = "warn" if large else "pass"
    detail = f"{total} bytes ({mb:.1f} MB)"
    if large:
        detail += "; large add-data candidates: " + ", ".join(large[:5])
    return RuntimeCheck("add-data source size", status, detail)


def directory_size(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    if not path.is_dir():
        return 0
    return sum(file.stat().st_size for file in path.rglob("*") if file.is_file())


def uses_playwright(build_profile: dict[str, Any]) -> bool:
    collect_all = build_profile.get("collect_all") if isinstance(build_profile, dict) else []
    return isinstance(collect_all, list) and any(str(item).lower() == "playwright" for item in collect_all)


def overall_status(checks: list[RuntimeCheck]) -> str:
    statuses = {check.status for check in checks}
    if "fail" in statuses:
        return "fail"
    if "warn" in statuses:
        return "warn"
    return "pass"


def runtime_report_markdown(result: RuntimeCheckResult) -> str:
    lines = [
        "# Frozen-Folder Distribution Check Report",
        "",
        f"- app_id: `{result.app_id}`",
        f"- overall_status: `{result.overall_status}`",
        "",
        "| Status | Check | Detail |",
        "| --- | --- | --- |",
    ]
    lines.extend(f"| {check.status} | {check.name} | {check.detail} |" for check in result.checks)
    if result.evidence:
        lines.extend(["", "## Evidence", "", "```json", json.dumps(result.evidence, ensure_ascii=False, indent=2), "```"])
    lines.extend(["", "Normal App Studio registration verifies the generated exe/frozen-folder payload, not runtime/app_env."])
    return "\n".join(lines) + "\n"


def write_runtime_reports(context: StudioContext, output_dir: Path, result: RuntimeCheckResult) -> None:
    report = runtime_report_markdown(result)
    write_text(output_dir / "runtime_check_report.md", report)
    write_json(output_dir / "runtime_check_result.json", result.to_dict())
    log_dir = context.repo_root / "data" / "logs" / "app_studio"
    write_text(log_dir / f"{context.app_id}_runtime_check_report.md", report)
    write_json(log_dir / f"{context.app_id}_runtime_check_result.json", result.to_dict())
