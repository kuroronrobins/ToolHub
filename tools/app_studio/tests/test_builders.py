from __future__ import annotations

from contextlib import contextmanager
import json
import os
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

from app_studio.ai_metadata_suggester import metadata_prompt, suggest_metadata
from app_studio.build_profile import analyze_exe_readiness, default_build_profile
from app_studio.icon_generator import image_api_prompt
from app_studio.app_env_builder import create_app_env, create_build_env
from app_studio.approval import approve_app, validate_approval_inputs
from app_studio.build_planner import make_build_plan
from app_studio.execution_tester import build_execution_result, record_blocked_execution, run_execution_checks
from app_studio.exporter import export_suggestion
from app_studio.frozen_folder_builder import build_report as frozen_build_report
from app_studio.frozen_folder_builder import detect_pyinstaller_environment_issue, pyinstaller_command
from app_studio.frozen_folder_builder import probe_pyinstaller
from app_studio.lock_generator import generate_lock
from app_studio.models import BuildPlan, DependencyReport, FileRecord, GeneratedArtifacts, ImportOptions, SecretFinding, SecretScanReport, SourceInventory
from app_studio.models import AppEnvBuildResult, LockGenerationResult
from app_studio.openai_client import generate_image
from app_studio.runtime_checker import verify_runtime
from app_studio.scanner import create_context
from app_studio.util import write_json, write_text
from main import parse_args as parse_app_studio_args, run_import


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

    def test_build_env_is_created_under_output_dir_not_runtime_app_envs(self) -> None:
        with workspace_tempdir() as root:
            context = make_context(root)
            requirements = context.source_root / "requirements.txt"
            requirements.write_text("", encoding="utf-8")

            result = create_build_env(context, requirements)

            self.assertTrue(result.ok)
            self.assertTrue(result.app_env_path.is_relative_to(context.output_dir))
            self.assertFalse((context.repo_root / "runtime" / "app_envs" / context.app_id).exists())
            self.assertIn("internal build environment", result.report)


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

    def test_build_env_python_updates_lock_even_when_source_lock_exists(self) -> None:
        with workspace_tempdir() as root:
            context = make_context(root)
            (context.source_root / "requirements.lock").write_text("requests==2.0.0\n", encoding="utf-8")
            final = context.output_dir / "final_app"
            final.mkdir()
            requirements = final / "requirements.txt"
            requirements.write_text("requests>=2\n", encoding="utf-8")
            fake_python = context.output_dir / "build_env" / "Scripts" / "python.exe"
            fake_python.parent.mkdir(parents=True)
            fake_python.write_text("fake", encoding="utf-8")

            completed = types.SimpleNamespace(returncode=0, stdout="requests==2.31.0\n", stderr="")
            with patch("app_studio.lock_generator.subprocess.run", return_value=completed):
                result = generate_lock(context, requirements, app_env_python=fake_python)

            self.assertTrue(result.ok)
            self.assertEqual((final / "requirements.lock").read_text(encoding="utf-8"), "requests==2.31.0\n")
            self.assertEqual(result.source, "pip freeze")

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
            self.assertIn("--contents-directory", command)
            self.assertEqual(command[command.index("--contents-directory") + 1], ".")
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

    def test_pyinstaller_probe_retries_without_user_site_for_pathlib_issue(self) -> None:
        calls = []

        def fake_run(command, **kwargs):
            calls.append(kwargs.get("env", {}))
            if len(calls) == 1:
                return type("Completed", (), {"returncode": 1, "stdout": "", "stderr": "obsolete backport pathlib package"})()
            return type("Completed", (), {"returncode": 0, "stdout": "6.0.0", "stderr": ""})()

        with patch("app_studio.frozen_folder_builder.subprocess.run", side_effect=fake_run):
            result, no_user_site, _, stderr = probe_pyinstaller(Path("python"), Path("."))

        self.assertEqual(result.returncode, 0)
        self.assertTrue(no_user_site)
        self.assertEqual(calls[1]["PYTHONNOUSERSITE"], "1")
        self.assertIn("PYTHONNOUSERSITE=1", stderr)

    def test_pyinstaller_command_adds_nested_paths_hidden_imports_and_data(self) -> None:
        with workspace_tempdir() as root:
            context = make_context(root)
            source = context.source_root
            package_main = source / "xcgate_flows" / "src" / "main.py"
            flow_file = source / "xcgate_flows" / "flows" / "xcgate_upload.flow"
            package_main.parent.mkdir(parents=True)
            flow_file.parent.mkdir(parents=True)
            package_main.write_text("print('main')\n", encoding="utf-8")
            flow_file.write_text("goto https://example.com\n", encoding="utf-8")
            inventory = SourceInventory(
                [
                    FileRecord(package_main, "xcgate_flows/src/main.py", 12, True, "project source package", "source"),
                    FileRecord(flow_file, "xcgate_flows/flows/xcgate_upload.flow", 24, True, "runtime definition file", "asset"),
                ]
            )
            profile = default_build_profile(context, inventory, DependencyReport("test", ["playwright>=1.46,<2.0"], [], []))

            command = pyinstaller_command(Path("python"), context, Path("dist"), Path("build"), Path("spec"), profile)

            self.assertIn("--paths", command)
            self.assertIn(str(source / "xcgate_flows"), command)
            self.assertIn("--hidden-import", command)
            self.assertIn("src.main", command)
            self.assertIn("--add-data", command)
            self.assertIn(f"{flow_file}{os.pathsep}xcgate_flows/flows", command)
            self.assertIn("--collect-all", command)
            self.assertIn("playwright", command)

    def test_exe_readiness_reports_profile_and_manual_checks(self) -> None:
        with workspace_tempdir() as root:
            context = make_context(root)
            flow_file = context.source_root / "flows" / "main.flow"
            flow_file.parent.mkdir()
            flow_file.write_text("goto https://example.com\n", encoding="utf-8")
            inventory = SourceInventory([FileRecord(flow_file, "flows/main.flow", 24, True, "runtime definition file", "asset")])
            dependency_report = DependencyReport("requirements.txt", ["playwright>=1.46,<2.0"], [], [])
            profile = default_build_profile(context, inventory, dependency_report)

            readiness = analyze_exe_readiness(context, BuildPlan("frozen-folder", "exe", "bin/demo_app/demo_app.exe", None, []), inventory, dependency_report, SecretScanReport([]), profile)

            self.assertEqual(readiness["overall_status"], "warn")
            self.assertTrue(readiness["manual_checks"])
            check_names = {item["name"] for item in readiness["checks"]}
            self.assertIn("playwright browser dependency", check_names)


