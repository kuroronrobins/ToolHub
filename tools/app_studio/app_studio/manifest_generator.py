from __future__ import annotations

from typing import Any

from .app_contract import infer_run_mode_from_source
from .models import BuildPlan, StudioContext
from .util import yaml_scalar


def generate_app_yaml(context: StudioContext, plan: BuildPlan, metadata: dict[str, Any]) -> str:
    categories = list_or_default(metadata.get("categories"), ["業務ツール"])
    use_cases = list_or_default(metadata.get("use_cases"), [f"{context.name} をToolHubから起動する"])
    inputs = list_or_default(metadata.get("inputs"), ["アプリ設定に依存"])
    outputs = list_or_default(metadata.get("outputs"), ["アプリ実行結果"])
    notes = list_or_default(metadata.get("notes"), ["正式登録前に実行確認と人間承認が必要です。"])
    keywords = list_or_default(metadata.get("keywords"), [context.name, context.app_id])
    examples = list_or_default(metadata.get("examples"), [f"{context.name} を起動したい"])
    short_description = str(metadata.get("short_description") or f"{context.name} をToolHubから起動するアプリです。")
    description = str(metadata.get("description") or short_description)
    release_notes = list_or_empty(metadata.get("release_notes"))
    change_summary = str(metadata.get("change_summary") or "").strip()
    mode = infer_run_mode(context)
    required_runtime = plan.required_runtime
    distribution_mode = plan.mode.replace("-", "_")
    shared_env_id = plan.env_id if plan.mode == "shared-env" else ""
    if shared_env_id:
        required_runtime = f"python-shared-env:{shared_env_id}"

    lines = [
        f"id: {yaml_scalar(context.app_id)}",
        f"name: {yaml_scalar(context.name)}",
        "",
        "display:",
        "  icon: icon.png",
        "  icon_fallback: icon.svg",
        f"  short_description: {yaml_scalar(short_description)}",
        "  categories:",
        *[f"    - {yaml_scalar(item)}" for item in categories],
        "",
        "detail:",
        "  description: >",
        *[f"    {line}" for line in wrap_block(description)],
        "  use_cases:",
        *[f"    - {yaml_scalar(item)}" for item in use_cases],
        "  inputs:",
        *[f"    - {yaml_scalar(item)}" for item in inputs],
        "  outputs:",
        *[f"    - {yaml_scalar(item)}" for item in outputs],
        "  notes:",
        *[f"    - {yaml_scalar(item)}" for item in notes],
        "",
        "search:",
        "  keywords:",
        *[f"    - {yaml_scalar(item)}" for item in keywords],
        "  examples:",
        *[f"    - {yaml_scalar(item)}" for item in examples],
        "",
        "run:",
        f"  runner: {plan.runner}",
        f"  entry: {plan.entry}",
        f"  mode: {mode}",
        *([f"  env_id: {yaml_scalar(shared_env_id)}"] if shared_env_id else []),
        "",
        "admin:",
        f"  version: {context.version}",
        "  owner: admin",
        "  requirements: requirements.txt",
        "  log_dir: logs",
        "",
        "runtime:",
        f"  distribution_mode: {distribution_mode}",
        f"  app_env: {yaml_scalar(context.app_id if plan.mode == 'app-env' else None)}",
        f"  required_runtime: {yaml_scalar(required_runtime)}",
        "  requirements_lock: requirements.lock",
        *(
            [
                "  shared_env:",
                f"    env_id: {yaml_scalar(shared_env_id)}",
                "    scope: versioned",
            ]
            if shared_env_id
            else []
        ),
        "",
        "build:",
        "  managed_by: toolhub_app_studio",
        f"  build_mode: {plan.mode}",
        f"  source_entry: {context.entry}",
        f"  output_mirror: {context.output_dir}",
        "",
        "quality:",
        "  approval_required: true",
        "  execution_test_required: true",
    ]
    if change_summary or release_notes:
        lines.extend(["", "release:"])
        if change_summary:
            lines.extend(["  change_summary: >", *[f"    {line}" for line in wrap_block(change_summary)]])
        if release_notes:
            lines.extend(["  release_notes:", *[f"    - {yaml_scalar(item)}" for item in release_notes]])
    return "\n".join(lines).rstrip() + "\n"


def list_or_default(value: Any, default: list[str]) -> list[str]:
    if isinstance(value, list) and value:
        return [str(item) for item in value if str(item).strip()] or default
    return default


def list_or_empty(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    return []


def wrap_block(text: str) -> list[str]:
    stripped = text.strip()
    return stripped.splitlines() or [""]


def infer_run_mode(context: StudioContext) -> str:
    return infer_run_mode_from_source(context)
