from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from .models import AppEnvBuildResult, StudioContext
from .util import assert_within, timestamp, write_text


def create_app_env(context: StudioContext, requirements_path: Path, rebuild: bool = False, extra_packages: list[str] | None = None) -> AppEnvBuildResult:
    app_env_root = context.repo_root / "runtime" / "app_envs"
    app_env_path = app_env_root / context.app_id
    assert_within(app_env_path, app_env_root, "app_env target")

    if app_env_path.exists() and not rebuild:
        result = AppEnvBuildResult(
            ok=True,
            skipped=True,
            app_env_path=app_env_path,
            python_path=app_env_python(app_env_path),
            python_source="existing_app_env",
            report=build_report(
                context,
                app_env_path,
                app_env_python(app_env_path),
                "existing_app_env",
                ["Existing app_env was kept because -RebuildAppEnv was not specified."],
                "",
            ),
        )
        write_app_env_report(context, result)
        return result

    if app_env_path.exists() and rebuild:
        backup = context.repo_root / "backups" / "app_studio" / timestamp() / context.app_id / "app_env"
        assert_within(backup, context.repo_root / "backups", "app_env backup")
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(app_env_path), str(backup))

    base_python, source = select_base_python(context)
    notes = [f"Base Python source: {source}", f"Base Python: {base_python}"]
    app_env_path.parent.mkdir(parents=True, exist_ok=True)

    create_command = [str(base_python), "-m", "venv", str(app_env_path)]
    create = run_command(create_command, context.repo_root)
    notes.append(command_summary("venv create", create_command, create))
    if create.returncode != 0:
        install_path = install_requirements_path(requirements_path)
        if "ensurepip" in create.stderr and not (install_path and has_installable_requirements(install_path)):
            if app_env_path.exists():
                shutil.rmtree(app_env_path, ignore_errors=True)
            retry_command = [str(base_python), "-m", "venv", "--without-pip", str(app_env_path)]
            create = run_command(retry_command, context.repo_root)
            notes.append(command_summary("venv create without pip", retry_command, create))
        if create.returncode != 0:
            result = AppEnvBuildResult(False, False, app_env_path, base_python, source, build_report(context, app_env_path, base_python, source, notes, "venv creation failed"), "venv creation failed")
            write_app_env_report(context, result)
            return result

    env_python = app_env_python(app_env_path)
    if not env_python.is_file():
        result = AppEnvBuildResult(False, False, app_env_path, env_python, source, build_report(context, app_env_path, env_python, source, notes, "created app_env does not contain Scripts/python.exe"), "app_env python missing")
        write_app_env_report(context, result)
        return result

    install_path = install_requirements_path(requirements_path)
    if install_path and has_installable_requirements(install_path):
        pip_probe = run_command([str(env_python), "-m", "pip", "--version"], context.repo_root)
        notes.append(command_summary("pip probe", [str(env_python), "-m", "pip", "--version"], pip_probe))
        if pip_probe.returncode != 0:
            result = AppEnvBuildResult(False, False, app_env_path, env_python, source, build_report(context, app_env_path, env_python, source, notes, "pip is not available in the app_env"), "pip missing")
            write_app_env_report(context, result)
            return result
        install_command = [str(env_python), "-m", "pip", "install", "--disable-pip-version-check", "-r", str(install_path)]
        install = run_command(install_command, context.repo_root)
        notes.append(command_summary("pip install", install_command, install))
        if install.returncode != 0:
            cleanup_cache(app_env_path)
            result = AppEnvBuildResult(False, False, app_env_path, env_python, source, build_report(context, app_env_path, env_python, source, notes, "pip install failed"), "pip install failed")
            write_app_env_report(context, result)
            return result
    else:
        notes.append("No installable requirements were found. pip install was skipped.")

    packages = [package for package in (extra_packages or []) if package.strip()]
    if packages:
        pip_probe = run_command([str(env_python), "-m", "pip", "--version"], context.repo_root)
        notes.append(command_summary("pip probe for build tools", [str(env_python), "-m", "pip", "--version"], pip_probe))
        if pip_probe.returncode != 0:
            result = AppEnvBuildResult(False, False, app_env_path, env_python, source, build_report(context, app_env_path, env_python, source, notes, "pip is not available for build tool install"), "pip missing")
            write_app_env_report(context, result)
            return result
        install_tools_command = [str(env_python), "-m", "pip", "install", "--disable-pip-version-check", *packages]
        install_tools = run_command(install_tools_command, context.repo_root)
        notes.append(command_summary("pip install build tools", install_tools_command, install_tools))
        if install_tools.returncode != 0:
            cleanup_cache(app_env_path)
            result = AppEnvBuildResult(False, False, app_env_path, env_python, source, build_report(context, app_env_path, env_python, source, notes, "build tool install failed"), "build tool install failed")
            write_app_env_report(context, result)
            return result

    cleanup_cache(app_env_path)
    result = AppEnvBuildResult(True, False, app_env_path, env_python, source, build_report(context, app_env_path, env_python, source, notes, ""), "")
    write_app_env_report(context, result)
    return result


