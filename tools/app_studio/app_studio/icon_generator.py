from __future__ import annotations

import json
import os
from pathlib import Path
import re
import time
from typing import Any
import zlib

from .ai_metadata_suggester import build_icon_design_brief, sanitize_ai_text, suggest_icon_prompt
from .default_icon import DEFAULT_ICON_REASON, DEFAULT_ICON_SOURCE, default_icon_png, default_icon_svg
from .models import DependencyReport, IconCandidateAsset, IconConcept, IconDesignBrief, SecretScanReport, StudioContext
from .openai_client import ai_enabled, complete_json, decode_base64_image, failure_guidance, generate_image, has_api_key, edit_image, image_model, is_internal_placeholder_model, normalize_failure_class, text_model
from .secret_scanner import ai_submission_block_reason, scan_ai_payload_text, secret_scan_status


API_ICON_RESOLUTION = "1024x1024"
DEFAULT_ICON_CANDIDATE_COUNT = 3
DEFAULT_ICON_REGENERATION_CANDIDATE_COUNT = 1
MAX_ICON_CANDIDATE_COUNT = 6

ICON_REGENERATION_MODES = {"tweak", "refine", "redesign", "fresh"}
ICON_IMAGE_QUALITY_MODES: dict[str, dict[str, str]] = {
    "draft": {"size": API_ICON_RESOLUTION, "quality": "low"},
    "standard": {"size": API_ICON_RESOLUTION, "quality": "medium"},
    "high": {"size": API_ICON_RESOLUTION, "quality": "high"},
}

ICON_STYLE_PRESETS: dict[str, dict[str, str]] = {
    "user_prompt": {
        "label": "user_prompt",
        "material": "derive the visual material from the user's icon prompt; do not add an unrelated house style",
        "color": "derive color, mood, and contrast from the user's icon prompt",
        "edge": "keep the user's requested style while preserving small-icon readability",
        "lighting": "derive lighting and depth from the user's icon prompt",
        "forbidden": "do not add a separate preset style that conflicts with the user's prompt",
    },
    "modern": {
        "label": "modern",
        "material": "clean contemporary digital icon with crisp high-DPI surfaces",
        "color": "balanced professional colors with one clear accent",
        "edge": "smooth precise edges and readable silhouette",
        "lighting": "soft controlled depth",
        "forbidden": "do not force glass, clay, pencil, watercolor, or photoreal materials",
    },
    "vivid": {
        "label": "vivid",
        "material": "bold graphic app icon",
        "color": "high saturation, strong contrast, energetic accent colors",
        "edge": "sharp simple silhouette and clean outlines",
        "lighting": "clear punchy highlights without clutter",
        "forbidden": "avoid muted corporate palettes and low-contrast pastel-only colors",
    },
    "realistic": {
        "label": "realistic",
        "material": "realistic small object icon with tactile surfaces",
        "color": "natural but polished colors",
        "edge": "physically plausible edges, readable object silhouettes",
        "lighting": "studio-object lighting on a clean icon background",
        "forbidden": "no photo background, no busy scene, no full screenshot",
    },
    "colored_pencil": {
        "label": "colored_pencil",
        "material": "colored-pencil grain, hand-drawn strokes, paper-like texture",
        "color": "layered colored-pencil hues with gentle variation",
        "edge": "visible hand-drawn outline, still clean enough at small size",
        "lighting": "soft hand-rendered shadow",
        "forbidden": "no glassmorphism, no glossy 3D plastic, no photoreal object render",
    },
    "watercolor": {
        "label": "watercolor",
        "material": "watercolor wash with controlled pigment edges",
        "color": "transparent layered color with tasteful saturation",
        "edge": "soft organic edges plus a clear main silhouette",
        "lighting": "paper-light, no hard 3D lighting",
        "forbidden": "no glossy material, no dense UI screenshot",
    },
    "flat_vector": {
        "label": "flat_vector",
        "material": "flat vector shapes",
        "color": "small palette of distinct flat colors",
        "edge": "clear geometric edges and simple negative space",
        "lighting": "no realistic lighting, optional subtle flat shadow",
        "forbidden": "no 3D render, no texture grain, no photoreal object",
    },
    "3d_soft": {
        "label": "3d_soft",
        "material": "soft 3D rounded material",
        "color": "friendly color blocks with gentle gradients",
        "edge": "rounded readable forms, not toy-like clutter",
        "lighting": "soft studio lighting and ambient occlusion",
        "forbidden": "no text, no busy UI, no harsh chrome",
    },
    "glassmorphism": {
        "label": "glassmorphism",
        "material": "translucent glass layers with subtle refraction",
        "color": "cool transparent surfaces with one vivid accent",
        "edge": "crisp glass edges and clear silhouette",
        "lighting": "soft reflective highlights",
        "forbidden": "no muddy low-contrast glass, no tiny text",
    },
    "clay": {
        "label": "clay",
        "material": "matte clay-like dimensional shapes",
        "color": "warm clean clay colors with one accent",
        "edge": "simple rounded sculpted silhouette",
        "lighting": "soft shadows, tactile but uncluttered",
        "forbidden": "no glossy glass, no photoreal background, no fine text",
    },
    "custom": {
        "label": "custom",
        "material": "follow the user's custom style before ToolHub house style",
        "color": "follow the user's custom color request",
        "edge": "keep only enough clarity for small icon readability",
        "lighting": "follow the user's custom lighting request",
        "forbidden": "do not override the user's custom style with generic modern polish",
    },
}

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

ICON_CONCEPT_DIRECTIONS = [
    {
        "id": "literal",
        "label": "literal / function-first",
        "guidance": "Make the concrete action and input-to-output relationship immediately recognizable.",
        "style_family": "friendly dimensional workflow icon",
    },
    {
        "id": "balanced",
        "label": "balanced / modern functional",
        "guidance": "Balance clear workflow meaning with a polished modern silhouette and refined materials.",
        "style_family": "clean glassmorphism with restrained dimensional depth",
    },
    {
        "id": "signature",
        "label": "signature / memorable",
        "guidance": "Create a distinctive, ownable silhouette that still shows the app's action relationship.",
        "style_family": "premium editorial app icon with bold accent shape",
    },
]


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


def normalize_icon_revision_mode(mode: str | None) -> str:
    selected = (mode or "refine").strip().lower()
    return selected if selected in ICON_REGENERATION_MODES else "refine"


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


def select_icon_manifest_candidate(entries: list[Any], candidate_id: str | None) -> dict[str, Any] | None:
    candidates = [entry for entry in entries if isinstance(entry, dict)]
    requested = (candidate_id or "").strip()
    if requested:
        for candidate in candidates:
            if str(candidate.get("candidate_id") or candidate.get("id") or "") == requested:
                return candidate
    return candidates[0] if candidates else None


