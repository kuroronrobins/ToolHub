from __future__ import annotations

import hashlib
import html
import json
import os
from pathlib import Path
import struct
from typing import Any
import zlib

from .ai_metadata_suggester import build_icon_design_brief, sanitize_ai_text, suggest_icon_prompt
from .models import DependencyReport, IconCandidateAsset, IconConcept, IconDesignBrief, StudioContext
from .openai_client import complete_json, decode_base64_image, edit_image, generate_image, image_model, text_model


LOCAL_ICON_SIZE = 512
API_ICON_RESOLUTION = "1024x1024"
DEFAULT_ICON_CANDIDATE_COUNT = 3
MAX_ICON_CANDIDATE_COUNT = 6

ICON_STYLE_PRESETS: dict[str, dict[str, str]] = {
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

PALETTE = [
    ("#2F6F73", "#E8F3F1", "#74C9C3"),
    ("#4E5D8A", "#EEF1FA", "#A9B7F4"),
    ("#3F6C45", "#EFF6EF", "#9FD6A4"),
    ("#7A5C3E", "#F6F1EA", "#E4B06B"),
    ("#0F766E", "#ECFDF5", "#38BDF8"),
    ("#4F46E5", "#EEF2FF", "#F59E0B"),
]

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

ICON_VARIANTS = [
    {
        "id": "intuitive",
        "label": "用途が直感的に分かる案",
        "guidance": "Make the app's concrete workflow immediately recognizable through the primary motif and one supporting motif.",
    },
    {
        "id": "abstract",
        "label": "モダンで抽象的な案",
        "guidance": "Use a more abstract geometric silhouette while preserving the app-specific input/output metaphor.",
    },
    {
        "id": "distinctive",
        "label": "個性的で印象に残る案",
        "guidance": "Create a memorable silhouette with a distinctive accent shape, without adding text or visual clutter.",
    },
]

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
    svg = generate_local_svg(context, prompt_for_asset, style_reference)
    fallback_png = generate_local_png(context, prompt_for_asset, style_reference, size=LOCAL_ICON_SIZE)
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
    legacy_candidate = candidates[0] if candidates else None
    legacy_png = legacy_candidate.png if legacy_candidate else None
    legacy_url = legacy_candidate.url if legacy_candidate else ""
    saved_candidates = ", ".join(candidate.file_name or candidate.url_file_name or candidate.candidate_id for candidate in candidates) or "none"
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
            "## Image API Summary",
            "",
            json.dumps(image_api_summary(candidates, style_settings), ensure_ascii=False, indent=2),
            f"candidate_count: {len(candidates)}",
            f"api_candidate_count: {sum(1 for candidate in candidates if is_api_candidate(candidate))}",
            f"fallback_candidate_count: {sum(1 for candidate in candidates if candidate.is_fallback)}",
            f"last_image_api_failure: {last_image_api_failure(candidates) or 'none'}",
            f"saved_candidate: {saved_candidate_name(legacy_png, legacy_url)}",
            f"saved_candidates: {saved_candidates}",
            "",
            "PNG is the standard ToolHub App Studio icon output. API PNG candidates require human adoption before final icon.png is replaced.",
            "Fallback PNGs are placeholders for AI-disabled or API-failed runs and must not be treated as successful AI-generated candidates.",
            "candidate_manifest.json records each candidate source, model, prompt, status, resolution, failure reason, style preset, and fallback/API classification.",
            "Rule-based candidate scores are prompt/concept only; they do not inspect the generated image pixels.",
        ]
    )
    return initial_prompt, revision, svg, fallback_png, style_reference, report, legacy_png, legacy_url, candidates