def create_build_env(context: StudioContext, requirements_path: Path, rebuild: bool = True) -> AppEnvBuildResult:
    build_env_path = context.output_dir / "build_env"
    assert_within(build_env_path, context.output_dir, "build_env target")

    if build_env_path.exists():
        if not rebuild:
            result = AppEnvBuildResult(
                ok=True,
                skipped=True,
                app_env_path=build_env_path,
                python_path=app_env_python(build_env_path),
                python_source="existing_build_env",
                report=build_report(
                    context,
                    build_env_path,
                    app_env_python(build_env_path),
                    "existing_build_env",
                    ["Existing build_env was kept because rebuild was not requested."],
                    "",
                    title="Build Env Report",
                ),
            )
            write_build_env_report(context, result)
            return result
        shutil.rmtree(build_env_path)

    base_python, source = select_base_python(context)
    notes = [
        "This is an internal build environment for PyInstaller.",
        "It is not a user-facing app_env and must not be packaged into final_app, App Pack, release, or runtime/app_envs.",
        f"Base Python source: {source}",
        f"Base Python: {base_python}",
    ]
    build_env_path.parent.mkdir(parents=True, exist_ok=True)

    create_command = [str(base_python), "-m", "venv", str(build_env_path)]
    create = run_command(create_command, context.repo_root)
    notes.append(command_summary("venv create", create_command, create))
    if create.returncode != 0:
        install_path = install_requirements_path(requirements_path)
        if "ensurepip" in create.stderr and not (install_path and has_installable_requirements(install_path)):
            if build_env_path.exists():
                shutil.rmtree(build_env_path, ignore_errors=True)
            retry_command = [str(base_python), "-m", "venv", "--without-pip", str(build_env_path)]
            create = run_command(retry_command, context.repo_root)
            notes.append(command_summary("venv create without pip", retry_command, create))
        if create.returncode != 0:
            result = AppEnvBuildResult(False, False, build_env_path, base_python, source, build_report(context, build_env_path, base_python, source, notes, "build_env venv creation failed", title="Build Env Report"), "build_env venv creation failed")
            write_build_env_report(context, result)
            return result

    env_python = app_env_python(build_env_path)
    if not env_python.is_file():
        result = AppEnvBuildResult(False, False, build_env_path, env_python, source, build_report(context, build_env_path, env_python, source, notes, "created build_env does not contain python", title="Build Env Report"), "build_env python missing")
        write_build_env_report(context, result)
        return result

    install_path = install_requirements_path(requirements_path)
    if install_path and has_installable_requirements(install_path):
        pip_probe = run_command([str(env_python), "-m", "pip", "--version"], context.repo_root)
        notes.append(command_summary("pip probe", [str(env_python), "-m", "pip", "--version"], pip_probe))
        if pip_probe.returncode != 0:
            result = AppEnvBuildResult(False, False, build_env_path, env_python, source, build_report(context, build_env_path, env_python, source, notes, "pip is not available in the build_env", title="Build Env Report"), "pip missing")
            write_build_env_report(context, result)
            return result
        install_command = [str(env_python), "-m", "pip", "install", "--disable-pip-version-check", "-r", str(install_path)]
        install = run_command(install_command, context.repo_root)
        notes.append(command_summary("pip install app requirements", install_command, install))
        if install.returncode != 0:
            cleanup_cache(build_env_path)
            result = AppEnvBuildResult(False, False, build_env_path, env_python, source, build_report(context, build_env_path, env_python, source, notes, "build_env app dependency install failed", title="Build Env Report"), "build_env app dependency install failed")
            write_build_env_report(context, result)
            return result
    else:
        notes.append("No installable app requirements were found. App dependency install was skipped.")

    cleanup_cache(build_env_path)
    result = AppEnvBuildResult(True, False, build_env_path, env_python, source, build_report(context, build_env_path, env_python, source, notes, "", title="Build Env Report"), "")
    write_build_env_report(context, result)
    return result