def selected_candidate_image_path(icon_work: Path, candidate: dict[str, Any] | None) -> Path | None:
    if not candidate:
        legacy = icon_work / "icon_candidate_1.png"
        return legacy if legacy.is_file() else None
    file_name = str(candidate.get("file_name") or "").strip()
    if file_name:
        path = icon_work / file_name
        if path.is_file():
            return path
    legacy = icon_work / "icon_candidate_1.png"
    return legacy if legacy.is_file() else None


def build_icon_revision_api_base_prompt(
    brief: IconDesignBrief,
    base_candidate: dict[str, Any] | None,
    user_revision_instruction: str,
    revision_mode: str,
    icon_style_preset: str,
    icon_style_custom: str,
) -> str:
    mode = normalize_icon_revision_mode(revision_mode)
    base_id = str(base_candidate.get("candidate_id") or base_candidate.get("id") or "unknown") if base_candidate else "unknown"
    base_status = str(base_candidate.get("status") or "unknown") if base_candidate else "unknown"
    base_source = str(base_candidate.get("source") or "unknown") if base_candidate else "unknown"
    style_text = sanitize_ai_text(icon_style_custom, 900) if icon_style_custom else ""
    return "\n".join(
        [
            "ToolHub App Studio icon image request.",
            f"revision_mode: {mode}",
            f"change_strength: {mode}",
            "",
            "USER ICON REQUEST - PRIMARY SOURCE OF TRUTH:",
            sanitize_ai_text(user_revision_instruction, 2200),
            "",
            "Priority rule: follow the USER ICON REQUEST above before generated app metadata, previous prompts, style presets, or candidate concepts.",
            "If another section conflicts with the USER ICON REQUEST, ignore that conflicting generated section.",
            "The user may specify motif, composition, style, material, color, lighting, brand-like references, or motion; preserve those requirements explicitly.",
            "",
            "USER STYLE INSTRUCTION:",
            style_text or "Use the style described in the USER ICON REQUEST. Do not apply an additional preset style.",
            "",
            "APP CONTEXT - SECONDARY, ONLY TO AVOID A WRONG APP MEANING:",
            f"app_name: {brief.name}",
            f"app_purpose: {brief.purpose}",
            f"primary_action: {brief.primary_action}",
            f"input_objects: {', '.join(brief.input_objects)}",
            f"output_objects: {', '.join(brief.output_objects)}",
            f"action_flow: {brief.action_flow}",
            "",
            "PREVIOUS CANDIDATE REFERENCE:",
            f"base_candidate_id: {base_id}",
            f"base_candidate_status: {base_status}",
            f"base_candidate_source: {base_source}",
            f"selected_style_preset: {icon_style_preset or 'user_prompt'}",
            "Do not copy the previous image prompt or composition unless the USER ICON REQUEST asks to preserve it.",
            "",
            revision_mode_policy(mode),
        ]
    )


def revision_mode_policy(mode: str) -> str:
    if mode == "tweak":
        return "\n".join(
            [
                "MODE POLICY:",
                "- Use images.edit when a previous PNG is available.",
                "- Preserve the previous composition, primary motif, action flow, and color family.",
                "- Change only the requested color, line, texture, small detail, or minor readability issue.",
            ]
        )
    if mode == "refine":
        return "\n".join(
            [
                "MODE POLICY:",
                "- Use images.edit when a previous PNG is available.",
                "- Preserve the app function and useful main idea.",
                "- Improve supporting motif, color balance, silhouette, or style with a visible medium change.",
            ]
        )
    if mode == "redesign":
        return "\n".join(
            [
                "MODE POLICY:",
                "- Prefer a new generated image rather than editing the previous PNG.",
                "- Treat the previous candidate as reference only.",
                "- Must change the main motif or composition; color-only changes are insufficient.",
            ]
        )
    return "\n".join(
        [
            "MODE POLICY:",
            "- Do not use the previous PNG as an input image.",
            "- Do not inherit the old prompt or composition strongly.",
            "- Create a substantially different concept family, primary motif, composition, and color focus from the saved candidate.",
        ]
    )


def icon_revision_concepts(
    brief: IconDesignBrief,
    count: int,
    mode: str,
    base_candidate: dict[str, Any] | None,
    user_revision_instruction: str = "",
) -> list[IconConcept]:
    user_instruction = sanitize_ai_text(user_revision_instruction, 900)
    if user_instruction:
        return user_directed_icon_concepts(brief, count, mode, user_instruction)
    base = deterministic_icon_concepts(brief, max(count, 3))
    if mode == "tweak":
        ordered = base
    elif mode == "refine":
        ordered = [base[1], base[0], base[2]]
    else:
        ordered = [base[2], base[1], base[0]]
    concepts: list[IconConcept] = []
    for index, concept in enumerate(ordered[:count], start=1):
        if mode == "tweak":
            direction = "tweak"
            composition = f"Preserve the previous layout while applying the user's specific change: {concept.composition}"
            style_family = concept.style_family
        elif mode == "refine":
            direction = "refine"
            composition = f"Keep the main function but visibly improve the supporting motif, color, or silhouette: {concept.composition}"
            style_family = concept.style_family
        elif mode == "redesign":
            direction = "redesign"
            composition = f"Change the main motif or composition from the previous candidate while preserving {brief.action_flow}: {concept.composition}"
            style_family = "redesigned " + concept.style_family
        else:
            direction = "fresh"
            composition = f"Create a fresh, unrelated composition family for {brief.action_flow}; do not reuse the previous layout: {concept.composition}"
            style_family = "fresh alternative " + concept.style_family
        concepts.append(
            IconConcept(
                concept_id=f"{direction}_{index}",
                direction=direction,
                concept=f"{direction}: {brief.action_flow}",
                primary_motif=concept.primary_motif,
                secondary_motif=concept.secondary_motif,
                composition=composition,
                style_family=style_family,
                why_specific=concept.why_specific,
                avoid_elements=brief.avoid_generic,
            )
        )
    return concepts


def user_directed_icon_concepts(brief: IconDesignBrief, count: int, mode: str, user_instruction: str) -> list[IconConcept]:
    mode = normalize_icon_revision_mode(mode)
    directions = {
        "tweak": "small targeted variation of the user request",
        "refine": "polished version of the user request",
        "redesign": "new composition that follows the user request",
        "fresh": "fresh concept family that follows the user request",
    }
    concepts: list[IconConcept] = []
    for index in range(max(count, 1)):
        if index == 0:
            composition = f"Make the user's requested icon the main composition: {user_instruction}"
        elif index == 1:
            composition = f"Keep the user's requested motif and style, but simplify the silhouette for small icon readability: {user_instruction}"
        else:
            composition = f"Keep the user's requested motif, style, and transformation idea while changing only spacing, depth, or emphasis: {user_instruction}"
        concepts.append(
            IconConcept(
                concept_id=f"user_prompt_{index + 1}",
                direction=mode,
                concept=f"{directions.get(mode, 'user-directed icon')}: {user_instruction}",
                primary_motif="the main motif explicitly requested by the user",
                secondary_motif=f"secondary app context: {brief.action_flow}",
                composition=composition,
                style_family="user-specified style from the prompt",
                why_specific="Follows the user's written icon request first and uses app metadata only as secondary context.",
                avoid_elements=[
                    "unrequested style preset",
                    "generic abstract shapes only",
                    "tiny unreadable text",
                    "crowded UI screenshots",
                    "watermark",
                ],
            )
        )
    return concepts[:count]


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


