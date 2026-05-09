from __future__ import annotations

import json

from .ai_metadata_suggester import sanitize_ai_text
from .models import IconConcept, IconDesignBrief, StudioContext
from .openai_client import complete_json, text_model


ICON_REGENERATION_MODES = {"tweak", "refine", "redesign", "fresh"}

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

def normalize_icon_revision_mode(mode: str | None) -> str:
    selected = (mode or "refine").strip().lower()
    return selected if selected in ICON_REGENERATION_MODES else "refine"

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
