from __future__ import annotations

from contextlib import contextmanager
import json
import shutil
import unittest
import uuid
from pathlib import Path
import sys
import types
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools" / "app_studio"))
sys.path.insert(0, str(ROOT / "runner"))

from app_studio.ai_metadata_suggester import suggest_metadata
from app_studio.app_env_builder import create_app_env
from app_studio.approval import approve_app
from app_studio.build_planner import make_build_plan
from app_studio.execution_tester import build_execution_result, run_execution_checks
from app_studio.exporter import export_suggestion
from app_studio.frozen_folder_builder import build_report as frozen_build_report
from app_studio.frozen_folder_builder import detect_pyinstaller_environment_issue, pyinstaller_command
from app_studio.lock_generator import generate_lock
from app_studio.models import BuildPlan, DependencyReport, GeneratedArtifacts, ImportOptions, SecretFinding, SecretScanReport, SourceInventory
from app_studio.openai_client import generate_image
from app_studio.runtime_checker import verify_runtime
from app_studio.scanner import create_context
from app_studio.util import write_json, write_text


@contextmanager
def workspace_tempdir():
    base = ROOT / "data" / "tmp_tests"
    base.mkdir(parents=True, exist_ok=True)
    path = base / f"case_{uuid.uuid4().hex}"
    path.mkdir(parents=True, exist_ok=False)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def make_repo(root: Path) -> Path:
    repo = root / "repo"
    for name in ["apps", "release", "runner", "runtime/app_envs", "runtime/python", "data/logs/app_studio"]:
        (repo / name).mkdir(parents=True, exist_ok=True)
    write_json(repo / "release" / "app_manifest.json", {"schema_version": 1, "channel": "stable", "apps": {}})
    return repo


def make_context(root: Path, app_id: str = "demo_app"):
    repo = make_repo(root)
    source = root / "source"
    source.mkdir()
    entry = source / "main.py"
    entry.write_text("print('hello')\n", encoding="utf-8")
    context = create_context(ImportOptions(entry=entry, action="apply", app_id=app_id, name="Demo App"), repo)
    context.output_dir.mkdir(parents=True, exist_ok=True)
    return context


def write_minimal_registered_app(repo: Path, app_id: str, enabled: bool = False) -> None:
    app_dir = repo / "apps" / app_id
    app_dir.mkdir(parents=True, exist_ok=True)
    write_text(
        app_dir / "app.yaml",
        f"""id: {app_id}
name: Demo App
display:
  icon: icon.svg
  short_description: demo
  categories:
    - demo
detail:
  description: demo
run:
  runner: cli
  entry: main.py
  mode: cli
admin:
  version: 0.1.0
  owner: admin
  requirements: requirements.txt
  log_dir: logs
""",
    )
    write_text(app_dir / "README.md", "# Demo\n")
    write_text(app_dir / "requirements.txt", "")
    write_text(app_dir / "icon.svg", "<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 64 64\"/>")
    write_text(app_dir / "main.py", "print('ok')\n")
    write_json(
        repo / "release" / "app_manifest.json",
        {
            "schema_version": 1,
            "channel": "stable",
            "apps": {
                app_id: {
                    "version": "0.1.0",
                    "package": f"app_packs/{app_id}-0.1.0.zip",
                    "sha256": "",
                    "required_core": ">=0.1.0",
                    "required_runner": ">=0.1.0",
                    "required_runtime": None,
                    "enabled": enabled,
                }
            },
        },
    )


def write_execution_result(repo: Path, app_id: str, status: str, approval_allowed: bool) -> None:
    write_json(
        repo / "data" / "logs" / "app_studio" / f"{app_id}_execution_test_result.json",
        {
            "app_id": app_id,
            "generated_at": "2026-01-01T00:00:00",
            "overall_status": status,
            "approval_allowed": approval_allowed,
            "checks": [{"name": status, "status": status, "detail": "test"}],
        },
    )