def manifest_entry_is_fallback(entry: dict[str, Any]) -> bool:
    source = str(entry.get("source") or "")
    return bool(entry.get("fallback")) or "fallback" in source


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
            image_result = edit_image(variant_prompt, str(revision_image_path), size=api_size, quality=api_quality)
        elif allow_ai:
            image_result = generate_image(variant_prompt, size=api_size, quality=api_quality)
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


def generate_icon_concepts(
    context: StudioContext,
    brief: IconDesignBrief,
    prompt: str,
    allow_ai: bool,
    count: int,
) -> tuple[list[IconConcept], list[str]]:
    deterministic = deterministic_icon_concepts(brief, count)
    if not allow_ai:
        return deterministic, [skipped_concept_report("AI use was not allowed.")]

    result = complete_json(
        (
            "Return strict JSON with a concepts array. "
            "Each concept must include id, concept, primary_motif, secondary_motif, "
            "composition, style_family, why_specific, avoid_elements. "
            "Create genuinely different icon concepts, not minor style variations."
        ),
        json.dumps(
            {
                "app": {"app_id": context.app_id, "name": context.name},
                "icon_design_brief": brief.to_dict(),
                "base_prompt": sanitize_ai_text(prompt, 2200),
                "required_directions": ["literal", "balanced", "signature"],
                "rules": [
                    "literal: the app function is obvious at a glance.",
                    "balanced: modern and polished while still showing the action relationship.",
                    "signature: memorable and distinctive, with a different main silhouette.",
                    "Every concept must visualize the primary action using 2 to 4 meaningful objects.",
                    "Avoid generic abstract shapes, document-only, gear-only, check-only, nodes-only, and initial-letter-only designs.",
                    "No readable text or logo letters.",
                ],
            },
            ensure_ascii=False,
        ),
    )
    if not result.ok:
        return deterministic, [result.report]
    concepts = parse_icon_concepts(result.content, brief, count)
    if len(concepts) < count:
        existing = {concept.concept_id for concept in concepts}
        concepts.extend([concept for concept in deterministic if concept.concept_id not in existing])
    return concepts[:count], [result.report]


def parse_icon_concepts(content: str, brief: IconDesignBrief, count: int) -> list[IconConcept]:
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        return []
    if isinstance(parsed, dict):
        items = parsed.get("concepts")
    else:
        items = parsed
    if not isinstance(items, list):
        return []
    concepts: list[IconConcept] = []
    for index, item in enumerate(items[: max(count, 3)], start=1):
        if not isinstance(item, dict):
            continue
        direction = sanitize_ai_text(str(item.get("direction") or item.get("id") or ICON_CONCEPT_DIRECTIONS[(index - 1) % 3]["id"]), 40)
        concept_id = sanitize_ai_text(str(item.get("id") or f"{direction}_{index}"), 60).replace(" ", "_") or f"concept_{index}"
        avoid_elements = item.get("avoid_elements")
        if not isinstance(avoid_elements, list):
            avoid_elements = brief.avoid_generic
        concepts.append(
            IconConcept(
                concept_id=concept_id,
                direction=direction,
                concept=sanitize_ai_text(str(item.get("concept") or f"{brief.primary_action} workflow"), 220),
                primary_motif=sanitize_ai_text(str(item.get("primary_motif") or brief.composition_template), 180),
                secondary_motif=sanitize_ai_text(str(item.get("secondary_motif") or ", ".join(brief.output_objects[:2])), 160),
                composition=sanitize_ai_text(str(item.get("composition") or brief.composition_template), 260),
                style_family=sanitize_ai_text(str(item.get("style_family") or ICON_CONCEPT_DIRECTIONS[(index - 1) % 3]["style_family"]), 160),
                why_specific=sanitize_ai_text(str(item.get("why_specific") or brief.action_flow), 220),
                avoid_elements=[sanitize_ai_text(str(value), 120) for value in avoid_elements[:8]],
            )
        )
    return concepts


def deterministic_icon_concepts(brief: IconDesignBrief, count: int) -> list[IconConcept]:
    """Deterministic prompt concepts only; this never creates local image candidates."""
    concepts: list[IconConcept] = []
    for index in range(max(count, 3)):
        direction = ICON_CONCEPT_DIRECTIONS[index % len(ICON_CONCEPT_DIRECTIONS)]
        if direction["id"] == "literal":
            composition = brief.composition_template
            primary = f"{brief.primary_action} action between {', '.join(brief.input_objects[:2])} and {', '.join(brief.output_objects[:2])}"
            secondary = "clear directional path"
        elif direction["id"] == "balanced":
            composition = f"Layer {brief.input_objects[0] if brief.input_objects else 'input'} and {brief.output_objects[0] if brief.output_objects else 'output'} around one clean action arc."
            primary = f"polished {brief.primary_action} workflow silhouette"
            secondary = "subtle material contrast and action arc"
        else:
            composition = f"Use one bold signature shape to show {brief.action_flow}, changing the silhouette and color focus from earlier concepts."
            primary = f"memorable {brief.primary_action} emblem"
            secondary = "distinct accent shape tied to the output"
        concepts.append(
            IconConcept(
                concept_id=f"{direction['id']}_{index + 1}",
                direction=direction["id"],
                concept=f"{direction['label']}: {brief.action_flow}",
                primary_motif=primary,
                secondary_motif=secondary,
                composition=composition,
                style_family=direction["style_family"],
                why_specific=f"Specific to this app because it shows {brief.action_flow}, not a generic app symbol.",
                avoid_elements=brief.avoid_generic,
            )
        )
    return concepts[:count]


def skipped_concept_report(reason: str) -> str:
    return "\n".join(
        [
            "api: responses.create",
            "status: skipped",
            f"model: {text_model()}",
            "used_api: false",
            f"deterministic_reason: {reason or 'AI use was not allowed.'}",
        ]
    )


