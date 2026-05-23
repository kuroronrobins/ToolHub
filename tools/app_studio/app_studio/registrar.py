from __future__ import annotations

import copy
import json
import shutil
import time
import zipfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from .app_pack_contract import (
    APP_PACK_REQUIRED_APP_FILES,
    app_pack_required_entries,
    app_pack_requirements_lock_entry,
    app_relative_path,
    app_studio_frozen_folder_manifest,
    normalize_app_relative_entry,
    normalize_policy_value,
    normalize_yaml_scalar,
    yaml_section_scalar,
)
from .exporter import copy_pack_to_output
from .models import BuildPlan, StudioContext
from .payload_policy import is_forbidden_packaged_payload
from .util import assert_within, file_sha256, timestamp, write_json, write_text


BACKUP_STRATEGY = "move_existing_app_directory"
BACKUP_SAFETY_NOTE = (
    "Existing apps/<app_id> is moved under backups/app_studio before replacement; "
    "release/app_manifest.json is copied beside it for manual rollback."
)
APP_PACK_STRATEGY = "direct_zip_from_apps_dir"
APP_PACK_COMPRESSION = zipfile.ZIP_DEFLATED
APP_PACK_COMPRESSLEVEL = 1
APP_PACK_COMPRESSION_NAME = "ZIP_DEFLATED"
APP_PACK_COMPRESSION_POLICY = "balanced_size_speed"
APP_PACK_COMPRESSION_POLICY_NOTE = (
    "Use ZIP_DEFLATED compresslevel=1 for every normal App Studio registration. "
    "This keeps release/update payloads materially smaller than uncompressed zip while avoiding the slower high-compression levels."
)
APP_PACK_DISTRIBUTION_NOTE = (
    "App Pack generation never skips required-entry inspection, SHA256 calculation, or manifest updates; "
    "larger uncompressed App Packs would increase release storage and update transfer size."
)
APP_PACK_REJECTED_COMPRESSION_OPTIONS = [
    "ZIP_STORED: fastest, but produces much larger App Packs and update payloads.",
    "ZIP_DEFLATED level 0: valid in Python zipfile, but effectively uncompressed and larger without distribution benefit.",
    "ZIP_DEFLATED level 6 or 9: smaller than level 1, but slower and not enough smaller to justify as the default registration path.",
    "app-specific compression switching: rejected to keep one standard App Pack generation path.",
]
REGISTRATION_TOP_LEVEL_STEPS = {
    "backup_existing_total",
    "remove_existing_app",
    "copy_final_app_to_apps",
    "manifest_update_before_pack",
    "package_app_pack_total",
    "copy_pack_to_output_mirror",
}


