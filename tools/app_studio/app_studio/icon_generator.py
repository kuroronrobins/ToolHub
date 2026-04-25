from __future__ import annotations

import hashlib
import html
from pathlib import Path

from .ai_metadata_suggester import suggest_icon_prompt
from .models import StudioContext
from .openai_client import decode_base64_image, generate_image


PALETTE = [
    ("#2F6F73", "#E8F3F1"),
    ("#5A5F7A", "#EEF0F6"),
    ("#3F6C45", "#EFF6EF"),
    ("#7A5C3E", "#F6F1EA"),
]


def collect_icon_style_reference(repo_root: Path) -> str:
    app_dirs = sorted((repo_root / "apps").glob("*"))
    names = []
    for app_dir in app_dirs:
        if (app_dir / "app.yaml").is_file() and (app_dir / "icon.svg").is_file():
            names.append(app_dir.name)
    if not names:
        return "No existing app icons were found."
    return "Existing ToolHub icon references: " + ", ".join(names)


def generate_icon_assets(context: StudioContext, revision_prompt: str | None = None, allow_ai: bool = True) -> tuple[str, str, str, str, str]:
    initial_prompt, revision, svg, style_reference, report, _, _ = generate_icon_assets_with_candidates(context, revision_prompt, allow_ai)
    return initial_prompt, revision, svg, style_reference, report


def generate_icon_assets_with_candidates(context: StudioContext, revision_prompt: str | None = None, allow_ai: bool = True) -> tuple[str, str, str, str, str, bytes | None, str]:
    style_reference = collect_icon_style_reference(context.repo_root)
    initial_prompt, initial_report = suggest_icon_prompt(context, allow_ai=allow_ai)
    if revision_prompt:
        revision, revision_report = suggest_icon_prompt(context, revision_prompt, allow_ai=allow_ai)
    else:
        revision = "No revision prompt was provided."
        revision_report = "No revision prompt was provided."
    prompt_for_svg = revision if revision_prompt else initial_prompt
    image_result = generate_image(prompt_for_svg) if allow_ai else None
    png_bytes, image_url, image_note = image_candidate_from_result(image_result)
    svg = generate_local_svg(context, prompt_for_svg, style_reference)
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
            image_result.report if image_result else "OpenAI image generation skipped because AI use was not allowed.",
            image_note,
            "",
            "The final icon.svg is always a local deterministic SVG fallback so the launcher can render it safely.",
        ]
    )
    return initial_prompt, revision, svg, style_reference, report, png_bytes, image_url


def image_candidate_from_result(image_result) -> tuple[bytes | None, str, str]:
    if image_result is None or not image_result.ok or not image_result.content:
        return None, "", "No API image candidate was saved."
    content = image_result.content.strip()
    if content.startswith("http://") or content.startswith("https://"):
        return None, content, "API returned an image URL. It will be saved as icon_candidate_1.url.txt."
    try:
        return decode_base64_image(content), "", "API returned b64 image data. It will be saved as icon_candidate_1.png."
    except Exception:
        return None, "", "API image data could not be decoded; fallback SVG remains available."


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