def score_icon_candidate(brief: IconDesignBrief, concept: IconConcept, prior_candidates: list[IconCandidateAsset]) -> dict[str, float]:
    text = " ".join(
        [
            concept.concept,
            concept.primary_motif,
            concept.secondary_motif,
            concept.composition,
            concept.why_specific,
        ]
    ).lower()
    action_hit = brief.primary_action and brief.primary_action.lower() in text
    object_hits = sum(1 for value in [*brief.input_objects, *brief.output_objects] if value.lower() in text)
    semantic = 3 + (2 if action_hit else 0) + min(3, object_hits)
    specificity = 4 + min(3, object_hits) + (1 if "generic" in " ".join(concept.avoid_elements).lower() else 0)
    object_count = estimate_visual_object_count(concept.composition)
    legibility = 8 if 2 <= object_count <= 4 else 5
    aesthetics = 7 if any(term in concept.style_family.lower() for term in ["modern", "polished", "premium", "glass", "dimensional", "editorial"]) else 5
    diversity = 8
    for prior in prior_candidates:
        prior_concept = prior.concept or {}
        prior_text = " ".join(
            str(prior_concept.get(key, ""))
            for key in ["concept", "primary_motif", "composition", "style_family"]
        ).lower()
        if jaccard_similarity(text, prior_text) > 0.42:
            diversity = min(diversity, 4)
    return {
        "semantic_clarity": float(min(10, semantic)),
        "specificity": float(min(10, specificity)),
        "small_size_legibility": float(legibility),
        "aesthetics": float(aesthetics),
        "diversity": float(diversity),
    }


def apply_icon_candidate_quality(
    candidate: IconCandidateAsset,
    brief: IconDesignBrief,
    concept: IconConcept,
    prior_candidates: list[IconCandidateAsset],
) -> None:
    evaluation = evaluate_icon_candidate_quality(candidate, brief, concept, prior_candidates)
    candidate.semantic_score = evaluation["semantic_score"]
    candidate.specificity_score = evaluation["specificity_score"]
    candidate.small_size_score = evaluation["small_size_score"]
    candidate.aesthetic_score = evaluation["aesthetic_score"]
    candidate.revision_follow_score = evaluation["revision_follow_score"]
    candidate.generic_risk_score = evaluation["generic_risk_score"]
    candidate.quality_total = evaluation["quality_total"]
    candidate.quality_label = str(evaluation["quality_label"])
    candidate.quality_reasons = list(evaluation["quality_reasons"])
    candidate.quality_warnings = list(evaluation["quality_warnings"])
    candidate.score_basis = str(evaluation["score_basis"])
    candidate.image_evaluation_status = str(evaluation["image_evaluation_status"])
    candidate.image_evaluation_note = str(evaluation["image_evaluation_note"])


def evaluate_icon_candidate_quality(
    candidate: IconCandidateAsset,
    brief: IconDesignBrief,
    concept: IconConcept,
    prior_candidates: list[IconCandidateAsset],
) -> dict[str, Any]:
    scores = candidate.scores or score_icon_candidate(brief, concept, prior_candidates)
    semantic = float(scores.get("semantic_clarity") or 0.0)
    specificity = float(scores.get("specificity") or 0.0)
    small_size = float(scores.get("small_size_legibility") or 0.0)
    aesthetic = float(scores.get("aesthetics") or 0.0)
    reasons: list[str] = []
    warnings: list[str] = []
    note_parts: list[str] = []

    prompt_text = " ".join(
        [
            candidate.prompt,
            concept.concept,
            concept.primary_motif,
            concept.secondary_motif,
            concept.composition,
            concept.why_specific,
            " ".join(concept.avoid_elements),
        ]
    )
    generic_risk = generic_icon_risk_score(prompt_text, brief, candidate)
    revision_follow = revision_follow_score(candidate.prompt, candidate, warnings)

    pixel_status = "not_run"
    if candidate.png:
        metrics = png_quality_metrics(candidate.png)
        pixel_status = "deterministic_png_check"
        if metrics.get("ok"):
            small_size = max(small_size, float(metrics["small_size_score"]))
            aesthetic = max(aesthetic, float(metrics["aesthetic_score"]))
            reasons.extend(metrics["reasons"])
            warnings.extend(metrics["warnings"])
            note_parts.append(
                f"PNG pixels inspected with deterministic small-size and contrast checks ({metrics['width']}x{metrics['height']})."
            )
        else:
            warnings.append(str(metrics.get("warning") or "PNG pixels could not be decoded for small-size checks."))
            note_parts.append("PNG pixel inspection was attempted but unavailable; prompt/concept checks were used.")
    elif candidate.url:
        pixel_status = "not_run"
        warnings.append("API returned an image URL; ToolHub did not download pixels for this local evaluation.")
        note_parts.append("Pixel evaluation was not run because only an image URL was available.")
    else:
        warnings.append("No PNG candidate was available for pixel evaluation.")
        note_parts.append("Pixel evaluation was not run because no PNG bytes were available.")

    if candidate.is_fallback:
        warnings.append("Fallback PNG is a placeholder and should not be treated as a successful AI image.")
        aesthetic = min(aesthetic, 7.0)
    if candidate.source == "fallback_after_api_failure":
        revision_follow = min(revision_follow, 6.0)
        warnings.append("Image API failed or returned unusable content; revision fidelity is uncertain.")
    if generic_risk >= 7:
        warnings.append("Candidate may be too generic for this app purpose.")
    elif generic_risk <= 3:
        reasons.append("App-specific action/object signals are present.")
    if semantic >= 8:
        reasons.append("The concept clearly references the app function.")
    if specificity >= 8:
        reasons.append("The candidate is more specific than a generic launcher icon.")

    quality_total = candidate_quality_total(
        semantic,
        specificity,
        small_size,
        aesthetic,
        revision_follow,
        generic_risk,
    )
    return {
        "semantic_score": round(semantic, 2),
        "specificity_score": round(specificity, 2),
        "small_size_score": round(small_size, 2),
        "aesthetic_score": round(aesthetic, 2),
        "revision_follow_score": round(revision_follow, 2),
        "generic_risk_score": round(generic_risk, 2),
        "quality_total": round(quality_total, 2),
        "quality_label": quality_label(quality_total),
        "quality_reasons": dedupe_text(reasons)[:5],
        "quality_warnings": dedupe_text(warnings)[:6],
        "score_basis": "rule_based_pixels_and_prompt" if pixel_status == "deterministic_png_check" else "rule_based_prompt_and_manifest",
        "image_evaluation_status": pixel_status,
        "image_evaluation_note": " ".join(note_parts)
        or "Vision evaluation was not run; deterministic prompt/concept checks were used.",
    }


def candidate_quality_total(
    semantic: float,
    specificity: float,
    small_size: float,
    aesthetic: float,
    revision_follow: float,
    generic_risk: float,
) -> float:
    positive = semantic + specificity + small_size + aesthetic + revision_follow
    generic_balance = max(0.0, 10.0 - generic_risk)
    return max(0.0, min(100.0, ((positive + generic_balance) / 60.0) * 100.0))


