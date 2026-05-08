from __future__ import annotations

import shutil
from pathlib import Path

from .file_classifier import inventory_markdown, toolhubignore_suggestion_markdown
from .icon_generator import generate_local_png, image_api_summary
from .models import BuildPlan, DependencyReport, GeneratedArtifacts, IconCandidateAsset, SecretScanReport, SourceInventory, StudioContext
from .secret_scanner import secret_report_markdown
from .util import copy_file_preserving_root, reset_output_dir, write_bytes, write_json, write_text


def export_suggestion(
    context: StudioContext,
    inventory: SourceInventory,
    dependency_report: DependencyReport,
    secret_report: SecretScanReport,
    plan: BuildPlan,
    artifacts: GeneratedArtifacts,
) -> Path:
    output_dir = reset_output_dir(context.entry, context.app_id, preserve_relative_paths=["build_env", "build_tmp/pip_cache"])
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
    write_text(icon_work / "icon_fallback.svg", artifacts.icon_svg)
    write_text(icon_work / "icon_final.svg", artifacts.icon_svg)
    icon_final_png = artifacts.icon_final_png or generate_local_png(context, artifacts.icon_prompt_revision or artifacts.icon_prompt_initial, "")
    write_bytes(icon_work / "icon_final.png", icon_final_png)
    if artifacts.icon_ai_report:
        write_text(icon_work / "ai_generation_report.md", artifacts.icon_ai_report)
    if artifacts.icon_candidate_png:
        write_bytes(icon_work / "icon_candidate_1.png", artifacts.icon_candidate_png)
    if artifacts.icon_candidate_url:
        write_text(icon_work / "icon_candidate_1.url.txt", artifacts.icon_candidate_url + "\n")
    write_icon_candidates(icon_work, artifacts)

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
    candidates = artifacts.icon_candidates or legacy_icon_candidates(artifacts)
    for candidate in candidates:
        if candidate.png and candidate.file_name:
            write_bytes(icon_work / candidate.file_name, candidate.png)
        if candidate.url and candidate.url_file_name:
            write_text(icon_work / candidate.url_file_name, candidate.url + "\n")
    write_json(
        icon_work / "candidate_manifest.json",
        {
            "schema_version": 2,
            "standard_icon_size": "512x512",
            "api_icon_size": "1024x1024",
            "legacy_candidate_png": "icon_candidate_1.png",
            "function_interpretation": artifacts.icon_design_brief or artifacts.import_plan.get("icon_function_interpretation", {}),
            "image_api_summary": image_api_summary(candidates, {"preset": artifacts.import_plan.get("icon_style_preset", "")}),
            "candidates": [candidate.manifest_entry() for candidate in candidates],
        },
    )


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
