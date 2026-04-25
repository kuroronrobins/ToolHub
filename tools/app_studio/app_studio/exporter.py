from __future__ import annotations

import shutil
from pathlib import Path

from .file_classifier import inventory_markdown
from .models import BuildPlan, DependencyReport, GeneratedArtifacts, SecretScanReport, SourceInventory, StudioContext
from .secret_scanner import secret_report_markdown
from .util import copy_file_preserving_root, reset_output_dir, write_json, write_text


def export_suggestion(
    context: StudioContext,
    inventory: SourceInventory,
    dependency_report: DependencyReport,
    secret_report: SecretScanReport,
    plan: BuildPlan,
    artifacts: GeneratedArtifacts,
) -> Path:
    output_dir = reset_output_dir(context.entry, context.app_id)
    write_json(output_dir / "import_plan.json", artifacts.import_plan)
    write_text(output_dir / "file_inventory.md", inventory_markdown(inventory))
    write_json(output_dir / "file_inventory.json", inventory.to_dict())
    write_json(output_dir / "dependency_report.json", dependency_report.to_dict())
    write_text(output_dir / "secret_scan_report.md", secret_report_markdown(secret_report, context.source_root))
    write_text(output_dir / "build_plan.md", artifacts.build_plan_md)
    write_text(output_dir / "proposed_app.yaml", artifacts.app_yaml)
    write_text(output_dir / "proposed_README.md", artifacts.readme)
    write_text(output_dir / "proposed_requirements.txt", artifacts.requirements)

    icon_work = output_dir / "icon_work"
    write_text(icon_work / "icon_prompt_initial.md", artifacts.icon_prompt_initial)
    write_text(icon_work / "icon_prompt_revision.md", artifacts.icon_prompt_revision)
    write_text(icon_work / "icon_candidate_1.svg", artifacts.icon_svg)
    write_text(icon_work / "icon_final.svg", artifacts.icon_svg)
    if artifacts.icon_ai_report:
        write_text(icon_work / "ai_generation_report.md", artifacts.icon_ai_report)

    final_app = output_dir / "final_app"
    write_text(final_app / "app.yaml", artifacts.app_yaml)
    write_text(final_app / "README.md", artifacts.readme)
    write_text(final_app / "requirements.txt", artifacts.requirements)
    write_text(final_app / "icon.svg", artifacts.icon_svg)
    source_lock = context.source_root / "requirements.lock"
    if source_lock.is_file():
        shutil.copy2(source_lock, final_app / "requirements.lock")
    populate_final_app_sources(context, inventory, plan, final_app)
    (output_dir / "app_pack").mkdir(parents=True, exist_ok=True)
    write_text(output_dir / "execution_test_report.md", "# Execution Test Report\n\nNot run yet. Apply must run execution checks.\n")
    write_text(output_dir / "approval_record.md", "# Approval Record\n\nNot approved yet.\n")
    return output_dir


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

    src_dir = final_app / "src"
    for source in inventory.included_files:
        if source.name.lower() in {"requirements.txt", "requirements.lock", "pyproject.toml", "readme.md", "README.md".lower()}:
            continue
        copy_file_preserving_root(source, context.source_root, src_dir)


def copy_pack_to_output(package_path: Path, output_dir: Path) -> None:
    destination = output_dir / "app_pack" / package_path.name
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(package_path, destination)
