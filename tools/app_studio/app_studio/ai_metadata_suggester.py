from __future__ import annotations

import json
import re
from typing import Any

from .models import DependencyReport, IconDesignBrief, SecretScanReport, StudioContext
from .openai_client import complete_json, ai_enabled, has_api_key, text_model


def suggest_metadata(context: StudioContext, secret_report: SecretScanReport | None = None) -> dict[str, Any]:
    if secret_report and secret_report.blocks_ai_submission:
        metadata = fallback_metadata(context)
        metadata["_ai_generation_report"] = "\n".join(
            [
                "api: responses.create",
                "status: skipped",
                f"model: {text_model()}",
                f"ai_enabled: {str(ai_enabled()).lower()}",
                f"api_key_present: {str(has_api_key()).lower()}",
                "parse_status: not_attempted",
                "fallback_reason: secret scan blocked AI submission, AI skipped",
            ]
        )
        return metadata

    result = complete_json(
        (
            "Return concise ToolHub app metadata as strict JSON. "
            "All human-facing values must be natural Japanese. "
            "Do not include secrets, credentials, or local absolute paths."
        ),
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


def _legacy_suggest_icon_prompt_removed(context: StudioContext, revision_prompt: str | None = None, allow_ai: bool = True) -> tuple[str, str]:
    base = (
        f"ToolHub用アイコン。{context.name} の用途が伝わる、64x64でも見やすいシンプルな業務アプリ風アイコン。"
        "落ち着いた配色、余白のある構図、既存ToolHubアイコンと並べても違和感のない見た目。"
    )
    if revision_prompt:
        base = base + "\n修正指示:\n" + revision_prompt.strip()
    if not allow_ai:
        return base, "OpenAI icon prompt generation skipped because AI use was not allowed."

    result = complete_json(
        "Return JSON with one string field named icon_prompt. The icon_prompt must be Japanese. Do not include secrets.",
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


def suggest_icon_prompt(
    context: StudioContext,
    revision_prompt: str | None = None,
    allow_ai: bool = True,
    metadata: dict[str, Any] | None = None,
    dependency_report: DependencyReport | None = None,
    style_reference: str = "",
) -> tuple[str, str]:
    brief = build_icon_design_brief(context, metadata, dependency_report, style_reference)
    base = icon_prompt_from_brief(brief, revision_prompt)
    if not allow_ai:
        return base, "OpenAI icon prompt generation skipped because AI use was not allowed."

    result = complete_json(
        (
            "Return JSON with one string field named icon_prompt. "
            "The icon_prompt must be natural Japanese for an image generation model. "
            "Do not include secrets, credentials, local absolute paths, or unreadable logo text."
        ),
        json.dumps(
            {
                "icon_design_brief": brief.to_dict(),
                "base_prompt": base,
                "revision_context": sanitize_ai_text(revision_prompt or "", 1600),
                "required": [
                    "Reflect this app's concrete purpose, inputs, outputs, and business domain.",
                    "Use a distinctive primary motif plus a supporting app-specific motif.",
                    "Avoid generic document-only, gear-only, check-only, or initial-letter-only icons.",
                    "Keep the icon readable at 32px and polished at 256px or larger.",
                ],
            },
            ensure_ascii=False,
        ),
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


def build_icon_design_brief(
    context: StudioContext,
    metadata: dict[str, Any] | None = None,
    dependency_report: DependencyReport | None = None,
    style_reference: str = "",
) -> IconDesignBrief:
    metadata = metadata or {}
    source_files = safe_source_file_names(context)
    readme_excerpt = readme_excerpt_for_icon(context)
    dependency_signals = dependency_signal_list(dependency_report)
    categories = clean_metadata_list(metadata.get("categories"))
    keywords = clean_metadata_list(metadata.get("keywords"))
    use_cases = clean_metadata_list(metadata.get("use_cases"))
    inputs = clean_metadata_list(metadata.get("inputs"))
    outputs = clean_metadata_list(metadata.get("outputs"))
    short_description = sanitize_ai_text(str(metadata.get("short_description") or ""), 240)
    description = sanitize_ai_text(str(metadata.get("description") or ""), 700)
    purpose = first_non_empty(
        [
            short_description,
            description,
            readme_excerpt,
            f"{context.name} ({context.app_id})",
        ]
    )
    motif_source = " ".join(
        [
            context.app_id,
            context.name,
            context.entry.name,
            purpose,
            " ".join(categories),
            " ".join(keywords),
            " ".join(use_cases),
            " ".join(inputs),
            " ".join(outputs),
            " ".join(source_files),
            " ".join(dependency_signals),
        ]
    )
    primary_motif, secondary_motifs, palette, texture = infer_icon_design_language(motif_source)
    return IconDesignBrief(
        app_id=context.app_id,
        name=context.name,
        entry_name=context.entry.name,
        purpose=purpose,
        primary_motif=primary_motif,
        secondary_motifs=secondary_motifs,
        avoid=[
            "書類だけのアイコン",
            "歯車だけのアイコン",
            "チェックだけのアイコン",
            "頭文字だけのアイコン",
            "読めない小さい文字やロゴ風文字",
            "写真風、画面キャプチャ風、過密なUI画面",
        ],
        palette=palette,
        texture=texture,
        small_size_rule="32pxでも主役モチーフの輪郭が判別でき、細かい文字に頼らない。",
        high_resolution_rule="256px以上では輪郭、光沢、余白、素材感がきれいに見える高精細な仕上げ。",
        toolhub_style_rule="既存ToolHubアイコンと並べて違和感のない、角丸の余白と落ち着いた業務向け品質。",
        categories=categories,
        keywords=keywords,
        use_cases=use_cases,
        inputs=inputs,
        outputs=outputs,
        source_files=source_files,
        dependency_signals=dependency_signals,
        readme_excerpt=readme_excerpt,
        style_reference=sanitize_ai_text(style_reference, 500),
    )


def icon_prompt_from_brief(brief: IconDesignBrief, revision_prompt: str | None = None) -> str:
    lines = [
        "ToolHub向けのモダンな高精細PNGアプリアイコンを作成する。",
        f"アプリ: {brief.name} ({brief.app_id})",
        f"用途: {brief.purpose}",
        f"主役モチーフ: {brief.primary_motif}",
        f"補助モチーフ: {', '.join(brief.secondary_motifs)}",
        f"カテゴリ/キーワード: {', '.join((brief.categories + brief.keywords)[:10]) or '未指定'}",
        f"入力: {', '.join(brief.inputs[:5]) or '未指定'}",
        f"出力: {', '.join(brief.outputs[:5]) or '未指定'}",
        f"技術/依存関係の手がかり: {', '.join(brief.dependency_signals[:8]) or '未指定'}",
        f"避ける表現: {', '.join(brief.avoid)}",
        f"色・質感: {brief.palette}。{brief.texture}",
        f"小サイズ視認性: {brief.small_size_rule}",
        f"高精細品質: {brief.high_resolution_rule}",
        f"ToolHub統一感: {brief.toolhub_style_rule}",
        "構図: 中央に特徴的なシルエットを置き、余白を十分に取り、アプリ固有の用途が直感的に伝わるようにする。",
    ]
    if brief.use_cases:
        lines.append(f"代表的な利用場面: {', '.join(brief.use_cases[:4])}")
    if brief.readme_excerpt:
        lines.append(f"READMEからの要約手がかり: {brief.readme_excerpt}")
    if brief.style_reference:
        lines.append(f"既存アイコン参照: {brief.style_reference}")
    if revision_prompt:
        lines.extend(
            [
                "",
                "直前候補に対する修正コンテキスト:",
                sanitize_ai_text(revision_prompt, 1800),
                "修正では、維持したい要素を残しつつ、ユーザーの変更指示を優先する。",
            ]
        )
    return "\n".join(lines)


def infer_icon_design_language(text: str) -> tuple[str, list[str], str, str]:
    normalized = text.lower()
    rules: list[tuple[tuple[str, ...], tuple[str, list[str], str, str]]] = [
        (
            ("csv", "excel", "spreadsheet", "table", "dataframe", "pandas", "集計", "データ"),
            (
                "整ったデータグリッドから洞察が立ち上がるシンボル",
                ["小さなグラフの流れ", "入力テーブルを示すタイル"],
                "ティール、ミント、濃いグレーを基調にした知的な配色",
                "半透明レイヤーと軽いガラス感",
            ),
        ),
        (
            ("upload", "download", "sync", "browser", "playwright", "flow", "web", "selenium", "自動", "連携"),
            (
                "連携フローを示すノードと上向きの転送アーク",
                ["ブラウザ操作を連想させるカーソル", "クラウドへ進む軌跡"],
                "ブルーグリーン、シアン、白のクリーンな配色",
                "発光を抑えた滑らかな樹脂感",
            ),
        ),
        (
            ("report", "pdf", "invoice", "帳票", "請求", "レポート", "検収"),
            (
                "帳票から分析チャートが浮き上がるシンボル",
                ["ページ端の折り返しではなく固有の指標マーク", "確認済みのデータバー"],
                "インディゴ、スレート、アクセントのアンバー",
                "マットな紙質とシャープなチャートの対比",
            ),
        ),
        (
            ("image", "photo", "vision", "screenshot", "画像", "写真"),
            (
                "画像フレームと解析スパークを組み合わせたシンボル",
                ["山形の抽象フレーム", "検出ポイント"],
                "エメラルド、ネイビー、淡いライム",
                "滑らかなグラデーションと粒立ちの少ない光沢",
            ),
        ),
        (
            ("search", "find", "index", "scan", "検索", "探索", "診断"),
            (
                "検索レンズと発見されたデータ片を組み合わせたシンボル",
                ["焦点リング", "強調された結果タイル"],
                "ディープグリーン、アクア、ウォームグレー",
                "クリアなレンズ感と控えめな影",
            ),
        ),
        (
            ("calendar", "schedule", "agenda", "date", "予定", "日程"),
            (
                "予定表と時間の流れを一体化したシンボル",
                ["タイムラインの点", "次の予定を示すアクセント"],
                "サファイア、ペールブルー、コーラルのアクセント",
                "フラットな面と細いハイライト",
            ),
        ),
    ]
    for keywords, design in rules:
        if any(keyword in normalized for keyword in keywords):
            return design
    return (
        "アプリ固有の処理を抽象化した立体的なワークユニット",
        ["入力から出力へ進む短い軌跡", "用途を示す小さな補助タイル"],
        "落ち着いたティール、インディゴ、明るい中間色",
        "柔らかい影と軽いサテン調の質感",
    )


def clean_metadata_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    cleaned: list[str] = []
    for item in value:
        text = sanitize_ai_text(str(item), 120)
        if text and text not in cleaned:
            cleaned.append(text)
    return cleaned[:12]


def dependency_signal_list(report: DependencyReport | None) -> list[str]:
    if not report:
        return []
    values: list[str] = []
    for item in [*report.import_roots, *report.third_party_candidates, *report.requirements]:
        text = sanitize_ai_text(str(item), 80)
        text = re.split(r"[<>=!~\[]", text, maxsplit=1)[0].strip()
        if text and text not in values:
            values.append(text)
    return values[:16]


def safe_source_file_names(context: StudioContext) -> list[str]:
    names: list[str] = []
    sensitive_fragments = ("secret", "token", "password", "credential", "apikey", "api_key", ".env", ".pem", ".key")
    for path in sorted(context.source_root.glob("*")):
        if not path.is_file():
            continue
        name = path.name
        lower = name.lower()
        if any(fragment in lower for fragment in sensitive_fragments):
            continue
        names.append(sanitize_ai_text(name, 100))
        if len(names) >= 24:
            break
    return names


def readme_excerpt_for_icon(context: StudioContext) -> str:
    readme = context.source_root / "README.md"
    if not readme.is_file():
        return ""
    return sanitize_ai_text(readme.read_text(encoding="utf-8", errors="replace"), 1000)


def sanitize_ai_text(value: str, limit: int = 800) -> str:
    text = str(value or "")
    text = re.sub(r"sk-[A-Za-z0-9_-]+", "sk-...redacted", text)
    text = re.sub(r"(?i)(api[_-]?key|token|password|secret)\s*[:=]\s*\S+", r"\1=[redacted]", text)
    text = re.sub(r"[A-Za-z]:\\[^\s,;\"']+", "[local path]", text)
    text = re.sub(r"(?<!\w)/(?:[^/\s]+/)+[^/\s,;\"']+", "[local path]", text)
    text = text.replace("\r", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text).strip()
    return text[:limit]


def first_non_empty(values: list[str]) -> str:
    for value in values:
        if value.strip():
            return value.strip()
    return "ToolHubから起動する業務アプリ"


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
            "language": "ja-JP",
            "style": "業務アプリらしい簡潔な日本語。英語カテゴリ utility/testing/minimal/demo は使わず、日本語に言い換える。",
            "rules": [
                "name と app_id は固有名詞や英数字でもよい。",
                "short_description, description, categories, keywords, examples, use_cases, inputs, outputs, notes は日本語で書く。",
                "keywords は日本語中心。ただし固有名詞、app_id、ファイル名は英数字のままでよい。",
                "READMEやファイル内容を丸ごと引用しない。",
                "APIキー、パスワード、token、credential、secret値を含めない。",
            ],
            "source_files": [path.name for path in sorted(context.source_root.glob("*.py"))[:20]],
            "readme_excerpt": readme_excerpt,
            "existing_app_ids": app_names[:20],
            "required_schema": {
                "short_description": "日本語の短い一言説明",
                "description": "日本語の詳細説明",
                "categories": ["日本語カテゴリ"],
                "use_cases": ["日本語の用途"],
                "inputs": ["日本語の入力説明"],
                "outputs": ["日本語の出力説明"],
                "notes": ["日本語の注意点"],
                "keywords": ["日本語中心の検索キーワード"],
                "examples": ["日本語の利用例"],
            },
            "example": {
                "short_description": "ToolHubの登録動作を確認するためのテストアプリです。",
                "description": "このアプリは、App Studioによる登録、メタデータ反映、起動確認の流れを検証するための最小構成のテストアプリです。",
                "categories": ["開発支援", "テスト"],
                "keywords": ["テスト", "動作確認", "ToolHub"],
                "examples": ["ToolHubへの登録動作を確認する"],
                "use_cases": ["App Studioの登録フロー検証", "メタデータ反映確認"],
                "inputs": ["コマンドライン引数"],
                "outputs": ["標準出力"],
                "notes": ["正式登録前に実行確認を行ってください。"],
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