class AppEnvBuilderTests(unittest.TestCase):
    def test_app_env_uses_development_python_when_runtime_missing(self) -> None:
        with workspace_tempdir() as root:
            context = make_context(root)
            requirements = context.source_root / "requirements.txt"
            requirements.write_text("", encoding="utf-8")

            result = create_app_env(context, requirements)

            self.assertTrue(result.ok)
            self.assertEqual(result.python_source, "development_python_fallback")
            self.assertIn("development_python_fallback", result.report)

    def test_rebuild_false_keeps_existing_app_env(self) -> None:
        with workspace_tempdir() as root:
            context = make_context(root)
            existing = context.repo_root / "runtime" / "app_envs" / context.app_id
            (existing / "Scripts").mkdir(parents=True)
            marker = existing / "marker.txt"
            marker.write_text("keep", encoding="utf-8")

            result = create_app_env(context, context.source_root / "requirements.txt", rebuild=False)

            self.assertTrue(result.ok)
            self.assertTrue(result.skipped)
            self.assertTrue(marker.exists())

    def test_rebuild_true_creates_backup(self) -> None:
        with workspace_tempdir() as root:
            context = make_context(root)
            existing = context.repo_root / "runtime" / "app_envs" / context.app_id
            existing.mkdir(parents=True)
            (existing / "marker.txt").write_text("old", encoding="utf-8")

            result = create_app_env(context, context.source_root / "requirements.txt", rebuild=True)

            self.assertTrue(result.ok)
            backups = list((context.repo_root / "backups" / "app_studio").glob(f"*/{context.app_id}/app_env"))
            self.assertTrue(backups)


class LockGeneratorTests(unittest.TestCase):
    def test_existing_requirements_lock_is_copied_first(self) -> None:
        with workspace_tempdir() as root:
            context = make_context(root)
            (context.source_root / "requirements.lock").write_text("requests==2.0.0\n", encoding="utf-8")
            final = context.output_dir / "final_app"
            final.mkdir()
            requirements = final / "requirements.txt"
            requirements.write_text("requests\n", encoding="utf-8")

            result = generate_lock(context, requirements)

            self.assertTrue(result.ok)
            self.assertEqual((final / "requirements.lock").read_text(encoding="utf-8"), "requests==2.0.0\n")
            self.assertEqual(result.source, "existing requirements.lock")

    def test_requirements_txt_generates_lock_report(self) -> None:
        with workspace_tempdir() as root:
            context = make_context(root)
            final = context.output_dir / "final_app"
            final.mkdir()
            requirements = final / "requirements.txt"
            requirements.write_text("requests==2.0.0\n", encoding="utf-8")

            result = generate_lock(context, requirements)

            self.assertTrue(result.ok)
            self.assertIn("requirements.txt normalization", result.report)
            self.assertTrue((context.output_dir / "lock_generation_report.md").is_file())

    def test_skip_lock_does_not_create_lock(self) -> None:
        with workspace_tempdir() as root:
            context = make_context(root)
            final = context.output_dir / "final_app"
            final.mkdir()
            requirements = final / "requirements.txt"
            requirements.write_text("requests==2.0.0\n", encoding="utf-8")

            result = generate_lock(context, requirements, skip=True)

            self.assertTrue(result.skipped)
            self.assertFalse((final / "requirements.lock").exists())


