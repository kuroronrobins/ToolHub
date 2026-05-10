from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .build_profile import managed_build_python, normalize_build_profile, pyinstaller_profile_args, resolve_profile_source
from .models import BuildPlan, FrozenBuildResult, StudioContext
from .payload_policy import should_exclude_payload_path
from .trace import BUILD_TMP_DIRNAME, app_studio_trace, is_runtime_app_env_path, planned_build_env_python
from .util import assert_within, reset_directory, write_text


PYINSTALLER_ARTIFACT_ROOT = Path(BUILD_TMP_DIRNAME) / "pyi"
PYINSTALLER_DIST_DIR = "d"
PYINSTALLER_WORK_DIR = "b"
PYINSTALLER_SPEC_DIR = "s"
SANITIZED_DATA_DIR = "sanitized_data"
WINDOWS_MAX_PATH = 260


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

    input_error = validate_frozen_build_inputs(context)
    if input_error:
        result = FrozenBuildResult(False, False, None, build_report(context, plan, [], input_error, None), [], input_error)
        write_frozen_report(context, result)
        return result

    python = select_python(context)
    if python is None:
        error = "Managed build Python is not available. Apply must create the internal build_env before the frozen-folder build."
        result = FrozenBuildResult(False, False, None, build_report(context, plan, [], error, None), [], error)
        write_frozen_report(context, result)
        return result
    if not python.is_file():
        error = (
            "Managed build Python was selected but the executable is missing before PyInstaller build. "
            f"selected_python={python}; output_dir={context.output_dir}. "
            "The App Studio internal build_env may have been moved or deleted. Rerun Apply after restoring the source and output folder."
        )
        result = FrozenBuildResult(False, False, None, build_report(context, plan, [[str(python), "-m", "PyInstaller", "--version"]], error, None), [], error)
        write_frozen_report(context, result)
        return result
    expected_python = planned_build_env_python(context)
    if python.resolve() != expected_python.resolve() or is_runtime_app_env_path(context.repo_root, python):
        error = (
            "Refusing to run PyInstaller with a non-build_env Python. "
            f"selected_python={python}; expected_build_env_python={expected_python}; "
            "reason=normal registration must use build_env, not runtime/app_envs."
        )
        result = FrozenBuildResult(False, False, None, build_report(context, plan, [[str(python), "-m", "PyInstaller", "--version"]], error, None), [], error)
        write_frozen_report(context, result)
        return result
    probe_command = [str(python), "-m", "PyInstaller", "--version"]
    probe, no_user_site, probe_stdout, probe_stderr = probe_pyinstaller(python, context.source_root)
    if probe.returncode != 0:
        error = f"PyInstaller is not available in build_env Python: {python}. Build-only dependencies must be installed before the frozen-folder build."
        result = FrozenBuildResult(False, False, None, build_report(context, plan, [probe_command], error, None, probe_stdout, probe_stderr, probe_stdout=probe_stdout, no_user_site=no_user_site), probe_command, error)
        write_frozen_report(context, result)
        return result

    artifacts, dist, work, spec = pyinstaller_artifact_paths(output_dir)
    reset_directory(artifacts, output_dir)
    dist.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)
    spec.mkdir(parents=True, exist_ok=True)

    effective_build_profile, sanitizer_records = prepare_sanitized_build_profile(context, output_dir, build_profile)
    command = pyinstaller_command(python, context, dist, work, spec, effective_build_profile)
    if any("--onefile" in arg for arg in command):
        error = "Refusing to run PyInstaller with --onefile."
        result = FrozenBuildResult(False, False, None, build_report(context, plan, [command], error, None, payload_sanitizer_records=sanitizer_records), command, error)
        write_frozen_report(context, result)
        return result

    completed = run_pyinstaller_command(command, context.source_root, no_user_site=no_user_site)
    if completed.returncode != 0:
        error = "PyInstaller --onedir build failed."
        result = FrozenBuildResult(False, False, None, build_report(context, plan, [probe_command, command], error, None, completed.stdout, completed.stderr, probe_stdout=probe_stdout, no_user_site=no_user_site, payload_sanitizer_records=sanitizer_records), command, error)
        write_frozen_report(context, result)
        return result

    built_dir = dist / context.app_id
    built_exe = built_dir / exe_name(context.app_id)
    if not built_exe.is_file():
        error = f"Expected frozen executable was not found: {built_exe}"
        result = FrozenBuildResult(False, False, None, build_report(context, plan, [probe_command, command], error, None, completed.stdout, completed.stderr, probe_stdout=probe_stdout, no_user_site=no_user_site, payload_sanitizer_records=sanitizer_records), command, error)
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
    result = FrozenBuildResult(True, False, exe_path, build_report(context, plan, [probe_command, command], "", exe_path, completed.stdout, completed.stderr, probe_stdout=probe_stdout, no_user_site=no_user_site, payload_sanitizer_records=sanitizer_records), command, "")
    write_frozen_report(context, result)
    return result


