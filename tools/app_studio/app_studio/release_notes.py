from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .ai_metadata_suggester import append_parse_status, sanitize_ai_text
from .openai_client import ai_enabled, complete_json, has_api_key, text_model
from .secret_scanner import ai_submission_block_reason, scan_ai_payload_text, secret_scan_status


def build_release_notes_draft(context: dict[str, Any]) -> dict[str, Any]:
    prompt_payload = release_notes_prompt_payload(context)
    repo_root = Path(str(context.get("repo_root") or ".")).resolve()
    payload_text = json.dumps(prompt_payload, ensure_ascii=False, indent=2)
    payload_report = scan_ai_payload_text(payload_text, repo_root, "release_notes_prompt")
    if payload_report.blocks_ai_submission:
        fallback = fallback_release_notes(context, "secret scan blocked release notes prompt, AI skipped")
        fallback["ai_report"] = "\n".join(
            [
                "api: responses.create",
                "status: skipped",
                f"model: {text_model()}",
                f"ai_enabled: {str(ai_enabled()).lower()}",
                f"api_key_present: {str(has_api_key()).lower()}",
                f"ai_payload_secret_scan_status: {secret_scan_status(payload_report)}",
                f"ai_submission_block_reason: {ai_submission_block_reason(payload_report)}",
                "parse_status: not_attempted",
                "fallback_reason: secret scan blocked release notes prompt, AI skipped",
            ]
        )
        return fallback

    result = complete_json(
        (
            "Return ToolHub release notes as strict JSON. "
            "The user section must be natural Japanese for non-technical end users. "
            "Avoid internal paths, GitHub details, commit IDs, sha256, PowerShell, Rust, Node, Tauri, runner, runtime, and manifest wording in the user section. "
            "The admin section may include concise technical changes and validation."
        ),
        payload_text,
    )
    if result.ok:
        parsed = parse_release_notes_json(result.content)
        if parsed:
            draft = normalize_release_notes(context, parsed, source="ai")
            draft["ai_report"] = append_parse_status(
                append_release_notes_secret_scan_status(result.report, payload_report),
                "success",
                "",
            )
            return draft

    fallback_reason = "release notes JSON parse failed" if result.ok else "AI release notes generation was not available"
    fallback = fallback_release_notes(context, fallback_reason)
    fallback["ai_report"] = append_parse_status(
        append_release_notes_secret_scan_status(result.report, payload_report),
        "failed" if result.ok else "not_attempted",
        fallback_reason if result.ok else "",
    )
    return fallback


def release_notes_prompt_payload(context: dict[str, Any]) -> dict[str, Any]:
    app_names = [app.get("name") or app.get("id") for app in context.get("apps", []) if app.get("enabled", True)]
    app_names = [sanitize_ai_text(str(name), 80) for name in app_names if str(name).strip()][:12]
    return {
        "task": "Create release notes for a ToolHub desktop app update.",
        "version": sanitize_ai_text(str(context.get("version") or ""), 40),
        "tag": sanitize_ai_text(str(context.get("tag") or ""), 60),
        "app_names": app_names,
        "installer_file": sanitize_ai_text(str(context.get("installer_file") or ""), 120),
        "dirty_source_files": safe_file_list(context.get("dirty_source_files")),
        "dirty_release_files": safe_file_list(context.get("dirty_release_files")),
        "checks": [
            {
                "id": sanitize_ai_text(str(check.get("id") or ""), 60),
                "status": sanitize_ai_text(str(check.get("status") or ""), 20),
                "message": sanitize_ai_text(str(check.get("message") or ""), 180),
            }
            for check in context.get("checks", [])[:12]
            if isinstance(check, dict)
        ],
        "required_output": {
            "user": {
                "title": "short Japanese title",
                "summary": "one short, benefit-focused Japanese sentence",
                "highlights": ["3 to 5 short Japanese bullets"],
                "added_apps": ["new or notable app names only"],
                "recommended": True,
            },
            "admin": {
                "summary": "concise admin summary",
                "changes": ["technical changes are allowed here"],
                "validation": ["validation performed or recommended"],
            },
            "github_release_notes": "Japanese markdown release body for GitHub Release",
        },
    }


def parse_release_notes_json(content: str) -> dict[str, Any] | None:
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if "\n" in text:
            text = text.split("\n", 1)[1]
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    if not isinstance(data.get("user"), dict):
        return None
    return data