class FrozenFolderTests(unittest.TestCase):
    def test_pyinstaller_command_uses_onedir_not_onefile(self) -> None:
        with workspace_tempdir() as root:
            context = make_context(root)
            command = pyinstaller_command(Path("python"), context, Path("dist"), Path("build"), Path("spec"))

            self.assertIn("--onedir", command)
            self.assertNotIn("--onefile", command)

    def test_frozen_plan_entry_matches_folder_exe_layout(self) -> None:
        with workspace_tempdir() as root:
            context = make_context(root)
            context.requested_build_mode = "frozen-folder"
            plan = make_build_plan(context, inventory=type("I", (), {"included_files": [context.entry], "import_roots": []})())

            self.assertEqual(plan.entry, f"bin/{context.app_id}/{context.app_id}.exe")

    def test_missing_frozen_exe_blocks_approval(self) -> None:
        with workspace_tempdir() as root:
            context = make_context(root)
            app_dir = context.repo_root / "apps" / context.app_id
            app_dir.mkdir(parents=True)
            write_text(app_dir / "app.yaml", "id: demo_app\nname: Demo\nrun:\n  runner: exe\n  entry: bin/demo_app/demo_app.exe\n  mode: gui\ndisplay:\n  icon: icon.svg\n  short_description: demo\n  categories:\n    - demo\ndetail:\n  description: demo\n")
            plan = BuildPlan("frozen-folder", "exe", "bin/demo_app/demo_app.exe", None, [])

            result = run_execution_checks(context, plan, context.output_dir)

            self.assertEqual(result.overall_status, "fail")
            self.assertFalse(result.approval_allowed)

    def test_pathlib_backport_issue_is_reported_without_uninstall(self) -> None:
        with workspace_tempdir() as root:
            context = make_context(root)
            plan = BuildPlan("frozen-folder", "exe", "bin/demo_app/demo_app.exe", None, [])
            stderr = "The 'pathlib' package is an obsolete backport of a standard library package. python -m pip uninstall pathlib"

            hints = detect_pyinstaller_environment_issue("", stderr)
            report = frozen_build_report(context, plan, [["python", "-m", "PyInstaller", "--version"]], "probe failed", None, "", stderr)

            self.assertTrue(hints)
            self.assertIn("obsolete pathlib backport", report)
            self.assertIn("did not uninstall", report)


class ExecutionAndApprovalTests(unittest.TestCase):
    def test_app_yaml_parse_fail_blocks_approval(self) -> None:
        with workspace_tempdir() as root:
            context = make_context(root)
            app_dir = context.repo_root / "apps" / context.app_id
            app_dir.mkdir(parents=True)
            write_text(app_dir / "app.yaml", "not: enough\n")
            plan = BuildPlan("app-env", "python_app_env", "src/main.py", "python-embedded-toolhub-001", [])

            result = build_execution_result(context, plan)

            self.assertEqual(result.overall_status, "fail")
            self.assertFalse(result.approval_allowed)

    def test_warn_result_can_be_approved_when_warnings_allowed(self) -> None:
        with workspace_tempdir() as root:
            repo = make_repo(root)
            app_id = "demo_app"
            write_minimal_registered_app(repo, app_id)
            write_execution_result(repo, app_id, "warn", True)

            approve_app(repo, app_id, strict=False, allow_warnings=True)
            manifest = json.loads((repo / "release" / "app_manifest.json").read_text(encoding="utf-8"))

            self.assertTrue(manifest["apps"][app_id]["enabled"])

    def test_strict_approval_rejects_warning(self) -> None:
        with workspace_tempdir() as root:
            repo = make_repo(root)
            app_id = "demo_app"
            write_minimal_registered_app(repo, app_id)
            write_execution_result(repo, app_id, "warn", True)

            with self.assertRaises(Exception):
                approve_app(repo, app_id, strict=True, allow_warnings=False)
            manifest = json.loads((repo / "release" / "app_manifest.json").read_text(encoding="utf-8"))
            self.assertFalse(manifest["apps"][app_id]["enabled"])

    def test_fail_result_does_not_enable_app(self) -> None:
        with workspace_tempdir() as root:
            repo = make_repo(root)
            app_id = "demo_app"
            write_minimal_registered_app(repo, app_id)
            write_execution_result(repo, app_id, "fail", False)

            with self.assertRaises(Exception):
                approve_app(repo, app_id)
            manifest = json.loads((repo / "release" / "app_manifest.json").read_text(encoding="utf-8"))
            self.assertFalse(manifest["apps"][app_id]["enabled"])


