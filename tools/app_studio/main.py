from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from app_studio.ai_metadata_suggester import suggest_metadata
from app_studio.app_env_builder import create_app_env
from app_studio.approval import approve_app
from app_studio.build_planner import build_plan_markdown, make_build_plan
from app_studio.dependency_analyzer import analyze_dependencies
from app_studio.execution_tester import run_execution_checks
from app_studio.exporter import export_suggestion
from app_studio.file_classifier import classify_files
from app_studio.frozen_folder_builder import build_frozen_folder
from app_studio.icon_generator import generate_icon_assets_with_candidates
from app_studio.lock_generator import generate_lock
from app_studio.manifest_generator import generate_app_yaml
from app_studio.metadata_override import apply_metadata_override, load_metadata_override
from app_studio.models import BUILD_MODES, GeneratedArtifacts, ImportOptions
from app_studio.readme_generator import generate_readme
from app_studio.registrar import apply_registration
from app_studio.runtime_checker import verify_runtime
from app_studio.scanner import create_context
from app_studio.secret_scanner import scan_secrets
from app_studio.util import find_repo_root


def parse_args(argv: list[str]) -> argparse.Namespace:
    if argv and argv[0] == "approve":
        parser = argparse.ArgumentParser(description="Approve a ToolHub App Studio import.")
        parser.add_argument("command")
        parser.add_argument("--app-id", required=True)
        parser.add_argument("--strict-approval", action="store_true")
        parser.add_argument("--allow-warnings", action="store_true")
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
    parser.add_argument("--create-app-env", action="store_true")
    parser.add_argument("--rebuild-app-env", action="store_true")
    parser.add_argument("--skip-app-env-build", action="store_true")
    parser.add_argument("--generate-lock", action="store_true")
    parser.add_argument("--skip-lock", action="store_true")
    parser.add_argument("--build-frozen-folder", action="store_true")
    parser.add_argument("--rebuild-frozen-folder", action="store_true")
    parser.add_argument("--skip-frozen-build", action="store_true")
    parser.add_argument("--verify-runtime", action="store_true")
    parser.add_argument("--metadata-override")
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
            allow_warnings = True if args.allow_warnings or not args.strict_approval else False
            record_path = approve_app(repo_root, args.app_id, strict=args.strict_approval, allow_warnings=allow_warnings)
            print(f"Approval record was created: {record_path}")
            return 0
        return run_import(args, repo_root)
    except Exception as exc:
        print(f"ToolHub App Studio error: {exc}", file=sys.stderr)
        return 1


