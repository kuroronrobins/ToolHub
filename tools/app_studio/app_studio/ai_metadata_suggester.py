from __future__ import annotations

import json
from typing import Any

from .models import SecretScanReport, StudioContext
from .openai_client import complete_json, ai_enabled, has_api_key, text_model


def suggest_metadata(context: StudioContext, secret_report: SecretScanReport | None = None) -> dict[str, Any]:
    if secret_report and secret_report.has_high:
        metadata = fallback_metadata(context)
        metadata["_ai_generation_report"] = "\n".join(
            [
                "api: responses.create",
                "status: skipped",
                f"model: {text_model()}",
                f"ai_enabled: {str(ai_enabled()).lower()}",
                f"api_key_present: {str(has_api_key()).lower()}",
                "parse_status: not_attempted",
                "fallback_reason: high severity secret detected, AI skipped",
            ]
        )
        return metadata

    result = complete_json(
        "Return concise ToolHub app metadata as strict JSON. Do not include secrets or local absolute paths.",
        metadata_prompt(context),
    )
    if result.ok:
        parsed = parse_metadata_json(result.content)
        if parsed:
            parsed["_ai_generation_report"] = append_parse_status(result.report, "success", "")
            return parsed

    metadata = fallback_metadata(context)
    metadata["_ai_generation_report"] = append_parse_status(
        result.report,
        "failed" if result.ok else "not_attempted",
        "metadata JSON parse failed" if result.ok else "",
    )
    return metadata


def suggest_icon_prompt(context: StudioContext, revision_prompt: str | None = None, allow_ai: bool = True) -> tuple[str, str]:
    base = (
        f"ToolHub icon for {context.name}. 64x64 viewBox, simple business app line art, "
        "calm colors, readable at small sizes, consistent with existing ToolHub icons."
    )
    if revision_prompt:
        base = base + "\nRevision request:\n" + revision_prompt.strip()
    if not allow_ai:
        return base, "OpenAI icon prompt generation skipped because AI use was not allowed."

    result = complete_json(
        "Return JSON with one string field named icon_prompt. Do not include secrets.",
        json.dumps({"app_id": context.app_id, "name": context.name, "base_prompt": base}, ensure_ascii=False),
    )
    if result.ok:
        try:
            data = json.loads(result.content)
            prompt = str(data.get("icon_prompt") or "").strip()
            if prompt:
                return prompt, append_parse_status(result.report, "success", "")
        except json.JSONDecodeError:
            pass
    return base, append_parse_status(result.report, "failed" if result.ok else "not_attempted", "icon prompt JSON parse failed" if result.ok else "")


def fallback_metadata(context: StudioContext) -> dict[str, Any]:
    return {
        "short_description": f"{context.name} をToolHubから起動するアプリです。",
        "description": f"{context.name} は、指定されたメインファイルをもとにToolHubへ取り込むためのアプリ定義です。",
        "categories": ["業務ツール"],
        "use_cases": [f"{context.name} をToolHubからすばやく起動する"],
        "inputs": ["アプリ設定に依存"],
        "outputs": ["アプリ実行結果"],
        "notes": ["正式登録前に実行確認と人間承認が必要です。"],
        "keywords": [context.name, context.app_id, "ToolHub"],
        "examples": [f"{context.name} を起動したい"],
    }


def metadata_prompt(context: StudioContext) -> str:
    app_names = []
    for app_dir in sorted((context.repo_root / "apps").glob("*")):
        app_yaml = app_dir / "app.yaml"
        if app_yaml.is_file():
            app_names.append(app_dir.name)
    readme = context.source_root / "README.md"
    readme_excerpt = readme.read_text(encoding="utf-8", errors="replace")[:1200] if readme.is_file() else ""
    return json.dumps(
        {
            "app_id": context.app_id,
            "name": context.name,
            "entry_name": context.entry.name,
            "source_files": [path.name for path in sorted(context.source_root.glob("*.py"))[:20]],
            "readme_excerpt": readme_excerpt,
            "existing_app_ids": app_names[:20],
            "required_schema": {
                "short_description": "string",
                "description": "string",
                "categories": ["string"],
                "use_cases": ["string"],
                "inputs": ["string"],
                "outputs": ["string"],
                "notes": ["string"],
                "keywords": ["string"],
                "examples": ["string"],
            },
        },
        ensure_ascii=False,
    )


def parse_metadata_json(content: str) -> dict[str, Any] | None:
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return None
    required_strings = ["short_description", "description"]
    required_lists = ["categories", "use_cases", "inputs", "outputs", "notes", "keywords", "examples"]
    if not all(isinstance(data.get(key), str) and data[key].strip() for key in required_strings):
        return None
    if not all(isinstance(data.get(key), list) and data[key] for key in required_lists):
        return None
    return data


def append_parse_status(report: str, status: str, reason: str) -> str:
    lines = [report, f"parse_status: {status}"]
    if reason:
        lines.append(f"parse_fallback_reason: {reason}")
    return "\n".join(lines)
