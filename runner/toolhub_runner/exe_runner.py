from __future__ import annotations

from .base_runner import BaseRunner, RunnerResult
from .env_manager import build_app_env


class ExeRunner(BaseRunner):
    def run(self) -> RunnerResult:
        entry = self.app_entry()
        command = [str(entry)]
        env = build_app_env(self.project_root, self.manifest)
        if self.manifest.run.show_terminal:
            return self.start_visible_terminal(command, env)
        if self.manifest.run.mode == "cli":
            return self.run_blocking(command, env)
        return self.start_detached(command, env)

