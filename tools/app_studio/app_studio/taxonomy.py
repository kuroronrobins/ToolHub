from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TaxonomyItem:
    id: str
    label: str
    aliases: tuple[str, ...] = ()


PRIMARY_CATEGORIES: tuple[TaxonomyItem, ...] = (
    TaxonomyItem("workflow_automation", "業務自動化", ("自動化", "業務支援", "業務効率化", "業務ツール", "ブラウザ操作", "ランチャー")),
    TaxonomyItem("document_pdf", "文書・PDF", ("PDF", "文書管理", "ドキュメント", "文書", "帳票", "書類")),
    TaxonomyItem("spreadsheet", "Excel・表計算", ("Excel", "Excel操作", "表計算", "スプレッドシート", "xlsx", "xlsm")),
    TaxonomyItem("forms_accounting", "帳票・会計", ("帳票登録", "電子帳票", "会計", "請求書", "伝票")),
    TaxonomyItem("web_browser", "Web・ブラウザ", ("Web操作", "ブラウザ操作", "Playwright", "Selenium")),
    TaxonomyItem("development_admin", "開発・管理", ("開発支援", "管理", "診断", "テスト")),
    TaxonomyItem("other", "その他", ("未分類", "その他")),
)

TARGET_CATEGORIES: tuple[TaxonomyItem, ...] = (
    TaxonomyItem("xcgate", "XCgate", ("XC-Gate", "XCGate", "XC gate", "電子帳票")),
    TaxonomyItem("compass", "COMPASS", ("COMPASSO", "コンパッソ")),
    TaxonomyItem("3dx", "3DX", ("3DExperience", "3DEXPERIENCE", "3D EXPERIENCE")),
    TaxonomyItem("excel", "Excel", ("Microsoft Excel", "Office Excel", "xlsx", "xlsm")),
    TaxonomyItem("pdf", "PDF", ("PDF Workbench", "pdf")),
    TaxonomyItem("windows", "Windows", ("Windows", "Win32", "PowerShell")),
)

TAG_CATEGORIES: tuple[TaxonomyItem, ...] = (
    TaxonomyItem("bulk", "一括処理", ("一括", "バッチ", "まとめて", "複数")),
    TaxonomyItem("download", "ダウンロード", ("取得", "ダウンロード", "download", "fetch")),
    TaxonomyItem("upload", "アップロード", ("アップロード", "upload")),
    TaxonomyItem("register", "登録", ("登録", "帳票登録")),
    TaxonomyItem("replace", "置換", ("置換", "差し替え", "反映")),
    TaxonomyItem("id_acquisition", "ID取得", ("ID取得", "ドキュメントID", "ID発行")),
    TaxonomyItem("browser_operation", "ブラウザ操作", ("ブラウザ", "Playwright", "Selenium", "Web操作")),
    TaxonomyItem("document_management", "文書管理", ("文書管理", "ドキュメント", "文書")),
    TaxonomyItem("conversion", "変換", ("変換", "convert", "export")),
    TaxonomyItem("editing", "編集", ("編集", "加工", "管理")),
)


def normalize_metadata_taxonomy(metadata: dict[str, Any]) -> dict[str, Any]:
    result = dict(metadata)
    infer_missing = result.pop("_taxonomy_infer", True) is not False
    text = metadata_taxonomy_text(result)

    primary = normalize_primary_category(result.get("primary_category"), result.get("categories"), text)
    targets = normalize_list(result.get("target_categories"), TARGET_CATEGORIES)
    tags = normalize_list(result.get("tags"), TAG_CATEGORIES)

    if infer_missing and not targets:
        targets = infer_targets(text)
    if infer_missing and not tags:
        tags = infer_tags(text)

    legacy_categories = clean_string_list(result.get("categories"))
    if primary == "その他" and legacy_categories:
        primary = normalize_primary_category(legacy_categories[0], legacy_categories, text)

    result["primary_category"] = primary
    result["target_categories"] = targets
    result["tags"] = tags
    result["categories"] = display_categories(primary, targets, tags, legacy_categories)
    result["proposed_new_categories"] = clean_proposed_categories(result.get("proposed_new_categories"))
    return result


