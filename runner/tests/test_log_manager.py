from __future__ import annotations

import os
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from toolhub_runner.env_manager import browser_profile_dir, build_app_env
from toolhub_runner.log_manager import create_run_log_paths


ROOT = Path(__file__).resolve().parents[2]
TEST_TMP = ROOT / "data" / "test_tmp"


class LogManagerTests(unittest.TestCase):
    def test_log_paths_use_user_data_root_when_configured(self) -> None:
        TEST_TMP.mkdir(parents=True, exist_ok=True)
        user_data_root = TEST_TMP / "log_manager_user_data"
        with patch.dict(os.environ, {"TOOLHUB_USER_DATA_ROOT": str(user_data_root)}):
            paths = create_run_log_paths(Path("project"), "demo_cli_app")

        self.assertEqual(paths.log_dir, user_data_root / "data" / "logs" / "demo_cli_app")
        self.assertTrue(paths.log_dir.is_dir())

    def test_browser_profile_uses_user_data_root_when_configured(self) -> None:
        TEST_TMP.mkdir(parents=True, exist_ok=True)
        user_data_root = TEST_TMP / "browser_profile_user_data"
        with patch.dict(os.environ, {"TOOLHUB_USER_DATA_ROOT": str(user_data_root)}):
            path = browser_profile_dir(Path("project"), "demo_playwright_app")

        self.assertEqual(path, user_data_root / "data" / "browser_profiles" / "demo_playwright_app")
        self.assertTrue(path.is_dir())

    def test_app_env_disables_bytecode_writes_for_registered_sources(self) -> None:
        manifest = SimpleNamespace(id="sample_app", app_dir=Path("project") / "apps" / "sample_app")

        env = build_app_env(Path("project"), manifest)

        self.assertEqual(env["PYTHONDONTWRITEBYTECODE"], "1")


if __name__ == "__main__":
    unittest.main()
