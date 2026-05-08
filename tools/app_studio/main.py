from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from app_studio.ai_metadata_suggester import build_icon_design_brief, suggest_metadata
from app_studio.app_env_builder import create_build_env, install_build_tools
from app_studio.approval import approve_app
from app_studio.build_profile import (
    analyze_exe_readiness,
    default_build_profile,
    load_build_profile,
    merge_build_profiles,
    saved_build_profile_path,
    write_build_profile_files,
)
from app_studio.build_planner import build_plan_markdown, make_build_plan
from app_studio.dependency_analyzer import analyze_dependencies
from app_studio.execution_tester import record_blocked_execution, run_execution_checks
from app_studio.exporter import export_suggestion
from app_studio.file_classifier import classify_files
from app_studio.frozen_folder_builder import build_frozen_folder
from app_studio.icon_generator import DEFAULT_ICON_REGENERATION_CANDIDATE_COUNT, ICON_IMAGE_QUALITY_MODES, ICON_REGENERATION_MODES, generate_icon_assets_with_candidates, regenerate_icon_only
from app_studio.icon_override import apply_icon_override, load_icon_override
from app_studio.lock_generator import generate_lock
from app_studio.manifest_generator import generate_app_yaml
from app_studio.metadata_override import apply_metadata_override, load_metadata_override
from app_studio.models import BUILD_MODES, NORMAL_REGISTRATION_BUILD_MODE, NORMAL_REGISTRATION_POLICY, GeneratedArtifacts, ImportOptions
from app_studio.openai_client import test_image_generation_connection
from app_studio.readme_generator import generate_readme
from app_studio.registrar import apply_registration
from app_studio.runtime_checker import verify_runtime
from app_studio.scanner import create_context
from app_studio.secret_scanner import scan_secrets
from app_studio.timing import TimingRecorder, write_timing_reports
from app_studio.trace import app_studio_trace, merge_trace_into_import_plan
from app_studio.util import find_repo_root


def parse_args(argv: list[str]) -> argparse.Namespace:
    if argv and argv[0] == "approve":
        parser = argparse.ArgumentParser(description="Approve a ToolHub App Studio import.")
        parser.add_argument("command")
        parser.add_argument("--app-id", required=True)
        parser.add_argument("--strict-approval", action="store_true")
        parser.add_argument("--allow-warnings", action="store_true")
        return parser.parse_args(argv)

    if argv and argv[0] == "image-test":
        parser = argparse.ArgumentParser(description="Run a real OpenAI image generation connectivity test.")
        parser.add_argument("command")
        parser.add_argument("--image-model")
        return parser.parse_args(argv)

    if argv and argv[0] == "icon-regenerate":
        parser = argparse.ArgumentParser(description="Regenerate App Studio icon candidates without rerunning Suggest.")
        parser.add_argument("command")
        parser.add_argument("--app-id", required=True)
        parser.add_argument("--output-dir", required=True)
        parser.add_argument("--base-candidate-id")
        parser.add_argument("--user-revision-instruction", required=True)
        parser.add_argument("--revision-mode", default="refine", choices=sorted(ICON_REGENERATION_MODES))
        parser.add_argument("--icon-style-preset")
        parser.add_argument("--icon-style-custom")
        parser.add_argument("--candidate-count", type=int, default=DEFAULT_ICON_REGENERATION_CANDIDATE_COUNT)
        parser.add_argument("--image-quality-mode", default="standard", choices=sorted(ICON_IMAGE_QUALITY_MODES))
        return parser.parse_args(argv)

    if argv and argv[0] == "import":
        argv = argv[1:]
    parser = argparse.ArgumentParser(description="ToolHub App Studio")
    parser.add_argument("--entry", required=True)
    parser.add_argument("--source-root")
    parser.add_argument("--app-id")
    parser.add_argument("--name")
    parser.add_argument("--build-mode", default="auto", choices=sorted(BUILD_MODES))
    parser.add_argument("--icon-prompt")
    parser.add_argument("--icon-style-preset")
    parser.add_argument("--icon-style-custom")
    parser.add_argument("--icon-revision-image")
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
    parser.add_argument("--icon-override")
    parser.add_argument("--build-profile")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--suggest", action="store_true")
    mode.add_argument("--apply", action="store_true")
    parser.set_defaults(command="import")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    args = parse_args(raw_argv)
    args._raw_argv = raw_argv
    repo_root = find_repo_root(Path.cwd())
    try:
        if args.command == "approve":
            allow_warnings = True if args.allow_warnings or not args.strict_approval else False
            record_path = approve_app(repo_root, args.app_id, strict=args.strict_approval, allow_warnings=allow_warnings)
            print(f"Approval record was created: {record_path}")
            return 0
        if args.command == "image-test":
            return run_image_test(args.image_model)
        if args.command == "icon-regenerate":
            return run_icon_regenerate(args, repo_root)
        return run_import(args, repo_root)
    except Exception as exc:
        print(f"ToolHub App Studio error: {exc}", file=sys.stderr)
        return 1


