from __future__ import annotations

import sys

from .base_runner import BaseRunner, RunnerResult
from .env_manager import build_app_env


class CliRunner(BaseRunner):
    def run(self) -> RunnerResult:
        entry = self.app_entry()
        command = [sys.executable, str(entry)]
        env = build_app_env(self.project_root, self.manifest)
        if self.manifest.run.show_terminal:
            return self.start_visible_terminal(command, env)
        return self.run_blocking(command, env)

