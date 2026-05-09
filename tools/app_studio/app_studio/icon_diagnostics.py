from __future__ import annotations

from typing import Any

from .default_icon import DEFAULT_ICON_REASON, DEFAULT_ICON_SOURCE
from .icon_candidates import is_api_candidate
from .icon_compat import normalize_image_evaluation_status
from .models import IconCandidateAsset
from .openai_client import ai_enabled, failure_guidance, has_api_key, image_model, is_internal_placeholder_model, normalize_failure_class
from .secret_scanner import secret_scan_status


API_ICON_RESOLUTION = "1024x1024"


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
    image_evaluation_status = normalize_image_evaluation_status(statuses)
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