def run_import(args: argparse.Namespace, repo_root: Path) -> int:
    validate_flag_combination(args)
    normalize_normal_registration_args(args)
    action = "dry-run" if args.dry_run else "suggest" if args.suggest else "apply"
    options = ImportOptions(
        entry=Path(args.entry),
        action=action,
        source_root=Path(args.source_root) if args.source_root else None,
        app_id=args.app_id,
        name=args.name,
        build_mode=args.build_mode,
        icon_prompt=args.icon_prompt,
        icon_style_preset=args.icon_style_preset,
        icon_style_custom=args.icon_style_custom,
        icon_revision_image_path=Path(args.icon_revision_image) if args.icon_revision_image else None,
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
        build_profile_path=Path(args.build_profile) if args.build_profile else None,
    )
    context = create_context(options, repo_root)
    timings = TimingRecorder(context, action)
    timings.mark("preflight", "pass", "CLI options and normal registration policy were validated.")
    with timings.phase("file_inventory"):
        inventory = classify_files(context)
    with timings.phase("secret_scan"):
        secret_report = scan_secrets(context.source_root, inventory)
    with timings.phase("dependency_analysis"):
        dependency_report, proposed_requirements = analyze_dependencies(context, inventory)
        plan = make_build_plan(context, inventory)
    context.build_mode = plan.mode
    build_profile = default_build_profile(context, inventory, dependency_report)
    existing_profile_path = saved_build_profile_path(context)
    if existing_profile_path.is_file():
        build_profile = merge_build_profiles(build_profile, load_build_profile(existing_profile_path), "saved+auto")
    if options.build_profile_path:
        build_profile = merge_build_profiles(build_profile, load_build_profile(options.build_profile_path), "manual+auto")
    exe_readiness = analyze_exe_readiness(context, plan, inventory, dependency_report, secret_report, build_profile)
    with timings.phase("metadata_ai_fallback"):
        metadata = suggest_metadata(context, secret_report)
    metadata_override_applied: list[str] = []
    metadata_override_warnings: list[str] = []
    if options.metadata_override_path:
        override = load_metadata_override(options.metadata_override_path)
        metadata, metadata_override_applied, metadata_override_warnings = apply_metadata_override(metadata, override)
    app_yaml = generate_app_yaml(context, plan, metadata)
    readme = generate_readme(context, plan)
    ai_skip_reason = "secret scan blocked AI submission, AI skipped" if secret_report.blocks_ai_submission else ""
    with timings.phase("icon_generation_fallback"):
        icon_prompt_initial, icon_prompt_revision, icon_svg, fallback_png, style_reference, icon_ai_report, icon_candidate_png, icon_candidate_url, icon_candidates = generate_icon_assets_with_candidates(
            context,
            args.icon_prompt,
            allow_ai=not secret_report.blocks_ai_submission,
            ai_skip_reason=ai_skip_reason,
            metadata=metadata,
            dependency_report=dependency_report,
            icon_style_preset=options.icon_style_preset,
            icon_style_custom=options.icon_style_custom,
            revision_image_path=str(options.icon_revision_image_path) if options.icon_revision_image_path else None,
        )
    icon_design_brief = build_icon_design_brief(context, metadata, dependency_report, style_reference).to_dict()
    icon_override_warnings: list[str] = []
    selected_icon_source = "fallback_png"
    icon_final_png = fallback_png
    if args.icon_override:
        icon_override = load_icon_override(Path(args.icon_override))
        icon_final_png, selected_icon_source, icon_override_warnings = apply_icon_override(fallback_png, icon_override)
    build_plan_md = build_plan_markdown(plan, context)
    import_plan = {
        "app_id": context.app_id,
        "name": context.name,
        "version": context.version,
        "entry": str(context.entry),
        "source_root": str(context.source_root),
        "source_root_origin": context.source_root_origin,
        "source_root_warnings": context.source_root_warnings,
        "entry_relative": context.entry_relative.as_posix(),
        "source_scope": inventory.summary(),
        "excluded_directories": inventory.excluded_directories[:100],
        "toolhubignore_patterns": inventory.toolhubignore_patterns,
        "output_dir": str(context.output_dir),
        "requested_build_mode": context.requested_build_mode,
        "selected_build_mode": plan.mode,
        "registration_policy": NORMAL_REGISTRATION_POLICY,
        "runner": plan.runner,
        "run_entry": plan.entry,
        "required_runtime": plan.required_runtime,
        "secret_high_findings": secret_report.has_high,
        "ai_blocked_by_secret_scan": secret_report.blocks_ai_submission,
        "apply_blocked_by_secret_scan": secret_report.blocks_apply,
        "blocking_secret_findings_count": len(secret_report.blocking_findings),
        "warning_secret_findings_count": len(secret_report.warning_findings),
        "manual_check_secret_findings_count": len(secret_report.manual_check_findings),
        "false_positive_secret_findings_count": len(secret_report.false_positive_candidates),
        "secret_scan_report": str(context.output_dir / "secret_scan_report.md"),
        "blocking_secret_findings": secret_finding_summaries(secret_report.blocking_findings, context.source_root),
        "icon_style_reference": style_reference,
        "icon_style_preset": options.icon_style_preset or "",
        "icon_style_custom": options.icon_style_custom or "",
        "icon_revision_image_used": bool(options.icon_revision_image_path),
        "icon_function_interpretation": icon_design_brief,
        "icon_candidate_count": len(icon_candidates),
        "selected_icon_source": selected_icon_source,
        "icon_override_used": selected_icon_source != "fallback_png",
        "icon_override_warnings": icon_override_warnings,
        "metadata_ai_report": metadata.get("_ai_generation_report", ""),
        "metadata_override_used": bool(metadata_override_applied),
        "metadata_override_keys": metadata_override_applied,
        "metadata_override_warnings": metadata_override_warnings,
        "create_app_env": options.create_app_env,
        "generate_lock": options.generate_lock,
        "build_frozen_folder": options.build_frozen_folder,
        "verify_runtime": options.verify_runtime,
        "build_env": str(context.output_dir / "build_env"),
        "build_profile_source": build_profile.get("source"),
        "exe_readiness_status": exe_readiness.get("overall_status"),
        "manual_checks": exe_readiness.get("manual_checks", []),
    }
    import_plan.update(app_studio_trace(context, args))
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
        icon_final_png=icon_final_png,
        icon_candidate_png=icon_candidate_png,
        icon_candidate_url=icon_candidate_url,
        icon_candidates=icon_candidates,
        icon_design_brief=icon_design_brief,
        build_profile=build_profile,
        exe_readiness=exe_readiness,
    )

    print_summary(context.app_id, context.name, action, plan.mode, len(inventory.included_files), len(secret_report.findings), context.output_dir)
    if options.metadata_override_path:
        print(f"- metadata_override_keys: {', '.join(metadata_override_applied) if metadata_override_applied else 'none'}")
        if metadata_override_warnings:
            print(f"- metadata_override_warnings: {len(metadata_override_warnings)}")
    if args.icon_override:
        print(f"- selected_icon_source: {selected_icon_source}")
        if icon_override_warnings:
            print(f"- icon_override_warnings: {len(icon_override_warnings)}")
    if action == "dry-run":
        return 0

    with timings.phase("export_suggestion"):
        output_dir = export_suggestion(context, inventory, dependency_report, secret_report, plan, artifacts)
    write_build_profile_files(context, output_dir, build_profile, exe_readiness)
    merge_trace_into_import_plan(output_dir, app_studio_trace(context, args))
    write_timing_reports(context, output_dir, timings)
    print(f"Suggestion artifacts were saved: {output_dir}")

    if action == "suggest":
        return 0

    record_blocked_execution(context, output_dir, "apply started", "Apply started and has not reached final execution checks yet.", plan)

    if secret_report.blocks_apply:
        detail = (
            f"Apply was blocked by {len(secret_report.blocking_findings)} blocking secret finding(s). "
            f"Warnings={len(secret_report.warning_findings)}, manual_checks={len(secret_report.manual_check_findings)}. "
            f"Report: {output_dir / 'secret_scan_report.md'}. "
            f"Top findings: {'; '.join(secret_finding_summaries(secret_report.blocking_findings, context.source_root)[:5])}"
        )
        record_blocked_execution(context, output_dir, "secret scan", detail, plan)
        write_timing_reports(context, output_dir, timings)
        print(detail, file=sys.stderr)
        return 1

    final_app = output_dir / "final_app"
    requirements_path = final_app / "requirements.txt"
    build_env_python = None

    if plan.mode != NORMAL_REGISTRATION_BUILD_MODE:
        record_blocked_execution(context, output_dir, "registration policy", f"Normal registration requires {NORMAL_REGISTRATION_BUILD_MODE}, got {plan.mode}.", plan)
        write_timing_reports(context, output_dir, timings)
        return 1

    with timings.phase("build_env_creation"):
        build_env_result = create_build_env(context, requirements_path, rebuild=True)
    timings.mark("dependency_install", "included", "Dependency install runs inside build_env creation and is reported in build_env_report.md.")
    print(f"build_env status: ok={build_env_result.ok}, skipped={build_env_result.skipped}, path={build_env_result.app_env_path}")
    if not build_env_result.ok:
        record_blocked_execution(context, output_dir, "build_env", build_env_result.error or "build_env creation failed.", plan)
        write_timing_reports(context, output_dir, timings)
        return 1
    build_env_python = build_env_result.python_path
    merge_trace_into_import_plan(output_dir, app_studio_trace(context, args, build_env_python=build_env_python))

    with timings.phase("requirements_lock_generation"):
        lock_result = generate_lock(context, requirements_path, app_env_python=build_env_python)
    print(f"requirements.lock status: ok={lock_result.ok}, source={lock_result.source}")
    if not lock_result.ok:
        record_blocked_execution(context, output_dir, "requirements.lock", lock_result.error or "requirements.lock generation failed.", plan)
        write_timing_reports(context, output_dir, timings)
        return 1

    with timings.phase("build_tools_install"):
        build_tool_result = install_build_tools(context, build_env_result.app_env_path, ["PyInstaller>=6,<7", "pyinstaller-hooks-contrib>=2024.0"])
    print(f"build tool install status: ok={build_tool_result.ok}, skipped={build_tool_result.skipped}")
    if not build_tool_result.ok:
        record_blocked_execution(context, output_dir, "build tools", build_tool_result.error or "Build tool install failed.", plan)
        write_timing_reports(context, output_dir, timings)
        return 1

    timings.mark("pyinstaller_probe", "included", "PyInstaller probe is executed inside the frozen-folder build phase and reported in frozen_folder_build_report.md.")
    with timings.phase("pyinstaller_build"):
        frozen_result = build_frozen_folder(context, plan, output_dir, rebuild=True, build_profile=build_profile)
    merge_trace_into_import_plan(
        output_dir,
        app_studio_trace(
            context,
            args,
            build_env_python=build_env_python,
            pyinstaller_probe_python=build_env_python,
            pyinstaller_build_python=build_env_python,
        ),
    )
    print(f"frozen-folder build status: ok={frozen_result.ok}, skipped={frozen_result.skipped}")
    if not frozen_result.ok:
        record_blocked_execution(
            context,
            output_dir,
            "frozen-folder build",
            frozen_result.error or "Frozen-folder build failed before temporary registration.",
            plan,
        )
        write_timing_reports(context, output_dir, timings)
        return 1

    with timings.phase("distribution_check"):
        runtime_result = verify_runtime(context, output_dir, plan, build_profile)
    print(f"distribution check status: {runtime_result.overall_status}")
    if runtime_result.overall_status == "fail":
        record_blocked_execution(context, output_dir, "frozen-folder distribution check", "Distribution verification failed. Review runtime_check_report.md.", plan)
        write_timing_reports(context, output_dir, timings)
        return 1

    try:
        with timings.phase("registration_copy"):
            package_path = apply_registration(context, plan, final_app, output_dir)
    except Exception as exc:
        record_blocked_execution(context, output_dir, "registration copy", f"Registration copy or app pack generation failed: {exc!r}", plan)
        write_timing_reports(context, output_dir, timings)
        raise
    with timings.phase("execution_checks"):
        execution_result = run_execution_checks(context, plan, output_dir, secret_report, runtime_result)
    timings.mark("result_refresh", "not_applicable", "GUI result refresh is measured in the launcher after CLI completion.")
    write_timing_reports(context, output_dir, timings)
    print(f"Temporary registration completed: apps/{context.app_id}")
    print(f"App Pack was generated: {package_path}")
    print(f"execution_test_result overall_status={execution_result.overall_status}, approval_allowed={execution_result.approval_allowed}")
    print("release/app_manifest.json starts with enabled=false for imported apps.")
    return 0 if execution_result.approval_allowed else 1


