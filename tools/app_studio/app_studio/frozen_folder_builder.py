from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from .build_profile import managed_build_python, pyinstaller_profile_args
from .models import BuildPlan, FrozenBuildResult, StudioContext
from .util import assert_within, reset_directory, write_text


def build_frozen_folder(
    context: StudioContext,
    plan: BuildPlan,
    output_dir: Path,
    rebuild: bool = False,
    build_profile: dict | None = None,
) -> FrozenBuildResult:
    if plan.mode != "frozen-folder":
        result = FrozenBuildResult(True, True, None, build_report(context, plan, [], "Skipped because build mode is not frozen-folder.", None), [], "")
        write_frozen_report(context, result)
        return result

    final_bin = output_dir / "final_app" / "bin" / context.app_id
    if final_bin.exists() and not rebuild and (final_bin / exe_name(context.app_id)).is_file():
        exe_path = final_bin / exe_name(context.app_id)
        result = FrozenBuildResult(True, True, exe_path, build_report(context, plan, [], "Existing frozen-folder output was kept.", exe_path), [], "")
        write_frozen_report(context, result)
        return result

    python = select_python(context)
    if python is None:
        error = "Managed build Python is not available. Apply must create output_dir/build_env before the frozen-folder build."
        result = FrozenBuildResult(False, False, None, build_report(context, plan, [], error, None), [], error)
        write_frozen_report(context, result)
        return result
    probe_command = [str(python), "-m", "PyInstaller", "--version"]
    probe, no_user_site, probe_stdout, probe_stderr = probe_pyinstaller(python, context.source_root)
    if probe.returncode != 0:
        error = "PyInstaller is not available in build_env. Build-only dependencies must be installed before the frozen-folder build."
        result = FrozenBuildResult(False, False, None, build_report(context, plan, [probe_command], error, None, probe_stdout, probe_stderr), [], error)
        write_frozen_report(context, result)
        return result

    artifacts = output_dir / "build_artifacts" / "pyinstaller"
    dist = artifacts / "dist"
    work = artifacts / "build"
    spec = artifacts / "spec"
    reset_directory(artifacts, output_dir)
    dist.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)
    spec.mkdir(parents=True, exist_ok=True)

    command = pyinstaller_command(python, context, dist, work, spec, build_profile)
    if any("--onefile" in arg for arg in command):
        error = "Refusing to run PyInstaller with --onefile."
        result = FrozenBuildResult(False, False, None, build_report(context, plan, [command], error, None), command, error)
        write_frozen_report(context, result)
        return result

    completed = run_pyinstaller_command(command, context.source_root, no_user_site=no_user_site)
    if completed.returncode != 0:
        error = "PyInstaller --onedir build failed."
        result = FrozenBuildResult(False, False, None, build_report(context, plan, [command], error, None, completed.stdout, completed.stderr), command, error)
        write_frozen_report(context, result)
        return result

    built_dir = dist / context.app_id
    built_exe = built_dir / exe_name(context.app_id)
    if not built_exe.is_file():
        error = f"Expected frozen executable was not found: {built_exe}"
        result = FrozenBuildResult(False, False, None, build_report(context, plan, [command], error, None, completed.stdout, completed.stderr), command, error)
        write_frozen_report(context, result)
        return result

    assert_within(final_bin, output_dir / "final_app", "frozen output")
    if final_bin.exists():
        shutil.rmtree(final_bin)
    shutil.copytree(built_dir, final_bin)
    build_required = output_dir / "final_app" / "bin" / "BUILD_REQUIRED.txt"
    if build_required.is_file():
        build_required.unlink()
    exe_path = final_bin / exe_name(context.app_id)
    result = FrozenBuildResult(True, False, exe_path, build_report(context, plan, [command], "", exe_path, completed.stdout, completed.stderr), command, "")
    write_frozen_report(context, result)
    return result


def select_python(context: StudioContext) -> Path | None:
    return managed_build_python(context)


