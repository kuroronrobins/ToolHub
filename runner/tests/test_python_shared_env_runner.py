from __future__ import annotations

from contextlib import contextmanager
import os
import shutil
import sys
import unittest
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from toolhub_runner.base_runner import RunnerResult
from toolhub_runner.manifest import Admin, AppManifest, Detail, Display, Run, Search
from toolhub_runner.python_shared_env_runner import PythonSharedEnvRunner


ROOT = Path(__file__).resolve().parents[2]


@contextmanager
def workspace_tempdir():
    base = ROOT / "data" / "tmp_tests"
    base.mkdir(parents=True, exist_ok=True)
    path = base / f"shared_env_case_{uuid.uuid4().hex}"
    path.mkdir(parents=True, exist_ok=False)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def make_manifest(app_dir: Path) -> AppManifest:
    return AppManifest(
        id="shared_sample",
        name="Shared Sample",
        app_dir=app_dir,
        display=Display(icon="icon.svg", short_description="desc", categories=["cat"]),
        detail=Detail(description="desc"),
        search=Search(),
        run=Run(runner="python_shared_env", entry="main.py", mode="cli", env_id="py313-demo"),
        admin=Admin(),
    )


class CapturingSharedEnvRunner(PythonSharedEnvRunner):
    def __init__(self, project_root: Path, manifest: AppManifest) -> None:
        super().__init__(project_root, manifest)
        self.captured_command: list[str] = []
        self.captured_env: dict[str, str] = {}
        self.captured_cwd: Path | None = None

    def run_blocking(self, command: list[str], env: dict[str, str], cwd: Path | None = None) -> RunnerResult:
        self.captured_command = command
        self.captured_env = env
        self.captured_cwd = cwd
        return RunnerResult(ok=True, app_id=self.manifest.id, user_message="ok", log_path=None)


class PythonSharedEnvRunnerTests(unittest.TestCase):
    def test_run_uses_bundled_python_with_shared_env_bootstrap(self) -> None:
        with workspace_tempdir() as root:
            app_dir = root / "apps" / "shared_sample"
            app_dir.mkdir(parents=True)
            entry = app_dir / "main.py"
            entry.write_text("print('ok')\n", encoding="utf-8")

            bundled_python = root / "runtime" / "python" / ("python.exe" if os.name == "nt" else "bin/python")
            bundled_python.parent.mkdir(parents=True)
            bundled_python.write_text("", encoding="utf-8")

            env_root = root / "runtime" / "envs" / "py313-demo"
            site_packages = env_root / "Lib" / "site-packages"
            scripts = env_root / ("Scripts" if os.name == "nt" else "bin")
            pywin32_system32 = site_packages / "pywin32_system32"
            pywin32_system32.mkdir(parents=True)
            scripts.mkdir(parents=True)
            (scripts / ("python.exe" if os.name == "nt" else "python")).write_text("", encoding="utf-8")

            runner = CapturingSharedEnvRunner(root, make_manifest(app_dir))
            result = runner.run()

            self.assertTrue(result.ok)
            self.assertEqual(Path(runner.captured_command[0]), bundled_python)
            self.assertEqual(Path(runner.captured_command[2]), env_root)
            self.assertEqual(Path(runner.captured_command[3]), entry)
            self.assertNotEqual(Path(runner.captured_command[0]), scripts / ("python.exe" if os.name == "nt" else "python"))
            self.assertEqual(runner.captured_env["VIRTUAL_ENV"], str(env_root))
            self.assertEqual(runner.captured_env["TOOLHUB_SHARED_ENV_SITE_PACKAGES"], str(site_packages))
            path_entries = runner.captured_env["PATH"].split(os.pathsep)
            self.assertEqual(path_entries[0], str(bundled_python.parent))
            self.assertIn(str(scripts), path_entries)
            self.assertIn(str(pywin32_system32), path_entries)
            self.assertEqual(runner.captured_cwd, app_dir)


if __name__ == "__main__":
    unittest.main()
