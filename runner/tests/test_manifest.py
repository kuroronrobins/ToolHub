from __future__ import annotations

import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from toolhub_runner.manifest import ManifestError, manifest_from_dict, load_app_manifest
from toolhub_runner.manifest import SUPPORTED_RUNNERS


ROOT = Path(__file__).resolve().parents[2]

VALID_DATA = {
    "id": "sample",
    "name": "サンプル",
    "display": {
        "icon": "icon.svg",
        "short_description": "説明",
        "categories": ["業務"],
    },
    "detail": {
        "description": "詳細説明です。",
        "use_cases": ["使い方"],
        "inputs": ["入力"],
        "outputs": ["出力"],
        "notes": ["注意"],
    },
    "search": {
        "keywords": ["サンプル"],
        "examples": ["探したい"],
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
        manifest = load_app_manifest(ROOT, "sample_cli_app")

        self.assertEqual(manifest.id, "sample_cli_app")
        self.assertEqual(manifest.name, "CLIサンプルアプリ")
        self.assertEqual(manifest.run.runner, "cli")
        self.assertIn("バッチ処理", manifest.display.categories)

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


if __name__ == "__main__":
    unittest.main()