def normalize_release_notes(context: dict[str, Any], data: dict[str, Any], source: str) -> dict[str, Any]:
    user = data.get("user") if isinstance(data.get("user"), dict) else {}
    admin = data.get("admin") if isinstance(data.get("admin"), dict) else {}
    user_notes = {
        "title": clean_or_default(user.get("title"), "新しいバージョンがあります", 80),
        "summary": clean_or_default(user.get("summary"), "新しい業務アプリや改善を利用できるようになりました。", 180),
        "highlights": clean_list(user.get("highlights"), 5, 120) or default_highlights(context),
        "added_apps": clean_list(user.get("added_apps") or user.get("addedApps"), 8, 80),
        "recommended": bool(user.get("recommended", True)),
    }
    admin_notes = {
        "summary": clean_or_default(admin.get("summary"), admin_summary(context), 240),
        "changes": clean_list(admin.get("changes"), 8, 180) or default_admin_changes(context),
        "validation": clean_list(admin.get("validation"), 8, 180) or default_validation(context),
    }
    manifest_notes = {
        "schema_version": 1,
        "generated_by": source,
        "edited_by_admin": False,
        "user": user_notes,
        "admin": admin_notes,
    }
    github_notes = clean_or_default(
        data.get("github_release_notes"),
        github_release_notes_from_manifest(context, manifest_notes),
        4000,
    )
    return {
        "ok": True,
        "source": source,
        "message": "AI release notes draft was generated." if source == "ai" else "Fallback release notes draft was generated.",
        "github_release_notes": github_notes,
        "manifest_release_notes": manifest_notes,
    }


def fallback_release_notes(context: dict[str, Any], reason: str) -> dict[str, Any]:
    notes = {
        "user": {
            "title": "新しいバージョンがあります",
            "summary": "新しい業務アプリや改善を利用できるようになりました。",
            "highlights": default_highlights(context),
            "added_apps": default_added_apps(context),
            "recommended": True,
        },
        "admin": {
            "summary": admin_summary(context),
            "changes": default_admin_changes(context),
            "validation": default_validation(context),
        },
    }
    draft = normalize_release_notes(context, notes, source="fallback")
    draft["ok"] = False
    draft["message"] = reason
    return draft


def default_highlights(context: dict[str, Any]) -> list[str]:
    apps = default_added_apps(context)
    highlights: list[str] = []
    if apps:
        highlights.append("利用できる業務アプリを更新しました")
    highlights.append("更新内容を確認してから進められるようにしました")
    highlights.append("日々の作業で使いやすい状態に整えました")
    return highlights[:5]


def default_added_apps(context: dict[str, Any]) -> list[str]:
    apps = context.get("apps", [])
    names: list[str] = []
    for app in apps:
        if not isinstance(app, dict) or app.get("enabled") is False:
            continue
        name = sanitize_ai_text(str(app.get("name") or app.get("id") or ""), 80)
        if name and name not in names:
            names.append(name)
    return names[:8]


def admin_summary(context: dict[str, Any]) -> str:
    version = sanitize_ai_text(str(context.get("version") or ""), 40)
    return f"ToolHub {version} release draft." if version else "ToolHub release draft."


def default_admin_changes(context: dict[str, Any]) -> list[str]:
    changes = safe_file_list(context.get("dirty_source_files"))[:5]
    if changes:
        return [f"Updated {item}" for item in changes]
    return ["Updated ToolHub release artifacts and app catalog."]


def default_validation(context: dict[str, Any]) -> list[str]:
    checks = context.get("checks", [])
    passed = [
        sanitize_ai_text(str(check.get("id") or ""), 80)
        for check in checks
        if isinstance(check, dict) and str(check.get("status") or "").lower() == "pass"
    ]
    return passed[:6] or ["Run launcher build and release verification before publishing."]


def github_release_notes_from_manifest(context: dict[str, Any], manifest_notes: dict[str, Any]) -> str:
    version = sanitize_ai_text(str(context.get("version") or ""), 40) or "next"
    user = manifest_notes["user"]
    admin = manifest_notes["admin"]
    lines = [
        f"# ToolHub {version}",
        "",
        str(user["summary"]),
        "",
        "## 利用者向け",
    ]
    lines.extend([f"- {item}" for item in user["highlights"]])
    if user["added_apps"]:
        lines.extend(["", "## 追加・更新されたアプリ"])
        lines.extend([f"- {item}" for item in user["added_apps"]])
    lines.extend(["", "## 管理者向け", str(admin["summary"])])
    lines.extend([f"- {item}" for item in admin["changes"]])
    if admin["validation"]:
        lines.extend(["", "## Validation"])
        lines.extend([f"- {item}" for item in admin["validation"]])
    return "\n".join(lines).strip()


def append_release_notes_secret_scan_status(report: str, payload_report: Any) -> str:
    return (
        (report or "").rstrip()
        + "\n"
        + "\n".join(
            [
                f"ai_payload_secret_scan_status: {secret_scan_status(payload_report)}",
                f"ai_submission_block_reason: {ai_submission_block_reason(payload_report)}",
            ]
        )
    )


def clean_or_default(value: Any, fallback: str, limit: int) -> str:
    text = sanitize_ai_text(str(value or ""), limit).strip()
    return text or fallback


def clean_list(value: Any, limit: int, item_limit: int) -> list[str]:
    if not isinstance(value, list):
        return []
    output: list[str] = []
    for item in value:
        text = sanitize_ai_text(str(item or ""), item_limit).strip()
        if text and text not in output:
            output.append(text)
        if len(output) >= limit:
            break
    return output


def safe_file_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    output: list[str] = []
    for item in value:
        text = sanitize_ai_text(str(item or ""), 160).strip()
        if text and text not in output:
            output.append(text)
        if len(output) >= 20:
            break
    return output
