from __future__ import annotations

import json
import os
from pathlib import Path
import time
from typing import Any

from .ai_metadata_suggester import build_icon_design_brief, sanitize_ai_text, suggest_icon_prompt
from .default_icon import DEFAULT_ICON_REASON, DEFAULT_ICON_SOURCE, default_icon_png, default_icon_svg
from .icon_candidates import image_candidate_from_result, is_api_candidate, manifest_entry_is_fallback, saved_candidate_name, select_icon_manifest_candidate, selected_candidate_image_path
from .icon_diagnostics import API_ICON_RESOLUTION, image_api_summary, image_failure_diagnostics_from_reports, report_value, skipped_image_report
from .icon_prompt import ICON_REGENERATION_MODES, build_icon_revision_api_base_prompt, generate_icon_concepts, icon_revision_concepts, icon_style_settings, image_api_prompt, normalize_icon_revision_mode
from .icon_quality import apply_icon_candidate_quality, score_icon_candidate
from .models import DependencyReport, IconCandidateAsset, IconDesignBrief, SecretScanReport, StudioContext
from .secret_scanner import ai_submission_block_reason, scan_ai_payload_text, secret_scan_status


DEFAULT_ICON_CANDIDATE_COUNT = 3
DEFAULT_ICON_REGENERATION_CANDIDATE_COUNT = 1
MAX_ICON_CANDIDATE_COUNT = 6

ICON_IMAGE_QUALITY_MODES: dict[str, dict[str, str]] = {
    "draft": {"size": API_ICON_RESOLUTION, "quality": "low"},
    "standard": {"size": API_ICON_RESOLUTION, "quality": "medium"},
    "high": {"size": API_ICON_RESOLUTION, "quality": "high"},
}


def collect_icon_style_reference(repo_root: Path) -> str:
    app_dirs = sorted((repo_root / "apps").glob("*"))
    names = []
    for app_dir in app_dirs:
        if (app_dir / "app.yaml").is_file() and ((app_dir / "icon.png").is_file() or (app_dir / "icon.svg").is_file()):
            names.append(app_dir.name)
    if not names:
        return "No existing app icons were found."
    return "Existing ToolHub icon references: " + ", ".join(names)

def generate_icon_assets(context: StudioContext, revision_prompt: str | None = None, allow_ai: bool = True) -> tuple[str, str, str, str, str]:
    initial_prompt, revision, svg, _, style_reference, report, _, _, _ = generate_icon_assets_with_candidates(context, revision_prompt, allow_ai)
    return initial_prompt, revision, svg, style_reference, report

