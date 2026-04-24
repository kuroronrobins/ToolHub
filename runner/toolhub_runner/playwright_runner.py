from __future__ import annotations

import sys

from .base_runner import BaseRunner, RunnerResult
from .env_manager import browser_profile_dir, build_app_env


class PlaywrightPythonRunner(BaseRunner):
    def run(self) -> RunnerResult:
        entry = self.app_entry()
        env = build_app_env(self.project_root, self.manifest)
        profile_dir = browser_profile_dir(self.project_root, self.manifest.id)
        env["TOOLHUB_BROWSER_PROFILE_DIR"] = str(profile_dir)
        env["TOOLHUB_FIRST_SETUP_MESSAGE"] = "初回設定が必要です。表示される画面でログインを完了してください。次回以降はそのまま使用できます。"
        command = [sys.executable, str(entry)]
        return self.run_blocking(command, env)