@contextmanager
def _registration_step(
    records: list[dict[str, Any]] | None,
    name: str,
    detail: str = "",
) -> Iterator[dict[str, Any]]:
    started = time.perf_counter()
    record: dict[str, Any] = {"name": name, "status": "pass", "detail": detail}
    try:
        yield record
    except Exception as exc:
        record["status"] = "fail"
        record["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        record["duration_seconds"] = round(time.perf_counter() - started, 3)
        if records is not None:
            records.append(record)


def _directory_stats(path: Path) -> dict[str, int]:
    files = 0
    total_bytes = 0
    if not path.exists():
        return {"files": 0, "bytes": 0}
    for file in path.rglob("*"):
        if file.is_file():
            files += 1
            total_bytes += file.stat().st_size
    return {"files": files, "bytes": total_bytes}


def _source_stats(path: Path) -> dict[str, int]:
    stats = _directory_stats(path)
    src_stats = _directory_stats(path / "src")
    return {
        "files": stats["files"],
        "bytes": stats["bytes"],
        "src_files": src_stats["files"],
        "src_bytes": src_stats["bytes"],
    }


def _format_bytes(value: int) -> str:
    amount = float(value)
    for unit in ("B", "KB", "MB", "GB"):
        if amount < 1024 or unit == "GB":
            if unit == "B":
                return f"{int(amount)} {unit}"
            return f"{amount:.1f} {unit}"
        amount /= 1024
    return f"{value} B"


def _payload_detail(payload: dict[str, Any]) -> str:
    return (
        f"run_entry={payload['run_entry']}; "
        f"sha256={payload['run_entry_sha256']}; "
        f"files={payload['files']}; bytes={payload['bytes']} ({_format_bytes(int(payload['bytes']))}); "
        f"src_files={payload['src_files']}; src_bytes={payload['src_bytes']} ({_format_bytes(int(payload['src_bytes']))}); "
        f"runtime_check={payload['runtime_check_evidence']}"
    )


def write_registration_copy_report(
    output_dir: Path,
    context: StudioContext,
    records: list[dict[str, Any]],
) -> None:
    total_seconds = round(
        sum(
            float(record.get("duration_seconds") or 0.0)
            for record in records
            if record.get("name") in REGISTRATION_TOP_LEVEL_STEPS
        ),
        3,
    )
    leaf_seconds = round(
        sum(
            float(record.get("duration_seconds") or 0.0)
            for record in records
            if not str(record.get("name") or "").endswith("_total")
        ),
        3,
    )
    write_json(
        output_dir / "registration_copy_breakdown.json",
        {
            "app_id": context.app_id,
            "top_level_recorded_seconds": total_seconds,
            "leaf_recorded_seconds": leaf_seconds,
            "records": records,
            "strategies": {
                "backup": {
                    "standard_strategy": BACKUP_STRATEGY,
                    "safety_note": BACKUP_SAFETY_NOTE,
                    "compression": "none",
                    "rejected_options": [
                        "zip backup: preserves shallow backup path but is dominated by compression time",
                        "App Pack only backup: fast but does not preserve a possibly divergent apps/<app_id> tree",
                    ],
                },
                "app_pack": {
                    "standard_strategy": APP_PACK_STRATEGY,
                    "selected_policy": APP_PACK_COMPRESSION_POLICY,
                    "policy_note": APP_PACK_COMPRESSION_POLICY_NOTE,
                    "distribution_note": APP_PACK_DISTRIBUTION_NOTE,
                    "compression": APP_PACK_COMPRESSION_NAME,
                    "compresslevel": APP_PACK_COMPRESSLEVEL,
                    "rejected_options": APP_PACK_REJECTED_COMPRESSION_OPTIONS,
                },
            },
            "safety": {
                "app_pack_structure_changed": False,
                "required_entry_inspection_skipped": False,
                "sha256_calculation_skipped": False,
                "manifest_update_skipped": False,
                "zip_compression": APP_PACK_COMPRESSION_NAME,
                "zip_compresslevel": APP_PACK_COMPRESSLEVEL,
                "zip_compression_policy": APP_PACK_COMPRESSION_POLICY,
                "backup_strategy": BACKUP_STRATEGY,
            },
        },
    )
    lines = [
        "# Registration Copy Report",
        "",
        f"- app_id: `{context.app_id}`",
        f"- top_level_recorded_seconds: `{total_seconds:.3f}`",
        f"- leaf_recorded_seconds: `{leaf_seconds:.3f}`",
        "- safety: App Pack structure, required-entry inspection, SHA256 calculation, and manifest update are preserved.",
        f"- backup_strategy: `{BACKUP_STRATEGY}`",
        f"- backup_safety_note: {BACKUP_SAFETY_NOTE}",
        f"- app_pack_strategy: `{APP_PACK_STRATEGY}`",
        f"- app_pack_compression_policy: `{APP_PACK_COMPRESSION_POLICY}`",
        f"- app_pack_compression_policy_note: {APP_PACK_COMPRESSION_POLICY_NOTE}",
        f"- app_pack_distribution_note: {APP_PACK_DISTRIBUTION_NOTE}",
        f"- app_pack_zip_compression: `{APP_PACK_COMPRESSION_NAME}`",
        f"- app_pack_zip_compresslevel: `{APP_PACK_COMPRESSLEVEL}`",
        "- rejected_backup_options: zip backup is dominated by compression time; App Pack only backup does not preserve a divergent apps tree.",
        f"- rejected_app_pack_options: {'; '.join(APP_PACK_REJECTED_COMPRESSION_OPTIONS)}",
        "",
        "| Step | Status | Seconds | Detail |",
        "| --- | --- | ---: | --- |",
    ]
    for record in records:
        detail = str(record.get("detail") or record.get("error") or "").replace("|", "\\|")
        lines.append(
            f"| `{record.get('name', '')}` | `{record.get('status', '')}` | "
            f"{float(record.get('duration_seconds') or 0.0):.3f} | {detail} |"
        )
    lines.append("")
    write_text(output_dir / "registration_copy_report.md", "\n".join(lines))


def apply_registration(
    context: StudioContext,
    plan: BuildPlan,
    final_app_dir: Path,
    output_dir: Path,
    breakdown: list[dict[str, Any]] | None = None,
) -> Path:
    records = breakdown if breakdown is not None else []
    manifest_path = context.repo_root / "release" / "app_manifest.json"
    original_manifest = copy.deepcopy(load_app_manifest_json(manifest_path)) if manifest_path.is_file() else None
    backup_root: Path | None = None
    registration_mutated = False
    try:
        with _registration_step(records, "final_app_payload_gate", f"path={final_app_dir}") as record:
            payload = validate_final_app_registration_payload(final_app_dir, output_dir)
            record.update(payload)
            record["detail"] = _payload_detail(payload)

        with _registration_step(records, "backup_existing_total"):
            backup_root = backup_existing(context.repo_root, context.app_id, breakdown=records)
            registration_mutated = backup_root is not None

        apps_dir = context.repo_root / "apps"
        target = apps_dir / context.app_id
        assert_within(target, apps_dir, "app registration target")
        with _registration_step(records, "remove_existing_app", f"path={target}"):
            if target.exists():
                shutil.rmtree(target)
                registration_mutated = True
        with _registration_step(
            records,
            "copy_final_app_to_apps",
            (
                f"files={payload['files']}; bytes={payload['bytes']} ({_format_bytes(int(payload['bytes']))}); "
                f"src_files={payload['src_files']}"
            ),
        ) as record:
            shutil.copytree(final_app_dir, target)
            registration_mutated = True
            copied_entry = require_app_relative_file(target, str(payload["run_entry"]), "run.entry")
            copied_sha256 = file_sha256(copied_entry)
            if copied_sha256 != payload["run_entry_sha256"]:
                raise ValueError(
                    "Copied run.entry SHA256 does not match final_app pre-copy gate: "
                    f"{payload['run_entry']} ({copied_sha256} != {payload['run_entry_sha256']})"
                )
            copied = _source_stats(target)
            record.update(
                {
                    "run_entry": payload["run_entry"],
                    "run_entry_sha256": copied_sha256,
                    "copied_files": copied["files"],
                    "copied_bytes": copied["bytes"],
                    "copied_src_files": copied["src_files"],
                    "copied_src_bytes": copied["src_bytes"],
                }
            )
            record["detail"] = (
                f"run_entry={payload['run_entry']}; sha256={copied_sha256}; "
                f"files={copied['files']}; bytes={copied['bytes']} ({_format_bytes(copied['bytes'])}); "
                f"src_files={copied['src_files']}; src_bytes={copied['src_bytes']} ({_format_bytes(copied['src_bytes'])})"
            )

        manifest_path = context.repo_root / "release" / "app_manifest.json"
        with _registration_step(records, "manifest_update_before_pack", f"path={manifest_path}"):
            manifest = load_app_manifest_json(manifest_path)
            manifest.setdefault("schema_version", 1)
            manifest.setdefault("channel", "stable")
            manifest.setdefault("apps", {})
            manifest["apps"][context.app_id] = manifest_entry_from_app_source(target, context, plan)
            write_json(manifest_path, manifest)
            registration_mutated = True
        with _registration_step(records, "package_app_pack_total"):
            package_path = package_app_pack(context.repo_root, context.app_id, breakdown=records)
        with _registration_step(records, "copy_pack_to_output_mirror", f"path={output_dir / 'app_pack'}"):
            copy_pack_to_output(package_path, output_dir)
        return package_path
    except Exception:
        if registration_mutated or backup_root is not None:
            try:
                rollback_registration(context.repo_root, context.app_id, backup_root, original_manifest, records)
            except Exception as rollback_exc:
                records.append(
                    {
                        "name": "rollback_registration",
                        "status": "fail",
                        "detail": f"{type(rollback_exc).__name__}: {rollback_exc}",
                        "duration_seconds": 0.0,
                    }
                )
        raise
    finally:
        write_registration_copy_report(output_dir, context, records)


def validate_final_app_registration_payload(final_app_dir: Path, output_dir: Path | None = None) -> dict[str, Any]:
    validate_no_forbidden_payload(final_app_dir)
    run_entry = require_app_yaml_file(final_app_dir, "run", "entry", "run.entry")
    run_entry_path = app_relative_path(final_app_dir, run_entry)
    run_entry_sha256 = file_sha256(run_entry_path)
    stats = _source_stats(final_app_dir)
    payload: dict[str, Any] = {
        "run_entry": run_entry,
        "run_entry_sha256": run_entry_sha256,
        "files": stats["files"],
        "bytes": stats["bytes"],
        "src_files": stats["src_files"],
        "src_bytes": stats["src_bytes"],
        "runtime_check_evidence": "not_available",
    }
    compare_runtime_run_entry_evidence(final_app_dir, run_entry, run_entry_sha256, output_dir, payload)
    return payload


def compare_runtime_run_entry_evidence(
    final_app_dir: Path,
    run_entry: str,
    run_entry_sha256: str,
    output_dir: Path | None,
    payload: dict[str, Any],
) -> None:
    if output_dir is None:
        return
    runtime_result_path = output_dir / "runtime_check_result.json"
    if not runtime_result_path.is_file():
        return
    data = json.loads(runtime_result_path.read_text(encoding="utf-8"))
    evidence = data.get("evidence") if isinstance(data, dict) else None
    if not isinstance(evidence, dict):
        payload["runtime_check_evidence"] = "missing"
        return

    recorded_entry = evidence.get("final_app_run_entry")
    recorded_sha256 = evidence.get("final_app_run_entry_sha256")
    compared = False
    if recorded_entry:
        normalized_entry = normalize_app_relative_entry(
            str(recorded_entry),
            final_app_dir,
            "runtime_check_result.json final_app_run_entry",
        )
        if normalized_entry != run_entry:
            raise ValueError(
                "final_app run.entry does not match runtime_check_result.json: "
                f"{run_entry} != {normalized_entry}"
            )
        payload["runtime_check_run_entry"] = normalized_entry
        compared = True
    if recorded_sha256:
        recorded_sha256_text = str(recorded_sha256)
        if recorded_sha256_text != run_entry_sha256:
            raise ValueError(
                "final_app run.entry SHA256 does not match runtime_check_result.json: "
                f"{run_entry} ({run_entry_sha256} != {recorded_sha256_text})"
            )
        payload["runtime_check_run_entry_sha256"] = recorded_sha256_text
        compared = True
    payload["runtime_check_evidence"] = "matched" if compared else "not_recorded"


def validate_no_forbidden_payload(final_app_dir: Path) -> None:
    if not final_app_dir.is_dir():
        raise FileNotFoundError(f"final_app is missing: {final_app_dir}")
    findings: list[str] = []
    for path in sorted(final_app_dir.rglob("*")):
        forbidden, reason = is_forbidden_packaged_payload(path.relative_to(final_app_dir), path.is_file())
        if forbidden:
            findings.append(f"{path.relative_to(final_app_dir).as_posix()} ({reason})")
    if findings:
        sample = "; ".join(findings[:10])
        suffix = f"; and {len(findings) - 10} more" if len(findings) > 10 else ""
        raise ValueError(f"final_app contains forbidden payload files: {sample}{suffix}")


def rollback_registration(
    repo_root: Path,
    app_id: str,
    backup_root: Path | None,
    original_manifest: dict[str, Any] | None,
    records: list[dict[str, Any]],
) -> None:
    apps_dir = repo_root / "apps"
    target = apps_dir / app_id
    manifest_path = repo_root / "release" / "app_manifest.json"
    assert_within(target, apps_dir, "app registration target")
    with _registration_step(records, "rollback_app_directory", f"path={target}"):
        if target.exists():
            shutil.rmtree(target)
        backup_app = backup_root / "app" if backup_root else None
        if backup_app and backup_app.is_dir():
            shutil.copytree(backup_app, target)
    with _registration_step(records, "rollback_manifest", f"path={manifest_path}"):
        if original_manifest is not None:
            write_json(manifest_path, original_manifest)


def backup_existing(
    repo_root: Path,
    app_id: str,
    breakdown: list[dict[str, Any]] | None = None,
) -> Path | None:
    app_dir = repo_root / "apps" / app_id
    manifest_path = repo_root / "release" / "app_manifest.json"
    manifest = load_app_manifest_json(manifest_path) if manifest_path.is_file() else {"apps": {}}
    app_exists = app_dir.exists()
    manifest_exists = app_id in (manifest.get("apps") or {})
    if not app_exists and not manifest_exists:
        return None

    backup_root = unique_backup_root(repo_root, app_id)
    assert_within(backup_root, repo_root / "backups", "backup target")
    backup_root.mkdir(parents=True, exist_ok=True)
    if app_exists:
        stats = _directory_stats(app_dir)
        with _registration_step(
            breakdown,
            "backup_existing_app_move",
            f"strategy={BACKUP_STRATEGY}; "
            f"files={stats['files']}; bytes={stats['bytes']} ({_format_bytes(stats['bytes'])})",
        ) as record:
            backup_app_dir = backup_root / "app"
            shutil.move(str(app_dir), str(backup_app_dir))
            record["backup_path"] = str(backup_app_dir)
            record["file_count"] = stats["files"]
            record["size_bytes"] = stats["bytes"]
            record["detail"] = (
                f"strategy={BACKUP_STRATEGY}; backup_path={backup_app_dir}; "
                f"files={stats['files']}; bytes={stats['bytes']} ({_format_bytes(stats['bytes'])})"
            )
    if manifest_path.is_file():
        with _registration_step(breakdown, "backup_manifest", f"path={manifest_path}"):
            shutil.copy2(manifest_path, backup_root / "app_manifest.json")
    return backup_root


def unique_backup_root(repo_root: Path, app_id: str) -> Path:
    base = repo_root / "backups" / "app_studio" / timestamp() / app_id
    if not base.exists():
        return base
    for index in range(2, 100):
        candidate = repo_root / "backups" / "app_studio" / f"{timestamp()}_{index}" / app_id
        if not candidate.exists():
            return candidate
    raise FileExistsError(f"Could not allocate a unique App Studio backup directory for app_id={app_id}")


def load_app_manifest_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"schema_version": 1, "channel": "stable", "apps": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def manifest_entry_from_app_source(app_dir: Path, context: StudioContext, plan: BuildPlan) -> dict[str, Any]:
    app_yaml = app_dir / "app.yaml"
    text = app_yaml.read_text(encoding="utf-8") if app_yaml.is_file() else ""
    version = yaml_section_scalar(text, "admin", "version") or context.version
    required_runtime = yaml_section_scalar(text, "runtime", "required_runtime")
    if required_runtime is None:
        required_runtime = plan.required_runtime
    return {
        "version": version,
        "package": f"app_packs/{context.app_id}-{version}.zip",
        "sha256": "",
        "required_core": ">=0.1.0",
        "required_runner": ">=0.1.0",
        "required_runtime": required_runtime,
        "enabled": False,
    }


def package_app_pack(
    repo_root: Path,
    app_id: str,
    breakdown: list[dict[str, Any]] | None = None,
) -> Path:
    manifest_path = repo_root / "release" / "app_manifest.json"
    with _registration_step(breakdown, "load_manifest_for_pack", f"path={manifest_path}"):
        manifest = load_app_manifest_json(manifest_path)
        app_entry = manifest.get("apps", {}).get(app_id)
        if not isinstance(app_entry, dict):
            raise ValueError(f"App is not listed in release/app_manifest.json: {app_id}")

    version = str(app_entry.get("version") or "0.1.0")
    app_dir = repo_root / "apps" / app_id
    with _registration_step(breakdown, "validate_app_pack_inputs", f"path={app_dir}"):
        if not app_dir.is_dir():
            raise FileNotFoundError(f"App directory is missing: {app_dir}")
        for required in APP_PACK_REQUIRED_APP_FILES:
            if not (app_dir / required).is_file():
                raise FileNotFoundError(f"Required app file is missing: {app_dir / required}")
        if not (app_dir / "icon.png").is_file() and not (app_dir / "icon.svg").is_file():
            raise FileNotFoundError(f"Required app icon is missing: {app_dir / 'icon.png'} or {app_dir / 'icon.svg'}")
        run_entry = require_app_yaml_file(app_dir, "run", "entry", "run.entry")
        display_icon = require_app_yaml_file(app_dir, "display", "icon", "display.icon")
        requirements_lock = app_pack_requirements_lock_entry(app_dir)
        if requirements_lock:
            require_app_relative_file(app_dir, requirements_lock, "runtime.requirements_lock")

    pack_manifest = {
        "schema_version": 1,
        "app_id": app_id,
        "version": version,
        "required_core": app_entry.get("required_core"),
        "required_runner": app_entry.get("required_runner"),
        "required_runtime": app_entry.get("required_runtime"),
        "package_sha256": "",
    }
    pack_manifest_text = json.dumps(pack_manifest, ensure_ascii=False, indent=2) + "\n"

    app_packs_dir = repo_root / "release" / "app_packs"
    app_packs_dir.mkdir(parents=True, exist_ok=True)
    package_path = app_packs_dir / f"{app_id}-{version}.zip"
    assert_within(package_path, app_packs_dir, "app pack")
    with _registration_step(breakdown, "remove_existing_app_pack", f"path={package_path}"):
        if package_path.exists():
            package_path.unlink()

    with _registration_step(
        breakdown,
        "compress_app_pack",
        f"strategy={APP_PACK_STRATEGY}; compression={APP_PACK_COMPRESSION_NAME}; "
        f"compresslevel={APP_PACK_COMPRESSLEVEL}; policy={APP_PACK_COMPRESSION_POLICY}; path={package_path}",
    ) as record:
        entry_count = 0
        with zipfile.ZipFile(
            package_path,
            "w",
            compression=APP_PACK_COMPRESSION,
            compresslevel=APP_PACK_COMPRESSLEVEL,
        ) as archive:
            for file in iter_app_pack_files(app_dir):
                archive.write(file, (Path(app_id) / file.relative_to(app_dir)).as_posix())
                entry_count += 1
            archive.writestr(f"{app_id}/pack_manifest.json", pack_manifest_text)
            entry_count += 1
        package_size = package_path.stat().st_size
        record["entry_count"] = entry_count
        record["size_bytes"] = package_size
        record["compression_policy"] = APP_PACK_COMPRESSION_POLICY
        record["compression"] = APP_PACK_COMPRESSION_NAME
        record["compresslevel"] = APP_PACK_COMPRESSLEVEL
        record["detail"] = (
            f"strategy={APP_PACK_STRATEGY}; compression={APP_PACK_COMPRESSION_NAME}; "
            f"compresslevel={APP_PACK_COMPRESSLEVEL}; policy={APP_PACK_COMPRESSION_POLICY}; entries={entry_count}; "
            f"size_bytes={package_size} ({_format_bytes(package_size)}); path={package_path}"
        )

    required_entries = app_pack_required_entries(
        app_id,
        run_entry=run_entry,
        display_icon=display_icon,
        requirements_lock=requirements_lock,
    )
    with _registration_step(breakdown, "inspect_app_pack_required_entries", f"path={package_path}") as record:
        with zipfile.ZipFile(package_path) as archive:
            names = {name.replace("\\", "/") for name in archive.namelist()}
            entry_count = len(names)
        missing_entries = sorted(required_entries - names)
        if missing_entries:
            raise FileNotFoundError(f"App Pack is missing required entries: {', '.join(missing_entries)}")
        record["entry_count"] = entry_count

    app_entry["package"] = f"app_packs/{app_id}-{version}.zip"
    with _registration_step(breakdown, "sha256_app_pack", f"path={package_path}") as record:
        app_entry["sha256"] = file_sha256(package_path)
        record["sha256"] = app_entry["sha256"]
        record["size_bytes"] = package_path.stat().st_size
    manifest["apps"][app_id] = app_entry
    with _registration_step(breakdown, "manifest_update_after_pack", f"path={manifest_path}"):
        write_json(manifest_path, manifest)
    return package_path


def require_app_yaml_file(app_dir: Path, section: str, key: str, label: str) -> str:
    app_yaml = app_dir / "app.yaml"
    text = app_yaml.read_text(encoding="utf-8")
    value = yaml_section_scalar(text, section, key)
    relative = normalize_app_relative_entry(value, app_dir, label)
    require_app_relative_file(app_dir, relative, label)
    return relative


def require_app_relative_file(app_dir: Path, relative: str, label: str) -> Path:
    path = app_relative_path(app_dir, relative)
    if not path.is_file():
        raise FileNotFoundError(f"Required app {label} file is missing: {path}")
    return path


def iter_app_pack_files(app_dir: Path) -> Iterator[Path]:
    for file in sorted(app_dir.rglob("*")):
        if not file.is_file():
            continue
        relative = file.relative_to(app_dir)
        if "__pycache__" in relative.parts:
            continue
        if file.suffix.lower() in {".pyc", ".pyo"}:
            continue
        if relative.as_posix() == "pack_manifest.json":
            continue
        yield file
