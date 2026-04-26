from __future__ import annotations

import hashlib
import html
from pathlib import Path
import struct
import zlib

from .ai_metadata_suggester import suggest_icon_prompt
from .models import StudioContext
from .openai_client import decode_base64_image, generate_image


PALETTE = [
    ("#2F6F73", "#E8F3F1"),
    ("#5A5F7A", "#EEF0F6"),
    ("#3F6C45", "#EFF6EF"),
    ("#7A5C3E", "#F6F1EA"),
]


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


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
    initial_prompt, revision, svg, _, style_reference, report, _, _ = generate_icon_assets_with_candidates(context, revision_prompt, allow_ai)
    return initial_prompt, revision, svg, style_reference, report


def generate_icon_assets_with_candidates(
    context: StudioContext,
    revision_prompt: str | None = None,
    allow_ai: bool = True,
    ai_skip_reason: str = "",
) -> tuple[str, str, str, bytes, str, str, bytes | None, str]:
    style_reference = collect_icon_style_reference(context.repo_root)
    initial_prompt, initial_report = suggest_icon_prompt(context, allow_ai=allow_ai)
    if revision_prompt:
        revision, revision_report = suggest_icon_prompt(context, revision_prompt, allow_ai=allow_ai)
    else:
        revision = "No revision prompt was provided."
        revision_report = "No revision prompt was provided."
    prompt_for_svg = revision if revision_prompt else initial_prompt
    image_result = generate_image(image_api_prompt(prompt_for_svg)) if allow_ai else None
    png_bytes, image_url, image_note = image_candidate_from_result(image_result)
    image_report = image_result.report if image_result else skipped_image_report(ai_skip_reason)
    svg = generate_local_svg(context, prompt_for_svg, style_reference)
    fallback_png = generate_local_png(context, prompt_for_svg, style_reference)
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
            image_report,
            f"saved_candidate: {saved_candidate_name(png_bytes, image_url)}",
            image_note,
            "",
            "PNG is the standard ToolHub App Studio icon output. API PNG candidates require human adoption before final icon.png is replaced.",
            "A deterministic local PNG and SVG fallback remain available when AI is disabled, missing, or blocked.",
        ]
    )
    return initial_prompt, revision, svg, fallback_png, style_reference, report, png_bytes, image_url


def image_api_prompt(prompt: str) -> str:
    return "\n".join(
        [
            prompt.strip(),
            "",
            "English rendering guidance: Create a clean 1024x1024 PNG app icon for a desktop launcher.",
            "Use a simple centered symbol, calm professional colors, no tiny text, no watermark, no mockup frame.",
        ]
    )


def image_candidate_from_result(image_result) -> tuple[bytes | None, str, str]:
    if image_result is None or not image_result.ok or not image_result.content:
        reason = image_result.fallback_reason if image_result else "AI image generation was skipped."
        return None, "", f"No API image candidate was saved. reason={reason or 'none'}"
    content = image_result.content.strip()
    if content.startswith("http://") or content.startswith("https://"):
        return None, content, "API returned an image URL. It will be saved as icon_candidate_1.url.txt."
    try:
        return decode_base64_image(content), "", "API returned b64 image data. It will be saved as icon_candidate_1.png."
    except Exception:
        return None, "", "API image data could not be decoded; fallback SVG remains available."


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
    stroke, fill = PALETTE[digest[0] % len(PALETTE)]
    letter = html.escape((context.name.strip() or context.app_id)[0].upper())
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" role="img" aria-label="{html.escape(context.name)} icon">
  <rect x="10" y="8" width="44" height="48" rx="8" fill="{fill}" stroke="{stroke}" stroke-width="3"/>
  <path d="M22 22h20M22 32h20M22 42h12" fill="none" stroke="{stroke}" stroke-width="3" stroke-linecap="round"/>
  <circle cx="46" cy="46" r="8" fill="#ffffff" stroke="{stroke}" stroke-width="3"/>
  <text x="46" y="50" text-anchor="middle" font-family="Arial, sans-serif" font-size="10" font-weight="700" fill="{stroke}">{letter}</text>
</svg>
"""


def generate_local_png(context: StudioContext, prompt: str, style_reference: str, size: int = 64) -> bytes:
    digest = hashlib.sha256((context.app_id + prompt + style_reference).encode("utf-8")).digest()
    stroke_hex, fill_hex = PALETTE[digest[0] % len(PALETTE)]
    stroke = hex_to_rgb(stroke_hex)
    fill = hex_to_rgb(fill_hex)
    white = (255, 255, 255)
    transparent = (0, 0, 0, 0)
    pixels: list[list[tuple[int, int, int, int]]] = []
    for y in range(size):
        row: list[tuple[int, int, int, int]] = []
        for x in range(size):
            color = transparent
            if 10 <= x <= 54 and 8 <= y <= 56:
                color = (*fill, 255)
            if border_pixel(x, y):
                color = (*stroke, 255)
            if (22 <= x <= 42 and y in {22, 23, 32, 33}) or (22 <= x <= 34 and y in {42, 43}):
                color = (*stroke, 255)
            if (x - 46) * (x - 46) + (y - 46) * (y - 46) <= 64:
                color = (*white, 255)
            if 49 <= (x - 46) * (x - 46) + (y - 46) * (y - 46) <= 81:
                color = (*stroke, 255)
            if letter_mark_pixel(x, y, digest):
                color = (*stroke, 255)
            row.append(color)
        pixels.append(row)
    return encode_png_rgba(pixels)


def border_pixel(x: int, y: int) -> bool:
    on_outer = 10 <= x <= 54 and 8 <= y <= 56 and (x in {10, 11, 53, 54} or y in {8, 9, 55, 56})
    corner_cut = (x < 14 and y < 12) or (x > 50 and y < 12) or (x < 14 and y > 52) or (x > 50 and y > 52)
    return on_outer and not corner_cut


def letter_mark_pixel(x: int, y: int, digest: bytes) -> bool:
    pattern = digest[1] % 3
    if pattern == 0:
        return (43 <= x <= 49 and y in {43, 44}) or (43 <= x <= 49 and y in {48, 49}) or (43 <= y <= 49 and x in {43, 44})
    if pattern == 1:
        return (43 <= y <= 49 and x in {43, 44, 48, 49}) or (43 <= x <= 49 and y in {43, 44})
    return (43 <= x <= 49 and y in {43, 44, 48, 49}) or (43 <= y <= 49 and x in {43, 44, 48, 49})


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    stripped = value.lstrip("#")
    return int(stripped[0:2], 16), int(stripped[2:4], 16), int(stripped[4:6], 16)


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
