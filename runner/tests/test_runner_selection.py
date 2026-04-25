from __future__ import annotations

import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from toolhub_runner.cli_runner import CliRunner
from toolhub_runner.exe_runner import ExeRunner
from toolhub_runner.main import select_runner
from toolhub_runner.manifest import Admin, AppManifest, Detail, Display, Run, Search
from toolhub_runner.playwright_runner import PlaywrightPythonRunner
from toolhub_runner.python_app_env_runner import PythonAppEnvRunner
from toolhub_runner.python_runner import PythonRunner


def make_manifest(runner: str) -> AppManifest:
    return AppManifest(
        id="sample",
        name="Sample",
        app_dir=Path("apps/sample"),
        display=Display(icon="icon.svg", short_description="desc", categories=["cat"]),
        detail=Detail(description="desc"),
        search=Search(),
        run=Run(runner=runner, entry="main.py", mode="cli"),
        admin=Admin(),
    )


class RunnerSelectionTests(unittest.TestCase):
    def test_select_python_runner(self) -> None:
        self.assertIsInstance(select_runner(Path("."), make_manifest("python")), PythonRunner)

    def test_select_cli_runner(self) -> None:
        self.assertIsInstance(select_runner(Path("."), make_manifest("cli")), CliRunner)

    def test_select_exe_runner(self) -> None:
        self.assertIsInstance(select_runner(Path("."), make_manifest("exe")), ExeRunner)

    def test_select_web_operation_runner(self) -> None:
        self.assertIsInstance(select_runner(Path("."), make_manifest("playwright_python")), PlaywrightPythonRunner)

    def test_select_python_app_env_runner(self) -> None:
        self.assertIsInstance(select_runner(Path("."), make_manifest("python_app_env")), PythonAppEnvRunner)


if __name__ == "__main__":
    unittest.main()