class OpenAIFallbackTests(unittest.TestCase):
    def test_api_key_missing_uses_fallback(self) -> None:
        with workspace_tempdir() as root:
            context = make_context(root)
            with patch.dict("os.environ", {"TOOLHUB_APP_STUDIO_AI_ENABLED": "true"}, clear=True):
                metadata = suggest_metadata(context)

            self.assertIn("_ai_generation_report", metadata)
            self.assertIn("OPENAI_API_KEY", metadata["_ai_generation_report"])

    def test_ai_disabled_does_not_call_api(self) -> None:
        with workspace_tempdir() as root:
            context = make_context(root)
            with patch.dict("os.environ", {"TOOLHUB_APP_STUDIO_AI_ENABLED": "false"}, clear=True):
                metadata = suggest_metadata(context)

            self.assertIn("AI is disabled", metadata["_ai_generation_report"])

    def test_text_model_missing_uses_metadata_fallback(self) -> None:
        with workspace_tempdir() as root:
            context = make_context(root)
            with patch.dict("os.environ", {"TOOLHUB_APP_STUDIO_AI_ENABLED": "true", "OPENAI_API_KEY": "sk-test1234abcd"}, clear=True):
                metadata = suggest_metadata(context)

            self.assertIn("model is not configured", metadata["_ai_generation_report"])

    def test_high_secret_skips_ai(self) -> None:
        with workspace_tempdir() as root:
            context = make_context(root)
            report = SecretScanReport([SecretFinding(context.entry, "content", "high", "OPENAI_API_KEY")])

            metadata = suggest_metadata(context, report)

            self.assertIn("high severity secret", metadata["_ai_generation_report"])

    def test_responses_api_success_parses_metadata_json(self) -> None:
        with workspace_tempdir() as root:
            context = make_context(root)
            payload = {
                "short_description": "AI short",
                "description": "AI long",
                "categories": ["AI"],
                "use_cases": ["Use"],
                "inputs": ["Input"],
                "outputs": ["Output"],
                "notes": ["Note"],
                "keywords": ["ai"],
                "examples": ["example"],
            }

            class Responses:
                def create(self, **kwargs):
                    self.kwargs = kwargs
                    return types.SimpleNamespace(output_text=json.dumps(payload))

            responses = Responses()
            client = types.SimpleNamespace(responses=responses)
            with patch.dict("os.environ", {"TOOLHUB_APP_STUDIO_AI_ENABLED": "true", "TOOLHUB_APP_STUDIO_TEXT_MODEL": "text-model", "OPENAI_API_KEY": "sk-test1234abcd"}, clear=True):
                with patch.dict(sys.modules, {"openai": types.SimpleNamespace(OpenAI=lambda: client)}):
                    metadata = suggest_metadata(context)

            self.assertEqual(metadata["short_description"], "AI short")
            self.assertEqual(responses.kwargs["model"], "text-model")
            self.assertIn("api: responses.create", metadata["_ai_generation_report"])
            self.assertIn("status: success", metadata["_ai_generation_report"])
            self.assertIn("parse_status: success", metadata["_ai_generation_report"])

    def test_responses_api_invalid_json_falls_back_with_parse_reason(self) -> None:
        with workspace_tempdir() as root:
            context = make_context(root)
            client = types.SimpleNamespace(responses=types.SimpleNamespace(create=lambda **_: types.SimpleNamespace(output_text="not json")))
            with patch.dict("os.environ", {"TOOLHUB_APP_STUDIO_AI_ENABLED": "true", "TOOLHUB_APP_STUDIO_TEXT_MODEL": "text-model", "OPENAI_API_KEY": "sk-test1234abcd"}, clear=True):
                with patch.dict(sys.modules, {"openai": types.SimpleNamespace(OpenAI=lambda: client)}):
                    metadata = suggest_metadata(context)

            self.assertNotEqual(metadata["short_description"], "not json")
            self.assertIn("parse_status: failed", metadata["_ai_generation_report"])

    def test_images_generate_accepts_b64_without_response_format(self) -> None:
        calls = []

        class Images:
            def generate(self, **kwargs):
                calls.append(kwargs)
                return types.SimpleNamespace(data=[types.SimpleNamespace(b64_json="iVBORw0KGgo=")])

        client = types.SimpleNamespace(images=Images())
        with patch.dict("os.environ", {"TOOLHUB_APP_STUDIO_AI_ENABLED": "true", "TOOLHUB_APP_STUDIO_IMAGE_MODEL": "gpt-image-2", "OPENAI_API_KEY": "sk-test1234abcd"}, clear=True):
            with patch.dict(sys.modules, {"openai": types.SimpleNamespace(OpenAI=lambda: client)}):
                result = generate_image("prompt")

        self.assertTrue(result.ok)
        self.assertEqual(result.content_type, "b64_png")
        self.assertNotIn("response_format", calls[0])

    def test_images_generate_accepts_url_candidate(self) -> None:
        client = types.SimpleNamespace(images=types.SimpleNamespace(generate=lambda **_: types.SimpleNamespace(data=[types.SimpleNamespace(url="https://example.com/icon.png")])))
        with patch.dict("os.environ", {"TOOLHUB_APP_STUDIO_AI_ENABLED": "true", "TOOLHUB_APP_STUDIO_IMAGE_MODEL": "gpt-image-2", "OPENAI_API_KEY": "sk-test1234abcd"}, clear=True):
            with patch.dict(sys.modules, {"openai": types.SimpleNamespace(OpenAI=lambda: client)}):
                result = generate_image("prompt")

        self.assertTrue(result.ok)
        self.assertEqual(result.content_type, "url")
        self.assertEqual(result.content, "https://example.com/icon.png")

    def test_images_generate_retries_without_optional_parameters(self) -> None:
        calls = []

        class Images:
            def generate(self, **kwargs):
                calls.append(kwargs)
                if len(calls) == 1:
                    raise TypeError("Unknown parameter: output_format")
                return types.SimpleNamespace(data=[types.SimpleNamespace(b64_json="iVBORw0KGgo=")])

        client = types.SimpleNamespace(images=Images())
        with patch.dict("os.environ", {"TOOLHUB_APP_STUDIO_AI_ENABLED": "true", "TOOLHUB_APP_STUDIO_IMAGE_MODEL": "gpt-image-2", "OPENAI_API_KEY": "sk-test1234abcd"}, clear=True):
            with patch.dict(sys.modules, {"openai": types.SimpleNamespace(OpenAI=lambda: client)}):
                result = generate_image("prompt")

        self.assertTrue(result.ok)
        self.assertIn("output_format", calls[0])
        self.assertNotIn("output_format", calls[1])
        self.assertNotIn("quality", calls[1])
        self.assertNotIn("response_format", calls[0])
        self.assertNotIn("response_format", calls[1])

    def test_images_generate_failure_reports_fallback_reason(self) -> None:
        client = types.SimpleNamespace(images=types.SimpleNamespace(generate=lambda **_: (_ for _ in ()).throw(RuntimeError("BadRequestError: broken"))))
        with patch.dict("os.environ", {"TOOLHUB_APP_STUDIO_AI_ENABLED": "true", "TOOLHUB_APP_STUDIO_IMAGE_MODEL": "gpt-image-2", "OPENAI_API_KEY": "sk-test1234abcd"}, clear=True):
            with patch.dict(sys.modules, {"openai": types.SimpleNamespace(OpenAI=lambda: client)}):
                result = generate_image("prompt")

        self.assertFalse(result.ok)
        self.assertEqual(result.status, "failed")
        self.assertIn("fallback_reason: Image API failed", result.report)

    def test_empty_image_model_uses_image_fallback(self) -> None:
        with patch.dict("os.environ", {"TOOLHUB_APP_STUDIO_AI_ENABLED": "true", "TOOLHUB_APP_STUDIO_IMAGE_MODEL": "", "OPENAI_API_KEY": "sk-test1234abcd"}, clear=True):
            result = generate_image("prompt")

        self.assertFalse(result.ok)
        self.assertIn("model is not configured", result.report)