def prepare_sanitized_build_profile(
    context: StudioContext,
    output_dir: Path,
    build_profile: dict[str, Any] | None,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    if not build_profile:
        return build_profile, []

    normalized = normalize_build_profile(build_profile)
    sanitized_root = output_dir / BUILD_TMP_DIRNAME / SANITIZED_DATA_DIR
    reset_directory(sanitized_root, output_dir)
    sanitized_root.mkdir(parents=True, exist_ok=True)

    sanitized_add_data: list[dict[str, str]] = []
    records: list[dict[str, Any]] = []
    for index, item in enumerate(normalized["add_data"]):
        source_label = item["source"]
        destination = item["destination"]
        source = resolve_profile_source(context, source_label)
        policy_relative = source_policy_relative(context, source, source_label)
        exclude, reason = should_exclude_payload_path(policy_relative)
        if exclude:
            records.append(
                {
                    "source": source_label,
                    "destination": destination,
                    "status": "excluded",
                    "reason": reason,
                    "included_files": 0,
                    "excluded_files": 0,
                }
            )
            continue
        if source.is_dir():
            stage = sanitized_root / f"{index:03d}_{safe_stage_name(destination or source.name)}"
            included_files, excluded_files = copy_sanitized_directory(source, stage)
            sanitized_add_data.append({"source": str(stage), "destination": destination})
            records.append(
                {
                    "source": source_label,
                    "staged_source": str(stage),
                    "destination": destination,
                    "status": "staged",
                    "reason": "directory add_data sanitized before PyInstaller",
                    "included_files": included_files,
                    "excluded_files": excluded_files,
                }
            )
            continue
        if source.is_file():
            sanitized_add_data.append(item)
            records.append(
                {
                    "source": source_label,
                    "destination": destination,
                    "status": "kept",
                    "reason": "file add_data passed through",
                    "included_files": 1,
                    "excluded_files": 0,
                }
            )
            continue
        sanitized_add_data.append(item)
        records.append(
            {
                "source": source_label,
                "destination": destination,
                "status": "kept_missing",
                "reason": "source did not exist during sanitizer; PyInstaller will report the missing input",
                "included_files": 0,
                "excluded_files": 0,
            }
        )

    sanitized = {**normalized, "add_data": sanitized_add_data}
    return sanitized, records


def copy_sanitized_directory(source: Path, destination: Path) -> tuple[int, int]:
    included_files = 0
    excluded_files = 0
    destination.mkdir(parents=True, exist_ok=True)
    for path in sorted(source.rglob("*")):
        relative = path.relative_to(source)
        exclude, _reason = should_exclude_payload_path(relative)
        if exclude:
            if path.is_file():
                excluded_files += 1
            continue
        target = destination / relative
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        if path.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
            included_files += 1
    return included_files, excluded_files


def source_policy_relative(context: StudioContext, source: Path, source_label: str) -> Path:
    try:
        return source.resolve().relative_to(context.source_root.resolve())
    except Exception:
        return Path(source_label)


def safe_stage_name(value: str) -> str:
    cleaned = value.replace("\\", "_").replace("/", "_").replace(":", "_").strip("._ ")
    return cleaned or "data"


def select_python(context: StudioContext) -> Path | None:
    return managed_build_python(context)


def validate_frozen_build_inputs(context: StudioContext) -> str:
    if not context.source_root.is_dir():
        return (
            "Source root directory is missing before PyInstaller build. "
            f"source_root={context.source_root}. Restore the app source or select the current source folder, then rerun Apply."
        )
    if not context.entry.is_file():
        return (
            "Source entry file is missing before PyInstaller build. "
            f"entry={context.entry}; source_root={context.source_root}. Restore the app source or select the current entry file, then rerun Apply."
        )
    if not context.entry.resolve().is_relative_to(context.source_root.resolve()):
        return (
            "Source entry is outside source_root before PyInstaller build. "
            f"entry={context.entry}; source_root={context.source_root}. Select a source_root that contains the entry file."
        )
    return ""


def pyinstaller_artifact_paths(output_dir: Path) -> tuple[Path, Path, Path, Path]:
    artifacts = output_dir / PYINSTALLER_ARTIFACT_ROOT
    return (
        artifacts,
        artifacts / PYINSTALLER_DIST_DIR,
        artifacts / PYINSTALLER_WORK_DIR,
        artifacts / PYINSTALLER_SPEC_DIR,
    )


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
    try:
        return subprocess.run(command, cwd=str(cwd), text=True, encoding="utf-8", errors="replace", stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, env=env)
    except OSError as exc:
        stderr = "\n".join(
            [
                f"{exc.__class__.__name__}: {exc}",
                f"executable: {command[0] if command else ''}",
                f"working_directory: {cwd}",
            ]
        )
        return subprocess.CompletedProcess(command, 127, "", stderr)


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


def build_report(
    context: StudioContext,
    plan: BuildPlan,
    commands: list[list[str]],
    error: str,
    exe_path: Path | None,
    stdout: str = "",
    stderr: str = "",
    probe_stdout: str = "",
    no_user_site: bool = False,
    payload_sanitizer_records: list[dict[str, Any]] | None = None,
) -> str:
    status = "FAIL" if error else "PASS"
    selected_python = Path(commands[0][0]) if commands and commands[0] else None
    build_env_python = planned_build_env_python(context)
    trace = app_studio_trace(
        context,
        build_env_python=build_env_python,
        pyinstaller_probe_python=selected_python,
        pyinstaller_build_python=selected_python,
    )
    lines = [
        "# Frozen Folder Build Report",
        "",
        f"- app_id: `{context.app_id}`",
        f"- status: `{status}`",
        f"- expected_entry: `{plan.entry}`",
        f"- expected_exe: `{context.output_dir / 'final_app' / plan.entry}`",
        f"- actual_exe: `{exe_path}`",
        f"- exe_path: `{exe_path}`",
        f"- selected_python: `{selected_python}`",
        f"- build_env_python: `{build_env_python}`",
        f"- pyinstaller_probe_python: `{selected_python}`",
        f"- pyinstaller_build_python: `{selected_python}`",
        f"- pyinstaller_version: `{probe_stdout.strip() or 'unknown'}`",
        f"- working_directory: `{context.source_root}`",
        f"- pyinstaller_artifacts: `{pyinstaller_artifact_summary(commands)}`",
        f"- pyinstaller_layout: `--onedir --contents-directory .`",
        f"- contents_directory_dot: `{any('--contents-directory' == arg and index + 1 < len(command) and command[index + 1] == '.' for command in commands for index, arg in enumerate(command))}`",
        f"- no_user_site: `{str(no_user_site).lower()}`",
        "",
        "## Execution Trace",
        "",
        "```json",
        __import__("json").dumps(trace, ensure_ascii=False, indent=2),
        "```",
        "",
        "## Commands",
        "",
    ]
    if commands:
        lines.extend(f"- `{' '.join(command)}`" for command in commands)
    else:
        lines.append("- No command was run.")
    if payload_sanitizer_records is not None:
        excluded_files = sum(int(record.get("excluded_files") or 0) for record in payload_sanitizer_records)
        staged_dirs = sum(1 for record in payload_sanitizer_records if record.get("status") == "staged")
        lines.extend(
            [
                "",
                "## Payload Sanitizer",
                "",
                f"- add_data_entries: `{len(payload_sanitizer_records)}`",
                f"- staged_directories: `{staged_dirs}`",
                f"- excluded_generated_files: `{excluded_files}`",
                "",
                "| Status | Source | Destination | Included | Excluded | Reason |",
                "| --- | --- | --- | ---: | ---: | --- |",
            ]
        )
        for record in payload_sanitizer_records:
            reason = str(record.get("reason") or "").replace("|", "\\|")
            lines.append(
                "| "
                f"{record.get('status', '')} | "
                f"`{record.get('source', '')}` | "
                f"`{record.get('destination', '')}` | "
                f"{int(record.get('included_files') or 0)} | "
                f"{int(record.get('excluded_files') or 0)} | "
                f"{reason} |"
            )
    if stdout or stderr:
        lines.extend(["", "## Output", "", "```text", stdout[-4000:].strip(), stderr[-4000:].strip(), "```"])
    lines.extend(
        [
            "",
            "## Environment Summary",
            "",
            f"- PYTHONNOUSERSITE: `{str(no_user_site).lower()}`",
            f"- PATH entries: `{len(os.environ.get('PATH', '').split(os.pathsep))}`",
        ]
    )
    issues = detect_pyinstaller_environment_issue(stdout, stderr)
    if issues:
        lines.extend(["", "## Environment Issue Hints", ""])
        lines.extend(f"- {issue}" for issue in issues)
    failure_hints = classify_pyinstaller_failure(stdout, stderr, commands)
    if error and failure_hints:
        lines.extend(["", "## Failure Classification", ""])
        lines.extend(f"- {hint}" for hint in failure_hints)
    if error:
        lines.extend(["", "## Error", "", error])
    return "\n".join(lines) + "\n"


def classify_pyinstaller_failure(stdout: str, stderr: str, commands: list[list[str]] | None = None) -> list[str]:
    text = f"{stdout}\n{stderr}"
    lower = text.lower()
    command_text = " ".join(" ".join(command) for command in (commands or [])).lower()
    missing_path = extract_filenotfound_path(text)
    hints: list[str] = []

    if "filenotfounderror" in lower and "collect" in lower and "playwright" in lower:
        if missing_path and os.name == "nt" and len(missing_path) >= WINDOWS_MAX_PATH:
            hints.extend(
                [
                    "category: pyinstaller_windows_long_path_collect_failure",
                    f"cause: PyInstaller reached COLLECT but the destination path length was {len(missing_path)} characters.",
                    "source_scope_related: false",
                    "next_action: shorten PyInstaller dist/work/spec paths or app_id/output paths; do not add `.auth` or storage state to the package as a workaround.",
                ]
            )
            return hints
        hints.extend(
            [
                "category: pyinstaller_collect_all_data_copy_failure",
                "cause: PyInstaller reached COLLECT but failed while copying Playwright package data.",
                "source_scope_related: false",
                "next_action: review Playwright collect_all/add-data handling or PyInstaller hooks-contrib behavior; do not add `.auth` or storage state to the package as a workaround.",
            ]
        )
    elif "filenotfounderror" in lower or "winerror 2" in lower or "no such file or directory" in lower or "cannot find the file" in lower:
        hints.extend(
            [
                "category: pyinstaller_input_path_missing",
                "cause: PyInstaller could not start because an executable, working directory, entry file, or input path was missing.",
                "next_action: confirm the app source entry and App Studio internal build_env still exist, then rerun Apply.",
            ]
        )
    elif "hook" in lower and "failed" in lower:
        hints.extend(
            [
                "category: pyinstaller_hook_failure",
                "cause: PyInstaller or a hook raised an error during analysis/build.",
                "next_action: identify the failing hook and dependency version before changing source scope.",
            ]
        )
    elif "modulenotfounderror" in lower or "no module named" in lower:
        hints.extend(
            [
                "category: missing_package_or_hidden_import",
                "cause: PyInstaller or runtime import analysis could not find a module.",
                "next_action: confirm requirements.txt and hidden_imports before retrying.",
            ]
        )
    elif "dll load failed" in lower or "loadlibrary" in lower:
        hints.extend(
            [
                "category: binary_dependency_failure",
                "cause: a native dependency failed to load during PyInstaller analysis/build.",
                "next_action: confirm binary wheels and runtime DLL dependencies.",
            ]
        )
    elif "syntaxerror" in lower:
        hints.extend(
            [
                "category: source_syntax_error",
                "cause: Python source could not be parsed or compiled.",
                "next_action: fix the source syntax or encoding before retrying.",
            ]
        )

    if "--collect-all playwright" in command_text and not any("playwright" in hint for hint in hints):
        hints.append("note: PyInstaller command includes `--collect-all playwright`; Playwright browser/runtime verification still requires manual launch checks.")
    return hints


def extract_filenotfound_path(text: str) -> str:
    marker = "No such file or directory: "
    if marker not in text:
        return ""
    tail = text.rsplit(marker, 1)[1].strip()
    quote = tail[:1]
    if quote in {"'", '"'}:
        tail = tail[1:]
        return tail.split(quote, 1)[0]
    return tail.splitlines()[0].strip()


def pyinstaller_artifact_summary(commands: list[list[str]]) -> str:
    if not commands:
        return "not created"
    command = commands[-1]
    values: dict[str, str] = {}
    for option in ["--distpath", "--workpath", "--specpath"]:
        if option in command:
            index = command.index(option)
            if index + 1 < len(command):
                values[option.removeprefix("--")] = command[index + 1]
    if not values:
        return "not specified"
    return ", ".join(f"{key}={value}" for key, value in values.items())


def write_frozen_report(context: StudioContext, result: FrozenBuildResult) -> None:
    write_text(context.output_dir / "frozen_folder_build_report.md", result.report)
    write_text(context.repo_root / "data" / "logs" / "app_studio" / f"{context.app_id}_frozen_folder_build_report.md", result.report)