def quality_label(total: float) -> str:
    if total >= 82:
        return "excellent"
    if total >= 68:
        return "good"
    if total >= 52:
        return "usable"
    return "weak"


def generic_icon_risk_score(text: str, brief: IconDesignBrief, candidate: IconCandidateAsset) -> float:
    normalized = text.lower()
    risk = 6.0
    action = brief.primary_action.lower()
    if action and action in normalized:
        risk -= 2.0
    object_hits = sum(1 for value in [*brief.input_objects, *brief.output_objects] if value.lower() in normalized)
    risk -= min(3.0, float(object_hits))
    if brief.composition_template and any(term in normalized for term in ["flow", "converging", "branching", "transforming", "side by side", "arrow"]):
        risk -= 1.0
    generic_terms = [
        "generic abstract",
        "document-only",
        "gear-only",
        "check-only",
        "nodes-only",
        "initial-letter",
        "logo letters",
    ]
    risk += sum(1.5 for term in generic_terms if term in normalized)
    if candidate.is_fallback:
        risk += 1.5
    return max(0.0, min(10.0, risk))


def revision_follow_score(prompt: str, candidate: IconCandidateAsset, warnings: list[str]) -> float:
    instruction = extract_revision_instruction(prompt)
    if not instruction:
        return 8.0
    terms = meaningful_terms(instruction)
    if not terms:
        return 7.0
    normalized_prompt = prompt.lower()
    hits = sum(1 for term in terms if term in normalized_prompt)
    score = 4.0 + min(5.0, (hits / max(1, len(terms))) * 5.0)
    if candidate.api == "images.edit" and candidate.status in {"success", "completed"}:
        score += 1.0
    if candidate.is_fallback:
        warnings.append("Revision instruction is present in the prompt, but fallback output cannot prove visual compliance.")
    return max(0.0, min(10.0, score))


def extract_revision_instruction(prompt: str) -> str:
    markers = [
        "USER ICON REQUEST - HIGHEST PRIORITY:",
        "USER ICON REQUEST - PRIMARY SOURCE OF TRUTH:",
        "USER REVISION INSTRUCTION - MUST FOLLOW VERBATIM:",
    ]
    for marker in markers:
        if marker not in prompt:
            continue
        tail = prompt.split(marker, 1)[1]
        return sanitize_ai_text(tail.split("\n\n", 1)[0], 800)
    return ""


def meaningful_terms(text: str) -> list[str]:
    normalized = re.sub(r"[^0-9A-Za-z\u3040-\u30ff\u3400-\u9fff]+", " ", text.lower())
    stop = {"the", "and", "for", "with", "this", "that", "icon", "app", "png", "する", "して", "ください"}
    terms = []
    for term in normalized.split():
        if len(term) < 3 or term in stop:
            continue
        if term not in terms:
            terms.append(term)
    return terms[:16]


def png_quality_metrics(data: bytes) -> dict[str, Any]:
    decoded = decode_png_rows_rgba(data)
    if not decoded:
        width, height = png_dimensions(data)
        return {
            "ok": False,
            "warning": f"PNG pixel decoder could not inspect this file ({width}x{height or '?'}).",
        }
    width, height, rows = decoded
    samples = sampled_rgba_pixels(rows, width, height)
    if not samples:
        return {"ok": False, "warning": "PNG had no visible pixels to evaluate."}
    luminances = [rgba_luminance(pixel) for pixel in samples if pixel[3] > 16]
    alpha_pixels = sum(1 for pixel in samples if pixel[3] > 16)
    alpha_ratio = alpha_pixels / max(1, len(samples))
    contrast = (max(luminances) - min(luminances)) / 255.0 if luminances else 0.0
    distinct = len({quantized_rgb(pixel) for pixel in samples if pixel[3] > 16})
    bbox_ratio = visible_bbox_ratio(rows, width, height)
    downsample16 = downsample_edge_score(rows, width, height, 16)
    downsample32 = downsample_edge_score(rows, width, height, 32)

    warnings: list[str] = []
    reasons: list[str] = []
    if width < 256 or height < 256:
        warnings.append("PNG resolution is lower than the preferred API review size.")
    if contrast < 0.20:
        warnings.append("Low contrast may reduce small-size legibility.")
    else:
        reasons.append("Contrast is sufficient for small-size review.")
    if distinct < 4:
        warnings.append("Very few distinguishable color groups were detected.")
    bbox_margin_score = 0.5
    if alpha_ratio < 0.98:
        if bbox_ratio < 0.18:
            warnings.append("Visible motif appears too small inside the icon canvas.")
            bbox_margin_score = -1.0
        elif bbox_ratio > 0.96:
            warnings.append("Visible motif may be too close to the icon edges.")
            bbox_margin_score = -0.5
        else:
            reasons.append("Visible motif uses the canvas with reasonable margins.")
            bbox_margin_score = 1.0
    if downsample16 < 0.16:
        warnings.append("16px downsample loses too much shape information.")
    elif downsample32 >= 0.20:
        reasons.append("32px downsample keeps a recognizable silhouette.")

    small_score = 4.0
    small_score += min(2.0, contrast * 4.0)
    small_score += min(2.0, downsample16 * 8.0)
    small_score += bbox_margin_score
    small_score += 1.0 if distinct >= 4 else -1.0
    aesthetic_score = 5.0
    aesthetic_score += min(2.0, contrast * 3.0)
    aesthetic_score += 1.0 if distinct >= 5 else 0.0
    aesthetic_score += 1.0 if 0.45 <= alpha_ratio <= 1.0 else 0.0
    aesthetic_score += 1.0 if alpha_ratio >= 0.98 or 0.25 <= bbox_ratio <= 0.90 else 0.0

    return {
        "ok": True,
        "width": width,
        "height": height,
        "small_size_score": max(0.0, min(10.0, small_score)),
        "aesthetic_score": max(0.0, min(10.0, aesthetic_score)),
        "warnings": warnings,
        "reasons": reasons,
    }