class IconCandidateExportTests(unittest.TestCase):
    def test_png_candidate_is_saved(self) -> None:
        with workspace_tempdir() as root:
            context = make_context(root)
            artifacts = minimal_artifacts(context, icon_candidate_png=b"\x89PNG\r\n\x1a\n")

            output = export_suggestion(context, SourceInventory([]), DependencyReport("test", [], [], []), SecretScanReport([]), BuildPlan("app-env", "python_app_env", "src/main.py", None, []), artifacts)

            self.assertTrue((output / "icon_work" / "icon_candidate_1.png").is_file())
            self.assertTrue((output / "icon_work" / "icon_final.png").is_file())
            self.assertTrue((output / "final_app" / "icon.png").is_file())
            self.assertTrue((output / "final_app" / "icon.svg").is_file())

    def test_url_candidate_is_saved(self) -> None:
        with workspace_tempdir() as root:
            context = make_context(root)
            artifacts = minimal_artifacts(context, icon_candidate_url="https://example.com/icon.png")

            output = export_suggestion(context, SourceInventory([]), DependencyReport("test", [], [], []), SecretScanReport([]), BuildPlan("app-env", "python_app_env", "src/main.py", None, []), artifacts)

            self.assertEqual((output / "icon_work" / "icon_candidate_1.url.txt").read_text(encoding="utf-8").strip(), "https://example.com/icon.png")
            self.assertTrue((output / "icon_work" / "icon_final.png").is_file())

    def test_api_failure_still_leaves_final_svg(self) -> None:
        with workspace_tempdir() as root:
            context = make_context(root)
            artifacts = minimal_artifacts(context)

            output = export_suggestion(context, SourceInventory([]), DependencyReport("test", [], [], []), SecretScanReport([]), BuildPlan("app-env", "python_app_env", "src/main.py", None, []), artifacts)

            self.assertTrue((output / "icon_work" / "icon_final.png").is_file())
            self.assertTrue((output / "icon_work" / "icon_fallback.svg").is_file())


