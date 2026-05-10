from __future__ import annotations

import shutil
from pathlib import Path

from .default_icon import DEFAULT_ICON_REASON, DEFAULT_ICON_SOURCE, default_icon_png
from .file_classifier import inventory_markdown, toolhubignore_suggestion_markdown
from .icon_generator import image_api_summary
from .models import BuildPlan, DependencyReport, GeneratedArtifacts, IconCandidateAsset, SecretScanReport, SourceInventory, StudioContext
from .secret_scanner import secret_report_markdown
from .trace import BUILD_ENV_DIRNAME, BUILD_TMP_DIRNAME
from .util import copy_file_preserving_root, reset_output_dir, write_bytes, write_json, write_text


def export_suggestion(
    context: StudioContext,
    inventory: SourceInventory,
    dependency_report: DependencyReport,
    secret_report: SecretScanReport,
    plan: BuildPlan,
    artifacts: GeneratedArtifacts,
) -> Path:
    output_dir = reset_output_dir(
        context.entry,
        context.app_id,
        preserve_relative_paths=[BUILD_ENV_DIRNAME, f"{BUILD_TMP_DIRNAME}/pip"],
    )
    write_json(output_dir / "import_plan.json", artifacts.import_plan)
    if artifacts.build_profile:
        write_json(output_dir / "build_profile.json", artifacts.build_profile)
    if artifacts.exe_readiness:
        write_json(output_dir / "exe_readiness.json", artifacts.exe_readiness)
    inventory_report = inventory_markdown(inventory)
    write_text(output_dir / "file_inventory.md", inventory_report)
    write_text(output_dir / "file_inventory_report.md", inventory_report)
    write_json(output_dir / "file_inventory.json", inventory.to_dict())
    toolhubignore_suggestion = toolhubignore_suggestion_markdown(inventory)
    if toolhubignore_suggestion:
        write_text(output_dir / "suggested_toolhubignore.md", toolhubignore_suggestion)
    write_json(output_dir / "dependency_report.json", dependency_report.to_dict())
    write_text(output_dir / "secret_scan_report.md", secret_report_markdown(secret_report, context.source_root))
    write_json(output_dir / "secret_scan_report.json", secret_report.to_dict())
    write_text(output_dir / "build_plan.md", artifacts.build_plan_md)
    write_text(output_dir / "proposed_app.yaml", artifacts.app_yaml)
    write_text(output_dir / "proposed_README.md", artifacts.readme)
    write_text(output_dir / "proposed_requirements.txt", artifacts.requirements)

    icon_work = output_dir / "icon_work"
    write_text(icon_work / "icon_prompt_initial.md", artifacts.icon_prompt_initial)
    write_text(icon_work / "icon_prompt_revision.md", artifacts.icon_prompt_revision)
    # Legacy SVG compatibility artifact. Current App Studio icon selection uses PNG
    # API candidates, uploaded PNG overrides, or the ToolHub common default icon.
    write_text(icon_work / "icon_fallback.svg", artifacts.icon_svg)
    write_text(icon_work / "icon_final.svg", artifacts.icon_svg)
    icon_final_png = artifacts.icon_final_png or default_icon_png()
    write_bytes(icon_work / "icon_final.png", icon_final_png)
    if artifacts.icon_ai_report:
        write_text(icon_work / "ai_generation_report.md", artifacts.icon_ai_report)
    if artifacts.icon_candidate_png:
        write_bytes(icon_work / "icon_candidate_1.png", artifacts.icon_candidate_png)
    if artifacts.icon_candidate_url:
        write_text(icon_work / "icon_candidate_1.url.txt", artifacts.icon_candidate_url + "\n")
    write_icon_candidates(icon_work, artifacts)
    write_json(icon_work / "ai_generation_report.json", ai_generation_report_json(artifacts))

    final_app = output_dir / "final_app"
    write_text(final_app / "app.yaml", artifacts.app_yaml)
    write_text(final_app / "README.md", artifacts.readme)
    write_text(final_app / "requirements.txt", artifacts.requirements)
    write_bytes(final_app / "icon.png", icon_final_png)
    write_text(final_app / "icon.svg", artifacts.icon_svg)
    if artifacts.build_profile:
        write_json(final_app / "build_profile.json", artifacts.build_profile)
    if artifacts.exe_readiness:
        write_json(final_app / "exe_readiness.json", artifacts.exe_readiness)
    source_lock = context.source_root / "requirements.lock"
    if source_lock.is_file():
        shutil.copy2(source_lock, final_app / "requirements.lock")
    populate_final_app_sources(context, inventory, plan, final_app)
    (output_dir / "app_pack").mkdir(parents=True, exist_ok=True)
    write_text(output_dir / "execution_test_report.md", "# Execution Test Report\n\nNot run yet. Apply must run execution checks.\n")
    write_text(output_dir / "approval_record.md", "# Approval Record\n\nNot approved yet.\n")
    return output_dir