def run_image_test(image_model: str | None = None) -> int:
    result = test_image_generation_connection(image_model)
    payload = {
        "ok": result.ok,
        "status": result.status,
        "model": result.model,
        "api": result.api,
        "content_type": result.content_type,
        "resolution": result.resolution,
        "fallback_reason": result.fallback_reason,
        "error": result.error,
        "error_category": result.error_category,
        "used_api": result.used_api,
        "message": "Image API test passed." if result.ok else (result.fallback_reason or result.error or "Image API test failed."),
    }
    print(json_dumps(payload))
    return 0 if result.ok else 1


def run_icon_regenerate(args: argparse.Namespace, repo_root: Path) -> int:
    result = regenerate_icon_only(
        output_dir=Path(args.output_dir),
        app_id=args.app_id,
        repo_root=repo_root,
        base_candidate_id=args.base_candidate_id,
        user_revision_instruction=args.user_revision_instruction,
        revision_mode=args.revision_mode,
        icon_style_preset=args.icon_style_preset,
        icon_style_custom=args.icon_style_custom,
        candidate_count=args.candidate_count,
        image_quality_mode=args.image_quality_mode,
    )
    print(json_dumps(result))
    return 0 if result.get("ok") else 1


def json_dumps(value: dict) -> str:
    import json

    return json.dumps(value, ensure_ascii=False)


