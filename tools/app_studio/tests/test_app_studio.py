from __future__ import annotations

from contextlib import contextmanager
import json
import shutil
import unittest
import uuid
import zipfile
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools" / "app_studio"))
sys.path.insert(0, str(ROOT / "runner"))

from app_studio.build_profile import default_build_profile
from app_studio.build_planner import make_build_plan
from app_studio.dependency_analyzer import analyze_dependencies
from app_studio.file_classifier import classify_files, inventory_markdown, toolhubignore_suggestion_markdown
from app_studio.frozen_folder_builder import classify_pyinstaller_failure, pyinstaller_artifact_paths
from app_studio.manifest_generator import generate_app_yaml
from app_studio.metadata_override import apply_metadata_override, load_metadata_override
from app_studio.models import BuildPlan, ImportOptions
from app_studio.icon_override import apply_icon_override, load_icon_override
from app_studio.scanner import create_context
from app_studio.secret_scanner import scan_secrets
from app_studio.registrar import apply_registration, backup_existing
from app_studio.util import default_app_id_for_entry, reset_output_dir
from toolhub_runner.manifest import manifest_from_dict, load_yaml_mapping
from main import normalize_normal_registration_args
from main import parse_args as parse_app_studio_args


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
    def test_normal_registration_policy_forces_frozen_folder_pipeline(self) -> None:
        args = parse_app_studio_args(["--entry", "main.py", "--apply"])

        normalize_normal_registration_args(args)

        self.assertEqual(args.build_mode, "frozen-folder")
        self.assertTrue(args.generate_lock)
        self.assertTrue(args.build_frozen_folder)
        self.assertTrue(args.rebuild_frozen_folder)
        self.assertTrue(args.verify_runtime)
        self.assertFalse(args.create_app_env)
        self.assertFalse(args.rebuild_app_env)
        self.assertFalse(args.skip_app_env_build)

    def test_normal_registration_policy_rejects_existing_exe_entry(self) -> None:
        args = parse_app_studio_args(["--entry", "tool.exe", "--apply"])

        with self.assertRaises(ValueError):
            normalize_normal_registration_args(args)

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

    def test_secret_scanner_does_not_block_excluded_auth_directory(self) -> None:
        with workspace_tempdir() as temp:
            root = Path(temp)
            (root / ".auth").mkdir()
            (root / ".auth" / "storage_state.json").write_text('{"token": "secret"}\n', encoding="utf-8")
            (root / "main.py").write_text("print('ok')\n", encoding="utf-8")

            report = scan_secrets(root)

            self.assertFalse(report.has_high)
            self.assertTrue(any(finding.kind == "excluded-sensitive-directory" for finding in report.findings))

    def test_secret_scanner_classifies_apply_blocks_by_inventory(self) -> None:
        with workspace_tempdir() as temp:
            root = Path(temp)
            repo = root / "repo"
            (repo / "apps").mkdir(parents=True)
            (repo / "release").mkdir()
            (repo / "runner").mkdir()
            source = root / "source"
            source.mkdir()
            entry = source / "main.py"
            entry.write_text(
                "\n".join(
                    [
                        "token = None",
                        "from pathlib import Path",
                        "Path('assets/runtime.json').read_text()",
                    ]
                ),
                encoding="utf-8",
            )
            (source / "README.md").write_text("Set OPENAI_API_KEY in your environment.\n", encoding="utf-8")
            (source / "config.example.yaml").write_text('api_key: "<your key>"\n', encoding="utf-8")
            (source / ".env").write_text("OPENAI_API_KEY=sk-realisticvalue1234567890\n", encoding="utf-8")
            (source / "storage_state.json").write_text('{"cookies": [{"value": "abc"}]}\n', encoding="utf-8")
            (source / "logs").mkdir()
            (source / "logs" / "run.log").write_text("token=sk-logvalue123456789012345\n", encoding="utf-8")
            (source / "assets").mkdir()
            (source / "assets" / "runtime.json").write_text('{"api_key": "sk-packagedvalue1234567890"}\n', encoding="utf-8")

            context = create_context(ImportOptions(entry=entry, action="suggest", app_id="secret_app", name="Secret App"), repo)
            inventory = classify_files(context)
            report = scan_secrets(source, inventory)
            findings_by_path = {finding.path.relative_to(source).as_posix(): finding for finding in report.findings}

            self.assertFalse(findings_by_path["README.md"].blocks_apply)
            self.assertTrue(findings_by_path["README.md"].false_positive_candidate)
            self.assertNotIn("config.example.yaml", findings_by_path)
            if "main.py" in findings_by_path:
                self.assertFalse(findings_by_path["main.py"].blocks_apply)
            self.assertTrue(findings_by_path[".env"].blocks_apply)
            self.assertTrue(findings_by_path["storage_state.json"].blocks_apply)
            self.assertTrue(findings_by_path["assets/runtime.json"].blocks_apply)
            self.assertNotIn("logs/run.log", findings_by_path)
            self.assertTrue(report.blocks_apply)
            self.assertTrue(report.blocks_ai_submission)

    def test_nested_runtime_files_and_requirements_are_detected(self) -> None:
        with workspace_tempdir() as temp:
            root = Path(temp)
            repo = root / "repo"
            (repo / "apps").mkdir(parents=True)
            (repo / "release").mkdir()
            (repo / "runner").mkdir()
            source = root / "source"
            flows = source / "xcgate_flows"
            (flows / "flows").mkdir(parents=True)
            (flows / ".auth").mkdir()
            (flows / "src").mkdir()
            entry = source / "run_xcgate_upload.py"
            entry.write_text("import subprocess\n", encoding="utf-8")
            (flows / "requirements.txt").write_text("\ufeff# --- runtime ---\nplaywright>=1.46,<2.0\nPyYAML>=6.0,<7.0\n", encoding="utf-8")
            (flows / "config.yaml").write_text("options:\n  headless: false\n", encoding="utf-8")
            (flows / "flows" / "xcgate_upload.flow").write_text("goto https://example.com\n", encoding="utf-8")
            (flows / ".auth" / "mega_state.json").write_text('{"token": "secret"}\n', encoding="utf-8")
            (flows / "src" / "main.py").write_text("print('main')\n", encoding="utf-8")

            context = create_context(ImportOptions(entry=entry, action="suggest", app_id="xcgate", name="XCgate"), repo)
            inventory = classify_files(context)
            included = {Path(record.relative_path).as_posix() for record in inventory.records if record.include}
            dependency_report, requirements = analyze_dependencies(context, inventory)

            self.assertIn("xcgate_flows/requirements.txt", included)
            self.assertIn("xcgate_flows/config.yaml", included)
            self.assertIn("xcgate_flows/flows/xcgate_upload.flow", included)
            self.assertIn("xcgate_flows/src/main.py", included)
            self.assertNotIn("xcgate_flows/.auth/mega_state.json", included)
            self.assertEqual(dependency_report.source, "nested-requirements.txt")
            self.assertIn("playwright>=1.46,<2.0", requirements)
            self.assertIn("PyYAML>=6.0,<7.0", requirements)
            self.assertNotIn("--- runtime ---", requirements)

    def test_code_referenced_runtime_files_are_included_without_extension_whitelist(self) -> None:
        with workspace_tempdir() as temp:
            root = Path(temp)
            repo = root / "repo"
            (repo / "apps").mkdir(parents=True)
            (repo / "release").mkdir()
            (repo / "runner").mkdir()
            source = root / "source"
            (source / "flows").mkdir(parents=True)
            entry = source / "main.py"
            entry.write_text(
                "\n".join(
                    [
                        "from pathlib import Path",
                        "import os",
                        "import helpers",
                        "open('data.json').read()",
                        "Path(__file__).parent / 'config.yaml'",
                        "open(os.path.join('flows', 'upload.flow')).read()",
                        "input_name = 'dynamic.csv'",
                        "open(input_name).read()",
                    ]
                ),
                encoding="utf-8",
            )
            (source / "helpers.py").write_text(
                "\n".join(
                    [
                        "from pathlib import Path",
                        "Path('table.csv').read_text()",
                        "Path('settings.toml').read_text()",
                        "Path('app.ini').read_text()",
                    ]
                ),
                encoding="utf-8",
            )
            for name in ["data.json", "config.yaml", "table.csv", "settings.toml", "app.ini", "unused.csv"]:
                (source / name).write_text("x\n", encoding="utf-8")
            (source / "flows" / "upload.flow").write_text("goto https://example.com\n", encoding="utf-8")
            (source / ".env").write_text("TOKEN=x\n", encoding="utf-8")

            context = create_context(ImportOptions(entry=entry, action="suggest", app_id="asset_app", name="Asset App"), repo)
            inventory = classify_files(context)
            included = {Path(record.relative_path).as_posix() for record in inventory.records if record.include}
            records = {Path(record.relative_path).as_posix(): record for record in inventory.records}

            for name in ["data.json", "config.yaml", "table.csv", "settings.toml", "app.ini", "flows/upload.flow"]:
                self.assertIn(name, included)
                self.assertIn(records[name].detected_from, {"code_reference", "resource_directory", "well_known_config"})
            self.assertNotIn("unused.csv", included)
            self.assertEqual(records[".env"].status, "blocked")
            self.assertTrue(inventory.manual_checks)

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
            self.assertEqual(manifest.run.runner, "exe")
            self.assertEqual(manifest.run.entry, "bin/demo_app/demo_app.exe")
            self.assertEqual(data["display"]["icon"], "icon.png")
            self.assertEqual(data["display"]["icon_fallback"], "icon.svg")
            self.assertEqual(data["runtime"]["distribution_mode"], "frozen_folder")
            self.assertEqual(data["runtime"]["requirements_lock"], "requirements.lock")
            self.assertEqual(data["build"]["managed_by"], "toolhub_app_studio")
            self.assertEqual(data["build"]["build_mode"], "frozen-folder")

    def test_metadata_override_applies_manifest_fields(self) -> None:
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
            metadata, applied, warnings = apply_metadata_override(
                {"short_description": "old", "categories": ["old"], "keywords": ["old"]},
                {
                    "short_description": "New short",
                    "description": "New long",
                    "categories": ["ops", "reports"],
                    "keywords": ["demo", "report"],
                },
            )
            yaml_text = generate_app_yaml(context, plan, metadata)

            self.assertEqual(warnings, [])
            self.assertIn("short_description", applied)
            self.assertIn("short_description: New short", yaml_text)
            self.assertIn("- ops", yaml_text)
            self.assertIn("- report", yaml_text)

    def test_metadata_override_empty_values_do_not_overwrite(self) -> None:
        metadata, applied, warnings = apply_metadata_override(
            {"short_description": "keep", "categories": ["keep"]},
            {"short_description": "  ", "categories": []},
        )

        self.assertEqual(warnings, [])
        self.assertEqual(applied, [])
        self.assertEqual(metadata["short_description"], "keep")
        self.assertEqual(metadata["categories"], ["keep"])

    def test_metadata_override_json_loads(self) -> None:
        with workspace_tempdir() as temp:
            path = Path(temp) / "override.json"
            path.write_text('{"short_description": "Loaded", "categories": ["ops"]}', encoding="utf-8")

            loaded = load_metadata_override(path)

            self.assertEqual(loaded["short_description"], "Loaded")
            self.assertEqual(loaded["categories"], ["ops"])

    def test_metadata_override_cli_argument_is_supported(self) -> None:
        args = parse_app_studio_args(
            [
                "import",
                "--entry",
                "main.py",
                "--source-root",
                "src",
                "--metadata-override",
                "override.json",
                "--icon-override",
                "icon_override.json",
                "--build-profile",
                "build_profile.json",
                "--suggest",
            ]
        )

        self.assertEqual(args.metadata_override, "override.json")
        self.assertEqual(args.source_root, "src")
        self.assertEqual(args.icon_override, "icon_override.json")
        self.assertEqual(args.build_profile, "build_profile.json")

    def test_explicit_source_root_keeps_entry_relative(self) -> None:
        with workspace_tempdir() as temp:
            root = Path(temp)
            repo = root / "repo"
            (repo / "apps").mkdir(parents=True)
            (repo / "release").mkdir()
            (repo / "runner").mkdir()
            source = root / "project"
            entry = source / "src" / "main.py"
            entry.parent.mkdir(parents=True)
            entry.write_text("print('hello')\n", encoding="utf-8")

            context = create_context(
                ImportOptions(entry=entry, action="suggest", source_root=source, app_id="scoped_app", name="Scoped App"),
                repo,
            )

            self.assertEqual(context.source_root, source.resolve())
            self.assertEqual(context.source_root_origin, "explicit")
            self.assertEqual(context.entry_relative.as_posix(), "src/main.py")

    def test_explicit_source_root_rejects_entry_outside_scope(self) -> None:
        with workspace_tempdir() as temp:
            root = Path(temp)
            repo = root / "repo"
            (repo / "apps").mkdir(parents=True)
            (repo / "release").mkdir()
            (repo / "runner").mkdir()
            source = root / "project"
            source.mkdir()
            entry = root / "other" / "main.py"
            entry.parent.mkdir()
            entry.write_text("print('hello')\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "source_root"):
                create_context(
                    ImportOptions(entry=entry, action="suggest", source_root=source, app_id="bad_scope", name="Bad Scope"),
                    repo,
                )

    def test_inventory_excludes_generated_work_and_output_directories(self) -> None:
        with workspace_tempdir() as temp:
            root = Path(temp)
            repo = root / "repo"
            (repo / "apps").mkdir(parents=True)
            (repo / "release").mkdir()
            (repo / "runner").mkdir()
            source = root / "source"
            source.mkdir()
            entry = source / "main.py"
            entry.write_text("print('ok')\n", encoding="utf-8")
            for dirname in [".git", ".venv", "work", "results", "ToolHub_AppStudio_Output", "logs", "tmp", "sessions", "screenshots"]:
                folder = source / dirname
                folder.mkdir(parents=True)
                (folder / "ignored.py").write_text("OPENAI_API_KEY='sk-ignored123456789012345'\n", encoding="utf-8")

            context = create_context(ImportOptions(entry=entry, action="suggest", app_id="scope_app", name="Scope App"), repo)
            inventory = classify_files(context)
            excluded_dirs = {item["relative_path"] for item in inventory.excluded_directories}
            included = {record.relative_path for record in inventory.records if record.include}
            report = scan_secrets(context.source_root, inventory)

            self.assertTrue({".git", ".venv", "work", "results", "ToolHub_AppStudio_Output", "logs", "tmp", "sessions", "screenshots"}.issubset(excluded_dirs))
            self.assertEqual(included, {"main.py"})
            self.assertFalse(any("ignored.py" in str(finding.path) for finding in report.findings))

    def test_secret_scan_skips_runtime_output_directories_without_inventory(self) -> None:
        with workspace_tempdir() as temp:
            root = Path(temp)
            (root / "logs").mkdir()
            (root / "tmp").mkdir()
            (root / "main.py").write_text("print('ok')\n", encoding="utf-8")
            (root / "logs" / "leaked.log").write_text("OPENAI_API_KEY='sk-ignored123456789012345'\n", encoding="utf-8")
            (root / "tmp" / "token.txt").write_text("token='ignored-secret-value-1234567890'\n", encoding="utf-8")

            report = scan_secrets(root)

            self.assertFalse(any("logs" in str(finding.path) or "tmp" in str(finding.path) for finding in report.findings))

    def test_toolhubignore_excludes_directories_and_files(self) -> None:
        with workspace_tempdir() as temp:
            root = Path(temp)
            repo = root / "repo"
            (repo / "apps").mkdir(parents=True)
            (repo / "release").mkdir()
            (repo / "runner").mkdir()
            source = root / "source"
            source.mkdir()
            entry = source / "main.py"
            entry.write_text("print('ok')\n", encoding="utf-8")
            (source / ".toolhubignore").write_text("# local ignore\nscratch/\n*.bak\n", encoding="utf-8-sig")
            (source / "scratch").mkdir()
            (source / "scratch" / "ignored.json").write_text('{"secret": "value"}\n', encoding="utf-8")
            (source / "notes.bak").write_text("do not package\n", encoding="utf-8")

            context = create_context(ImportOptions(entry=entry, action="suggest", app_id="ignore_app", name="Ignore App"), repo)
            inventory = classify_files(context)
            records = {record.relative_path: record for record in inventory.records}
            excluded_dirs = {item["relative_path"] for item in inventory.excluded_directories}

            self.assertIn("scratch", excluded_dirs)
            self.assertEqual(records["notes.bak"].status, "exclude")
            self.assertIn(".toolhubignore", records["notes.bak"].reason)
            self.assertEqual(inventory.toolhubignore_patterns, ["scratch", "*.bak"])

    def test_auth_directory_without_toolhubignore_blocks_apply_by_inventory(self) -> None:
        with workspace_tempdir() as temp:
            root = Path(temp)
            repo = root / "repo"
            (repo / "apps").mkdir(parents=True)
            (repo / "release").mkdir()
            (repo / "runner").mkdir()
            source = root / "source"
            flows = source / "xcgate_flows"
            (flows / ".auth").mkdir(parents=True)
            entry = source / "run_xcgate_upload.py"
            entry.write_text("print('ok')\n", encoding="utf-8")
            (flows / ".auth" / "mega_state.json").write_text('{"cookies": [{"value": "real-session"}]}\n', encoding="utf-8")

            context = create_context(ImportOptions(entry=entry, action="suggest", app_id="auth_block", name="Auth Block"), repo)
            inventory = classify_files(context)
            report = scan_secrets(context.source_root, inventory)
            records = {record.relative_path: record for record in inventory.records}
            finding = next(finding for finding in report.findings if finding.path.name == "mega_state.json")

            self.assertEqual(records["xcgate_flows/.auth/mega_state.json"].status, "blocked")
            self.assertTrue(report.blocks_apply)
            self.assertTrue(finding.blocks_apply)
            self.assertIn(".toolhubignore", finding.recommended_action)
            self.assertIn(".auth/", toolhubignore_suggestion_markdown(inventory))

    def test_toolhubignore_excluded_auth_state_skips_secret_scan_build_profile_and_app_pack(self) -> None:
        with workspace_tempdir() as temp:
            root = Path(temp)
            repo = root / "repo"
            (repo / "apps").mkdir(parents=True)
            (repo / "release").mkdir()
            (repo / "runner").mkdir()
            source = root / "source"
            flows = source / "xcgate_flows"
            (flows / ".auth").mkdir(parents=True)
            (flows / "flows").mkdir(parents=True)
            (flows / "src").mkdir()
            entry = source / "run_xcgate_upload.py"
            entry.write_text("import xcgate_flows.src.worker\n", encoding="utf-8")
            (source / ".toolhubignore").write_text(".auth/\nstorage_state.json\n", encoding="utf-8")
            (source / "storage_state.json").write_text('{"cookies": [{"value": "real-session"}]}\n', encoding="utf-8")
            (flows / ".auth" / "mega_state.json").write_text('{"cookies": [{"value": "real-session"}]}\n', encoding="utf-8")
            (flows / "flows" / "upload.flow").write_text("goto https://example.com\n", encoding="utf-8")
            (flows / "src" / "__init__.py").write_text("", encoding="utf-8")
            (flows / "src" / "worker.py").write_text("print('worker')\n", encoding="utf-8")

            context = create_context(ImportOptions(entry=entry, action="suggest", app_id="auth_ignore", name="Auth Ignore"), repo)
            inventory = classify_files(context)
            records = {record.relative_path: record for record in inventory.records}
            report = scan_secrets(context.source_root, inventory)
            dependency_report, _ = analyze_dependencies(context, inventory)
            profile = default_build_profile(context, inventory, dependency_report)

            self.assertFalse(any(record.relative_path.endswith(".auth/mega_state.json") for record in inventory.records))
            self.assertEqual(records["storage_state.json"].status, "exclude")
            self.assertEqual(records["storage_state.json"].category, "sensitive_runtime_state")
            self.assertFalse(report.blocks_apply)
            self.assertFalse(any("mega_state.json" in str(finding.path) or "storage_state.json" in str(finding.path) for finding in report.findings))
            self.assertEqual([item["relative_path"] for item in inventory.sensitive_excluded_directories], ["xcgate_flows/.auth"])
            self.assertEqual([item["relative_path"] for item in inventory.sensitive_excluded_files], ["storage_state.json"])
            self.assertIn("Sensitive Runtime State Excluded", inventory_markdown(inventory))
            self.assertIn("Already Explicitly Excluded", toolhubignore_suggestion_markdown(inventory))
            profile_payload = "\n".join(
                [
                    *profile["paths"],
                    *profile["hidden_imports"],
                    *(item["source"] for item in profile["add_data"]),
                ]
            )
            self.assertNotIn(".auth", profile_payload)
            self.assertNotIn("storage_state.json", profile_payload)

            final_app = root / "final_app"
            (final_app / "bin" / "auth_ignore").mkdir(parents=True)
            (final_app / "bin" / "auth_ignore" / "auth_ignore.exe").write_bytes(b"fake exe")
            (final_app / "app.yaml").write_text(
                "\n".join(
                    [
                        "id: auth_ignore",
                        "display:",
                        "  name: Auth Ignore",
                        "  icon: icon.png",
                        "run:",
                        "  runner: exe",
                        "  entry: bin/auth_ignore/auth_ignore.exe",
                        "runtime:",
                        "  required_runtime: null",
                        "admin:",
                        "  version: 0.1.0",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            (final_app / "README.md").write_text("# Auth Ignore\n", encoding="utf-8")
            (final_app / "requirements.txt").write_text("", encoding="utf-8")
            (final_app / "icon.png").write_bytes(b"\x89PNG\r\n\x1a\nfake")
            breakdown: list[dict[str, object]] = []
            output_dir = root / "output"
            package_path = apply_registration(
                context,
                BuildPlan(mode="frozen-folder", runner="exe", entry="bin/auth_ignore/auth_ignore.exe", required_runtime=None, reasons=[]),
                final_app,
                output_dir,
                breakdown=breakdown,
            )

            with zipfile.ZipFile(package_path) as archive:
                names = archive.namelist()
            self.assertFalse(any(".auth/" in name or "mega_state.json" in name or "storage_state.json" in name for name in names))
            self.assertTrue((output_dir / "registration_copy_report.md").is_file())
            report = json.loads((output_dir / "registration_copy_breakdown.json").read_text(encoding="utf-8"))
            step_names = {record["name"] for record in report["records"]}
            self.assertIn("copy_final_app_to_apps", step_names)
            self.assertIn("compress_app_pack", step_names)
            self.assertIn("sha256_app_pack", step_names)
            self.assertIn("copy_pack_to_output_mirror", step_names)
            self.assertEqual(report["safety"]["required_entry_inspection_skipped"], False)
            self.assertEqual(report["strategies"]["app_pack"]["selected_policy"], "balanced_size_speed")
            self.assertEqual(report["strategies"]["app_pack"]["compression"], "ZIP_DEFLATED")
            self.assertEqual(report["strategies"]["app_pack"]["compresslevel"], 1)
            compress_record = next(record for record in report["records"] if record["name"] == "compress_app_pack")
            self.assertEqual(compress_record["compression_policy"], "balanced_size_speed")
            self.assertEqual(compress_record["compression"], "ZIP_DEFLATED")
            self.assertEqual(compress_record["compresslevel"], 1)
            self.assertEqual(compress_record["entry_count"], len(names))

    def test_excluded_files_do_not_enter_build_profile(self) -> None:
        with workspace_tempdir() as temp:
            root = Path(temp)
            repo = root / "repo"
            (repo / "apps").mkdir(parents=True)
            (repo / "release").mkdir()
            (repo / "runner").mkdir()
            source = root / "source"
            (source / "src").mkdir(parents=True)
            (source / "assets").mkdir()
            (source / "work" / "assets").mkdir(parents=True)
            entry = source / "main.py"
            entry.write_text("import src.worker\n", encoding="utf-8")
            (source / "src" / "__init__.py").write_text("", encoding="utf-8")
            (source / "src" / "worker.py").write_text("print('worker')\n", encoding="utf-8")
            (source / "assets" / "keep.json").write_text("{}\n", encoding="utf-8")
            (source / "work" / "module.py").write_text("print('ignore')\n", encoding="utf-8")
            (source / "work" / "assets" / "ignore.json").write_text("{}\n", encoding="utf-8")

            context = create_context(ImportOptions(entry=entry, action="suggest", app_id="profile_app", name="Profile App"), repo)
            inventory = classify_files(context)
            dependency_report, _ = analyze_dependencies(context, inventory)
            profile = default_build_profile(context, inventory, dependency_report)
            self.assertFalse(any(value == "work" or value.startswith("work/") for value in profile["paths"]))
            self.assertFalse(any(value == "work.module" or value.startswith("work.") for value in profile["hidden_imports"]))
            self.assertFalse(any(item["source"].startswith("work/") for item in profile["add_data"]))
            self.assertIn("src", profile["paths"])
            self.assertIn("assets/keep.json", [item["source"] for item in profile["add_data"]])

    def test_pyinstaller_playwright_collect_failure_is_classified(self) -> None:
        output = "\n".join(
            [
                "INFO: Building COLLECT COLLECT-00.toc",
                "FileNotFoundError: [Errno 2] No such file or directory: '...playwright\\\\driver\\\\package\\\\lib\\\\tools\\\\cli-client\\\\skill\\\\references\\\\element-attributes.md'",
            ]
        )

        hints = classify_pyinstaller_failure(
            output,
            "",
            [["python", "-m", "PyInstaller", "--collect-all", "playwright", "main.py"]],
        )

        self.assertIn("category: pyinstaller_collect_all_data_copy_failure", hints)
        self.assertIn("source_scope_related: false", hints)

    def test_pyinstaller_long_path_playwright_collect_failure_is_classified(self) -> None:
        missing = "C:\\" + ("very_long_segment\\" * 18) + "playwright\\driver\\package\\lib\\tools\\cli-client\\skill\\references\\element-attributes.md"
        output = "\n".join(
            [
                "INFO: Building COLLECT COLLECT-00.toc",
                f"FileNotFoundError: [Errno 2] No such file or directory: '{missing}'",
            ]
        )

        hints = classify_pyinstaller_failure(
            output,
            "",
            [["python", "-m", "PyInstaller", "--collect-all", "playwright", "main.py"]],
        )

        self.assertIn("category: pyinstaller_windows_long_path_collect_failure", hints)
        self.assertIn("source_scope_related: false", hints)

    def test_pyinstaller_artifact_paths_use_short_directory_names(self) -> None:
        output_dir = Path("C:/tmp/source/ToolHub_AppStudio_Output/run_xcgate_upload_phase1b_check")

        artifacts, dist, work, spec = pyinstaller_artifact_paths(output_dir)

        self.assertEqual(artifacts.as_posix(), "C:/tmp/source/ToolHub_AppStudio_Output/run_xcgate_upload_phase1b_check/bt/pyi")
        self.assertEqual(dist.name, "d")
        self.assertEqual(work.name, "b")
        self.assertEqual(spec.name, "s")

    def test_existing_app_backup_moves_app_directory(self) -> None:
        with workspace_tempdir() as temp:
            repo = Path(temp)
            app_id = "playwright_app"
            app_dir = repo / "apps" / app_id
            deep_file = (
                app_dir
                / "bin"
                / app_id
                / "playwright"
                / "driver"
                / "package"
                / "lib"
                / "tools"
                / "cli-client"
                / "skill"
                / "references"
                / "element-attributes.md"
            )
            deep_file.parent.mkdir(parents=True)
            deep_file.write_text("# attributes\n", encoding="utf-8")
            (repo / "release").mkdir()
            (repo / "release" / "app_manifest.json").write_text(
                '{"schema_version": 1, "apps": {"playwright_app": {"version": "0.1.0"}}}\n',
                encoding="utf-8",
            )

            backup = backup_existing(repo, app_id)

            self.assertIsNotNone(backup)
            assert backup is not None
            self.assertTrue((backup / "app").is_dir())
            self.assertFalse((backup / "app.zip").exists())
            self.assertFalse(app_dir.exists())
            self.assertTrue((backup / "app_manifest.json").is_file())
            self.assertTrue(
                (
                    backup
                    / "app"
                    / "bin"
                    / app_id
                    / "playwright"
                    / "driver"
                    / "package"
                    / "lib"
                    / "tools"
                    / "cli-client"
                    / "skill"
                    / "references"
                    / "element-attributes.md"
                ).is_file()
            )

    def test_metadata_override_invalid_json_fails_clearly(self) -> None:
        with workspace_tempdir() as temp:
            path = Path(temp) / "override.json"
            path.write_text("{invalid", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "metadata override JSON is invalid"):
                load_metadata_override(path)

    def test_icon_override_adopts_png(self) -> None:
        png = "data:image/png;base64,iVBORw0KGgo="
        final_png, source, warnings = apply_icon_override(
            b"\x89PNG\r\n\x1a\ndefault",
            {"selected_icon_source": "candidate_png", "png_base64": png},
        )

        self.assertEqual(source, "candidate_png")
        self.assertEqual(warnings, [])
        self.assertTrue(final_png.startswith(b"\x89PNG\r\n\x1a\n"))

    def test_icon_override_legacy_fallback_uses_default_icon(self) -> None:
        default_png = b"\x89PNG\r\n\x1a\ndefault"
        final_png, source, warnings = apply_icon_override(
            default_png,
            {"selected_icon_source": "fallback_png"},
        )

        self.assertEqual(final_png, default_png)
        self.assertEqual(source, "default_icon")
        self.assertTrue(warnings)

    def test_icon_override_invalid_json_fails_clearly(self) -> None:
        with workspace_tempdir() as temp:
            path = Path(temp) / "icon_override.json"
            path.write_text("{invalid", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "icon override JSON is invalid"):
                load_icon_override(path)


if __name__ == "__main__":
    unittest.main()
