from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools" / "app_studio"))

from app_studio.taxonomy import automation_target_category_error, normalize_metadata_taxonomy


def test_normalize_metadata_taxonomy_keeps_automation_targets() -> None:
    metadata = normalize_metadata_taxonomy(
        {
            "short_description": "XC-Gateへの帳票登録をブラウザ操作で自動化します。",
            "description": "Excelファイルを使ってXCgateの登録処理を一括実行します。",
            "categories": ["業務支援", "ブラウザ操作"],
            "keywords": ["XC-Gate", "登録", "一括処理"],
        }
    )

    assert metadata["primary_category"] == "業務自動化"
    assert "XCgate" in metadata["target_categories"]
    assert "登録" in metadata["tags"]
    assert metadata["categories"][0] == "XCgate"
    assert "XCgate" in metadata["categories"]


def test_automation_metadata_requires_target_categories() -> None:
    assert automation_target_category_error(
        {
            "primary_category": "業務自動化",
            "target_categories": [],
            "tags": ["ブラウザ操作"],
        }
    )
    assert not automation_target_category_error(
        {
            "primary_category": "業務自動化",
            "target_categories": ["COMPASS"],
            "tags": ["ブラウザ操作"],
        }
    )