def decode_png_rows_rgba(data: bytes) -> tuple[int, int, list[bytes]] | None:
    if not data.startswith(PNG_SIGNATURE):
        return None
    offset = len(PNG_SIGNATURE)
    width = 0
    height = 0
    bit_depth = 0
    color_type = 0
    idat = bytearray()
    try:
        while offset + 8 <= len(data):
            length = int.from_bytes(data[offset:offset + 4], "big")
            chunk_type = data[offset + 4:offset + 8]
            chunk_data = data[offset + 8:offset + 8 + length]
            offset += 12 + length
            if chunk_type == b"IHDR":
                width = int.from_bytes(chunk_data[0:4], "big")
                height = int.from_bytes(chunk_data[4:8], "big")
                bit_depth = chunk_data[8]
                color_type = chunk_data[9]
                if chunk_data[12] != 0:
                    return None
            elif chunk_type == b"IDAT":
                idat.extend(chunk_data)
            elif chunk_type == b"IEND":
                break
        if not width or not height or bit_depth != 8 or color_type not in {0, 2, 4, 6}:
            return None
        channels = {0: 1, 2: 3, 4: 2, 6: 4}[color_type]
        row_len = width * channels
        raw = zlib.decompress(bytes(idat))
        rows: list[bytes] = []
        prev = bytearray(row_len)
        cursor = 0
        for _ in range(height):
            filter_type = raw[cursor]
            cursor += 1
            row = bytearray(raw[cursor:cursor + row_len])
            cursor += row_len
            unfilter_png_row(row, prev, channels, filter_type)
            rows.append(convert_png_row_to_rgba(row, color_type))
            prev = row
        return width, height, rows
    except Exception:
        return None