class NormalRegistrationFlowTests(unittest.TestCase):
    def test_xcgate_like_apply_uses_build_env_for_pyinstaller_and_registers_exe(self) -> None:
        with workspace_tempdir() as root:
            repo = make_repo(root)
            app_id = "xcgate_upload"
            source = root / "s"
            flows = source / "xcgate_flows" / "flows"
            src = source / "xcgate_flows" / "src"
            flows.mkdir(parents=True)
            src.mkdir(parents=True)
            entry = source / "run_xcgate_upload.py"
            write_text(entry, "from xcgate_flows.src import main\nmain.run()\n")
            write_text(source / "xcgate_flows" / "config.yaml", "headless: true\n")
            write_text(flows / "xcgate_upload.flow", "goto https://example.com\n")
            write_text(flows / "3dx_create_ids.flow", "goto https://example.com/3dx\n")
            write_text(src / "__init__.py", "")
            write_text(src / "main.py", "def run():\n    print('ok')\n")
            profile_path = source / "build_profile_override.json"
            write_json(
                profile_path,
                {
                    "paths": ["xcgate_flows"],
                    "hidden_imports": ["src.main"],
                    "collect_all": ["playwright"],
                    "add_data": [
                        {"source": "xcgate_flows/config.yaml", "destination": "xcgate_flows"},
                        {"source": "xcgate_flows/flows/3dx_create_ids.flow", "destination": "xcgate_flows/flows"},
                        {"source": "xcgate_flows/flows/xcgate_upload.flow", "destination": "xcgate_flows/flows"},
                    ],
                    "required_files": [
                        "xcgate_flows/config.yaml",
                        "xcgate_flows/flows/3dx_create_ids.flow",
                        "xcgate_flows/flows/xcgate_upload.flow",
                    ],
                },
            )
            argv = [
                "--entry",
                str(entry),
                "--app-id",
                app_id,
                "--name",
                "Run XCgate Upload",
                "--build-profile",
                str(profile_path),
                "--apply",
            ]
            args = parse_app_studio_args(argv)
            args._raw_argv = argv
            pyinstaller_commands: list[list[str]] = []

            def fake_create_build_env(context, requirements_path, rebuild=True):
                build_env = context.output_dir / "build_env"
                python = build_env / ("Scripts" if os.name == "nt" else "bin") / ("python.exe" if os.name == "nt" else "python")
                write_text(python, "fake python\n")
                return AppEnvBuildResult(True, False, build_env, python, "test_build_env", "ok\n", "")

            def fake_generate_lock(context, requirements_path, app_env_python=None, skip=False):
                self.assertTrue(str(app_env_python).startswith(str(context.output_dir / "build_env")))
                lock = requirements_path.parent / "requirements.lock"
                write_text(lock, "")
                return LockGenerationResult(True, False, lock, "test", "ok\n", "")

            def fake_install_build_tools(context, build_env_path, packages):
                self.assertTrue(build_env_path.is_relative_to(context.output_dir))
                self.assertIn("PyInstaller>=6,<7", packages)
                return AppEnvBuildResult(True, False, build_env_path, build_env_path / ("Scripts" if os.name == "nt" else "bin") / ("python.exe" if os.name == "nt" else "python"), "test_build_env", "ok\n", "")

            def fake_pyinstaller(command, cwd, no_user_site=False):
                pyinstaller_commands.append(command)
                self.assertIn("build_env", command[0])
                self.assertNotIn("runtime\\app_envs", command[0].replace("/", "\\"))
                if "--version" in command:
                    return types.SimpleNamespace(returncode=0, stdout="6.10.0\n", stderr="")
                dist = Path(command[command.index("--distpath") + 1])
                app_id = command[command.index("--name") + 1]
                built_dir = dist / app_id
                built_dir.mkdir(parents=True)
                write_text(built_dir / (app_id + ".exe"), "fake exe\n")
                for index, value in enumerate(command):
                    if value != "--add-data":
                        continue
                    source_text, destination = command[index + 1].split(os.pathsep, 1)
                    source_path = Path(source_text)
                    target = built_dir / destination / source_path.name
                    if target.parent.exists() and target.parent.is_file():
                        target.parent.unlink()
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(source_path.read_text(encoding="utf-8"), encoding="utf-8")
                return types.SimpleNamespace(returncode=0, stdout="build ok\n", stderr="")

            with patch("main.create_build_env", side_effect=fake_create_build_env), patch("main.generate_lock", side_effect=fake_generate_lock), patch("main.install_build_tools", side_effect=fake_install_build_tools), patch("app_studio.frozen_folder_builder.run_pyinstaller_command", side_effect=fake_pyinstaller):
                exit_code = run_import(args, repo)

            self.assertEqual(exit_code, 0)
            output_dir = source / "ToolHub_AppStudio_Output" / app_id
            final_exe = output_dir / "final_app" / "bin" / app_id / f"{app_id}.exe"
            registered_exe = repo / "apps" / app_id / "bin" / app_id / f"{app_id}.exe"
            self.assertTrue(final_exe.is_file())
            self.assertTrue(registered_exe.is_file())
            self.assertFalse((output_dir / "final_app" / "bin" / "BUILD_REQUIRED.txt").exists())
            self.assertFalse((repo / "apps" / "run_xcgate_upload_fixture" / "bin" / "BUILD_REQUIRED.txt").exists())
            self.assertGreaterEqual(len(pyinstaller_commands), 2)
            build_command = pyinstaller_commands[-1]
            self.assertIn("--onedir", build_command)
            self.assertIn("--contents-directory", build_command)
            self.assertEqual(build_command[build_command.index("--contents-directory") + 1], ".")

            import_plan = json.loads((output_dir / "import_plan.json").read_text(encoding="utf-8"))
            self.assertEqual(import_plan["app_studio_policy_id"], "normal_python_source_to_frozen_folder_build_env_v2")
            self.assertFalse(import_plan["create_app_env"])
            self.assertIn("build_env", import_plan["build_env_python"])
            self.assertIn("build_env", import_plan["pyinstaller_probe_python"])
            self.assertIn("build_env", import_plan["pyinstaller_build_python"])
            self.assertNotIn("runtime\\app_envs", json.dumps(import_plan).replace("/", "\\"))

            app_yaml = (repo / "apps" / app_id / "app.yaml").read_text(encoding="utf-8")
            self.assertIn(f"entry: bin/{app_id}/{app_id}.exe", app_yaml)
            execution = json.loads((output_dir / "execution_test_result.json").read_text(encoding="utf-8"))
            self.assertTrue(execution["approval_allowed"])
            self.assertIn("app_studio_policy_id", execution["evidence"])
            runtime = json.loads((output_dir / "runtime_check_result.json").read_text(encoding="utf-8"))
            self.assertNotEqual(runtime["overall_status"], "fail")
            self.assertIn("app_studio_policy_id", runtime["evidence"])
            frozen_report = (output_dir / "frozen_folder_build_report.md").read_text(encoding="utf-8")
            self.assertIn("build_env", frozen_report)
            self.assertIn("--contents-directory .", frozen_report)


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

    def test_approval_rejects_stale_execution_result_with_context(self) -> None:
        with workspace_tempdir() as root:
            repo = make_repo(root)
            app_id = "demo_app"
            write_minimal_registered_app(repo, app_id)
            write_execution_result(repo, app_id, "pass", True)
            result_path = repo / "data" / "logs" / "app_studio" / f"{app_id}_execution_test_result.json"
            app_yaml = repo / "apps" / app_id / "app.yaml"
            newer = result_path.stat().st_mtime + 10
            os.utime(app_yaml, (newer, newer))
            manifest = json.loads((repo / "release" / "app_manifest.json").read_text(encoding="utf-8"))

            with self.assertRaisesRegex(ValueError, "stale.*result_path"):
                validate_approval_inputs(repo, manifest, app_id, strict=False, allow_warnings=True)

    def test_approval_failure_reports_result_path_and_fail_checks(self) -> None:
        with workspace_tempdir() as root:
            repo = make_repo(root)
            app_id = "demo_app"
            write_minimal_registered_app(repo, app_id)
            write_execution_result(repo, app_id, "fail", False)
            manifest = json.loads((repo / "release" / "app_manifest.json").read_text(encoding="utf-8"))

            with self.assertRaises(ValueError) as cm:
                validate_approval_inputs(repo, manifest, app_id, strict=False, allow_warnings=True)

            message = str(cm.exception)
            self.assertIn("result_path=", message)
            self.assertIn("fail_checks=", message)

    def test_blocked_execution_writes_failed_result(self) -> None:
        with workspace_tempdir() as root:
            context = make_context(root)

            result = record_blocked_execution(context, context.output_dir, "frozen-folder build", "PyInstaller failed")

            self.assertEqual(result.overall_status, "fail")
            self.assertFalse(result.approval_allowed)
            data = json.loads((context.output_dir / "execution_test_result.json").read_text(encoding="utf-8"))
            self.assertEqual(data["checks"][0]["name"], "frozen-folder build")
            self.assertEqual(data["checks"][0]["status"], "fail")
            self.assertIn("evidence", data)


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
            with patch.dict("os.environ", {"TOOLHUB_APP_STUDIO_AI_ENABLED": "true", "OPENAI_API_KEY": "<DUMMY_OPENAI_API_KEY>"}, clear=True):
                metadata = suggest_metadata(context)

            self.assertIn("model is not configured", metadata["_ai_generation_report"])

    def test_high_secret_skips_ai(self) -> None:
        with workspace_tempdir() as root:
            context = make_context(root)
            report = SecretScanReport([SecretFinding(context.entry, "content", "high", "OPENAI_API_KEY")])

            metadata = suggest_metadata(context, report)

            self.assertIn("high severity secret", metadata["_ai_generation_report"])

    def test_metadata_prompt_requests_japanese_output(self) -> None:
        with workspace_tempdir() as root:
            context = make_context(root)
            prompt = metadata_prompt(context)
            data = json.loads(prompt)

            self.assertEqual(data["language"], "ja-JP")
            self.assertIn("日本語", json.dumps(data, ensure_ascii=False))

    def test_metadata_fallback_is_japanese(self) -> None:
        with workspace_tempdir() as root:
            context = make_context(root)
            with patch.dict("os.environ", {"TOOLHUB_APP_STUDIO_AI_ENABLED": "false"}, clear=True):
                metadata = suggest_metadata(context)

            self.assertIn("起動", metadata["short_description"])
            self.assertIn("業務ツール", metadata["categories"])

    def test_responses_api_success_parses_metadata_json(self) -> None:
        with workspace_tempdir() as root:
            context = make_context(root)
            payload = {
                "short_description": "AIが作成した一言説明です。",
                "description": "AIが作成した詳細説明です。",
                "categories": ["開発支援"],
                "use_cases": ["登録内容の確認"],
                "inputs": ["コマンドライン引数"],
                "outputs": ["標準出力"],
                "notes": ["正式登録前に確認してください。"],
                "keywords": ["AI", "登録"],
                "examples": ["ToolHubへの登録内容を確認する"],
            }

            class Responses:
                def create(self, **kwargs):
                    self.kwargs = kwargs
                    return types.SimpleNamespace(output_text=json.dumps(payload))

            responses = Responses()
            client = types.SimpleNamespace(responses=responses)
            with patch.dict("os.environ", {"TOOLHUB_APP_STUDIO_AI_ENABLED": "true", "TOOLHUB_APP_STUDIO_TEXT_MODEL": "text-model", "OPENAI_API_KEY": "<DUMMY_OPENAI_API_KEY>"}, clear=True):
                with patch.dict(sys.modules, {"openai": types.SimpleNamespace(OpenAI=lambda: client)}):
                    metadata = suggest_metadata(context)

            self.assertEqual(metadata["short_description"], "AIが作成した一言説明です。")
            self.assertEqual(responses.kwargs["model"], "text-model")
            self.assertIn("api: responses.create", metadata["_ai_generation_report"])
            self.assertIn("status: success", metadata["_ai_generation_report"])
            self.assertIn("parse_status: success", metadata["_ai_generation_report"])

    def test_responses_api_invalid_json_falls_back_with_parse_reason(self) -> None:
        with workspace_tempdir() as root:
            context = make_context(root)
            client = types.SimpleNamespace(responses=types.SimpleNamespace(create=lambda **_: types.SimpleNamespace(output_text="not json")))
            with patch.dict("os.environ", {"TOOLHUB_APP_STUDIO_AI_ENABLED": "true", "TOOLHUB_APP_STUDIO_TEXT_MODEL": "text-model", "OPENAI_API_KEY": "<DUMMY_OPENAI_API_KEY>"}, clear=True):
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
        with patch.dict("os.environ", {"TOOLHUB_APP_STUDIO_AI_ENABLED": "true", "TOOLHUB_APP_STUDIO_IMAGE_MODEL": "gpt-image-2", "OPENAI_API_KEY": "<DUMMY_OPENAI_API_KEY>"}, clear=True):
            with patch.dict(sys.modules, {"openai": types.SimpleNamespace(OpenAI=lambda: client)}):
                result = generate_image("prompt")

        self.assertTrue(result.ok)
        self.assertEqual(result.content_type, "b64_png")
        self.assertNotIn("response_format", calls[0])

    def test_images_generate_accepts_url_candidate(self) -> None:
        client = types.SimpleNamespace(images=types.SimpleNamespace(generate=lambda **_: types.SimpleNamespace(data=[types.SimpleNamespace(url="https://example.com/icon.png")])))
        with patch.dict("os.environ", {"TOOLHUB_APP_STUDIO_AI_ENABLED": "true", "TOOLHUB_APP_STUDIO_IMAGE_MODEL": "gpt-image-2", "OPENAI_API_KEY": "<DUMMY_OPENAI_API_KEY>"}, clear=True):
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
        with patch.dict("os.environ", {"TOOLHUB_APP_STUDIO_AI_ENABLED": "true", "TOOLHUB_APP_STUDIO_IMAGE_MODEL": "gpt-image-2", "OPENAI_API_KEY": "<DUMMY_OPENAI_API_KEY>"}, clear=True):
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
        with patch.dict("os.environ", {"TOOLHUB_APP_STUDIO_AI_ENABLED": "true", "TOOLHUB_APP_STUDIO_IMAGE_MODEL": "gpt-image-2", "OPENAI_API_KEY": "<DUMMY_OPENAI_API_KEY>"}, clear=True):
            with patch.dict(sys.modules, {"openai": types.SimpleNamespace(OpenAI=lambda: client)}):
                result = generate_image("prompt")

        self.assertFalse(result.ok)
        self.assertEqual(result.status, "failed")
        self.assertIn("fallback_reason: Image API failed", result.report)

    def test_empty_image_model_uses_image_fallback(self) -> None:
        with patch.dict("os.environ", {"TOOLHUB_APP_STUDIO_AI_ENABLED": "true", "TOOLHUB_APP_STUDIO_IMAGE_MODEL": "", "OPENAI_API_KEY": "<DUMMY_OPENAI_API_KEY>"}, clear=True):
            result = generate_image("prompt")

        self.assertFalse(result.ok)
        self.assertIn("model is not configured", result.report)

    def test_image_api_prompt_keeps_japanese_and_adds_rendering_guidance(self) -> None:
        prompt = image_api_prompt("日本語のアイコン指示")

        self.assertIn("日本語のアイコン指示", prompt)
        self.assertIn("English rendering guidance", prompt)


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
    def test_frozen_distribution_check_fails_without_exe(self) -> None:
        with workspace_tempdir() as root:
            context = make_context(root)
            plan = BuildPlan("frozen-folder", "exe", f"bin/{context.app_id}/{context.app_id}.exe", None, [])
            final_app = context.output_dir / "final_app"
            final_app.mkdir(parents=True)
            write_text(final_app / "app.yaml", f"run:\n  runner: exe\n  entry: {plan.entry}\n")

            result = verify_runtime(context, context.output_dir, plan, {"add_data": []})

            self.assertEqual(result.overall_status, "fail")
            self.assertTrue((context.output_dir / "runtime_check_report.md").is_file())
            self.assertTrue((context.output_dir / "runtime_check_result.json").is_file())
            self.assertTrue((context.repo_root / "data" / "logs" / "app_studio" / "demo_app_runtime_check_result.json").is_file())

    def test_frozen_distribution_check_detects_packaged_data_and_size(self) -> None:
        with workspace_tempdir() as root:
            context = make_context(root)
            plan = BuildPlan("frozen-folder", "exe", f"bin/{context.app_id}/{context.app_id}.exe", None, [])
            final_app = context.output_dir / "final_app"
            bin_root = final_app / "bin" / context.app_id
            bin_root.mkdir(parents=True)
            write_text(final_app / "app.yaml", f"run:\n  runner: exe\n  entry: {plan.entry}\n")
            write_text(bin_root / f"{context.app_id}.exe", "fake exe")
            write_text(bin_root / "config.yaml", "ok: true\n")
            (context.output_dir / "build_env").mkdir()

            result = verify_runtime(context, context.output_dir, plan, {"add_data": [{"source": "config.yaml", "destination": "."}]})

            checks = {check.name: check.status for check in result.checks}
            self.assertEqual(checks["frozen-folder executable exists"], "pass")
            self.assertEqual(checks["required add-data files"], "pass")
            self.assertEqual(checks["forbidden payload files"], "pass")
            self.assertEqual(checks["frozen-folder size"], "pass")

    def test_frozen_distribution_check_accepts_internal_add_data_with_warning(self) -> None:
        with workspace_tempdir() as root:
            context = make_context(root)
            plan = BuildPlan("frozen-folder", "exe", f"bin/{context.app_id}/{context.app_id}.exe", None, [])
            final_app = context.output_dir / "final_app"
            bin_root = final_app / "bin" / context.app_id
            internal_root = bin_root / "_internal"
            internal_root.mkdir(parents=True)
            write_text(final_app / "app.yaml", f"run:\n  runner: exe\n  entry: {plan.entry}\n")
            write_text(bin_root / f"{context.app_id}.exe", "fake exe")
            write_text(internal_root / "config.yaml", "ok: true\n")
            write_text(context.output_dir / "frozen_folder_build_report.md", "- command: python -m PyInstaller --onedir --contents-directory . main.py\n")
            (context.output_dir / "build_env").mkdir()

            result = verify_runtime(context, context.output_dir, plan, {"add_data": [{"source": "config.yaml", "destination": "."}]})

            required = next(check for check in result.checks if check.name == "required add-data files")
            self.assertEqual(required.status, "warn")
            self.assertIn("_internal", required.detail)

    def test_directory_add_data_does_not_require_double_nested_source_name(self) -> None:
        with workspace_tempdir() as root:
            context = make_context(root)
            plan = BuildPlan("frozen-folder", "exe", f"bin/{context.app_id}/{context.app_id}.exe", None, [])
            asset = context.source_root / "xcgate_flows" / "config.yaml"
            asset.parent.mkdir()
            write_text(asset, "ok: true\n")
            final_app = context.output_dir / "final_app"
            bin_root = final_app / "bin" / context.app_id
            bin_root.mkdir(parents=True)
            write_text(final_app / "app.yaml", f"run:\n  runner: exe\n  entry: {plan.entry}\n")
            write_text(bin_root / f"{context.app_id}.exe", "fake exe")
            (bin_root / "xcgate_flows").mkdir()
            write_text(bin_root / "xcgate_flows" / "config.yaml", "ok: true\n")
            write_text(context.output_dir / "frozen_folder_build_report.md", "- command: python -m PyInstaller --onedir --contents-directory . main.py\n")
            (context.output_dir / "build_env").mkdir()

            result = verify_runtime(
                context,
                context.output_dir,
                plan,
                {
                    "add_data": [{"source": "xcgate_flows", "destination": "xcgate_flows"}],
                    "required_files": ["xcgate_flows/config.yaml"],
                },
            )

            required = next(check for check in result.checks if check.name == "required add-data files")
            self.assertEqual(required.status, "pass")
            self.assertNotIn("xcgate_flows/xcgate_flows", required.detail)

    def test_frozen_distribution_check_blocks_user_auth_files_without_blocking_playwright_internals(self) -> None:
        with workspace_tempdir() as root:
            context = make_context(root)
            plan = BuildPlan("frozen-folder", "exe", f"bin/{context.app_id}/{context.app_id}.exe", None, [])
            final_app = context.output_dir / "final_app"
            bin_root = final_app / "bin" / context.app_id
            playwright_root = bin_root / "_internal" / "playwright"
            (playwright_root / "_impl").mkdir(parents=True)
            (playwright_root / "driver" / "package" / "lib" / "server").mkdir(parents=True)
            write_text(final_app / "app.yaml", f"run:\n  runner: exe\n  entry: {plan.entry}\n")
            write_text(bin_root / f"{context.app_id}.exe", "fake exe")
            write_text(playwright_root / "_impl" / "_cdp_session.py", "ok")
            write_text(playwright_root / "driver" / "package" / "lib" / "server" / "cookieStore.js", "ok")
            write_text(bin_root / "credentials.json", "{}")

            result = verify_runtime(context, context.output_dir, plan, {"add_data": []})

            forbidden = next(check for check in result.checks if check.name == "forbidden payload files")
            self.assertEqual(forbidden.status, "fail")
            self.assertIn("credentials.json", forbidden.detail)
            self.assertNotIn("cookieStore.js", forbidden.detail)
            self.assertNotIn("_cdp_session.py", forbidden.detail)


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
