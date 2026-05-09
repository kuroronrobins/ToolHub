from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools" / "app_studio"))

from app_studio.app_pack_contract import (
    app_yaml_display_icon_entry,
    app_yaml_run_entry,
    app_pack_contract_summary,
    app_pack_required_entries,
    app_pack_requirements_lock_entry,
    normalize_app_relative_entry,
)


FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "app_pack_contract"


def load_contract() -> dict:
    return json.loads((FIXTURE_ROOT / "expected_contract.json").read_text(encoding="utf-8"))


class AppPackContractFixtureTests(unittest.TestCase):
    def test_fixture_required_entries_match_python_contract_helpers(self) -> None:
        for case in load_contract()["cases"]:
            with self.subTest(case=case["id"]):
                app_dir = FIXTURE_ROOT / case["app_dir"]
                app_yaml_text = (app_dir / "app.yaml").read_text(encoding="utf-8")
                run_entry = app_yaml_run_entry(app_yaml_text, app_dir=app_dir)
                display_icon = app_yaml_display_icon_entry(app_yaml_text, app_dir=app_dir)
                requirements_lock = app_pack_requirements_lock_entry(app_dir)

                self.assertEqual(run_entry, case["expected_run_entry"])
                self.assertEqual(display_icon, case["expected_display_icon"])
                self.assertEqual(requirements_lock, case["expected_requirements_lock"])
                self.assertEqual(
                    sorted(
                        app_pack_required_entries(
                            case["app_id"],
                            run_entry=run_entry,
                            display_icon=display_icon,
                            requirements_lock=requirements_lock,
                        )
                    ),
                    sorted(case["expected_required_entries"]),
                )
                summary = app_pack_contract_summary(case["app_id"], app_yaml_text, app_dir=app_dir)
                self.assertEqual(summary["run_entry"], case["expected_run_entry"])
                self.assertEqual(summary["display_icon"], case["expected_display_icon"])
                self.assertEqual(summary["requirements_lock"], case["expected_requirements_lock"])
                self.assertEqual(summary["required_entries"], sorted(case["expected_required_entries"]))

    def test_legacy_runner_fixture_keeps_requirements_lock_optional(self) -> None:
        case = next(case for case in load_contract()["cases"] if case["id"] == "legacy_python_runner_lock_optional")
        self.assertIsNone(app_pack_requirements_lock_entry(FIXTURE_ROOT / case["app_dir"]))
        self.assertFalse((FIXTURE_ROOT / case["app_dir"] / "requirements.lock").exists())
        self.assertNotIn(f"{case['app_id']}/requirements.lock", case["expected_required_entries"])

    def test_app_relative_path_normalization_matches_fixture_contract(self) -> None:
        for case in load_contract()["path_normalization_cases"]:
            with self.subTest(case=case["id"]):
                if "expected" in case:
                    self.assertEqual(normalize_app_relative_entry(case["input"], label="fixture path"), case["expected"])
                else:
                    with self.assertRaisesRegex(ValueError, case["error_contains"]):
                        normalize_app_relative_entry(case["input"], label="fixture path")


if __name__ == "__main__":
    unittest.main()
