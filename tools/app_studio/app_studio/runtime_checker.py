from __future__ import annotations

import fnmatch
from pathlib import Path
from typing import Any

from .models import BuildPlan, RuntimeCheck, RuntimeCheckResult, StudioContext
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
        required_data_files_check(bin_root, build_profile),
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
    return RuntimeCheckResult(context.app_id, overall_status(checks), checks)


def verify_legacy_runtime(context: StudioContext, output_dir: Path) -> RuntimeCheckResult:
    checks = [
        RuntimeCheck(
            "legacy runtime check",
            "warn",
            "Normal App Studio registration now verifies frozen-folder distribution output. Legacy app_env runtime probing is skipped for this path.",
        )
    ]
    return RuntimeCheckResult(context.app_id, overall_status(checks), checks)


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


def required_data_files_check(bin_root: Path, build_profile: dict[str, Any]) -> RuntimeCheck:
    add_data = build_profile.get("add_data") if isinstance(build_profile, dict) else None
    if not isinstance(add_data, list) or not add_data:
        return RuntimeCheck("required add-data files", "warn", "No add_data entries are listed in build_profile.json.")
    missing: list[str] = []
    for item in add_data:
        if not isinstance(item, dict):
            continue
        source = str(item.get("source") or "")
        destination = str(item.get("destination") or "")
        if not source or not destination:
            continue
        expected = bin_root / destination / Path(source).name
        if not expected.exists():
            missing.append(expected.as_posix())
    if missing:
        return RuntimeCheck("required add-data files", "fail", "Missing packaged data files: " + ", ".join(missing[:10]))
    return RuntimeCheck("required add-data files", "pass", f"{len(add_data)} packaged data item(s) were found.")


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
    lines.extend(["", "Normal App Studio registration verifies the generated exe/frozen-folder payload, not runtime/app_env."])
    return "\n".join(lines) + "\n"


def write_runtime_reports(context: StudioContext, output_dir: Path, result: RuntimeCheckResult) -> None:
    report = runtime_report_markdown(result)
    write_text(output_dir / "runtime_check_report.md", report)
    write_json(output_dir / "runtime_check_result.json", result.to_dict())
    log_dir = context.repo_root / "data" / "logs" / "app_studio"
    write_text(log_dir / f"{context.app_id}_runtime_check_report.md", report)
    write_json(log_dir / f"{context.app_id}_runtime_check_result.json", result.to_dict())
