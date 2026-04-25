from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest.mock import patch

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from toolhub_runner.env_manager import browser_profile_dir
from toolhub_runner.log_manager import create_run_log_paths


ROOT = Path(__file__).resolve().parents[2]
TEST_TMP = ROOT / "data" / "test_tmp"


class LogManagerTests(unittest.TestCase):
    def test_log_paths_use_user_data_root_when_configured(self) -> None:
        TEST_TMP.mkdir(parents=True, exist_ok=True)
        user_data_root = TEST_TMP / "log_manager_user_data"
        with patch.dict(os.environ, {"TOOLHUB_USER_DATA_ROOT": str(user_data_root)}):
            paths = create_run_log_paths(Path("project"), "sample_cli_app")

        self.assertEqual(paths.log_dir, user_data_root / "data" / "logs" / "sample_cli_app")
        self.assertTrue(paths.log_dir.is_dir())

    def test_browser_profile_uses_user_data_root_when_configured(self) -> None:
        TEST_TMP.mkdir(parents=True, exist_ok=True)
        user_data_root = TEST_TMP / "browser_profile_user_data"
        with patch.dict(os.environ, {"TOOLHUB_USER_DATA_ROOT": str(user_data_root)}):
            path = browser_profile_dir(Path("project"), "sample_playwright_app")

        self.assertEqual(path, user_data_root / "data" / "browser_profiles" / "sample_playwright_app")
        self.assertTrue(path.is_dir())


if __name__ == "__main__":
    unittest.main()