def install_build_tools(context: StudioContext, build_env_path: Path, packages: list[str]) -> AppEnvBuildResult:
    assert_within(build_env_path, context.output_dir, "build_env target")
    env_python = app_env_python(build_env_path)
    notes = [
        "Installing build-only dependencies into internal build_env.",
        "Build tools are not written to requirements.lock.",
        f"Packages: {', '.join(packages)}",
    ]
    if not env_python.is_file():
        result = AppEnvBuildResult(False, False, build_env_path, env_python, "build_env", build_report(context, build_env_path, env_python, "build_env", notes, "build_env python missing", title="Build Tool Install Report"), "build_env python missing")
        write_build_env_tools_report(context, result)
        return result

    pip_probe = run_command([str(env_python), "-m", "pip", "--version"], context.repo_root)
    notes.append(command_summary("pip probe for build tools", [str(env_python), "-m", "pip", "--version"], pip_probe))
    if pip_probe.returncode != 0:
        result = AppEnvBuildResult(False, False, build_env_path, env_python, "build_env", build_report(context, build_env_path, env_python, "build_env", notes, "pip is not available for build tool install", title="Build Tool Install Report"), "pip missing")
        write_build_env_tools_report(context, result)
        return result

    install_tools_command = [str(env_python), "-m", "pip", "install", "--disable-pip-version-check", *packages]
    install_tools = run_command(install_tools_command, context.repo_root)
    notes.append(command_summary("pip install build tools", install_tools_command, install_tools))
    if install_tools.returncode != 0:
        cleanup_cache(build_env_path)
        result = AppEnvBuildResult(False, False, build_env_path, env_python, "build_env", build_report(context, build_env_path, env_python, "build_env", notes, "build tool install failed", title="Build Tool Install Report"), "build tool install failed")
        write_build_env_tools_report(context, result)
        return result

    cleanup_cache(build_env_path)
    result = AppEnvBuildResult(True, False, build_env_path, env_python, "build_env", build_report(context, build_env_path, env_python, "build_env", notes, "", title="Build Tool Install Report"), "")
    write_build_env_tools_report(context, result)
    return result


def select_base_python(context: StudioContext) -> tuple[Path, str]:
    runtime_python = context.repo_root / "runtime" / "python" / "python.exe"
    if runtime_python.is_file():
        return runtime_python, "toolhub_runtime_python"
    return Path(sys.executable), "development_python_fallback"


def app_env_python(app_env_path: Path) -> Path:
    if os.name == "nt":
        return app_env_path / "Scripts" / "python.exe"
    return app_env_path / "bin" / "python"


def install_requirements_path(requirements_path: Path) -> Path | None:
    if requirements_path.name == "requirements.lock" and requirements_path.is_file():
        return requirements_path
    lock = requirements_path.parent / "requirements.lock"
    if lock.is_file():
        return lock
    if requirements_path.is_file():
        return requirements_path
    return None


def has_installable_requirements(path: Path) -> bool:
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip().lstrip("\ufeff")
        if stripped and not stripped.startswith("#"):
            return True
    return False


def run_command(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONNOUSERSITE"] = "1"
    return subprocess.run(command, cwd=str(cwd), text=True, encoding="utf-8", errors="replace", stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, env=env)


def command_summary(label: str, command: list[str], completed: subprocess.CompletedProcess[str]) -> str:
    command_text = " ".join(command)
    stdout = completed.stdout[-4000:].strip()
    stderr = completed.stderr[-4000:].strip()
    return f"{label}: exit_code={completed.returncode}\ncommand: {command_text}\nstdout:\n{stdout}\nstderr:\n{stderr}"


def cleanup_cache(app_env_path: Path) -> None:
    for cache_dir in app_env_path.rglob("__pycache__"):
        if cache_dir.is_dir():
            shutil.rmtree(cache_dir, ignore_errors=True)
    for file in app_env_path.rglob("*.pyc"):
        try:
            file.unlink()
        except OSError:
            pass


def build_report(context: StudioContext, app_env_path: Path, python_path: Path | None, source: str, notes: list[str], error: str, title: str = "App Env Build Report") -> str:
    status = "FAIL" if error else "PASS"
    lines = [
        f"# {title}",
        "",
        f"- app_id: `{context.app_id}`",
        f"- status: `{status}`",
        f"- app_env_path: `{app_env_path}`",
        f"- python_path: `{python_path}`",
        f"- python_source: `{source}`",
        "",
        "## Notes",
        "",
    ]
    lines.extend(f"- {note}" for note in notes)
    if error:
        lines.extend(["", "## Error", "", error])
    return "\n".join(lines) + "\n"


def write_app_env_report(context: StudioContext, result: AppEnvBuildResult) -> None:
    write_text(context.output_dir / "app_env_build_report.md", result.report)
    write_text(context.repo_root / "data" / "logs" / "app_studio" / f"{context.app_id}_app_env_build_report.md", result.report)


def write_build_env_report(context: StudioContext, result: AppEnvBuildResult) -> None:
    write_text(context.output_dir / "build_env_report.md", result.report)
    write_text(context.repo_root / "data" / "logs" / "app_studio" / f"{context.app_id}_build_env_report.md", result.report)


def write_build_env_tools_report(context: StudioContext, result: AppEnvBuildResult) -> None:
    write_text(context.output_dir / "build_tool_install_report.md", result.report)
    write_text(context.repo_root / "data" / "logs" / "app_studio" / f"{context.app_id}_build_tool_install_report.md", result.report)