def run_import(args: argparse.Namespace, repo_root: Path) -> int:
    validate_flag_combination(args)
    action = "dry-run" if args.dry_run else "suggest" if args.suggest else "apply"
    options = ImportOptions(
        entry=Path(args.entry),
        action=action,
        app_id=args.app_id,
        name=args.name,
        build_mode=args.build_mode,
        icon_prompt=args.icon_prompt,
        version=args.version,
        create_app_env=args.create_app_env,
        rebuild_app_env=args.rebuild_app_env,
        skip_app_env_build=args.skip_app_env_build,
        generate_lock=args.generate_lock,
        skip_lock=args.skip_lock,
        build_frozen_folder=args.build_frozen_folder,
        rebuild_frozen_folder=args.rebuild_frozen_folder,
        skip_frozen_build=args.skip_frozen_build,
        verify_runtime=args.verify_runtime,
        metadata_override_path=Path(args.metadata_override) if args.metadata_override else None,
    )
    context = create_context(options, repo_root)
    inventory = classify_files(context)
    secret_report = scan_secrets(context.source_root)
    dependency_report, proposed_requirements = analyze_dependencies(context, inventory)
    plan = make_build_plan(context, inventory)
    context.build_mode = plan.mode
    metadata = suggest_metadata(context, secret_report)
    metadata_override_applied: list[str] = []
    metadata_override_warnings: list[str] = []
    if options.metadata_override_path:
        override = load_metadata_override(options.metadata_override_path)
        metadata, metadata_override_applied, metadata_override_warnings = apply_metadata_override(metadata, override)
    app_yaml = generate_app_yaml(context, plan, metadata)
    readme = generate_readme(context, plan)
    icon_prompt_initial, icon_prompt_revision, icon_svg, style_reference, icon_ai_report, icon_candidate_png, icon_candidate_url = generate_icon_assets_with_candidates(
        context,
        args.icon_prompt,
        allow_ai=not secret_report.has_high,
    )
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
        "metadata_ai_report": metadata.get("_ai_generation_report", ""),
        "metadata_override_used": bool(metadata_override_applied),
        "metadata_override_keys": metadata_override_applied,
        "metadata_override_warnings": metadata_override_warnings,
        "create_app_env": options.create_app_env,
        "generate_lock": options.generate_lock,
        "build_frozen_folder": options.build_frozen_folder,
        "verify_runtime": options.verify_runtime,
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
        icon_ai_report=icon_ai_report,
        icon_candidate_png=icon_candidate_png,
        icon_candidate_url=icon_candidate_url,
    )

    print_summary(context.app_id, context.name, action, plan.mode, len(inventory.included_files), len(secret_report.findings), context.output_dir)
    if options.metadata_override_path:
        print(f"- metadata_override_keys: {', '.join(metadata_override_applied) if metadata_override_applied else 'none'}")
        if metadata_override_warnings:
            print(f"- metadata_override_warnings: {len(metadata_override_warnings)}")
    if action == "dry-run":
        return 0

    output_dir = export_suggestion(context, inventory, dependency_report, secret_report, plan, artifacts)
    print(f"Suggestion artifacts were saved: {output_dir}")

    if action == "suggest":
        return 0

    if secret_report.has_high:
        print("Apply was blocked because high severity secret findings exist. Review secret_scan_report.md.", file=sys.stderr)
        return 1

    final_app = output_dir / "final_app"
    requirements_path = final_app / "requirements.txt"
    app_env_python = None

    should_build_app_env = plan.mode == "app-env" and (args.create_app_env or args.rebuild_app_env) and not args.skip_app_env_build
    if should_build_app_env:
        app_env_result = create_app_env(context, requirements_path, rebuild=args.rebuild_app_env)
        print(f"app_env build status: ok={app_env_result.ok}, skipped={app_env_result.skipped}")
        if not app_env_result.ok:
            return 1
        app_env_python = app_env_result.python_path

    if args.skip_lock:
        generate_lock(context, requirements_path, app_env_python=app_env_python, skip=True)
    elif args.generate_lock:
        lock_result = generate_lock(context, requirements_path, app_env_python=app_env_python)
        print(f"requirements.lock status: ok={lock_result.ok}, source={lock_result.source}")
        if not lock_result.ok:
            return 1

    if args.verify_runtime:
        runtime_result = verify_runtime(context, output_dir)
        print(f"runtime check status: {runtime_result.overall_status}")

    should_build_frozen = plan.mode == "frozen-folder" and (args.build_frozen_folder or args.rebuild_frozen_folder) and not args.skip_frozen_build
    if should_build_frozen:
        frozen_result = build_frozen_folder(context, plan, output_dir, rebuild=args.rebuild_frozen_folder)
        print(f"frozen-folder build status: ok={frozen_result.ok}, skipped={frozen_result.skipped}")
        if not frozen_result.ok:
            return 1

    package_path = apply_registration(context, plan, final_app, output_dir)
    execution_result = run_execution_checks(context, plan, output_dir, secret_report)
    print(f"Temporary registration completed: apps/{context.app_id}")
    print(f"App Pack was generated: {package_path}")
    print(f"execution_test_result overall_status={execution_result.overall_status}, approval_allowed={execution_result.approval_allowed}")
    print("release/app_manifest.json starts with enabled=false for imported apps.")
    return 0


def validate_flag_combination(args: argparse.Namespace) -> None:
    if args.generate_lock and args.skip_lock:
        raise ValueError("-GenerateLock and -SkipLock cannot be used together.")
    if args.create_app_env and args.skip_app_env_build:
        raise ValueError("-CreateAppEnv and -SkipAppEnvBuild cannot be used together.")
    if args.build_frozen_folder and args.skip_frozen_build:
        raise ValueError("-BuildFrozenFolder and -SkipFrozenBuild cannot be used together.")


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