def generate_icon_assets_with_candidates(
    context: StudioContext,
    revision_prompt: str | None = None,
    allow_ai: bool = True,
    ai_skip_reason: str = "",
    metadata: dict | None = None,
    dependency_report: DependencyReport | None = None,
    package_secret_report: SecretScanReport | None = None,
    icon_style_preset: str | None = None,
    icon_style_custom: str | None = None,
    revision_image_path: str | None = None,
) -> tuple[str, str, str, bytes, str, str, bytes | None, str, list[IconCandidateAsset]]:
    style_reference = collect_icon_style_reference(context.repo_root)
    brief = build_icon_design_brief(context, metadata, dependency_report, style_reference)
    initial_prompt, initial_report = suggest_icon_prompt(
        context,
        allow_ai=allow_ai,
        metadata=metadata,
        dependency_report=dependency_report,
        style_reference=style_reference,
        brief=brief,
    )
    if revision_prompt:
        revision, revision_report = suggest_icon_prompt(
            context,
            revision_prompt,
            allow_ai=allow_ai,
            metadata=metadata,
            dependency_report=dependency_report,
            style_reference=style_reference,
            brief=brief,
        )
    else:
        revision = "No revision prompt was provided."
        revision_report = "No revision prompt was provided."
    prompt_for_asset = revision if revision_prompt else initial_prompt
    style_settings = icon_style_settings(icon_style_preset, icon_style_custom, prompt_for_asset)
    svg = default_icon_svg()
    default_png = default_icon_png()
    candidates, image_reports = generate_icon_candidates(
        context,
        brief,
        prompt_for_asset,
        style_reference,
        allow_ai=allow_ai,
        ai_skip_reason=ai_skip_reason,
        count=icon_candidate_count(),
        style_settings=style_settings,
        revision_image_path=revision_image_path,
    )
    legacy_candidate = candidates[0] if candidates and is_api_candidate(candidates[0]) else None
    legacy_png = legacy_candidate.png if legacy_candidate else None
    legacy_url = legacy_candidate.url if legacy_candidate else ""
    saved_candidates = ", ".join(candidate.file_name or candidate.url_file_name or candidate.candidate_id for candidate in candidates) or "none"
    image_failure_diagnostics = image_failure_diagnostics_from_reports(image_reports)
    summary = image_api_summary(
        candidates,
        style_settings,
        {
            "package_secret_scan_status": secret_scan_status(package_secret_report),
            "package_secret_scan_findings": len(package_secret_report.findings) if package_secret_report else 0,
            "package_ai_submission_blocked": package_secret_report.blocks_ai_submission if package_secret_report else False,
            "package_ai_submission_block_reason": ai_submission_block_reason(package_secret_report),
            **image_failure_diagnostics,
        },
    )
    text_prompt_status = report_value(initial_report, "status") or ("skipped" if not allow_ai else "unknown")
    report = "\n".join(
        [
            "# AI Generation Report",
            "",
            "## Icon Prompt",
            "",
            initial_report,
            "",
            revision_report,
            "",
            "## Function Interpretation",
            "",
            json.dumps(brief.to_dict(), ensure_ascii=False, indent=2),
            "",
            "## Image Generation",
            "",
            "\n\n".join(image_reports) if image_reports else skipped_image_report(ai_skip_reason),
            "",
            "## Admin Diagnosis",
            "",
            f"text_prompt_generation_status: {text_prompt_status}",
            f"image_generation_status: {'success' if summary['image_api_success'] else 'failed'}",
            f"image_model: {summary['model']}",
            f"api_candidate_count: {summary['api_candidate_count']}",
            f"failure_class: {summary.get('failure_class') or 'none'}",
            f"failure_message: {summary.get('failure_message') or 'none'}",
            f"admin_next_action: {summary.get('admin_next_action') or 'none'}",
            f"package_secret_scan_status: {summary.get('package_secret_scan_status') or 'not_recorded'}",
            f"ai_payload_secret_scan_status: {summary.get('ai_payload_secret_scan_status') or 'not_run'}",
            f"ai_submission_blocked: {str(bool(summary.get('ai_submission_blocked'))).lower()}",
            f"ai_submission_block_reason: {summary.get('ai_submission_block_reason') or 'none'}",
            "",
            "## Image API Summary",
            "",
            json.dumps(summary, ensure_ascii=False, indent=2),
            f"candidate_count: {len(candidates)}",
            f"api_candidate_count: {sum(1 for candidate in candidates if is_api_candidate(candidate))}",
            f"last_image_api_failure: {summary.get('latest_image_api_failure') or 'none'}",
            f"saved_candidate: {saved_candidate_name(legacy_png, legacy_url)}",
            f"saved_candidates: {saved_candidates}",
            "",
            "PNG is the standard ToolHub App Studio icon output. API PNG candidates require human adoption before final icon.png is replaced.",
            "When no uploaded icon or adopted AI PNG is selected, ToolHub writes the common default icon to icon.png for packaging compatibility.",
            "AI image API failures do not create local fallback candidates. Fix the reported cause or adopt an uploaded/API-generated icon to replace the default icon.",
            "candidate_manifest.json records API image candidates only. The common default icon is not a candidate and is not scored.",
            "Vision evaluation is not required for registration. Deterministic score fields are internal hints for API candidates and must not be treated as visual quality guarantees.",
        ]
    )
    return initial_prompt, revision, svg, default_png, style_reference, report, legacy_png, legacy_url, candidates

def icon_candidate_count() -> int:
    raw = os.environ.get("TOOLHUB_APP_STUDIO_ICON_CANDIDATE_COUNT", "").strip()
    if not raw:
        return DEFAULT_ICON_CANDIDATE_COUNT
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_ICON_CANDIDATE_COUNT
    return max(1, min(MAX_ICON_CANDIDATE_COUNT, value))