def icon_candidate_count() -> int:
    raw = os.environ.get("TOOLHUB_APP_STUDIO_ICON_CANDIDATE_COUNT", "").strip()
    if not raw:
        return DEFAULT_ICON_CANDIDATE_COUNT
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_ICON_CANDIDATE_COUNT
    return max(1, min(MAX_ICON_CANDIDATE_COUNT, value))


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
) -> tuple[list[IconCandidateAsset], list[str]]:
    candidates: list[IconCandidateAsset] = []
    style_settings = style_settings or icon_style_settings(None, None, prompt)
    concept_list, reports = generate_icon_concepts(context, brief, prompt, allow_ai, count)
    image_skip_report_added = False
    use_edit_api = bool(revision_image_path and Path(revision_image_path).is_file())
    for index, concept in enumerate(concept_list[:count], start=1):
        variant_prompt = image_api_prompt(
            prompt,
            brief=brief,
            concept=concept,
            prior_candidate_ids=[candidate.candidate_id for candidate in candidates],
            style_settings=style_settings,
        )
        if allow_ai and use_edit_api:
            image_result = edit_image(variant_prompt, str(revision_image_path), size=API_ICON_RESOLUTION)
        elif allow_ai:
            image_result = generate_image(variant_prompt, size=API_ICON_RESOLUTION)
        else:
            image_result = None
        png_bytes, image_url, image_note = image_candidate_from_result(image_result, index)
        if image_result:
            reports.append(image_result.report)
        elif not image_skip_report_added:
            reports.append(skipped_image_report(ai_skip_reason))
            image_skip_report_added = True

        if png_bytes or image_url:
            candidates.append(
                IconCandidateAsset(
                    candidate_id=f"icon_candidate_{index}",
                    number=index,
                    source="api_edit" if image_result and image_result.api == "images.edit" else "api_generate",
                    prompt=variant_prompt,
                    model=image_result.model if image_result else "",
                    status=image_result.status if image_result else "success",
                    resolution=getattr(image_result, "resolution", API_ICON_RESOLUTION) or API_ICON_RESOLUTION,
                    is_fallback=False,
                    png=png_bytes,
                    url=image_url,
                    file_name=f"icon_candidate_{index}.png" if png_bytes else "",
                    url_file_name=f"icon_candidate_{index}.url.txt" if image_url else "",
                    notes=f"{concept.direction}: {image_note}",
                    api=image_result.api if image_result else "",
                    content_type=image_result.content_type if image_result else "",
                    fallback_reason="",
                    error_category=image_result.error_category if image_result else "",
                    concept_id=concept.concept_id,
                    concept=concept.to_dict(),
                    scores=score_icon_candidate(brief, concept, candidates),
                    score_total=0.0,
                )
            )
            candidates[-1].score_total = sum(candidates[-1].scores.values())
            continue

        fallback_prompt = image_api_prompt(
            prompt,
            brief=brief,
            concept=concept,
            prior_candidate_ids=[candidate.candidate_id for candidate in candidates],
            style_settings=style_settings,
        )
        scores = score_icon_candidate(brief, concept, candidates)
        fallback_reason = ""
        error_category = ""
        api_name = "images.edit" if use_edit_api else "images.generate"
        if image_result:
            fallback_reason = image_result.fallback_reason or image_result.error or image_note
            error_category = image_result.error_category
            api_name = image_result.api or api_name
        elif ai_skip_reason:
            fallback_reason = ai_skip_reason
        candidates.append(
            IconCandidateAsset(
                candidate_id=f"icon_candidate_{index}",
                number=index,
                source="fallback" if not allow_ai else "fallback_after_api_failure",
                prompt=fallback_prompt,
                model="local-deterministic-fallback",
                status="skipped" if not allow_ai else "fallback",
                resolution=f"{LOCAL_ICON_SIZE}x{LOCAL_ICON_SIZE}",
                is_fallback=True,
                png=generate_local_png(context, fallback_prompt, style_reference, size=LOCAL_ICON_SIZE),
                file_name=f"icon_candidate_{index}.png",
                notes=f"{concept.direction}: placeholder fallback. {image_note or ai_skip_reason or 'local fallback'}",
                api=api_name,
                content_type=getattr(image_result, "content_type", "none") if image_result else "none",
                fallback_reason=fallback_reason or "AI image generation did not produce a usable PNG or URL.",
                error_category=error_category,
                concept_id=concept.concept_id,
                concept=concept.to_dict(),
                scores=scores,
                score_total=sum(scores.values()),
            )
        )
    return candidates, reports


def generate_icon_concepts(
    context: StudioContext,
    brief: IconDesignBrief,
    prompt: str,
    allow_ai: bool,
    count: int,
) -> tuple[list[IconConcept], list[str]]:
    fallback = fallback_icon_concepts(brief, count)
    if not allow_ai:
        return fallback, [skipped_concept_report("AI use was not allowed.")]

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
        return fallback, [result.report]
    concepts = parse_icon_concepts(result.content, brief, count)
    if len(concepts) < count:
        existing = {concept.concept_id for concept in concepts}
        concepts.extend([concept for concept in fallback if concept.concept_id not in existing])
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


