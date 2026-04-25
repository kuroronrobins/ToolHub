from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from app_studio.ai_metadata_suggester import suggest_metadata
from app_studio.approval import approve_app
from app_studio.build_planner import build_plan_markdown, make_build_plan
from app_studio.dependency_analyzer import analyze_dependencies
from app_studio.exporter import export_suggestion
from app_studio.file_classifier import classify_files
from app_studio.icon_generator import generate_icon_assets
from app_studio.manifest_generator import generate_app_yaml
from app_studio.models import BUILD_MODES, GeneratedArtifacts, ImportOptions
from app_studio.readme_generator import generate_readme
from app_studio.registrar import apply_registration
from app_studio.scanner import create_context
from app_studio.secret_scanner import scan_secrets
from app_studio.util import find_repo_root
from app_studio.execution_tester import run_execution_checks


def parse_args(argv: list[str]) -> argparse.Namespace:
    if argv and argv[0] == "approve":
        parser = argparse.ArgumentParser(description="Approve a ToolHub App Studio import.")
        parser.add_argument("command")
        parser.add_argument("--app-id", required=True)
        return parser.parse_args(argv)

    if argv and argv[0] == "import":
        argv = argv[1:]
    parser = argparse.ArgumentParser(description="ToolHub App Studio")
    parser.add_argument("--entry", required=True)
    parser.add_argument("--app-id")
    parser.add_argument("--name")
    parser.add_argument("--build-mode", default="auto", choices=sorted(BUILD_MODES))
    parser.add_argument("--icon-prompt")
    parser.add_argument("--version", default="0.1.0")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--suggest", action="store_true")
    mode.add_argument("--apply", action="store_true")
    parser.set_defaults(command="import")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(list(sys.argv[1:] if argv is None else argv))
    repo_root = find_repo_root(Path.cwd())
    try:
        if args.command == "approve":
            record_path = approve_app(repo_root, args.app_id)
            print(f"承認記録を作成しました: {record_path}")
            return 0
        return run_import(args, repo_root)
    except Exception as exc:
        print(f"ToolHub App Studio エラー: {exc}", file=sys.stderr)
        return 1


def run_import(args: argparse.Namespace, repo_root: Path) -> int:
    action = "dry-run" if args.dry_run else "suggest" if args.suggest else "apply"
    options = ImportOptions(
        entry=Path(args.entry),
        action=action,
        app_id=args.app_id,
        name=args.name,
        build_mode=args.build_mode,
        icon_prompt=args.icon_prompt,
        version=args.version,
    )
    context = create_context(options, repo_root)
    inventory = classify_files(context)
    secret_report = scan_secrets(context.source_root)
    dependency_report, proposed_requirements = analyze_dependencies(context, inventory)
    plan = make_build_plan(context, inventory)
    context.build_mode = plan.mode
    metadata = suggest_metadata(context)
    app_yaml = generate_app_yaml(context, plan, metadata)
    readme = generate_readme(context, plan)
    icon_prompt_initial, icon_prompt_revision, icon_svg, style_reference = generate_icon_assets(context, args.icon_prompt)
    build_plan_md = build_plan_markdown(plan, context)
    import_plan = {
        "app_id": context.app_id,
        "name": context.name,
        "version": context.version,
        "entry": str(context.entry),
        "source_root": str(context.source_root),
        "output_dir": str(context.output_dir),
        "requested_build_mode": context.requested_build_mode,
        "selected_build_mode": plan.mode,
        "runner": plan.runner,
        "run_entry": plan.entry,
        "required_runtime": plan.required_runtime,
        "secret_high_findings": secret_report.has_high,
        "icon_style_reference": style_reference,
    }
    artifacts = GeneratedArtifacts(
        metadata=metadata,
        app_yaml=app_yaml,
        readme=readme,
        requirements=proposed_requirements,
        icon_prompt_initial=icon_prompt_initial,
        icon_prompt_revision=icon_prompt_revision,
        icon_svg=icon_svg,
        build_plan_md=build_plan_md,
        import_plan=import_plan,
    )

    print_summary(context.app_id, context.name, action, plan.mode, len(inventory.included_files), len(secret_report.findings), context.output_dir)
    if action == "dry-run":
        return 0

    output_dir = export_suggestion(context, inventory, dependency_report, secret_report, plan, artifacts)
    print(f"提案成果物を保存しました: {output_dir}")

    if action == "suggest":
        return 0

    if secret_report.has_high:
        print("high の秘密情報検出があるため Apply を中止しました。secret_scan_report.md を確認してください。", file=sys.stderr)
        return 1

    package_path = apply_registration(context, plan, output_dir / "final_app", output_dir)
    run_execution_checks(context, plan, output_dir)
    print(f"仮登録しました: apps/{context.app_id}")
    print(f"App Pack を生成しました: {package_path}")
    print("release/app_manifest.json には enabled=false で登録されています。")
    return 0


def print_summary(app_id: str, name: str, action: str, build_mode: str, included_count: int, finding_count: int, output_dir: Path) -> None:
    print("ToolHub App Studio")
    print(f"- action: {action}")
    print(f"- app_id: {app_id}")
    print(f"- name: {name}")
    print(f"- build_mode: {build_mode}")
    print(f"- included_files: {included_count}")
    print(f"- secret_findings: {finding_count}")
    print(f"- output: {output_dir}")


if __name__ == "__main__":
    raise SystemExit(main())

