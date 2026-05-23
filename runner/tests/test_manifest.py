from __future__ import annotations

from contextlib import contextmanager
import shutil
import sys
import unittest
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from toolhub_runner.manifest import SUPPORTED_RUNNERS
from toolhub_runner.manifest import ManifestError, load_app_manifest, manifest_from_dict


ROOT = Path(__file__).resolve().parents[2]


@contextmanager
def workspace_tempdir():
    base = ROOT / "data" / "tmp_tests"
    base.mkdir(parents=True, exist_ok=True)
    path = base / f"runner_case_{uuid.uuid4().hex}"
    path.mkdir(parents=True, exist_ok=False)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)

VALID_DATA = {
    "id": "sample",
    "name": "Sample",
    "display": {
        "icon": "icon.svg",
        "short_description": "Description",
        "categories": ["Tools"],
    },
    "detail": {
        "description": "Detailed description",
        "use_cases": ["Use"],
        "inputs": ["Input"],
        "outputs": ["Output"],
        "notes": ["Note"],
    },
    "search": {
        "keywords": ["sample"],
        "examples": ["find sample"],
    },
    "run": {
        "runner": "cli",
        "entry": "main.py",
        "mode": "cli",
    },
    "admin": {
        "version": "1.0.0",
        "owner": "admin",
        "requirements": "requirements.txt",
        "log_dir": "logs",
    },
}


class ManifestTests(unittest.TestCase):
    def test_load_app_manifest(self) -> None:
        with workspace_tempdir() as repo:
            app_dir = repo / "apps" / "demo_cli_app"
            app_dir.mkdir(parents=True)
            (app_dir / "app.yaml").write_text(
                """id: demo_cli_app
name: Demo CLI App
display:
  icon: icon.svg
  short_description: Demo app
  categories:
    - Tools
detail:
  description: Demo detail
  use_cases:
    - Test
  inputs:
    - None
  outputs:
    - Log
  notes:
    - Demo
search:
  keywords:
    - demo
  examples:
    - run demo
run:
  runner: cli
  entry: main.py
  mode: cli
admin:
  version: 1.0.0
  owner: admin
  requirements: requirements.txt
  log_dir: logs
""",
                encoding="utf-8",
            )

            manifest = load_app_manifest(repo, "demo_cli_app")

        self.assertEqual(manifest.id, "demo_cli_app")
        self.assertEqual(manifest.name, "Demo CLI App")
        self.assertEqual(manifest.run.runner, "cli")
        self.assertIn("Tools", manifest.display.categories)

    def test_missing_required_field_raises(self) -> None:
        with self.assertRaises(ManifestError):
            manifest_from_dict({"id": "sample"}, ROOT / "apps" / "sample")

    def test_unsupported_runner_raises(self) -> None:
        data = dict(VALID_DATA)
        data["run"] = dict(VALID_DATA["run"])
        data["run"]["runner"] = "unknown"
        with self.assertRaises(ManifestError):
            manifest_from_dict(data, ROOT / "apps" / "sample")

    def test_python_app_env_is_supported(self) -> None:
        self.assertIn("python_app_env", SUPPORTED_RUNNERS)

    def test_python_shared_env_is_supported(self) -> None:
        data = dict(VALID_DATA)
        data["run"] = dict(VALID_DATA["run"])
        data["run"]["runner"] = "python_shared_env"
        data["run"]["env_id"] = "py313-demo"

        manifest = manifest_from_dict(data, ROOT / "apps" / "sample")

        self.assertIn("python_shared_env", SUPPORTED_RUNNERS)
        self.assertEqual(manifest.run.env_id, "py313-demo")

    def test_run_show_terminal_defaults_to_false_and_parses_true(self) -> None:
        default_manifest = manifest_from_dict(dict(VALID_DATA), ROOT / "apps" / "sample")
        self.assertFalse(default_manifest.run.show_terminal)

        data = dict(VALID_DATA)
        data["run"] = dict(VALID_DATA["run"])
        data["run"]["show_terminal"] = True

        manifest = manifest_from_dict(data, ROOT / "apps" / "sample")

        self.assertTrue(manifest.run.show_terminal)


if __name__ == "__main__":
    unittest.main()