def write_icon_candidates(icon_work: Path, artifacts: GeneratedArtifacts) -> None:
    candidates = [candidate for candidate in (artifacts.icon_candidates or legacy_icon_candidates(artifacts)) if not candidate.is_fallback]
    for candidate in candidates:
        if candidate.png and candidate.file_name:
            write_bytes(icon_work / candidate.file_name, candidate.png)
        if candidate.url and candidate.url_file_name:
            write_text(icon_work / candidate.url_file_name, candidate.url + "\n")
    summary = artifacts.import_plan.get("icon_ai_diagnostics")
    if not isinstance(summary, dict):
        summary = image_api_summary(candidates, {"preset": artifacts.import_plan.get("icon_style_preset", "")})
    write_json(
        icon_work / "candidate_manifest.json",
        {
            "schema_version": 3,
            "standard_icon_size": "512x512",
            "api_icon_size": "1024x1024",
            "legacy_candidate_png": "icon_candidate_1.png" if candidates else "",
            "function_interpretation": artifacts.icon_design_brief or artifacts.import_plan.get("icon_function_interpretation", {}),
            "image_api_summary": summary,
            "candidates": [candidate.manifest_entry() for candidate in candidates],
        },
    )


def ai_generation_report_json(artifacts: GeneratedArtifacts) -> dict[str, object]:
    candidates = [candidate for candidate in (artifacts.icon_candidates or legacy_icon_candidates(artifacts)) if not candidate.is_fallback]
    summary = artifacts.import_plan.get("icon_ai_diagnostics")
    if not isinstance(summary, dict):
        summary = image_api_summary(candidates, {"preset": artifacts.import_plan.get("icon_style_preset", "")})
    selected_icon_source = str(artifacts.import_plan.get("selected_icon_source") or summary.get("selected_icon_source") or DEFAULT_ICON_SOURCE)
    default_icon_used = bool(artifacts.import_plan.get("default_icon_used", selected_icon_source == DEFAULT_ICON_SOURCE))
    return {
        "schema_version": 1,
        "text_prompt_generation_status": report_value(artifacts.icon_ai_report, "text_prompt_generation_status") or report_value(artifacts.icon_ai_report, "status"),
        "image_generation_status": "success" if summary.get("image_api_success") else "failed",
        "image_model": summary.get("model", ""),
        "api_candidate_count": summary.get("api_candidate_count", 0),
        "failure_class": summary.get("failure_class", ""),
        "failure_message": summary.get("failure_message", ""),
        "admin_next_action": summary.get("admin_next_action", ""),
        "selected_icon_source": selected_icon_source,
        "default_icon_used": default_icon_used,
        "default_icon_reason": artifacts.import_plan.get("default_icon_reason") or summary.get("default_icon_reason", DEFAULT_ICON_REASON),
        "icon_status": artifacts.import_plan.get("icon_status") or summary.get("icon_status", ""),
        "package_secret_scan_status": summary.get("package_secret_scan_status", "not_recorded"),
        "ai_payload_secret_scan_status": summary.get("ai_payload_secret_scan_status", "not_run"),
        "ai_submission_blocked": summary.get("ai_submission_blocked", False),
        "ai_submission_block_reason": summary.get("ai_submission_block_reason", ""),
    }


def report_value(report: str, key: str) -> str:
    prefix = f"{key}:"
    for line in (report or "").splitlines():
        stripped = line.strip()
        if stripped.startswith(prefix):
            return stripped[len(prefix):].strip()
    return ""


def legacy_icon_candidates(artifacts: GeneratedArtifacts) -> list[IconCandidateAsset]:
    if artifacts.icon_candidate_png:
        return [
            IconCandidateAsset(
                candidate_id="icon_candidate_1",
                number=1,
                source="api_or_legacy",
                prompt=artifacts.icon_prompt_revision or artifacts.icon_prompt_initial,
                model="unknown",
                status="legacy",
                resolution="unknown",
                is_fallback=False,
                png=artifacts.icon_candidate_png,
                file_name="icon_candidate_1.png",
                notes="Legacy single PNG candidate.",
            )
        ]
    if artifacts.icon_candidate_url:
        return [
            IconCandidateAsset(
                candidate_id="icon_candidate_1",
                number=1,
                source="api_or_legacy",
                prompt=artifacts.icon_prompt_revision or artifacts.icon_prompt_initial,
                model="unknown",
                status="legacy",
                resolution="unknown",
                is_fallback=False,
                url=artifacts.icon_candidate_url,
                url_file_name="icon_candidate_1.url.txt",
                notes="Legacy single URL candidate.",
            )
        ]
    return []


def populate_final_app_sources(context: StudioContext, inventory: SourceInventory, plan: BuildPlan, final_app: Path) -> None:
    if plan.mode == "existing-exe":
        bin_dir = final_app / "bin"
        bin_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(context.entry, bin_dir / context.entry.name)
        return

    if plan.mode == "frozen-folder":
        bin_dir = final_app / "bin"
        bin_dir.mkdir(parents=True, exist_ok=True)
        write_text(
            bin_dir / "BUILD_REQUIRED.txt",
            "Build this app with a folder-based frozen output such as PyInstaller --onedir. Do not use --onefile as the standard ToolHub packaging mode.\n",
        )
        return

    src_dir = final_app / "src"
    for source in inventory.included_files:
        if source.name.lower() in {"requirements.txt", "requirements.lock", "pyproject.toml", "readme.md", "README.md".lower()}:
            continue
        copy_file_preserving_root(source, context.source_root, src_dir)


def copy_pack_to_output(package_path: Path, output_dir: Path) -> None:
    destination = output_dir / "app_pack" / package_path.name
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(package_path, destination)
