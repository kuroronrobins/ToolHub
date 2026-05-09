from __future__ import annotations

import re
from typing import Any
import zlib

from .ai_metadata_suggester import sanitize_ai_text
from .models import IconCandidateAsset, IconConcept, IconDesignBrief


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


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
