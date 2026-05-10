from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .models import BuildPlan, DependencyReport, SecretScanReport, SourceInventory, StudioContext
from .trace import planned_build_env_python
from .util import write_json, write_text


SENSITIVE_ENV_PARTS = ("key", "secret", "token", "password", "credential")
PYINSTALLER_OPTION_KEYS = {"paths", "hidden_imports", "add_data", "add_binaries", "collect_all"}


def default_build_profile(context: StudioContext, inventory: SourceInventory, dependency_report: DependencyReport) -> dict[str, Any]:
    profile: dict[str, Any] = {
        "schema_version": 1,
        "app_id": context.app_id,
        "source": "auto",
        "paths": [],
        "hidden_imports": [],
        "add_data": [],
        "add_binaries": [],
        "collect_all": [],
        "runtime_cwd": None,
        "environment": {},
        "required_files": [],
        "manual_checks": [],
        "warnings": [],
        "source_root": str(context.source_root),
        "source_root_origin": context.source_root_origin,
        "entry_relative": context.entry_relative.as_posix(),
        "inventory_summary": inventory.summary(),
    }

    profile["paths"] = [path.relative_to(context.source_root).as_posix() for path in pyinstaller_search_paths(context, inventory)]
    profile["hidden_imports"] = pyinstaller_hidden_imports(context, inventory)
    data_entries = [
        {"source": source.relative_to(context.source_root).as_posix(), "destination": destination}
        for source, destination in pyinstaller_data_files(context, inventory)
    ]
    data_entries.extend(
        {"source": source.relative_to(context.source_root).as_posix(), "destination": source.relative_to(context.source_root).as_posix()}
        for source in pyinstaller_python_source_data_dirs(context, inventory)
    )
    profile["add_data"] = unique_mappings(data_entries)
    profile["required_files"] = [item["source"] for item in profile["add_data"]]
    profile["manual_checks"].extend(
        f"{item.get('source_file', '-')}: {item.get('pattern', '-')} - {item.get('reason', '-')}"
        for item in inventory.manual_checks
    )

    dependencies = requirement_names(dependency_report.requirements) | {root.lower() for root in dependency_report.import_roots}
    if "playwright" in dependencies:
        profile["collect_all"] = ["playwright"]
        profile["manual_checks"].extend(
            [
                "Playwright のブラウザバイナリがビルド用環境で利用できることを確認してください。",
                "認証済み storage state は自動同梱しません。初回ログインまたは手動認証の流れを確認してください。",
                "ブラウザ画面、ファイル選択、待機型の操作は自動完了確認の対象外です。人間による起動確認を行ってください。",
            ]
        )
    if "flet" in dependencies:
        profile["hidden_imports"] = unique_strings([*profile["hidden_imports"], "flet_desktop"])
        profile["collect_all"] = unique_strings([*profile["collect_all"], "flet", "flet_desktop"])
        profile["manual_checks"].append(
            "Flet desktop runtime を検出しました。build_env で flet-desktop を同一バージョンに補完し、frozen-folder 起動確認を行ってください。"
        )

    if profile["add_data"]:
        profile["warnings"].append(
            "ビルド前注意: frozen-folder作成後、必要な設定ファイル・データファイルは配布物検証で自動確認されます。"
        )
    if len([record for record in inventory.records if record.include and record.path.suffix.lower() == ".py"]) > 1 and not profile["hidden_imports"]:
        profile["warnings"].append("Multiple Python files were detected but no hidden imports were inferred.")

    return profile


def saved_build_profile_path(context: StudioContext) -> Path:
    return context.repo_root / "data" / "app_studio" / "build_profiles" / f"{context.app_id}.json"


