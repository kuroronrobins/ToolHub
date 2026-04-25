from __future__ import annotations

from contextlib import contextmanager
import shutil
import unittest
import uuid
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools" / "app_studio"))
sys.path.insert(0, str(ROOT / "runner"))

from app_studio.build_planner import make_build_plan
from app_studio.file_classifier import classify_files
from app_studio.manifest_generator import generate_app_yaml
from app_studio.models import ImportOptions
from app_studio.scanner import create_context
from app_studio.secret_scanner import scan_secrets
from app_studio.util import default_app_id_for_entry, reset_output_dir
from toolhub_runner.manifest import manifest_from_dict, load_yaml_mapping


@contextmanager
def workspace_tempdir():
    base = ROOT / "data" / "tmp_tests"
    base.mkdir(parents=True, exist_ok=True)
    path = base / f"case_{uuid.uuid4().hex}"
    path.mkdir(parents=True, exist_ok=False)
    try:
        yield str(path)
    finally:
        shutil.rmtree(path, ignore_errors=True)


class AppStudioTests(unittest.TestCase):
    def test_app_id_auto_generation_uses_parent_for_main(self) -> None:
        with workspace_tempdir() as temp:
            entry = Path(temp) / "My Agenda App" / "main.py"
            entry.parent.mkdir()
            entry.write_text("print('hello')\n", encoding="utf-8")

            self.assertEqual(default_app_id_for_entry(entry), "my_agenda_app")

    def test_output_dir_is_under_entry_parent(self) -> None:
        with workspace_tempdir() as temp:
            entry = Path(temp) / "app" / "main.py"
            entry.parent.mkdir()
            entry.write_text("print('hello')\n", encoding="utf-8")

            output = reset_output_dir(entry, "demo_app")

            self.assertTrue(output.is_relative_to(entry.parent.resolve()))
            self.assertEqual(output.name, "demo_app")

    def test_existing_output_is_overwritten_safely(self) -> None:
        with workspace_tempdir() as temp:
            entry = Path(temp) / "app" / "main.py"
            entry.parent.mkdir()
            entry.write_text("print('hello')\n", encoding="utf-8")
            old = entry.parent / "ToolHub_AppStudio_Output" / "demo_app" / "old.txt"
            old.parent.mkdir(parents=True)
            old.write_text("old", encoding="utf-8")

            output = reset_output_dir(entry, "demo_app")

            self.assertTrue(output.is_dir())
            self.assertFalse(old.exists())

    def test_secret_scanner_detects_env_and_api_key(self) -> None:
        with workspace_tempdir() as temp:
            root = Path(temp)
            (root / ".env").write_text("OPENAI_API_KEY=sk-test\n", encoding="utf-8")
            (root / "main.py").write_text("api_key = 'secret'\n", encoding="utf-8")

            report = scan_secrets(root)

            self.assertTrue(report.has_high)
            details = "\n".join(finding.detail for finding in report.findings)
            self.assertIn("api", details.lower())

    def test_manifest_generator_outputs_runner_compatible_yaml(self) -> None:
        with workspace_tempdir() as temp:
            root = Path(temp)
            repo = root / "repo"
            (repo / "apps").mkdir(parents=True)
            (repo / "release").mkdir()
            (repo / "runner").mkdir()
            source = root / "source"
            source.mkdir()
            entry = source / "main.py"
            entry.write_text("print('hello')\n", encoding="utf-8")

            context = create_context(ImportOptions(entry=entry, action="suggest", app_id="demo_app", name="Demo App"), repo)
            inventory = classify_files(context)
            plan = make_build_plan(context, inventory)
            yaml_text = generate_app_yaml(context, plan, {"short_description": "demo", "description": "demo", "categories": ["demo"]})
            app_dir = repo / "apps" / "demo_app"
            app_dir.mkdir()
            yaml_path = app_dir / "app.yaml"
            yaml_path.write_text(yaml_text, encoding="utf-8")

            data = load_yaml_mapping(yaml_path)
            manifest = manifest_from_dict(data, app_dir)

            self.assertEqual(manifest.id, "demo_app")
            self.assertEqual(manifest.run.runner, "python_app_env")


if __name__ == "__main__":
    unittest.main()