def probe_pyinstaller(python: Path, cwd: Path) -> tuple[subprocess.CompletedProcess[str], bool, str, str]:
    command = [str(python), "-m", "PyInstaller", "--version"]
    first = run_pyinstaller_command(command, cwd)
    if first.returncode == 0:
        return first, False, first.stdout, first.stderr

    if not detect_pyinstaller_environment_issue(first.stdout, first.stderr):
        return first, False, first.stdout, first.stderr

    retry = run_pyinstaller_command(command, cwd, no_user_site=True)
    stdout = "\n".join(part for part in [first.stdout, retry.stdout] if part)
    stderr = "\n".join(
        part
        for part in [
            first.stderr,
            "Retried with PYTHONNOUSERSITE=1 to ignore user site-packages.",
            retry.stderr,
        ]
        if part
    )
    return retry, retry.returncode == 0, stdout, stderr


def run_pyinstaller_command(command: list[str], cwd: Path, no_user_site: bool = False) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    if no_user_site:
        env["PYTHONNOUSERSITE"] = "1"
    return subprocess.run(command, cwd=str(cwd), text=True, encoding="utf-8", errors="replace", stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, env=env)


def pyinstaller_command(python: Path, context: StudioContext, dist: Path, work: Path, spec: Path, build_profile: dict | None = None) -> list[str]:
    command = [
        str(python),
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--onedir",
        "--clean",
        "--contents-directory",
        ".",
        "--name",
        context.app_id,
        "--distpath",
        str(dist),
        "--workpath",
        str(work),
        "--specpath",
        str(spec),
    ]
    if build_profile:
        command.extend(pyinstaller_profile_args(context, build_profile))
    command.append(str(context.entry))
    return command


def exe_name(app_id: str) -> str:
    return f"{app_id}.exe" if os.name == "nt" else app_id


def detect_pyinstaller_environment_issue(stdout: str, stderr: str) -> list[str]:
    text = f"{stdout}\n{stderr}".lower()
    findings: list[str] = []
    pathlib_signals = ["obsolete backport", "pathlib package", "backport of a standard library package", "pip uninstall pathlib"]
    if "pathlib" in text and any(signal in text for signal in pathlib_signals):
        findings.extend(
            [
                "PyInstaller output suggests an obsolete pathlib backport is installed.",
                "Python 3 includes pathlib in the standard library; the backport can break PyInstaller.",
                "Remove the backport from the build environment manually, for example: `python -m pip uninstall pathlib`.",
                "Recreate the internal build_env if needed, then rerun Apply.",
                "ToolHub App Studio did not uninstall anything automatically.",
            ]
        )
    return findings


def build_report(context: StudioContext, plan: BuildPlan, commands: list[list[str]], error: str, exe_path: Path | None, stdout: str = "", stderr: str = "") -> str:
    status = "FAIL" if error else "PASS"
    lines = [
        "# Frozen Folder Build Report",
        "",
        f"- app_id: `{context.app_id}`",
        f"- status: `{status}`",
        f"- expected_entry: `{plan.entry}`",
        f"- exe_path: `{exe_path}`",
        f"- pyinstaller_layout: `--onedir --contents-directory .`",
        f"- contents_directory_dot: `{any('--contents-directory' == arg and index + 1 < len(command) and command[index + 1] == '.' for command in commands for index, arg in enumerate(command))}`",
        "",
        "## Commands",
        "",
    ]
    if commands:
        lines.extend(f"- `{' '.join(command)}`" for command in commands)
    else:
        lines.append("- No command was run.")
    if stdout or stderr:
        lines.extend(["", "## Output", "", "```text", stdout[-4000:].strip(), stderr[-4000:].strip(), "```"])
    issues = detect_pyinstaller_environment_issue(stdout, stderr)
    if issues:
        lines.extend(["", "## Environment Issue Hints", ""])
        lines.extend(f"- {issue}" for issue in issues)
    if error:
        lines.extend(["", "## Error", "", error])
    return "\n".join(lines) + "\n"


def write_frozen_report(context: StudioContext, result: FrozenBuildResult) -> None:
    write_text(context.output_dir / "frozen_folder_build_report.md", result.report)
    write_text(context.repo_root / "data" / "logs" / "app_studio" / f"{context.app_id}_frozen_folder_build_report.md", result.report)