def load_build_profile(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"build profile JSON is invalid: {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"build profile must be a JSON object: {path}")
    return normalize_build_profile(data)


def normalize_build_profile(profile: dict[str, Any]) -> dict[str, Any]:
    normalized = {
        "schema_version": 1,
        "app_id": clean_string(profile.get("app_id")),
        "source": clean_string(profile.get("source")) or "manual",
        "paths": clean_string_list(profile.get("paths")),
        "hidden_imports": clean_string_list(profile.get("hidden_imports")),
        "add_data": clean_file_mappings(profile.get("add_data")),
        "add_binaries": clean_file_mappings(profile.get("add_binaries")),
        "collect_all": clean_string_list(profile.get("collect_all")),
        "runtime_cwd": clean_string(profile.get("runtime_cwd")),
        "environment": clean_environment(profile.get("environment")),
        "required_files": clean_string_list(profile.get("required_files")),
        "manual_checks": clean_string_list(profile.get("manual_checks")),
        "warnings": clean_string_list(profile.get("warnings")),
        "source_root": clean_string(profile.get("source_root")),
        "source_root_origin": clean_string(profile.get("source_root_origin")),
        "entry_relative": clean_string(profile.get("entry_relative")),
        "inventory_summary": profile.get("inventory_summary") if isinstance(profile.get("inventory_summary"), dict) else {},
    }
    if not normalized["required_files"]:
        normalized["required_files"] = [item["source"] for item in normalized["add_data"]]
    return normalized


def merge_build_profiles(base: dict[str, Any], override: dict[str, Any], source: str) -> dict[str, Any]:
    merged = normalize_build_profile(base)
    incoming = normalize_build_profile(override)
    merged["source"] = source
    if incoming.get("runtime_cwd"):
        merged["runtime_cwd"] = incoming["runtime_cwd"]
    for key in ["paths", "hidden_imports", "collect_all", "required_files", "manual_checks", "warnings"]:
        merged[key] = unique_strings([*merged.get(key, []), *incoming.get(key, [])])
    for key in ["add_data", "add_binaries"]:
        merged[key] = unique_mappings([*merged.get(key, []), *incoming.get(key, [])])
    merged["environment"] = {**merged.get("environment", {}), **incoming.get("environment", {})}
    return merged


def write_build_profile_files(context: StudioContext, output_dir: Path, profile: dict[str, Any], readiness: dict[str, Any]) -> None:
    write_json(output_dir / "build_profile.json", profile)
    write_text(output_dir / "build_profile_report.md", build_profile_markdown(profile, readiness))
    write_json(output_dir / "exe_readiness.json", readiness)
    write_text(output_dir / "exe_readiness_report.md", exe_readiness_markdown(readiness))
    write_json(saved_build_profile_path(context), profile)


def analyze_exe_readiness(
    context: StudioContext,
    plan: BuildPlan,
    inventory: SourceInventory,
    dependency_report: DependencyReport,
    secret_report: SecretScanReport,
    profile: dict[str, Any],
) -> dict[str, Any]:
    checks: list[dict[str, str]] = []
    if plan.mode != "frozen-folder":
        checks.append(readiness_check("build mode", "warn", f"Selected build mode is {plan.mode}; exe gate applies to frozen-folder only."))
    else:
        checks.append(readiness_check("build mode", "pass", "frozen-folder uses PyInstaller --onedir."))

    managed_python = managed_build_python(context)
    if managed_python:
        checks.append(readiness_check("managed build python", "pass", str(managed_python)))
    else:
        checks.append(readiness_check("managed build python", "warn", "build_env is not present yet. Apply creates a managed build environment under the App Studio output directory."))

    if has_requirements_lock(context, inventory):
        checks.append(readiness_check("requirements.lock", "pass", "A requirements.lock file is available."))
    else:
        checks.append(readiness_check("requirements.lock", "warn", "No requirements.lock was found. GenerateLock is recommended before formal distribution."))

    missing_profile_files = missing_required_files(context, profile)
    if missing_profile_files:
        checks.append(readiness_check("profile data files", "fail", "Missing source files: " + ", ".join(missing_profile_files)))
    elif profile.get("add_data"):
        checks.append(readiness_check("profile data files", "pass", f"{len(profile.get('add_data', []))} data file(s) will be passed to PyInstaller."))
    else:
        checks.append(readiness_check("profile data files", "warn", "No data files were inferred. Confirm this app does not need config/assets at runtime."))

    if profile.get("hidden_imports"):
        checks.append(readiness_check("hidden imports", "pass", f"{len(profile.get('hidden_imports', []))} hidden import candidate(s) were inferred."))
    else:
        checks.append(readiness_check("hidden imports", "warn", "No hidden imports were inferred. Dynamic imports may need manual profile entries."))

    dependencies = requirement_names(dependency_report.requirements) | {root.lower() for root in dependency_report.import_roots}
    if "playwright" in dependencies:
        checks.append(readiness_check("playwright browser dependency", "warn", "Playwright was detected. Browser binaries and login/manual flows require human launch verification."))
    if secret_report.blocks_apply:
        checks.append(readiness_check("secret scan", "fail", f"{len(secret_report.blocking_findings)} secret finding(s) block Apply."))
    elif secret_report.blocks_ai_submission or secret_report.findings:
        checks.append(readiness_check("secret scan", "warn", "Secret scan findings were classified as warnings/manual checks; Apply may continue if distribution checks pass."))

    overall = "fail" if any(check["status"] == "fail" for check in checks) else "warn" if any(check["status"] == "warn" for check in checks) else "pass"
    return {
        "app_id": context.app_id,
        "overall_status": overall,
        "checks": checks,
        "manual_checks": profile.get("manual_checks", []),
    }


def pyinstaller_profile_args(context: StudioContext, profile: dict[str, Any]) -> list[str]:
    normalized = normalize_build_profile(profile)
    args: list[str] = []
    for value in normalized["paths"]:
        args.extend(["--paths", str(resolve_profile_source(context, value))])
    for value in normalized["hidden_imports"]:
        args.extend(["--hidden-import", value])
    for value in normalized["collect_all"]:
        args.extend(["--collect-all", value])
    for item in normalized["add_data"]:
        args.extend(["--add-data", f"{resolve_profile_source(context, item['source'])}{os.pathsep}{item['destination']}"])
    for item in normalized["add_binaries"]:
        args.extend(["--add-binary", f"{resolve_profile_source(context, item['source'])}{os.pathsep}{item['destination']}"])
    return args


def pyinstaller_search_paths(context: StudioContext, inventory: SourceInventory) -> list[Path]:
    paths: set[Path] = set()
    for record in inventory.records:
        if not record.include or record.path.suffix.lower() != ".py":
            continue
        relative = Path(record.relative_path)
        if len(relative.parts) > 1:
            paths.add((context.source_root / relative.parts[0]).resolve())
    return sorted((path for path in paths if path.is_dir()), key=lambda path: path.as_posix().lower())


def pyinstaller_hidden_imports(context: StudioContext, inventory: SourceInventory) -> list[str]:
    modules: set[str] = set()
    for record in inventory.records:
        if not record.include or record.path.suffix.lower() != ".py":
            continue
        relative = Path(record.relative_path).with_suffix("")
        if not relative.parts:
            continue
        if module_parts_are_valid(relative.parts):
            modules.add(".".join(relative.parts))
        if len(relative.parts) > 1 and module_parts_are_valid(relative.parts[1:]):
            modules.add(".".join(relative.parts[1:]))
    return sorted(module for module in modules if module != context.entry.stem)


def pyinstaller_data_files(context: StudioContext, inventory: SourceInventory) -> list[tuple[Path, str]]:
    data_files: list[tuple[Path, str]] = []
    for record in inventory.records:
        if not record.include or record.category != "asset":
            continue
        if record.path.suffix.lower() == ".py":
            continue
        relative = Path(record.relative_path)
        destination = relative.parent.as_posix()
        if destination == ".":
            destination = "."
        data_files.append((record.path, destination))
    return sorted(data_files, key=lambda item: item[0].as_posix().lower())


def pyinstaller_python_source_data_dirs(context: StudioContext, inventory: SourceInventory) -> list[Path]:
    dirs: set[Path] = set()
    for record in inventory.records:
        if not record.include or record.path.suffix.lower() != ".py":
            continue
        relative = Path(record.relative_path)
        if len(relative.parts) < 3:
            continue
        source_dir = context.source_root / relative.parts[0] / relative.parts[1]
        if source_dir.is_dir():
            dirs.add(source_dir.resolve())
    return sorted(dirs, key=lambda path: path.as_posix().lower())


def build_profile_markdown(profile: dict[str, Any], readiness: dict[str, Any]) -> str:
    lines = ["# Build Profile", "", f"- app_id: `{profile.get('app_id')}`", f"- source: `{profile.get('source')}`", f"- readiness: `{readiness.get('overall_status')}`", ""]
    lines.extend(
        [
            "## Source Scope",
            "",
            f"- source_root: `{profile.get('source_root', '-')}`",
            f"- source_root_origin: `{profile.get('source_root_origin', '-')}`",
            f"- entry_relative: `{profile.get('entry_relative', '-')}`",
        ]
    )
    summary = profile.get("inventory_summary") or {}
    if isinstance(summary, dict):
        lines.extend(
            [
                f"- included_count: {summary.get('included_count', 0)}",
                f"- excluded_count: {summary.get('excluded_count', 0)}",
                f"- blocked_count: {summary.get('blocked_count', 0)}",
                f"- manual_check_count: {summary.get('manual_check_count', 0)}",
                f"- excluded_directory_count: {summary.get('excluded_directory_count', 0)}",
                f"- sensitive_excluded_directory_count: {summary.get('sensitive_excluded_directory_count', 0)}",
                f"- sensitive_excluded_file_count: {summary.get('sensitive_excluded_file_count', 0)}",
            ]
        )
    lines.append("")
    for key in sorted(PYINSTALLER_OPTION_KEYS):
        lines.append(f"## {key}")
        values = profile.get(key) or []
        lines.append(f"- count: {len(values)}")
        if values:
            for value in values:
                lines.append(f"- `{json.dumps(value, ensure_ascii=False)}`")
        else:
            lines.append("- none")
        lines.append("")
    if profile.get("manual_checks"):
        lines.append("## Manual Checks")
        lines.extend(f"- {item}" for item in profile["manual_checks"])
        lines.append("")
    return "\n".join(lines)


def exe_readiness_markdown(readiness: dict[str, Any]) -> str:
    lines = ["# Exe Readiness", "", f"- app_id: `{readiness.get('app_id')}`", f"- overall_status: `{readiness.get('overall_status')}`", "", "| Status | Check | Detail |", "| --- | --- | --- |"]
    for check in readiness.get("checks", []):
        lines.append(f"| {check.get('status')} | {check.get('name')} | {check.get('detail')} |")
    if readiness.get("manual_checks"):
        lines.extend(["", "## Manual Checks", ""])
        lines.extend(f"- {item}" for item in readiness["manual_checks"])
    return "\n".join(lines) + "\n"


def readiness_check(name: str, status: str, detail: str) -> dict[str, str]:
    return {"name": name, "status": status, "detail": detail}


def managed_build_python(context: StudioContext) -> Path | None:
    build_env = planned_build_env_python(context)
    return build_env if build_env.is_file() else None


def has_requirements_lock(context: StudioContext, inventory: SourceInventory) -> bool:
    if (context.source_root / "requirements.lock").is_file():
        return True
    return any(record.include and record.path.name.lower() == "requirements.lock" for record in inventory.records)


def missing_required_files(context: StudioContext, profile: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    for relative in profile.get("required_files", []):
        if not resolve_profile_source(context, relative).exists():
            missing.append(str(relative))
    return missing


def resolve_profile_source(context: StudioContext, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else context.source_root / path


def requirement_names(requirements: list[str]) -> set[str]:
    names: set[str] = set()
    for requirement in requirements:
        head = requirement.split(";", 1)[0].strip()
        for marker in ["==", ">=", "<=", "~=", "!=", ">", "<", "["]:
            head = head.split(marker, 1)[0]
        if head:
            names.add(head.strip().lower().replace("_", "-"))
    return names


def clean_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def clean_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return unique_strings(str(item).strip() for item in value if str(item).strip())


def clean_file_mappings(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    mappings: list[dict[str, str]] = []
    for item in value:
        if isinstance(item, dict):
            source = clean_string(item.get("source"))
            destination = clean_string(item.get("destination"))
        else:
            source = None
            destination = None
        if source and destination:
            mappings.append({"source": source, "destination": destination})
    return unique_mappings(mappings)


def clean_environment(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    cleaned: dict[str, str] = {}
    for key, raw_value in value.items():
        key_text = str(key).strip()
        value_text = str(raw_value).strip()
        lower = f"{key_text} {value_text}".lower()
        if not key_text or any(part in lower for part in SENSITIVE_ENV_PARTS):
            continue
        cleaned[key_text] = value_text
    return cleaned


def unique_strings(values: Any) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip()
        key = text.lower()
        if not text or key in seen:
            continue
        seen.add(key)
        result.append(text)
    return result


def unique_mappings(values: list[dict[str, str]]) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for item in values:
        key = (item["source"].lower(), item["destination"].lower())
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def module_parts_are_valid(parts: tuple[str, ...]) -> bool:
    return bool(parts) and all(part.isidentifier() for part in parts)
