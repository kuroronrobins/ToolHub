from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RUNNER_INITIAL_STATUS = "起動準備をしています"


class SampleAppEventTests(unittest.TestCase):
    def test_blocking_samples_do_not_emit_runner_initial_status(self) -> None:
        for app_id in ("sample_cli_app", "sample_playwright_app"):
            with self.subTest(app_id=app_id):
                text = (ROOT / "apps" / app_id / "main.py").read_text(encoding="utf-8")
                self.assertNotIn(RUNNER_INITIAL_STATUS, text)

    def test_blocking_samples_emit_processing_statuses(self) -> None:
        cli_text = (ROOT / "apps" / "sample_cli_app" / "main.py").read_text(encoding="utf-8")
        playwright_text = (ROOT / "apps" / "sample_playwright_app" / "main.py").read_text(encoding="utf-8")

        self.assertIn("データを確認しています", cli_text)
        self.assertIn("完了しました", cli_text)
        self.assertIn("画面を準備しています", playwright_text)
        self.assertIn("完了しました", playwright_text)


if __name__ == "__main__":
    unittest.main()
