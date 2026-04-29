from __future__ import annotations

import hashlib
import html
import os
from pathlib import Path
import struct
import zlib

from .ai_metadata_suggester import suggest_icon_prompt
from .models import DependencyReport, IconCandidateAsset, StudioContext
from .openai_client import decode_base64_image, generate_image


LOCAL_ICON_SIZE = 512
API_ICON_RESOLUTION = "1024x1024"
DEFAULT_ICON_CANDIDATE_COUNT = 3
MAX_ICON_CANDIDATE_COUNT = 6

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
) -> tuple[str, str, str, bytes, str, str, bytes | None, str, list[IconCandidateAsset]]:
    style_reference = collect_icon_style_reference(context.repo_root)
    initial_prompt, initial_report = suggest_icon_prompt(
        context,
        allow_ai=allow_ai,
        metadata=metadata,
        dependency_report=dependency_report,
        style_reference=style_reference,
    )
    if revision_prompt:
        revision, revision_report = suggest_icon_prompt(
            context,
            revision_prompt,
            allow_ai=allow_ai,
            metadata=metadata,
            dependency_report=dependency_report,
            style_reference=style_reference,
        )
    else:
        revision = "No revision prompt was provided."
        revision_report = "No revision prompt was provided."
    prompt_for_asset = revision if revision_prompt else initial_prompt
    svg = generate_local_svg(context, prompt_for_asset, style_reference)
    fallback_png = generate_local_png(context, prompt_for_asset, style_reference, size=LOCAL_ICON_SIZE)
    candidates, image_reports = generate_icon_candidates(
        context,
        prompt_for_asset,
        style_reference,
        allow_ai=allow_ai,
        ai_skip_reason=ai_skip_reason,
        count=icon_candidate_count(),
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
            "## Image Generation",
            "",
            "\n\n".join(image_reports) if image_reports else skipped_image_report(ai_skip_reason),
            f"candidate_count: {len(candidates)}",
            f"saved_candidate: {saved_candidate_name(legacy_png, legacy_url)}",
            f"saved_candidates: {saved_candidates}",
            "",
            "PNG is the standard ToolHub App Studio icon output. API PNG candidates require human adoption before final icon.png is replaced.",
            "A deterministic local PNG and SVG fallback remain available when AI is disabled, missing, blocked, or an API candidate fails.",
            "candidate_manifest.json records each candidate source, model, prompt, status, resolution, and fallback/API classification.",
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
    prompt: str,
    style_reference: str,
    allow_ai: bool,
    ai_skip_reason: str,
    count: int,
) -> tuple[list[IconCandidateAsset], list[str]]:
    candidates: list[IconCandidateAsset] = []
    reports: list[str] = []
    for index in range(1, count + 1):
        variant = ICON_VARIANTS[(index - 1) % len(ICON_VARIANTS)]
        variant_prompt = image_api_prompt(
            prompt,
            variant_label=variant["label"],
            variant_guidance=variant["guidance"],
            prior_candidate_ids=[candidate.candidate_id for candidate in candidates],
        )
        image_result = generate_image(variant_prompt, size=API_ICON_RESOLUTION) if allow_ai else None
        png_bytes, image_url, image_note = image_candidate_from_result(image_result, index)
        if image_result:
            reports.append(image_result.report)
        elif not reports:
            reports.append(skipped_image_report(ai_skip_reason))

        if png_bytes or image_url:
            candidates.append(
                IconCandidateAsset(
                    candidate_id=f"icon_candidate_{index}",
                    number=index,
                    source="api",
                    prompt=variant_prompt,
                    model=image_result.model if image_result else "",
                    status=image_result.status if image_result else "success",
                    resolution=getattr(image_result, "resolution", API_ICON_RESOLUTION) or API_ICON_RESOLUTION,
                    is_fallback=False,
                    png=png_bytes,
                    url=image_url,
                    file_name=f"icon_candidate_{index}.png" if png_bytes else "",
                    url_file_name=f"icon_candidate_{index}.url.txt" if image_url else "",
                    notes=f"{variant['label']}: {image_note}",
                )
            )
            continue

        fallback_prompt = "\n".join([prompt, f"Local fallback variation: {variant['label']}", variant["guidance"]])
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
                notes=f"{variant['label']}: {image_note or ai_skip_reason or 'local fallback'}",
            )
        )
    return candidates, reports


def image_api_prompt(
    prompt: str,
    variant_label: str = "",
    variant_guidance: str = "",
    prior_candidate_ids: list[str] | None = None,
) -> str:
    prior = ", ".join(prior_candidate_ids or [])
    return "\n".join(
        [
            prompt.strip(),
            "",
            "English rendering guidance: Create a modern, distinctive 1024x1024 PNG app icon for a desktop launcher.",
            "Use generous safe margins, a strong app-specific silhouette, polished high-DPI edges, and a refined material texture.",
            "The icon must communicate the actual app purpose, input/output flow, or target business task; do not rely on a generic office-app look.",
            f"Candidate direction: {variant_label or 'app-specific'}",
            variant_guidance or "Make this candidate visually distinct from generic business icons.",
            f"Do not repeat the same composition as previous candidates: {prior or 'none yet'}.",
            "Forbidden: tiny text, unreadable logo-like letters, photorealistic imagery, screenshots, crowded UI panels, document-only icons, gear-only icons, check-only icons, or initial-letter-only icons.",
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
