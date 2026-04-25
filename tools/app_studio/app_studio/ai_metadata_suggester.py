from __future__ import annotations

import os
from typing import Any

from .models import StudioContext


TEXT_MODEL = os.environ.get("TOOLHUB_APP_STUDIO_TEXT_MODEL", "local-deterministic-fallback")
IMAGE_MODEL = os.environ.get("TOOLHUB_APP_STUDIO_IMAGE_MODEL", "local-deterministic-fallback")


def suggest_metadata(context: StudioContext) -> dict[str, Any]:
    """Return app metadata.

    OpenAI integration can replace this function later. The MVP deliberately
    stays deterministic unless a future implementation opts into API calls.
    """
    _ = TEXT_MODEL
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


def suggest_icon_prompt(context: StudioContext, revision_prompt: str | None = None) -> str:
    _ = IMAGE_MODEL
    base = (
        f"{context.name} のToolHub用アイコン。64x64 viewBox、シンプルな業務アプリ向け線画、"
        "単色に近い落ち着いた配色、既存ToolHubアイコンと並べても違和感がないデザイン。"
    )
    if revision_prompt:
        return base + "\n\n修正指示:\n" + revision_prompt.strip()
    return base