class RuntimeCheckerTests(unittest.TestCase):
    def test_missing_runtime_records_fail(self) -> None:
        with workspace_tempdir() as root:
            context = make_context(root)

            result = verify_runtime(context, context.output_dir)

            self.assertIn(result.overall_status, {"warn", "fail"})
            self.assertTrue((context.output_dir / "runtime_check_report.md").is_file())
            self.assertTrue((context.output_dir / "runtime_check_result.json").is_file())
            self.assertTrue((context.repo_root / "data" / "logs" / "app_studio" / "demo_app_runtime_check_result.json").is_file())

    def test_app_env_python_checks_pass_when_present(self) -> None:
        with workspace_tempdir() as root:
            context = make_context(root)
            app_env_python = context.repo_root / "runtime" / "app_envs" / context.app_id / "Scripts" / "python.exe"
            app_env_python.parent.mkdir(parents=True, exist_ok=True)
            app_env_python.write_bytes(b"fake")

            with patch("app_studio.runtime_checker.subprocess.run") as run:
                run.return_value = type("Completed", (), {"returncode": 0, "stdout": "Python 3.13", "stderr": ""})()
                result = verify_runtime(context, context.output_dir)

            checks = {check.name: check.status for check in result.checks}
            self.assertEqual(checks["app_env python exists"], "pass")
            self.assertEqual(checks["app_env python --version"], "pass")


class DocsTests(unittest.TestCase):
    def test_old_pyinstaller_mvp_statement_was_removed(self) -> None:
        text = (ROOT / "docs" / "13_app_studio.md").read_text(encoding="utf-8")
        self.assertNotIn("MVP では実際の PyInstaller 実行は行わず", text)


def minimal_artifacts(context, icon_candidate_png: bytes | None = None, icon_candidate_url: str = "") -> GeneratedArtifacts:
    return GeneratedArtifacts(
        metadata={},
        app_yaml="id: demo_app\nname: Demo\n",
        readme="# Demo\n",
        requirements="",
        icon_prompt_initial="initial",
        icon_prompt_revision="revision",
        icon_svg="<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 64 64\"/>",
        build_plan_md="# Build\n",
        import_plan={"app_id": context.app_id},
        icon_ai_report="report",
        icon_final_png=b"\x89PNG\r\n\x1a\n",
        icon_candidate_png=icon_candidate_png,
        icon_candidate_url=icon_candidate_url,
    )


if __name__ == "__main__":
    unittest.main()