def validate_flag_combination(args: argparse.Namespace) -> None:
    if args.generate_lock and args.skip_lock:
        raise ValueError("-GenerateLock and -SkipLock cannot be used together.")
    if args.create_app_env and args.skip_app_env_build:
        raise ValueError("-CreateAppEnv and -SkipAppEnvBuild cannot be used together.")
    if args.build_frozen_folder and args.skip_frozen_build:
        raise ValueError("-BuildFrozenFolder and -SkipFrozenBuild cannot be used together.")


def normalize_normal_registration_args(args: argparse.Namespace) -> None:
    entry = Path(args.entry)
    if entry.suffix.lower() == ".exe":
        raise ValueError("Normal App Studio registration accepts Python source only. Existing exe registration is not available in the normal flow.")
    if args.skip_lock:
        raise ValueError("Normal App Studio registration always generates or updates requirements.lock; --skip-lock is not allowed.")
    if args.skip_frozen_build:
        raise ValueError("Normal App Studio registration always builds a frozen-folder; --skip-frozen-build is not allowed.")
    if args.skip_app_env_build:
        raise ValueError("Normal App Studio registration uses an internal build_env, not user-facing app_env; --skip-app-env-build is not allowed.")
    if args.create_app_env or args.rebuild_app_env:
        raise ValueError("Normal App Studio registration does not create runtime/app_envs. A temporary build_env is created internally.")
    if args.build_mode not in {"auto", NORMAL_REGISTRATION_BUILD_MODE}:
        print(f"Normal registration ignores legacy BuildMode={args.build_mode}; using {NORMAL_REGISTRATION_BUILD_MODE}.")
    args.build_mode = NORMAL_REGISTRATION_BUILD_MODE
    args.generate_lock = True
    args.build_frozen_folder = True
    args.verify_runtime = True
    args.create_app_env = False
    args.rebuild_app_env = False
    args.rebuild_frozen_folder = True
    args.skip_lock = False
    args.skip_frozen_build = False
    args.skip_app_env_build = False


def secret_finding_summaries(findings, source_root: Path) -> list[str]:
    summaries: list[str] = []
    for finding in findings[:10]:
        try:
            relative = finding.path.relative_to(source_root).as_posix()
        except ValueError:
            relative = str(finding.path)
        reason = finding.block_reason or finding.detail
        summaries.append(f"{relative} [{finding.kind}] {reason}")
    return summaries


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
