from __future__ import annotations

import sys

from .base_runner import BaseRunner, RunnerResult
from .env_manager import build_app_env


class CliRunner(BaseRunner):
    def run(self) -> RunnerResult:
        entry = self.app_entry()
        command = [sys.executable, str(entry)]
        return self.run_blocking(command, build_app_env(self.project_root, self.manifest))