def unfilter_png_row(row: bytearray, prev: bytearray, bpp: int, filter_type: int) -> None:
    if filter_type == 0:
        return
    for index in range(len(row)):
        left = row[index - bpp] if index >= bpp else 0
        up = prev[index] if index < len(prev) else 0
        up_left = prev[index - bpp] if index >= bpp and index - bpp < len(prev) else 0
        if filter_type == 1:
            row[index] = (row[index] + left) & 0xFF
        elif filter_type == 2:
            row[index] = (row[index] + up) & 0xFF
        elif filter_type == 3:
            row[index] = (row[index] + ((left + up) // 2)) & 0xFF
        elif filter_type == 4:
            row[index] = (row[index] + paeth_predictor(left, up, up_left)) & 0xFF


def paeth_predictor(left: int, up: int, up_left: int) -> int:
    estimate = left + up - up_left
    left_delta = abs(estimate - left)
    up_delta = abs(estimate - up)
    up_left_delta = abs(estimate - up_left)
    if left_delta <= up_delta and left_delta <= up_left_delta:
        return left
    if up_delta <= up_left_delta:
        return up
    return up_left


def convert_png_row_to_rgba(row: bytearray, color_type: int) -> bytes:
    output = bytearray()
    if color_type == 6:
        return bytes(row)
    if color_type == 2:
        for index in range(0, len(row), 3):
            output.extend([row[index], row[index + 1], row[index + 2], 255])
    elif color_type == 4:
        for index in range(0, len(row), 2):
            output.extend([row[index], row[index], row[index], row[index + 1]])
    else:
        for value in row:
            output.extend([value, value, value, 255])
    return bytes(output)


def png_dimensions(data: bytes) -> tuple[int, int]:
    if data.startswith(PNG_SIGNATURE) and len(data) >= 24:
        return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
    return 0, 0


def sampled_rgba_pixels(rows: list[bytes], width: int, height: int) -> list[tuple[int, int, int, int]]:
    stride = max(1, max(width, height) // 96)
    samples: list[tuple[int, int, int, int]] = []
    for y in range(0, height, stride):
        row = rows[y]
        for x in range(0, width, stride):
            offset = x * 4
            samples.append((row[offset], row[offset + 1], row[offset + 2], row[offset + 3]))
    return samples


def rgba_luminance(pixel: tuple[int, int, int, int]) -> float:
    return 0.2126 * pixel[0] + 0.7152 * pixel[1] + 0.0722 * pixel[2]


def quantized_rgb(pixel: tuple[int, int, int, int]) -> tuple[int, int, int]:
    return pixel[0] // 48, pixel[1] // 48, pixel[2] // 48


def visible_bbox_ratio(rows: list[bytes], width: int, height: int) -> float:
    min_x = width
    min_y = height
    max_x = -1
    max_y = -1
    stride = max(1, max(width, height) // 160)
    for y in range(0, height, stride):
        row = rows[y]
        for x in range(0, width, stride):
            alpha = row[x * 4 + 3]
            if alpha <= 16:
                continue
            min_x = min(min_x, x)
            min_y = min(min_y, y)
            max_x = max(max_x, x)
            max_y = max(max_y, y)
    if max_x < min_x or max_y < min_y:
        return 0.0
    return ((max_x - min_x + stride) * (max_y - min_y + stride)) / max(1, width * height)


def downsample_edge_score(rows: list[bytes], width: int, height: int, size: int) -> float:
    grid: list[list[float]] = []
    for gy in range(size):
        row_values: list[float] = []
        y0 = int(gy * height / size)
        y1 = max(y0 + 1, int((gy + 1) * height / size))
        for gx in range(size):
            x0 = int(gx * width / size)
            x1 = max(x0 + 1, int((gx + 1) * width / size))
            total = 0.0
            count = 0
            step_y = max(1, (y1 - y0) // 4)
            step_x = max(1, (x1 - x0) // 4)
            for y in range(y0, min(y1, height), step_y):
                row = rows[y]
                for x in range(x0, min(x1, width), step_x):
                    offset = x * 4
                    alpha = row[offset + 3] / 255.0
                    lum = rgba_luminance((row[offset], row[offset + 1], row[offset + 2], row[offset + 3]))
                    total += lum * alpha + 255.0 * (1.0 - alpha)
                    count += 1
            row_values.append(total / max(1, count))
        grid.append(row_values)
    edge_total = 0.0
    edge_count = 0
    for y in range(size):
        for x in range(size):
            current = grid[y][x]
            if x + 1 < size:
                edge_total += abs(current - grid[y][x + 1]) / 255.0
                edge_count += 1
            if y + 1 < size:
                edge_total += abs(current - grid[y + 1][x]) / 255.0
                edge_count += 1
    return edge_total / max(1, edge_count)


def dedupe_text(values: list[str]) -> list[str]:
    output: list[str] = []
    for value in values:
        text = value.strip()
        if text and text not in output:
            output.append(text)
    return output


def estimate_visual_object_count(text: str) -> int:
    normalized = text.lower()
    if "2 to 4" in normalized or "two or three" in normalized:
        return 3
    count = 1
    for token in [" and ", " to ", " into ", " with ", " between ", ","]:
        count += normalized.count(token)
    return max(1, min(6, count))


def jaccard_similarity(left: str, right: str) -> float:
    left_terms = {term for term in left.split() if len(term) > 3}
    right_terms = {term for term in right.split() if len(term) > 3}
    if not left_terms or not right_terms:
        return 0.0
    return len(left_terms & right_terms) / len(left_terms | right_terms)


def icon_style_settings(preset: str | None, custom: str | None, prompt: str) -> dict[str, str]:
    selected = normalize_icon_style_preset(preset, prompt)
    settings = dict(ICON_STYLE_PRESETS.get(selected, ICON_STYLE_PRESETS["user_prompt"]))
    settings["preset"] = selected
    custom_text = sanitize_ai_text(custom or "", 800)
    if selected == "custom" and custom_text:
        settings["custom"] = custom_text
        settings["material"] = custom_text
        settings["color"] = "follow the user's custom color and mood request"
        settings["lighting"] = "follow the user's custom lighting request"
    return settings


def normalize_icon_style_preset(preset: str | None, prompt: str = "") -> str:
    value = (preset or "").strip().lower().replace("-", "_").replace(" ", "_")
    if value in ICON_STYLE_PRESETS:
        return value
    return "user_prompt"


def infer_icon_style_preset(text: str) -> str:
    normalized = text.lower()
    rules = [
        ("colored_pencil", ["colored pencil", "colour pencil", "色鉛筆", "鉛筆"]),
        ("watercolor", ["watercolor", "watercolour", "水彩"]),
        ("realistic", ["realistic", "photoreal", "写実", "リアル"]),
        ("vivid", ["vivid", "ビビッド", "高彩度", "鮮やか"]),
        ("flat_vector", ["flat vector", "flat", "フラット", "ベクター"]),
        ("3d_soft", ["3d", "soft 3d", "立体", "ソフト3d"]),
        ("glassmorphism", ["glassmorphism", "glass", "ガラス"]),
        ("clay", ["clay", "クレイ", "粘土"]),
    ]
    for preset, keywords in rules:
        if any(keyword in normalized for keyword in keywords):
            return preset
    return ""


def extract_user_icon_request(prompt: str) -> str:
    markers = [
        "USER ICON REQUEST - HIGHEST PRIORITY:",
        "USER ICON REQUEST - PRIMARY SOURCE OF TRUTH:",
        "USER REVISION INSTRUCTION - MUST FOLLOW VERBATIM:",
        "USER ICON PROMPT - MUST FOLLOW:",
    ]
    for marker in markers:
        index = prompt.find(marker)
        if index < 0:
            continue
        rest = prompt[index + len(marker) :].strip()
        stop_markers = [
            "\n\nPriority rule:",
            "\n\nUSER STYLE INSTRUCTION:",
            "\n\nAPP CONTEXT",
            "\n\nThis instruction",
            "\n\nIcon concept JSON:",
        ]
        end = len(rest)
        for stop in stop_markers:
            stop_index = rest.find(stop)
            if stop_index >= 0:
                end = min(end, stop_index)
        value = sanitize_ai_text(rest[:end], 2200).strip()
        if value:
            return value
    return ""


def image_api_prompt(
    prompt: str,
    brief: IconDesignBrief | None = None,
    concept: IconConcept | None = None,
    prior_candidate_ids: list[str] | None = None,
    style_settings: dict[str, str] | None = None,
) -> str:
    prior = ", ".join(prior_candidate_ids or [])
    concept_data = concept.to_dict() if concept else {}
    style_settings = style_settings or icon_style_settings(None, None, prompt)
    preset = style_settings.get("preset", "user_prompt")
    custom = style_settings.get("custom", "")
    user_request = extract_user_icon_request(prompt) or sanitize_ai_text(prompt, 2200)
    generated_context = "" if user_request == prompt.strip() else sanitize_ai_text(prompt, 1800)
    return "\n".join(
        [
            "USER ICON REQUEST - HIGHEST PRIORITY:",
            user_request,
            "",
            "Follow the user request above as the source of truth for motif, composition, style, color, material, and mood.",
            "Do not replace the user's requested image with a generic workflow metaphor.",
            "Use app context only as a secondary guardrail so the icon still belongs to this app.",
            "",
            "STYLE SOURCE:",
            custom or "No separate style preset is selected. Derive the style from the user request.",
            "",
            "Generated concept JSON - optional support only, never an override:",
            json.dumps(concept_data, ensure_ascii=False),
            "",
            "English rendering guidance: Create a distinctive 1024x1024 PNG app icon for a desktop launcher.",
            "Style preset:",
            f"- preset: {preset}",
            f"- visual material: {style_settings.get('material', '')}",
            f"- color behavior: {style_settings.get('color', '')}",
            f"- line/edge treatment: {style_settings.get('edge', '')}",
            f"- lighting: {style_settings.get('lighting', '')}",
            f"- style-specific forbidden elements: {style_settings.get('forbidden', '')}",
            f"- custom style override: {custom}" if custom else "- custom style override: none",
            "Do not introduce a style preset that conflicts with the user's prompt.",
            "Use generous safe margins and a strong app-specific silhouette.",
            "If the user specified a central object, keep it central. If the user specified transformation, motion, material, or style, make that visibly dominant.",
            f"Primary action: {brief.primary_action if brief else 'unknown'}",
            f"Input objects: {', '.join(brief.input_objects) if brief else 'unknown'}",
            f"Output objects: {', '.join(brief.output_objects) if brief else 'unknown'}",
            f"App composition hint: {brief.composition_template if brief else 'use only if it supports the user request'}",
            f"Candidate direction: {concept.direction if concept else 'app-specific'}",
            concept.composition if concept else "Make this candidate visually distinct while following the user request.",
            f"Do not repeat the same composition as previous candidates: {prior or 'none yet'}.",
            "Use a small number of readable visual elements. Prioritize the user's requested subject over generated metadata.",
            "Forbidden unless explicitly requested by the user: generic abstract shapes only, tiny unreadable text, full-photo scenes, screenshots, crowded UI panels, gear-only icons, check-only icons, nodes-only icons, or initial-letter-only icons.",
            "Readable at 32px, attractive at 256px and above, no watermark, no mockup frame, transparent or clean icon background acceptable.",
            "",
            "Generated prompt context for audit - lower priority than USER ICON REQUEST:",
            generated_context or "none",
        ]
    )


def image_candidate_from_result(image_result, candidate_number: int = 1) -> tuple[bytes | None, str, str]:
    if image_result is None or not image_result.ok or not image_result.content:
        reason = image_result.fallback_reason if image_result else "AI image generation was skipped."
        return None, "", f"No API image candidate was saved for icon_candidate_{candidate_number}. reason={reason or 'none'}"
    content = image_result.content.strip()
    if content.startswith("http://") or content.startswith("https://"):
        return None, content, f"API returned an image URL. It will be saved as icon_candidate_{candidate_number}.url.txt."
    try:
        return decode_base64_image(content), "", f"API returned b64 image data. It will be saved as icon_candidate_{candidate_number}.png."
    except Exception:
        return None, "", f"API image data could not be decoded for icon_candidate_{candidate_number}; ToolHub default icon remains available."


def skipped_image_report(reason: str, error_category: str = "") -> str:
    failure_class = normalize_failure_class(error_category or reason)
    guidance = failure_guidance(failure_class, reason)
    return "\n".join(
        [
            "api: images.generate",
            "status: skipped",
            f"model: {image_model()}",
            f"ai_enabled: {str(ai_enabled()).lower()}",
            f"api_key_present: {str(has_api_key()).lower()}",
            "used_api: false",
            "content_type: none",
            "output_format: png",
            "quality: medium",
            f"resolution: {API_ICON_RESOLUTION}",
            f"error_category: {failure_class or 'none'}",
            f"failure_class: {failure_class or 'none'}",
            f"failure_message: {guidance.message_ja if failure_class else 'none'}",
            f"admin_next_action: {guidance.next_action_ja if failure_class else 'none'}",
            f"fallback_reason: {reason or 'AI use was not allowed.'}",
        ]
    )


def saved_candidate_name(png_bytes: bytes | None, image_url: str) -> str:
    if png_bytes:
        return "icon_candidate_1.png"
    if image_url:
        return "icon_candidate_1.url.txt"
    return "none"


def is_api_candidate(candidate: IconCandidateAsset) -> bool:
    return not candidate.is_fallback and candidate.source.startswith("api")


def last_image_api_failure(candidates: list[IconCandidateAsset]) -> str:
    for candidate in reversed(candidates):
        if candidate.fallback_reason:
            return candidate.fallback_reason
    return ""


def last_failure_class(candidates: list[IconCandidateAsset]) -> str:
    for candidate in reversed(candidates):
        value = normalize_failure_class(candidate.failure_class or candidate.error_category or candidate.fallback_reason)
        if value:
            return value
    return ""


def payload_secret_scan_status(candidates: list[IconCandidateAsset]) -> str:
    statuses = {candidate.ai_payload_secret_scan_status for candidate in candidates if candidate.ai_payload_secret_scan_status}
    if "blocked" in statuses:
        return "blocked"
    if "warning" in statuses:
        return "warning"
    if "passed" in statuses:
        return "passed"
    return "not_run"


def image_failure_diagnostics_from_reports(reports: list[str]) -> dict[str, Any]:
    diagnostics: dict[str, Any] = {}
    for report in reports:
        status = report_value(report, "status")
        if status == "success":
            continue
        reason = (
            report_value(report, "fallback_reason")
            or report_value(report, "error")
            or report_value(report, "message")
        )
        error_category = report_value(report, "error_category")
        failure_class = report_value(report, "failure_class") or normalize_failure_class(error_category or reason)
        if not reason and not failure_class:
            continue
        guidance = failure_guidance(failure_class, reason) if failure_class else None
        diagnostics.update(
            {
                "latest_image_api_failure": reason,
                "failure_class": failure_class,
                "failure_message": report_value(report, "failure_message") or (guidance.message_ja if guidance else ""),
                "admin_next_action": report_value(report, "admin_next_action") or (guidance.next_action_ja if guidance else ""),
                "ai_payload_secret_scan_status": "blocked" if failure_class == "secret_scan_blocked" else "",
                "ai_submission_blocked": failure_class == "secret_scan_blocked",
                "ai_submission_block_reason": reason if failure_class == "secret_scan_blocked" else "",
            }
        )
    return diagnostics


def report_value(report: str, key: str) -> str:
    prefix = f"{key}:"
    for line in report.splitlines():
        stripped = line.strip()
        if stripped.startswith(prefix):
            return stripped[len(prefix):].strip()
    return ""


def image_api_summary(
    candidates: list[IconCandidateAsset],
    style_settings: dict[str, str] | None = None,
    diagnostics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    api_candidates = [candidate for candidate in candidates if is_api_candidate(candidate)]
    model = next((candidate.model for candidate in candidates if candidate.model and not is_internal_placeholder_model(candidate.model)), image_model())
    diagnostics = diagnostics or {}
    latest_failure = last_image_api_failure(candidates)
    if not api_candidates:
        latest_failure = str(diagnostics.get("latest_image_api_failure") or latest_failure)
    failure_class = "" if api_candidates else str(diagnostics.get("failure_class") or last_failure_class(candidates))
    guidance = failure_guidance(failure_class, latest_failure) if failure_class else None
    payload_status = str(diagnostics.get("ai_payload_secret_scan_status") or payload_secret_scan_status(candidates))
    ai_blocked = (
        any(candidate.ai_submission_blocked for candidate in candidates)
        or bool(diagnostics.get("ai_submission_blocked") or False)
        or failure_class == "secret_scan_blocked"
    )
    ai_block_reason = next((candidate.ai_submission_block_reason for candidate in candidates if candidate.ai_submission_block_reason), "")
    ai_block_reason = str(diagnostics.get("ai_submission_block_reason") or ai_block_reason)
    package_status = str(diagnostics.get("package_secret_scan_status") or "not_recorded")
    statuses = {candidate.image_evaluation_status for candidate in candidates if candidate.image_evaluation_status}
    if "deterministic_png_check" in statuses:
        image_evaluation_status = "deterministic_png_check"
    elif "fallback_rule_based" in statuses:
        # Legacy manifests used this name for deterministic PNG checks.
        image_evaluation_status = "deterministic_png_check"
    elif statuses:
        image_evaluation_status = sorted(statuses)[0]
    else:
        image_evaluation_status = "not_run"
    return {
        "api_candidate_count": len(api_candidates),
        "image_api_success": bool(api_candidates),
        "image_generation_status": "success" if api_candidates else "failed",
        "latest_image_api_failure": latest_failure,
        "failure_class": failure_class,
        "failure_message": str(diagnostics.get("failure_message") or (guidance.message_ja if guidance else "")),
        "admin_next_action": str(diagnostics.get("admin_next_action") or (guidance.next_action_ja if guidance else "")),
        "selected_icon_source": str(diagnostics.get("selected_icon_source") or DEFAULT_ICON_SOURCE),
        "default_icon_used": bool(diagnostics.get("default_icon_used", not api_candidates)),
        "default_icon_reason": str(diagnostics.get("default_icon_reason") or DEFAULT_ICON_REASON),
        "icon_status": str(diagnostics.get("icon_status") or ("default_icon" if not api_candidates else "ai_candidates_available")),
        "package_secret_scan_status": package_status,
        "package_secret_scan_findings": int(diagnostics.get("package_secret_scan_findings") or 0),
        "package_ai_submission_blocked": bool(diagnostics.get("package_ai_submission_blocked") or False),
        "package_ai_submission_block_reason": str(diagnostics.get("package_ai_submission_block_reason") or ""),
        "ai_payload_secret_scan_status": payload_status,
        "ai_submission_blocked": bool(ai_blocked),
        "ai_submission_block_reason": ai_block_reason,
        "model": model,
        "style_preset": (style_settings or {}).get("preset", ""),
        "image_evaluation_status": image_evaluation_status,
        "image_evaluation_note": "Vision evaluation is not run in this MVP; candidates use deterministic prompt/concept checks and PNG small-size checks when pixels are available.",
    }
