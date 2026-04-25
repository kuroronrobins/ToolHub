from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from .models import BuildPlan, FrozenBuildResult, StudioContext
from .util import assert_within, reset_directory, write_text


def build_frozen_folder(context: StudioContext, plan: BuildPlan, output_dir: Path, rebuild: bool = False) -> FrozenBuildResult:
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
    probe = subprocess.run([str(python), "-m", "PyInstaller", "--version"], cwd=str(context.source_root), text=True, encoding="utf-8", errors="replace", stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if probe.returncode != 0:
        error = "PyInstaller is not available. Install it in the app_env or development environment, then rerun with -BuildFrozenFolder."
        result = FrozenBuildResult(False, False, None, build_report(context, plan, [[str(python), "-m", "PyInstaller", "--version"]], error, None, probe.stdout, probe.stderr), [], error)
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

    command = pyinstaller_command(python, context, dist, work, spec)
    if any("--onefile" in arg for arg in command):
        error = "Refusing to run PyInstaller with --onefile."
        result = FrozenBuildResult(False, False, None, build_report(context, plan, [command], error, None), command, error)
        write_frozen_report(context, result)
        return result

    completed = subprocess.run(command, cwd=str(context.source_root), text=True, encoding="utf-8", errors="replace", stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
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
    exe_path = final_bin / exe_name(context.app_id)
    result = FrozenBuildResult(True, False, exe_path, build_report(context, plan, [command], "", exe_path, completed.stdout, completed.stderr), command, "")
    write_frozen_report(context, result)
    return result


def select_python(context: StudioContext) -> Path:
    app_env = context.repo_root / "runtime" / "app_envs" / context.app_id / ("Scripts" if os.name == "nt" else "bin") / ("python.exe" if os.name == "nt" else "python")
    if app_env.is_file():
        return app_env
    runtime = context.repo_root / "runtime" / "python" / ("python.exe" if os.name == "nt" else "python")
    if runtime.is_file():
        return runtime
    return Path(sys.executable)


def pyinstaller_command(python: Path, context: StudioContext, dist: Path, work: Path, spec: Path) -> list[str]:
    return [
        str(python),
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--onedir",
        "--name",
        context.app_id,
        "--distpath",
        str(dist),
        "--workpath",
        str(work),
        "--specpath",
        str(spec),
        str(context.entry),
    ]


def exe_name(app_id: str) -> str:
    return f"{app_id}.exe" if os.name == "nt" else app_id


def build_report(context: StudioContext, plan: BuildPlan, commands: list[list[str]], error: str, exe_path: Path | None, stdout: str = "", stderr: str = "") -> str:
    status = "FAIL" if error else "PASS"
    lines = [
        "# Frozen Folder Build Report",
        "",
        f"- app_id: `{context.app_id}`",
        f"- status: `{status}`",
        f"- expected_entry: `{plan.entry}`",
        f"- exe_path: `{exe_path}`",
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
    if error:
        lines.extend(["", "## Error", "", error])
    return "\n".join(lines) + "\n"


def write_frozen_report(context: StudioContext, result: FrozenBuildResult) -> None:
    write_text(context.output_dir / "frozen_folder_build_report.md", result.report)
    write_text(context.repo_root / "data" / "logs" / "app_studio" / f"{context.app_id}_frozen_folder_build_report.md", result.report)