def icon_regeneration_candidate_count(value: int | None = None) -> int:
    if value is None:
        return DEFAULT_ICON_REGENERATION_CANDIDATE_COUNT
    return max(1, min(MAX_ICON_CANDIDATE_COUNT, int(value)))

def icon_image_generation_settings(mode: str | None = None) -> dict[str, str]:
    selected = (mode or "standard").strip().lower()
    if selected not in ICON_IMAGE_QUALITY_MODES:
        selected = "standard"
    settings = dict(ICON_IMAGE_QUALITY_MODES[selected])
    settings["mode"] = selected
    return settings

def regenerate_icon_only(
    output_dir: Path,
    app_id: str,
    repo_root: Path,
    base_candidate_id: str | None,
    user_revision_instruction: str,
    revision_mode: str = "refine",
    icon_style_preset: str | None = None,
    icon_style_custom: str | None = None,
    candidate_count: int | None = None,
    image_quality_mode: str | None = None,
) -> dict[str, Any]:
    timings: dict[str, float] = {}
    total_started = time.perf_counter()
    revision_mode = normalize_icon_revision_mode(revision_mode)
    count = icon_regeneration_candidate_count(candidate_count)
    generation_settings = icon_image_generation_settings(image_quality_mode)

    phase_started = time.perf_counter()
    output_dir = output_dir.resolve()
    icon_work = output_dir / "icon_work"
    manifest_path = icon_work / "candidate_manifest.json"
    import_plan_path = output_dir / "import_plan.json"
    manifest = read_json_file(manifest_path)
    import_plan = read_json_file(import_plan_path)
    existing_entries = list(manifest.get("candidates", [])) if isinstance(manifest.get("candidates"), list) else []
    selected_entry = select_icon_manifest_candidate(existing_entries, base_candidate_id)
    timings["manifest_read"] = time.perf_counter() - phase_started

    phase_started = time.perf_counter()
    context = context_from_saved_proposal(repo_root, output_dir, import_plan, app_id)
    brief = icon_design_brief_from_manifest(
        manifest.get("function_interpretation") if isinstance(manifest.get("function_interpretation"), dict) else {},
        import_plan,
        context,
    )
    style_prompt_seed = "\n".join(
        [
            str(selected_entry.get("prompt", "")) if selected_entry else "",
            user_revision_instruction,
        ]
    )
    style_settings = icon_style_settings(icon_style_preset, icon_style_custom, style_prompt_seed)
    prompt_for_asset = build_icon_revision_api_base_prompt(
        brief=brief,
        base_candidate=selected_entry,
        user_revision_instruction=user_revision_instruction,
        revision_mode=revision_mode,
        icon_style_preset=style_settings.get("preset", ""),
        icon_style_custom=style_settings.get("custom", "") or (icon_style_custom or ""),
    )
    revision_concepts = icon_revision_concepts(brief, count, revision_mode, selected_entry, user_revision_instruction)
    base_image = selected_candidate_image_path(icon_work, selected_entry)
    if revision_mode in {"redesign", "fresh"}:
        base_image = None
    force_generate = revision_mode in {"redesign", "fresh"}
    run_id = str(int(time.time() * 1000))
    candidate_id_prefix = f"icon_candidate_regen_{run_id}"
    file_name_prefix = f"icon_candidate_regen_{run_id}"
    timings["prompt_build"] = time.perf_counter() - phase_started

    phase_started = time.perf_counter()
    candidates, image_reports = generate_icon_candidates(
        context,
        brief,
        prompt_for_asset,
        collect_icon_style_reference(repo_root),
        allow_ai=True,
        ai_skip_reason="",
        count=count,
        style_settings=style_settings,
        revision_image_path=str(base_image) if base_image else None,
        concepts=revision_concepts,
        api_size=generation_settings["size"],
        api_quality=generation_settings["quality"],
        force_generate=force_generate,
        candidate_id_prefix=candidate_id_prefix,
        file_name_prefix=file_name_prefix,
    )
    for candidate in candidates:
        candidate.revision_of = str(selected_entry.get("candidate_id", "")) if selected_entry else ""
    timings["image_api_call"] = time.perf_counter() - phase_started

    phase_started = time.perf_counter()
    icon_work.mkdir(parents=True, exist_ok=True)
    write_icon_regeneration_files(
        icon_work=icon_work,
        manifest=manifest,
        candidates=candidates,
        existing_entries=existing_entries,
        brief=brief,
        style_settings=style_settings,
        revision_mode=revision_mode,
        image_quality_mode=generation_settings["mode"],
        user_revision_instruction=user_revision_instruction,
        prompt_for_asset=prompt_for_asset,
        image_reports=image_reports,
        timings=timings,
    )
    timings["file_write"] = time.perf_counter() - phase_started
    timings["total"] = time.perf_counter() - total_started
    update_icon_regeneration_timing(icon_work, timings)
    write_json_file(icon_work / "icon_regeneration_timing.json", timings)
    return {
        "ok": True,
        "app_id": context.app_id,
        "output_dir": str(output_dir),
        "candidate_count": len(candidates),
        "api_candidate_count": sum(1 for candidate in candidates if is_api_candidate(candidate)),
        "revision_mode": revision_mode,
        "image_quality_mode": generation_settings["mode"],
        "image_api_seconds": timings.get("image_api_call", 0.0),
        "used_revision_image": bool(base_image),
        "base_candidate_id": str(selected_entry.get("candidate_id", "")) if selected_entry else "",
    }