def automation_target_category_error(metadata: dict[str, Any]) -> str:
    normalized = normalize_metadata_taxonomy(metadata)
    if not requires_target_categories(normalized):
        return ""
    if normalized.get("target_categories"):
        return ""
    return "自動化アプリでは display.target_categories に XCgate、COMPASS、3DX などの自動化対象カテゴリが1件以上必要です。"


def requires_target_categories(metadata: dict[str, Any]) -> bool:
    primary = str(metadata.get("primary_category") or "").strip()
    if primary == "業務自動化":
        return True
    text = normalize_text(metadata_taxonomy_text(metadata))
    markers = ("自動化", "ブラウザ操作", "playwright", "selenium")
    return any(normalize_text(marker) in text for marker in markers)


def metadata_taxonomy_text(metadata: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in (
        "name",
        "short_description",
        "description",
        "primary_category",
        "categories",
        "target_categories",
        "tags",
        "keywords",
        "examples",
        "use_cases",
        "inputs",
        "outputs",
        "notes",
    ):
        value = metadata.get(key)
        if isinstance(value, list):
            parts.extend(str(item) for item in value)
        elif value is not None:
            parts.append(str(value))
    return " ".join(parts)


def normalize_primary_category(value: Any, legacy_categories: Any, text: str) -> str:
    explicit = normalize_one(value, PRIMARY_CATEGORIES)
    if explicit:
        return explicit
    for item in clean_string_list(legacy_categories):
        normalized = normalize_one(item, PRIMARY_CATEGORIES)
        if normalized:
            return normalized

    hits = score_items(text, PRIMARY_CATEGORIES)
    if hits:
        return hits[0]
    return "その他"


def normalize_list(value: Any, taxonomy: tuple[TaxonomyItem, ...]) -> list[str]:
    labels: list[str] = []
    for raw in clean_string_list(value):
        label = normalize_one(raw, taxonomy)
        if label and label not in labels:
            labels.append(label)
    return labels


def infer_targets(text: str) -> list[str]:
    return score_items(text, TARGET_CATEGORIES)


def infer_tags(text: str) -> list[str]:
    return score_items(text, TAG_CATEGORIES)[:5]


def normalize_one(value: Any, taxonomy: tuple[TaxonomyItem, ...]) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    normalized = normalize_text(raw)
    for item in taxonomy:
        candidates = (item.id, item.label, *item.aliases)
        if any(normalized == normalize_text(candidate) for candidate in candidates):
            return item.label
    for item in taxonomy:
        if any(normalize_text(candidate) in normalized for candidate in (item.label, *item.aliases)):
            return item.label
    return ""


def score_items(text: str, taxonomy: tuple[TaxonomyItem, ...]) -> list[str]:
    normalized = normalize_text(text)
    labels: list[str] = []
    for item in taxonomy:
        candidates = (item.id, item.label, *item.aliases)
        if any(normalize_text(candidate) in normalized for candidate in candidates):
            labels.append(item.label)
    return labels


def display_categories(primary: str, targets: list[str], tags: list[str], legacy_categories: list[str] | None = None) -> list[str]:
    values: list[str] = []
    main_target = targets[:1]
    related_targets = targets[1:]
    for item in [*main_target, primary, *related_targets, *tags, *(legacy_categories or [])]:
        text = str(item or "").strip()
        if text and text not in values:
            values.append(text)
    return values or ["その他"]


def clean_proposed_categories(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    cleaned: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        axis = str(item.get("axis") or "").strip()
        label = str(item.get("label") or "").strip()
        reason = str(item.get("reason") or "").strip()
        if axis not in {"primary", "target", "tag"} or not label:
            continue
        cleaned.append(
            {
                "axis": axis,
                "label": label[:80],
                "reason": reason[:240],
                "status": "pending",
            }
        )
    return cleaned[:5]


def clean_string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        candidates = re.split(r"[\n,、]", value)
    elif isinstance(value, list):
        candidates = value
    else:
        return []
    cleaned: list[str] = []
    for item in candidates:
        text = str(item or "").strip()
        if text and text not in cleaned:
            cleaned.append(text)
    return cleaned


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "").casefold().replace("-", ""))