def fallback_icon_concepts(brief: IconDesignBrief, count: int) -> list[IconConcept]:
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
            f"fallback_reason: {reason or 'AI use was not allowed.'}",
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
    settings = dict(ICON_STYLE_PRESETS.get(selected, ICON_STYLE_PRESETS["modern"]))
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
    inferred = infer_icon_style_preset(prompt)
    return inferred or "modern"


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
    preset = style_settings.get("preset", "modern")
    custom = style_settings.get("custom", "")
    return "\n".join(
        [
            prompt.strip(),
            "",
            "Icon concept JSON:",
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
            "Do not override the selected style preset with a generic polished/glass/3D look.",
            "Use generous safe margins and a strong app-specific silhouette.",
            "At a glance, the viewer must understand what the app does. Show the action relationship, not just the object type.",
            f"Primary action: {brief.primary_action if brief else 'unknown'}",
            f"Input objects: {', '.join(brief.input_objects) if brief else 'unknown'}",
            f"Output objects: {', '.join(brief.output_objects) if brief else 'unknown'}",
            f"Preferred composition template: {brief.composition_template if brief else '2 to 4 meaningful objects connected by one action path'}",
            f"Candidate direction: {concept.direction if concept else 'app-specific'}",
            concept.composition if concept else "Make this candidate visually distinct from generic business icons.",
            f"Do not repeat the same composition as previous candidates: {prior or 'none yet'}.",
            "Use 2 to 4 meaningful objects maximum. Prioritize silhouette and relationship over detail density.",
            "Forbidden: generic abstract shapes only, tiny text, readable or unreadable logo-like letters, unrequested full-photo scenes, screenshots, crowded UI panels, document-only icons, gear-only icons, check-only icons, nodes-only icons, or initial-letter-only icons.",
            "Readable at 32px, attractive at 256px and above, no watermark, no mockup frame, transparent or clean icon background acceptable.",
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
        return None, "", f"API image data could not be decoded for icon_candidate_{candidate_number}; fallback PNG remains available."


def skipped_image_report(reason: str) -> str:
    return "\n".join(
        [
            "api: images.generate",
            "status: skipped",
            "model: not_configured",
            "ai_enabled: false",
            "api_key_present: false",
            "used_api: false",
            "content_type: none",
            "output_format: png",
            "quality: medium",
            f"resolution: {API_ICON_RESOLUTION}",
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


def image_api_summary(candidates: list[IconCandidateAsset], style_settings: dict[str, str] | None = None) -> dict[str, Any]:
    api_candidates = [candidate for candidate in candidates if is_api_candidate(candidate)]
    fallback_candidates = [candidate for candidate in candidates if candidate.is_fallback]
    model = next((candidate.model for candidate in candidates if candidate.model and candidate.model != "local-deterministic-fallback"), image_model())
    return {
        "api_candidate_count": len(api_candidates),
        "fallback_candidate_count": len(fallback_candidates),
        "image_api_success": bool(api_candidates),
        "latest_image_api_failure": last_image_api_failure(candidates),
        "model": model,
        "style_preset": (style_settings or {}).get("preset", ""),
        "score_basis": "prompt_concept_only",
        "image_evaluation_status": "not_run",
        "image_evaluation_note": "Generated image pixels are not inspected by the rule-based score.",
    }


def generate_local_svg(context: StudioContext, prompt: str, style_reference: str) -> str:
    digest = hashlib.sha256((context.app_id + prompt + style_reference).encode("utf-8")).digest()
    stroke_hex, fill_hex, accent_hex = PALETTE[digest[0] % len(PALETTE)]
    motif = infer_local_motif(context, prompt, digest)
    motif_svg = svg_motif(motif, stroke_hex, accent_hex)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" role="img" aria-label="{html.escape(context.name)} icon">
  <rect x="6" y="6" width="52" height="52" rx="13" fill="{fill_hex}" stroke="{stroke_hex}" stroke-width="3"/>
  <circle cx="48" cy="16" r="7" fill="{accent_hex}" opacity="0.85"/>
  {motif_svg}
</svg>
"""


def svg_motif(motif: str, stroke: str, accent: str) -> str:
    if motif == "pdf_merge":
        return f"""<rect x="12" y="20" width="14" height="18" rx="3" fill="#ffffff" stroke="{stroke}" stroke-width="2"/>
  <rect x="21" y="14" width="14" height="18" rx="3" fill="#ffffff" stroke="{stroke}" stroke-width="2"/>
  <rect x="30" y="20" width="14" height="18" rx="3" fill="#ffffff" stroke="{stroke}" stroke-width="2"/>
  <path d="M18 41c9 7 19 7 28 0" fill="none" stroke="{accent}" stroke-width="4" stroke-linecap="round"/>
  <rect x="38" y="29" width="15" height="21" rx="4" fill="{accent}" stroke="{stroke}" stroke-width="2"/>"""
    if motif == "pdf_split":
        return f"""<rect x="22" y="14" width="20" height="27" rx="4" fill="#ffffff" stroke="{stroke}" stroke-width="3"/>
  <path d="M32 42v7M32 49l-9-5M32 49l9-5" stroke="{accent}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>
  <rect x="10" y="38" width="14" height="14" rx="3" fill="#ffffff" stroke="{stroke}" stroke-width="2"/>
  <rect x="40" y="38" width="14" height="14" rx="3" fill="#ffffff" stroke="{stroke}" stroke-width="2"/>"""
    if motif == "upload_flow":
        return f"""<rect x="12" y="34" width="18" height="14" rx="3" fill="#ffffff" stroke="{stroke}" stroke-width="2"/>
  <path d="M31 39c5-12 12-16 22-16" fill="none" stroke="{accent}" stroke-width="4" stroke-linecap="round"/>
  <path d="M48 16l6 7-9 2" fill="none" stroke="{accent}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>
  <path d="M41 30h12a6 6 0 0 0-2-11 9 9 0 0 0-17 3" fill="#ffffff" stroke="{stroke}" stroke-width="2"/>"""
    if motif == "transcribe_flow":
        return f"""<path d="M18 34c4-13 8-13 12 0s8 13 12 0" fill="none" stroke="{accent}" stroke-width="4" stroke-linecap="round"/>
  <rect x="14" y="17" width="14" height="22" rx="7" fill="#ffffff" stroke="{stroke}" stroke-width="3"/>
  <path d="M40 20h12M40 29h10M40 38h13" stroke="{stroke}" stroke-width="4" stroke-linecap="round"/>"""
    if motif == "compare_diff":
        return f"""<rect x="12" y="18" width="18" height="28" rx="4" fill="#ffffff" stroke="{stroke}" stroke-width="3"/>
  <rect x="34" y="18" width="18" height="28" rx="4" fill="#ffffff" stroke="{stroke}" stroke-width="3"/>
  <path d="M31 24h2M31 32h2M31 40h2" stroke="{accent}" stroke-width="4" stroke-linecap="round"/>
  <path d="M17 28h8M39 28h8M39 36h6" stroke="{accent}" stroke-width="3" stroke-linecap="round"/>"""
    if motif == "data_grid":
        return f"""<rect x="17" y="19" width="30" height="24" rx="4" fill="#ffffff" stroke="{stroke}" stroke-width="3"/>
  <path d="M27 19v24M37 19v24M17 31h30" stroke="{stroke}" stroke-width="2" opacity="0.75"/>
  <path d="M21 39l7-7 6 4 9-11" fill="none" stroke="{accent}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>"""
    if motif == "automation_flow":
        return f"""<path d="M17 38c8-18 22-18 30 0" fill="none" stroke="{stroke}" stroke-width="4" stroke-linecap="round"/>
  <circle cx="18" cy="39" r="6" fill="#ffffff" stroke="{stroke}" stroke-width="3"/>
  <circle cx="32" cy="22" r="6" fill="{accent}" stroke="{stroke}" stroke-width="3"/>
  <circle cx="46" cy="39" r="6" fill="#ffffff" stroke="{stroke}" stroke-width="3"/>"""
    if motif == "report_chart":
        return f"""<rect x="18" y="15" width="28" height="34" rx="5" fill="#ffffff" stroke="{stroke}" stroke-width="3"/>
  <path d="M25 39v-8M32 39V25M39 39V30" stroke="{accent}" stroke-width="5" stroke-linecap="round"/>
  <path d="M24 22h16" stroke="{stroke}" stroke-width="3" stroke-linecap="round"/>"""
    if motif == "image_frame":
        return f"""<rect x="15" y="18" width="34" height="28" rx="5" fill="#ffffff" stroke="{stroke}" stroke-width="3"/>
  <path d="M20 40l9-10 6 6 5-7 7 11" fill="{accent}" opacity="0.9"/>
  <circle cx="40" cy="25" r="4" fill="{stroke}"/>"""
    if motif == "search_lens":
        return f"""<circle cx="29" cy="29" r="12" fill="#ffffff" stroke="{stroke}" stroke-width="4"/>
  <path d="M38 38l10 10" stroke="{stroke}" stroke-width="5" stroke-linecap="round"/>
  <rect x="18" y="24" width="10" height="5" rx="2" fill="{accent}"/>
  <rect x="31" y="31" width="8" height="5" rx="2" fill="{accent}"/>"""
    if motif == "calendar_flow":
        return f"""<rect x="16" y="17" width="32" height="30" rx="5" fill="#ffffff" stroke="{stroke}" stroke-width="3"/>
  <path d="M16 26h32" stroke="{stroke}" stroke-width="3"/>
  <path d="M23 39l6-6 5 4 8-9" fill="none" stroke="{accent}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>"""
    return f"""<circle cx="32" cy="32" r="8" fill="{accent}" stroke="{stroke}" stroke-width="3"/>
  <path d="M20 41l12-9 12 9M20 23l12 9 12-9" fill="none" stroke="{stroke}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>"""


def generate_local_png(context: StudioContext, prompt: str, style_reference: str, size: int = LOCAL_ICON_SIZE) -> bytes:
    digest = hashlib.sha256((context.app_id + prompt + style_reference).encode("utf-8")).digest()
    stroke_hex, fill_hex, accent_hex = PALETTE[digest[0] % len(PALETTE)]
    stroke = (*hex_to_rgb(stroke_hex), 255)
    fill = (*hex_to_rgb(fill_hex), 255)
    accent = (*hex_to_rgb(accent_hex), 255)
    white = (255, 255, 255, 255)
    shadow = (15, 23, 42, 32)
    transparent = (0, 0, 0, 0)
    pixels = [[transparent for _ in range(size)] for _ in range(size)]
    scale = size / 512

    def px(value: float) -> int:
        return int(round(value * scale))

    fill_rounded_rect(pixels, px(50), px(58), px(462), px(470), px(92), shadow)
    fill_rounded_rect(pixels, px(42), px(42), px(470), px(470), px(96), fill)
    stroke_rounded_rect(pixels, px(42), px(42), px(470), px(470), px(96), px(10), stroke)
    fill_circle(pixels, px(378), px(126), px(56), (*hex_to_rgb(accent_hex), 210))
    fill_circle(pixels, px(150), px(395), px(34), (255, 255, 255, 165))
    draw_local_motif(pixels, infer_local_motif(context, prompt, digest), px, stroke, accent, white)
    return encode_png_rgba(pixels)


def infer_local_motif(context: StudioContext, prompt: str, digest: bytes) -> str:
    text = f"{context.app_id} {context.name} {context.entry.name} {prompt}".lower()
    if "pdf" in text and "merge" in text:
        return "pdf_merge"
    if "pdf" in text and "split" in text:
        return "pdf_split"
    if "transcribe" in text or "speech-to-text" in text or "waveform" in text:
        return "transcribe_flow"
    if "compare" in text or "diff" in text:
        return "compare_diff"
    if "upload" in text or "sync" in text:
        return "upload_flow"
    rules = [
        (("csv", "excel", "spreadsheet", "table", "dataframe", "pandas", "集計", "データ"), "data_grid"),
        (("upload", "download", "sync", "browser", "playwright", "flow", "web", "selenium", "自動", "連携"), "automation_flow"),
        (("report", "pdf", "invoice", "帳票", "請求", "レポート", "検収"), "report_chart"),
        (("image", "photo", "vision", "screenshot", "画像", "写真"), "image_frame"),
        (("search", "find", "index", "scan", "検索", "探索", "診断"), "search_lens"),
        (("calendar", "schedule", "agenda", "date", "予定", "日程"), "calendar_flow"),
    ]
    for keywords, motif in rules:
        if any(keyword in text for keyword in keywords):
            return motif
    return ["data_grid", "automation_flow", "report_chart", "search_lens", "network"][digest[1] % 5]


def draw_local_motif(pixels, motif: str, px, stroke, accent, white) -> None:
    if motif == "pdf_merge":
        for x, y in [(112, 190), (190, 138), (268, 190)]:
            fill_rounded_rect(pixels, px(x), px(y), px(x + 92), px(y + 118), px(18), white)
            stroke_rounded_rect(pixels, px(x), px(y), px(x + 92), px(y + 118), px(18), px(6), stroke)
            draw_line(pixels, px(x + 22), px(y + 36), px(x + 70), px(y + 36), px(5), (*stroke[:3], 150))
        draw_line(pixels, px(176), px(330), px(256), px(372), px(13), accent)
        draw_line(pixels, px(336), px(330), px(256), px(372), px(13), accent)
        fill_rounded_rect(pixels, px(292), px(278), px(404), px(420), px(22), accent)
        stroke_rounded_rect(pixels, px(292), px(278), px(404), px(420), px(22), px(7), stroke)
        draw_line(pixels, px(318), px(326), px(378), px(326), px(7), white)
        draw_line(pixels, px(318), px(358), px(364), px(358), px(7), white)
        return
    if motif == "pdf_split":
        fill_rounded_rect(pixels, px(196), px(102), px(316), px(258), px(24), white)
        stroke_rounded_rect(pixels, px(196), px(102), px(316), px(258), px(24), px(8), stroke)
        draw_line(pixels, px(256), px(270), px(256), px(334), px(13), accent)
        draw_line(pixels, px(256), px(334), px(164), px(392), px(13), accent)
        draw_line(pixels, px(256), px(334), px(348), px(392), px(13), accent)
        for x in [94, 306]:
            fill_rounded_rect(pixels, px(x), px(344), px(x + 112), px(426), px(20), white)
            stroke_rounded_rect(pixels, px(x), px(344), px(x + 112), px(426), px(20), px(7), stroke)
        return
    if motif == "upload_flow":
        fill_rounded_rect(pixels, px(108), px(310), px(246), px(396), px(22), white)
        stroke_rounded_rect(pixels, px(108), px(310), px(246), px(396), px(22), px(7), stroke)
        draw_line(pixels, px(236), px(320), px(368), px(190), px(15), accent)
        fill_polygon(pixels, [(360, 154), (410, 190), (354, 210)], px, accent)
        fill_rounded_rect(pixels, px(296), px(176), px(426), px(258), px(32), white)
        stroke_rounded_rect(pixels, px(296), px(176), px(426), px(258), px(32), px(7), stroke)
        fill_circle(pixels, px(330), px(176), px(34), white)
        fill_circle(pixels, px(382), px(174), px(42), white)
        return
    if motif == "transcribe_flow":
        fill_rounded_rect(pixels, px(132), px(148), px(218), px(302), px(43), white)
        stroke_rounded_rect(pixels, px(132), px(148), px(218), px(302), px(43), px(8), stroke)
        for offset in [0, 48, 96]:
            draw_line(pixels, px(190 + offset), px(340), px(210 + offset), px(288), px(10), accent)
            draw_line(pixels, px(210 + offset), px(288), px(230 + offset), px(340), px(10), accent)
        for y, width in [(178, 102), (226, 88), (274, 114)]:
            fill_rounded_rect(pixels, px(304), px(y), px(304 + width), px(y + 24), px(12), white)
            stroke_rounded_rect(pixels, px(304), px(y), px(304 + width), px(y + 24), px(12), px(4), stroke)
        return
    if motif == "compare_diff":
        fill_rounded_rect(pixels, px(112), px(146), px(234), px(372), px(24), white)
        stroke_rounded_rect(pixels, px(112), px(146), px(234), px(372), px(24), px(8), stroke)
        fill_rounded_rect(pixels, px(278), px(146), px(400), px(372), px(24), white)
        stroke_rounded_rect(pixels, px(278), px(146), px(400), px(372), px(24), px(8), stroke)
        fill_rounded_rect(pixels, px(242), px(184), px(270), px(334), px(14), accent)
        for y in [204, 260, 316]:
            draw_line(pixels, px(138), px(y), px(206), px(y), px(8), (*stroke[:3], 155))
            draw_line(pixels, px(304), px(y), px(374 if y != 260 else 350), px(y), px(8), accent if y == 260 else (*stroke[:3], 155))
        return
    if motif == "data_grid":
        fill_rounded_rect(pixels, px(142), px(164), px(370), px(348), px(28), white)
        stroke_rounded_rect(pixels, px(142), px(164), px(370), px(348), px(28), px(8), stroke)
        for x in [218, 294]:
            draw_line(pixels, px(x), px(172), px(x), px(340), px(5), (*stroke[:3], 160))
        for y in [226, 286]:
            draw_line(pixels, px(150), px(y), px(362), px(y), px(5), (*stroke[:3], 160))
        points = [(170, 316), (220, 265), (270, 294), (328, 220), (356, 238)]
        draw_polyline(pixels, points, px, px(11), accent)
        for x, y in points:
            fill_circle(pixels, px(x), px(y), px(12), accent)
        return
    if motif == "automation_flow":
        draw_line(pixels, px(158), px(334), px(256), px(178), px(12), stroke)
        draw_line(pixels, px(256), px(178), px(358), px(334), px(12), stroke)
        for x, y, r, color in [(158, 334, 42, white), (256, 178, 46, accent), (358, 334, 42, white)]:
            fill_circle(pixels, px(x), px(y), px(r), color)
            draw_circle(pixels, px(x), px(y), px(r), px(8), stroke)
        fill_polygon(pixels, [(328, 228), (386, 266), (350, 278), (366, 324), (342, 332), (326, 287), (292, 312)], px, white)
        draw_polyline(pixels, [(328, 228), (386, 266), (350, 278), (366, 324), (342, 332), (326, 287), (292, 312), (328, 228)], px, px(6), stroke)
        return
    if motif == "report_chart":
        fill_rounded_rect(pixels, px(154), px(118), px(360), px(398), px(30), white)
        stroke_rounded_rect(pixels, px(154), px(118), px(360), px(398), px(30), px(8), stroke)
        draw_line(pixels, px(196), px(184), px(318), px(184), px(10), stroke)
        for x, top in [(204, 304), (256, 236), (308, 270)]:
            fill_rounded_rect(pixels, px(x - 18), px(top), px(x + 18), px(344), px(10), accent)
        fill_circle(pixels, px(350), px(154), px(38), accent)
        draw_line(pixels, px(334), px(154), px(346), px(168), px(9), white)
        draw_line(pixels, px(346), px(168), px(370), px(138), px(9), white)
        return
    if motif == "image_frame":
        fill_rounded_rect(pixels, px(130), px(154), px(382), px(358), px(34), white)
        stroke_rounded_rect(pixels, px(130), px(154), px(382), px(358), px(34), px(8), stroke)
        fill_polygon(pixels, [(154, 324), (224, 246), (272, 298), (310, 246), (360, 324)], px, accent)
        fill_circle(pixels, px(322), px(204), px(26), stroke)
        draw_line(pixels, px(192), px(206), px(222), px(206), px(8), accent)
        draw_line(pixels, px(207), px(190), px(207), px(222), px(8), accent)
        return
    if motif == "search_lens":
        fill_circle(pixels, px(238), px(238), px(92), white)
        draw_circle(pixels, px(238), px(238), px(92), px(14), stroke)
        draw_line(pixels, px(304), px(304), px(380), px(380), px(24), stroke)
        fill_rounded_rect(pixels, px(184), px(214), px(234), px(246), px(12), accent)
        fill_rounded_rect(pixels, px(250), px(258), px(316), px(292), px(12), accent)
        return
    if motif == "calendar_flow":
        fill_rounded_rect(pixels, px(142), px(140), px(370), px(366), px(32), white)
        stroke_rounded_rect(pixels, px(142), px(140), px(370), px(366), px(32), px(8), stroke)
        fill_rounded_rect(pixels, px(142), px(140), px(370), px(204), px(32), accent)
        draw_line(pixels, px(184), px(272), px(234), px(312), px(12), stroke)
        draw_line(pixels, px(234), px(312), px(314), px(238), px(12), stroke)
        for x in [188, 256, 324]:
            fill_circle(pixels, px(x), px(228), px(12), (*stroke[:3], 190))
        return
    fill_circle(pixels, px(256), px(256), px(58), accent)
    draw_circle(pixels, px(256), px(256), px(58), px(10), stroke)
    for x, y in [(164, 178), (348, 178), (164, 338), (348, 338)]:
        draw_line(pixels, px(256), px(256), px(x), px(y), px(10), stroke)
        fill_circle(pixels, px(x), px(y), px(34), white)
        draw_circle(pixels, px(x), px(y), px(34), px(7), stroke)


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    stripped = value.lstrip("#")
    return int(stripped[0:2], 16), int(stripped[2:4], 16), int(stripped[4:6], 16)


def blend_pixel(pixels, x: int, y: int, color) -> None:
    if y < 0 or y >= len(pixels) or x < 0 or x >= len(pixels[y]):
        return
    alpha = color[3] / 255
    if alpha >= 1:
        pixels[y][x] = color
        return
    current = pixels[y][x]
    inverse = 1 - alpha
    pixels[y][x] = (
        int(color[0] * alpha + current[0] * inverse),
        int(color[1] * alpha + current[1] * inverse),
        int(color[2] * alpha + current[2] * inverse),
        min(255, int(color[3] + current[3] * inverse)),
    )


def fill_rounded_rect(pixels, x0: int, y0: int, x1: int, y1: int, radius: int, color) -> None:
    radius = max(0, radius)
    for y in range(max(0, y0), min(len(pixels), y1 + 1)):
        for x in range(max(0, x0), min(len(pixels[y]), x1 + 1)):
            cx = min(max(x, x0 + radius), x1 - radius)
            cy = min(max(y, y0 + radius), y1 - radius)
            if (x - cx) * (x - cx) + (y - cy) * (y - cy) <= radius * radius:
                blend_pixel(pixels, x, y, color)


def stroke_rounded_rect(pixels, x0: int, y0: int, x1: int, y1: int, radius: int, width: int, color) -> None:
    radius = max(0, radius)
    inner_radius = max(0, radius - width)
    for y in range(max(0, y0), min(len(pixels), y1 + 1)):
        for x in range(max(0, x0), min(len(pixels[y]), x1 + 1)):
            outer_cx = min(max(x, x0 + radius), x1 - radius)
            outer_cy = min(max(y, y0 + radius), y1 - radius)
            in_outer = (x - outer_cx) * (x - outer_cx) + (y - outer_cy) * (y - outer_cy) <= radius * radius
            if not in_outer:
                continue
            ix0, iy0, ix1, iy1 = x0 + width, y0 + width, x1 - width, y1 - width
            inner_cx = min(max(x, ix0 + inner_radius), ix1 - inner_radius)
            inner_cy = min(max(y, iy0 + inner_radius), iy1 - inner_radius)
            in_inner = ix0 <= x <= ix1 and iy0 <= y <= iy1 and (x - inner_cx) * (x - inner_cx) + (y - inner_cy) * (y - inner_cy) <= inner_radius * inner_radius
            if not in_inner:
                blend_pixel(pixels, x, y, color)


def fill_circle(pixels, cx: int, cy: int, radius: int, color) -> None:
    r2 = radius * radius
    for y in range(max(0, cy - radius), min(len(pixels), cy + radius + 1)):
        for x in range(max(0, cx - radius), min(len(pixels[y]), cx + radius + 1)):
            if (x - cx) * (x - cx) + (y - cy) * (y - cy) <= r2:
                blend_pixel(pixels, x, y, color)


def draw_circle(pixels, cx: int, cy: int, radius: int, width: int, color) -> None:
    outer = radius * radius
    inner = max(0, radius - width) * max(0, radius - width)
    for y in range(max(0, cy - radius), min(len(pixels), cy + radius + 1)):
        for x in range(max(0, cx - radius), min(len(pixels[y]), cx + radius + 1)):
            dist = (x - cx) * (x - cx) + (y - cy) * (y - cy)
            if inner <= dist <= outer:
                blend_pixel(pixels, x, y, color)


def draw_line(pixels, x0: int, y0: int, x1: int, y1: int, width: int, color) -> None:
    min_x = max(0, min(x0, x1) - width)
    max_x = min(len(pixels[0]) - 1, max(x0, x1) + width)
    min_y = max(0, min(y0, y1) - width)
    max_y = min(len(pixels) - 1, max(y0, y1) + width)
    dx = x1 - x0
    dy = y1 - y0
    length2 = dx * dx + dy * dy or 1
    radius2 = (width / 2) * (width / 2)
    for y in range(min_y, max_y + 1):
        for x in range(min_x, max_x + 1):
            t = max(0, min(1, ((x - x0) * dx + (y - y0) * dy) / length2))
            px = x0 + t * dx
            py = y0 + t * dy
            if (x - px) * (x - px) + (y - py) * (y - py) <= radius2:
                blend_pixel(pixels, x, y, color)


def draw_polyline(pixels, points: list[tuple[int, int]], px, width: int, color) -> None:
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        draw_line(pixels, px(x0), px(y0), px(x1), px(y1), width, color)


def fill_polygon(pixels, points: list[tuple[int, int]], px, color) -> None:
    scaled = [(px(x), px(y)) for x, y in points]
    min_x = max(0, min(x for x, _ in scaled))
    max_x = min(len(pixels[0]) - 1, max(x for x, _ in scaled))
    min_y = max(0, min(y for _, y in scaled))
    max_y = min(len(pixels) - 1, max(y for _, y in scaled))
    for y in range(min_y, max_y + 1):
        for x in range(min_x, max_x + 1):
            if point_in_polygon(x, y, scaled):
                blend_pixel(pixels, x, y, color)


def point_in_polygon(x: int, y: int, points: list[tuple[int, int]]) -> bool:
    inside = False
    j = len(points) - 1
    for i, point in enumerate(points):
        xi, yi = point
        xj, yj = points[j]
        intersects = ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / ((yj - yi) or 1) + xi)
        if intersects:
            inside = not inside
        j = i
    return inside


def encode_png_rgba(pixels: list[list[tuple[int, int, int, int]]]) -> bytes:
    height = len(pixels)
    width = len(pixels[0]) if height else 0
    raw = bytearray()
    for row in pixels:
        raw.append(0)
        for red, green, blue, alpha in row:
            raw.extend([red, green, blue, alpha])
    chunks = [
        png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)),
        png_chunk(b"IDAT", zlib.compress(bytes(raw))),
        png_chunk(b"IEND", b""),
    ]
    return PNG_SIGNATURE + b"".join(chunks)


def png_chunk(kind: bytes, data: bytes) -> bytes:
    checksum = zlib.crc32(kind + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", checksum)