def read_json_file(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}

def write_json_file(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

def write_text_file(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")

def context_from_saved_proposal(repo_root: Path, output_dir: Path, import_plan: dict[str, Any], app_id: str) -> StudioContext:
    saved_app_id = sanitize_ai_text(str(import_plan.get("app_id") or app_id or "app"), 120) or "app"
    name = sanitize_ai_text(str(import_plan.get("name") or saved_app_id), 160) or saved_app_id
    entry = Path(str(import_plan.get("entry") or output_dir / "unknown.py"))
    source_root = Path(str(import_plan.get("source_root") or entry.parent or output_dir))
    return StudioContext(
        repo_root=repo_root,
        entry=entry,
        source_root=source_root,
        source_root_origin=str(import_plan.get("source_root_origin") or "saved_import_plan"),
        source_root_warnings=list(import_plan.get("source_root_warnings") or []),
        app_id=saved_app_id,
        name=name,
        output_dir=output_dir,
        requested_build_mode=str(import_plan.get("requested_build_mode") or "frozen-folder"),
        build_mode=str(import_plan.get("selected_build_mode") or "frozen-folder"),
        version=str(import_plan.get("version") or "0.1.0"),
    )

def icon_design_brief_from_manifest(value: dict[str, Any], import_plan: dict[str, Any], context: StudioContext) -> IconDesignBrief:
    def text(key: str, fallback: str) -> str:
        return sanitize_ai_text(str(value.get(key) or value.get(to_camel_key(key)) or fallback), 600)

    def items(key: str, fallback: list[str]) -> list[str]:
        raw = value.get(key) or value.get(to_camel_key(key)) or fallback
        if not isinstance(raw, list):
            raw = fallback
        return [sanitize_ai_text(str(item), 160) for item in raw if str(item).strip()][:8]

    return IconDesignBrief(
        app_id=text("app_id", context.app_id),
        name=text("name", context.name),
        entry_name=text("entry_name", context.entry.name),
        purpose=text("purpose", context.name),
        app_kind=text("app_kind", "utility app"),
        primary_action=text("primary_action", "process"),
        secondary_action=text("secondary_action", "organize"),
        input_objects=items("input_objects", ["input file"]),
        output_objects=items("output_objects", ["output file"]),
        action_flow=text("action_flow", "input becomes output through the app's main action"),
        visual_priority=items("visual_priority", ["primary action", "input object", "output object"]),
        avoid_generic=items("avoid_generic", ["generic abstract shapes only", "document-only", "gear-only", "check-only", "initial-letter-only"]),
        composition_template=text("composition_template", "2 to 4 meaningful objects connected by one action path"),
        primary_motif=text("primary_motif", "main action relationship"),
        secondary_motifs=items("secondary_motifs", ["supporting output cue"]),
        avoid=items("avoid", ["tiny text", "crowded UI", "generic business icon"]),
        palette=text("palette", "use the selected style preset colors"),
        texture=text("texture", "use the selected style preset material"),
        small_size_rule=text("small_size_rule", "readable at 32px"),
        high_resolution_rule=text("high_resolution_rule", "attractive at 256px and above"),
        toolhub_style_rule=text("toolhub_style_rule", "compatible with ToolHub icons without becoming generic"),
        categories=items("categories", list_from_import_plan(import_plan, "categories")),
        keywords=items("keywords", list_from_import_plan(import_plan, "keywords")),
        use_cases=items("use_cases", list_from_import_plan(import_plan, "use_cases")),
        inputs=items("inputs", list_from_import_plan(import_plan, "inputs")),
        outputs=items("outputs", list_from_import_plan(import_plan, "outputs")),
        source_files=items("source_files", []),
        dependency_signals=items("dependency_signals", []),
        readme_excerpt=text("readme_excerpt", ""),
        style_reference=text("style_reference", str(import_plan.get("icon_style_reference") or "")),
    )

def to_camel_key(value: str) -> str:
    parts = value.split("_")
    return parts[0] + "".join(part.capitalize() for part in parts[1:])

def list_from_import_plan(import_plan: dict[str, Any], key: str) -> list[str]:
    value = import_plan.get(key)
    if isinstance(value, list):
        return [str(item) for item in value]
    return []

def write_icon_regeneration_files(
    icon_work: Path,
    manifest: dict[str, Any],
    candidates: list[IconCandidateAsset],
    existing_entries: list[Any],
    brief: IconDesignBrief,
    style_settings: dict[str, str],
    revision_mode: str,
    image_quality_mode: str,
    user_revision_instruction: str,
    prompt_for_asset: str,
    image_reports: list[str],
    timings: dict[str, float],
) -> None:
    write_text_file(icon_work / "icon_prompt_revision.md", prompt_for_asset)
    first_prompt = candidates[0].prompt if candidates else prompt_for_asset
    write_text_file(icon_work / "icon_final_image_prompt.md", first_prompt)
    for candidate in candidates:
        if candidate.png and candidate.file_name:
            (icon_work / candidate.file_name).write_bytes(candidate.png)
        if candidate.url and candidate.url_file_name:
            write_text_file(icon_work / candidate.url_file_name, candidate.url + "\n")
    first = candidates[0] if candidates else None
    if first and first.png:
        (icon_work / "icon_candidate_1.png").write_bytes(first.png)
    if first and first.url:
        write_text_file(icon_work / "icon_candidate_1.url.txt", first.url + "\n")

    new_entries = [candidate.manifest_entry() for candidate in candidates if not candidate.is_fallback]
    existing_candidate_ids = {str(entry.get("candidate_id") or entry.get("id") or "") for entry in new_entries}
    retained_entries = [
        entry
        for entry in existing_entries
        if (
            not isinstance(entry, dict)
            or (
                str(entry.get("candidate_id") or entry.get("id") or "") not in existing_candidate_ids
                and not manifest_entry_is_fallback(entry)
            )
        )
    ]
    combined_entries = new_entries + retained_entries
    for number, entry in enumerate(combined_entries, start=1):
        if isinstance(entry, dict):
            entry["number"] = number
    summary = image_api_summary(candidates, style_settings, image_failure_diagnostics_from_reports(image_reports))
    summary.update(
        {
            "revision_mode": revision_mode,
            "image_quality_mode": image_quality_mode,
            "user_revision_instruction": user_revision_instruction,
            "final_image_api_prompt": first_prompt,
            "image_api_seconds": timings.get("image_api_call", 0.0),
            "regeneration_candidate_count": len(candidates),
        }
    )
    manifest.update(
        {
            "schema_version": max(3, int(manifest.get("schema_version") or 0)),
            "standard_icon_size": "512x512",
            "api_icon_size": API_ICON_RESOLUTION,
            "legacy_candidate_png": "icon_candidate_1.png",
            "function_interpretation": brief.to_dict(),
            "image_api_summary": summary,
            "last_regeneration": {
                "revision_mode": revision_mode,
                "image_quality_mode": image_quality_mode,
                "user_revision_instruction": user_revision_instruction,
                "final_image_api_prompt": first_prompt,
                "timings": timings,
            },
            "candidates": combined_entries,
        }
    )
    write_json_file(icon_work / "candidate_manifest.json", manifest)
    write_json_file(
        icon_work / "ai_generation_report.json",
        {
            "schema_version": 1,
            "text_prompt_generation_status": "not_applicable",
            "image_generation_status": "success" if summary.get("image_api_success") else "failed",
            "image_model": summary.get("model", ""),
            "api_candidate_count": summary.get("api_candidate_count", 0),
            "failure_class": summary.get("failure_class", ""),
            "failure_message": summary.get("failure_message", ""),
            "admin_next_action": summary.get("admin_next_action", ""),
            "selected_icon_source": summary.get("selected_icon_source", DEFAULT_ICON_SOURCE),
            "default_icon_used": summary.get("default_icon_used", False),
            "default_icon_reason": summary.get("default_icon_reason", ""),
            "package_secret_scan_status": summary.get("package_secret_scan_status", "not_recorded"),
            "ai_payload_secret_scan_status": summary.get("ai_payload_secret_scan_status", "not_run"),
            "ai_submission_blocked": summary.get("ai_submission_blocked", False),
            "ai_submission_block_reason": summary.get("ai_submission_block_reason", ""),
        },
    )
    write_text_file(
        icon_work / "ai_generation_report.md",
        "\n".join(
            [
                "# AI Generation Report",
                "",
                "## Icon Regeneration",
                "",
                f"revision_mode: {revision_mode}",
                f"image_quality_mode: {image_quality_mode}",
                f"candidate_count: {len(candidates)}",
                f"api_candidate_count: {sum(1 for candidate in candidates if is_api_candidate(candidate))}",
                f"image_api_seconds: {timings.get('image_api_call', 0.0):.3f}",
                "",
                "## Admin Diagnosis",
                "",
                "text_prompt_generation_status: not_applicable",
                f"image_generation_status: {'success' if summary.get('image_api_success') else 'failed'}",
                f"image_model: {summary.get('model') or 'unknown'}",
                f"api_candidate_count: {summary.get('api_candidate_count', 0)}",
                f"failure_class: {summary.get('failure_class') or 'none'}",
                f"failure_message: {summary.get('failure_message') or 'none'}",
                f"admin_next_action: {summary.get('admin_next_action') or 'none'}",
                f"selected_icon_source: {summary.get('selected_icon_source') or DEFAULT_ICON_SOURCE}",
                f"default_icon_used: {str(bool(summary.get('default_icon_used'))).lower()}",
                f"default_icon_reason: {summary.get('default_icon_reason') or DEFAULT_ICON_REASON}",
                f"package_secret_scan_status: {summary.get('package_secret_scan_status') or 'not_recorded'}",
                f"ai_payload_secret_scan_status: {summary.get('ai_payload_secret_scan_status') or 'not_run'}",
                f"ai_submission_blocked: {str(bool(summary.get('ai_submission_blocked'))).lower()}",
                f"ai_submission_block_reason: {summary.get('ai_submission_block_reason') or 'none'}",
                "",
                "## Final Image API Prompt",
                "",
                first_prompt,
                "",
                "## Image Generation",
                "",
                "\n\n".join(image_reports),
                "",
                "## Timing",
                "",
                json.dumps(timings, ensure_ascii=False, indent=2),
            ]
        ),
    )

def update_icon_regeneration_timing(icon_work: Path, timings: dict[str, float]) -> None:
    manifest_path = icon_work / "candidate_manifest.json"
    manifest = read_json_file(manifest_path)
    if not manifest:
        return
    summary = manifest.get("image_api_summary")
    if isinstance(summary, dict):
        summary["image_api_seconds"] = timings.get("image_api_call", 0.0)
        summary["regeneration_timing"] = timings
    last_regeneration = manifest.get("last_regeneration")
    if isinstance(last_regeneration, dict):
        last_regeneration["timings"] = timings
    write_json_file(manifest_path, manifest)

def generate_icon_candidates(
    context: StudioContext,
    brief: IconDesignBrief,
    prompt: str,
    style_reference: str,
    allow_ai: bool,
    ai_skip_reason: str,
    count: int,
    style_settings: dict[str, str] | None = None,
    revision_image_path: str | None = None,
    concepts: list[IconConcept] | None = None,
    api_size: str = API_ICON_RESOLUTION,
    api_quality: str = "medium",
    force_generate: bool = False,
    candidate_id_prefix: str = "icon_candidate",
    file_name_prefix: str = "icon_candidate",
) -> tuple[list[IconCandidateAsset], list[str]]:
    candidates: list[IconCandidateAsset] = []
    style_settings = style_settings or icon_style_settings(None, None, prompt)
    if concepts is None:
        concept_list, reports = generate_icon_concepts(context, brief, prompt, allow_ai, count)
    else:
        concept_list = concepts
        reports = [
            "\n".join(
                [
                    "api: responses.create",
                    "status: skipped",
                    "model: deterministic-icon-regeneration",
                    "used_api: false",
                    "deterministic_reason: icon-regenerate reuses the saved function interpretation and deterministic revision concepts.",
                ]
            )
        ]
    image_skip_report_added = False
    use_edit_api = bool(revision_image_path and Path(revision_image_path).is_file() and not force_generate)
    for index, concept in enumerate(concept_list[:count], start=1):
        variant_prompt = image_api_prompt(
            prompt,
            brief=brief,
            concept=concept,
            prior_candidate_ids=[candidate.candidate_id for candidate in candidates],
            style_settings=style_settings,
        )
        payload_report = scan_ai_payload_text(variant_prompt, context.source_root, f"{candidate_id_prefix}_{index}_image_prompt")
        payload_blocked = payload_report.blocks_ai_submission
        payload_block_reason = ai_submission_block_reason(payload_report)
        if payload_blocked:
            image_result = None
            reports.append(skipped_image_report(payload_block_reason, error_category="secret_scan_blocked"))
        elif allow_ai and use_edit_api:
            image_result = _edit_image(variant_prompt, str(revision_image_path), size=api_size, quality=api_quality)
        elif allow_ai:
            image_result = _generate_image(variant_prompt, size=api_size, quality=api_quality)
        else:
            image_result = None
        png_bytes, image_url, image_note = image_candidate_from_result(image_result, index)
        if image_result:
            reports.append(image_result.report)
        elif not payload_blocked and not image_skip_report_added:
            reports.append(skipped_image_report(ai_skip_reason))
            image_skip_report_added = True

        if png_bytes or image_url:
            scores = score_icon_candidate(brief, concept, candidates)
            candidate = IconCandidateAsset(
                candidate_id=f"{candidate_id_prefix}_{index}",
                number=index,
                source="api_edit" if image_result and image_result.api == "images.edit" else "api_generate",
                prompt=variant_prompt,
                model=image_result.model if image_result else "",
                status=image_result.status if image_result else "success",
                resolution=getattr(image_result, "resolution", api_size) or api_size,
                is_fallback=False,
                png=png_bytes,
                url=image_url,
                file_name=f"{file_name_prefix}_{index}.png" if png_bytes else "",
                url_file_name=f"{file_name_prefix}_{index}.url.txt" if image_url else "",
                notes=f"{concept.direction}: {image_note}",
                api=image_result.api if image_result else "",
                content_type=image_result.content_type if image_result else "",
                fallback_reason="",
                error_category=image_result.error_category if image_result else "",
                failure_class=image_result.failure_class if image_result else "",
                failure_message=image_result.failure_message if image_result else "",
                admin_next_action=image_result.admin_next_action if image_result else "",
                ai_payload_secret_scan_status=secret_scan_status(payload_report),
                ai_submission_blocked=payload_blocked,
                ai_submission_block_reason=payload_block_reason,
                concept_id=concept.concept_id,
                concept=concept.to_dict(),
                scores=scores,
                score_total=sum(scores.values()),
            )
            apply_icon_candidate_quality(candidate, brief, concept, candidates)
            candidates.append(candidate)
            continue

        continue
    return candidates, reports


def _generate_image(prompt: str, **kwargs):
    from . import icon_generator as compat

    return compat.generate_image(prompt, **kwargs)


def _edit_image(prompt: str, image_path: str, **kwargs):
    from . import icon_generator as compat

    return compat.edit_image(prompt, image_path, **kwargs)
