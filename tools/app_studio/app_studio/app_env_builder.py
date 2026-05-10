from __future__ import annotations

import os
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from .models import AppEnvBuildResult, StudioContext
from .trace import planned_build_env_path, planned_build_tmp_path, planned_pip_cache_dir
from .util import assert_within, file_sha256, now_iso, timestamp, write_json, write_text


BUILD_ENV_CACHE_SCHEMA_VERSION = 1


def create_app_env(context: StudioContext, requirements_path: Path, rebuild: bool = False, extra_packages: list[str] | None = None) -> AppEnvBuildResult:
    app_env_root = context.repo_root / "runtime" / "app_envs"
    app_env_path = app_env_root / context.app_id
    temp_dir = context.repo_root / "data" / "tmp" / "app_studio_env"
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

    create_error = create_venv_with_pip(base_python, app_env_path, context.repo_root, temp_dir, notes)
    if create_error:
        result = AppEnvBuildResult(False, False, app_env_path, base_python, source, build_report(context, app_env_path, base_python, source, notes, create_error), create_error)
        write_app_env_report(context, result)
        return result

    env_python = app_env_python(app_env_path)
    if not env_python.is_file():
        result = AppEnvBuildResult(False, False, app_env_path, env_python, source, build_report(context, app_env_path, env_python, source, notes, "created app_env does not contain Scripts/python.exe"), "app_env python missing")
        write_app_env_report(context, result)
        return result

    install_path = install_requirements_path(requirements_path)
    if install_path and has_installable_requirements(install_path):
        pip_probe = run_command([str(env_python), "-m", "pip", "--version"], context.repo_root, temp_dir)
        notes.append(command_summary("pip probe", [str(env_python), "-m", "pip", "--version"], pip_probe))
        if pip_probe.returncode != 0:
            result = AppEnvBuildResult(False, False, app_env_path, env_python, source, build_report(context, app_env_path, env_python, source, notes, "pip is not available in the app_env"), "pip missing")
            write_app_env_report(context, result)
            return result
        install_command = [str(env_python), "-m", "pip", "install", "--disable-pip-version-check", "-r", str(install_path)]
        install = run_command(install_command, context.repo_root, temp_dir)
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
        pip_probe = run_command([str(env_python), "-m", "pip", "--version"], context.repo_root, temp_dir)
        notes.append(command_summary("pip probe for build tools", [str(env_python), "-m", "pip", "--version"], pip_probe))
        if pip_probe.returncode != 0:
            result = AppEnvBuildResult(False, False, app_env_path, env_python, source, build_report(context, app_env_path, env_python, source, notes, "pip is not available for build tool install"), "pip missing")
            write_app_env_report(context, result)
            return result
        install_tools_command = [str(env_python), "-m", "pip", "install", "--disable-pip-version-check", *packages]
        install_tools = run_command(install_tools_command, context.repo_root, temp_dir)
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


def create_build_env(
    context: StudioContext,
    requirements_path: Path,
    rebuild: bool = True,
    allow_cache: bool = False,
    build_profile_hash: str = "",
    build_tools_packages: list[str] | None = None,
) -> AppEnvBuildResult:
    build_env_path = planned_build_env_path(context)
    temp_dir = planned_build_tmp_path(context)
    pip_cache = pip_cache_dir(context)
    assert_within(build_env_path, context.output_dir, "build_env target")

    base_python, source = select_base_python(context)
    base_python_version = python_version_text(base_python, context.repo_root, temp_dir)
    install_path = install_requirements_path(requirements_path)
    key_parts = build_env_cache_key_parts(
        context=context,
        requirements_path=requirements_path,
        install_path=install_path,
        base_python=base_python,
        base_python_version=base_python_version,
        build_profile_hash=build_profile_hash,
        build_tools_packages=build_tools_packages or [],
    )
    cache_key = build_env_cache_key(key_parts)
    metadata_path = build_env_cache_metadata_path(build_env_path)
    cache_miss_reason = "build_env does not exist"

    if build_env_path.exists():
        if allow_cache:
            cache_hit, cache_miss_reason = validate_build_env_cache(
                context=context,
                build_env_path=build_env_path,
                expected_cache_key=cache_key,
                expected_key_parts=key_parts,
                temp_dir=temp_dir,
            )
            if cache_hit:
                env_python = app_env_python(build_env_path)
                result = AppEnvBuildResult(
                    ok=True,
                    skipped=True,
                    app_env_path=build_env_path,
                    python_path=env_python,
                    python_source="cached_build_env",
                    report=build_report(
                        context,
                        build_env_path,
                        env_python,
                        "cached_build_env",
                        [
                            "Existing build_env cache was reused.",
                            f"cache_key: {cache_key}",
                            f"cache_metadata: {metadata_path}",
                            f"pip_cache_dir: {pip_cache}",
                        ],
                        "",
                        title="Build Env Report",
                    ),
                    cache_hit=True,
                    cache_key=cache_key,
                    metadata_path=metadata_path,
                    pip_cache_dir=pip_cache,
                )
                write_build_env_report(context, result)
                return result
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
                cache_hit=False,
                cache_miss_reason="cache validation was not requested",
                cache_key=cache_key,
                metadata_path=metadata_path,
                pip_cache_dir=pip_cache,
            )
            write_build_env_report(context, result)
            return result
        if not allow_cache:
            cache_miss_reason = "cache disabled by request"
        shutil.rmtree(build_env_path)

    notes = [
        "This is an internal build environment for PyInstaller.",
        "It is not a user-facing app_env and must not be packaged into final_app, App Pack, release, or runtime/app_envs.",
        f"build_env_cache_hit: {False}",
        f"build_env_cache_miss_reason: {cache_miss_reason}",
        f"cache_key: {cache_key}",
        f"cache_metadata: {metadata_path}",
        f"pip_cache_dir: {pip_cache}",
        f"Base Python source: {source}",
        f"Base Python: {base_python}",
        f"Base Python version: {base_python_version}",
    ]
    build_env_path.parent.mkdir(parents=True, exist_ok=True)

    create_error = create_venv_with_pip(base_python, build_env_path, context.repo_root, temp_dir, notes)
    if create_error:
        result = AppEnvBuildResult(False, False, build_env_path, base_python, source, build_report(context, build_env_path, base_python, source, notes, create_error, title="Build Env Report"), create_error, False, cache_miss_reason, cache_key, metadata_path, pip_cache)
        write_build_env_report(context, result)
        return result

    env_python = app_env_python(build_env_path)
    if not env_python.is_file():
        result = AppEnvBuildResult(False, False, build_env_path, env_python, source, build_report(context, build_env_path, env_python, source, notes, "created build_env does not contain python", title="Build Env Report"), "build_env python missing", False, cache_miss_reason, cache_key, metadata_path, pip_cache)
        write_build_env_report(context, result)
        return result

    if install_path and has_installable_requirements(install_path):
        pip_probe = run_command([str(env_python), "-m", "pip", "--version"], context.repo_root, temp_dir, pip_cache_dir=pip_cache)
        notes.append(command_summary("pip probe", [str(env_python), "-m", "pip", "--version"], pip_probe))
        if pip_probe.returncode != 0:
            result = AppEnvBuildResult(False, False, build_env_path, env_python, source, build_report(context, build_env_path, env_python, source, notes, "pip is not available in the build_env", title="Build Env Report"), "pip missing", False, cache_miss_reason, cache_key, metadata_path, pip_cache)
            write_build_env_report(context, result)
            return result
        install_command = [str(env_python), "-m", "pip", "install", "--disable-pip-version-check", "-r", str(install_path)]
        install = run_command(install_command, context.repo_root, temp_dir, pip_cache_dir=pip_cache)
        notes.append(command_summary("pip install app requirements", install_command, install))
        if install.returncode != 0:
            cleanup_cache(build_env_path)
            result = AppEnvBuildResult(False, False, build_env_path, env_python, source, build_report(context, build_env_path, env_python, source, notes, "build_env app dependency install failed", title="Build Env Report"), "build_env app dependency install failed", False, cache_miss_reason, cache_key, metadata_path, pip_cache)
            write_build_env_report(context, result)
            return result
    else:
        notes.append("No installable app requirements were found. App dependency install was skipped.")

    cleanup_cache(build_env_path)
    metadata = {
        "schema_version": BUILD_ENV_CACHE_SCHEMA_VERSION,
        "created_at": now_iso(),
        "app_id": context.app_id,
        "cache_key": cache_key,
        "key_parts": key_parts,
        "pip_cache_dir": str(pip_cache),
    }
    write_json(metadata_path, metadata)
    result = AppEnvBuildResult(True, False, build_env_path, env_python, source, build_report(context, build_env_path, env_python, source, notes, "", title="Build Env Report"), "", False, cache_miss_reason, cache_key, metadata_path, pip_cache)
    write_build_env_report(context, result)
    return result


def install_build_tools(context: StudioContext, build_env_path: Path, packages: list[str]) -> AppEnvBuildResult:
    assert_within(build_env_path, context.output_dir, "build_env target")
    temp_dir = planned_build_tmp_path(context)
    pip_cache = pip_cache_dir(context)
    env_python = app_env_python(build_env_path)
    notes = [
        "Installing build-only dependencies into internal build_env.",
        "Build tools are not written to requirements.lock.",
        f"Packages: {', '.join(packages)}",
        f"pip_cache_dir: {pip_cache}",
    ]
    if not env_python.is_file():
        result = AppEnvBuildResult(False, False, build_env_path, env_python, "build_env", build_report(context, build_env_path, env_python, "build_env", notes, "build_env python missing", title="Build Tool Install Report"), "build_env python missing", pip_cache_dir=pip_cache)
        write_build_env_tools_report(context, result)
        return result

    pip_probe = run_command([str(env_python), "-m", "pip", "--version"], context.repo_root, temp_dir, pip_cache_dir=pip_cache)
    notes.append(command_summary("pip probe for build tools", [str(env_python), "-m", "pip", "--version"], pip_probe))
    if pip_probe.returncode != 0:
        result = AppEnvBuildResult(False, False, build_env_path, env_python, "build_env", build_report(context, build_env_path, env_python, "build_env", notes, "pip is not available for build tool install", title="Build Tool Install Report"), "pip missing", pip_cache_dir=pip_cache)
        write_build_env_tools_report(context, result)
        return result

    tool_status = build_tool_status(context, env_python, packages, temp_dir)
    notes.append(tool_status["summary"])
    if tool_status["satisfied"]:
        result = AppEnvBuildResult(
            True,
            True,
            build_env_path,
            env_python,
            "build_env",
            build_report(context, build_env_path, env_python, "build_env", notes + ["Build tool install skipped because installed versions satisfy requested specs."], "", title="Build Tool Install Report"),
            "",
            pip_cache_dir=pip_cache,
        )
        write_build_env_tools_report(context, result)
        update_build_env_cache_metadata(build_env_path, {"build_tools": tool_status})
        return result

    install_tools_command = [str(env_python), "-m", "pip", "install", "--disable-pip-version-check", *packages]
    install_tools = run_command(install_tools_command, context.repo_root, temp_dir, pip_cache_dir=pip_cache)
    notes.append(command_summary("pip install build tools", install_tools_command, install_tools))
    if install_tools.returncode != 0:
        cleanup_cache(build_env_path)
        result = AppEnvBuildResult(False, False, build_env_path, env_python, "build_env", build_report(context, build_env_path, env_python, "build_env", notes, "build tool install failed", title="Build Tool Install Report"), "build tool install failed", pip_cache_dir=pip_cache)
        write_build_env_tools_report(context, result)
        return result

    tool_status_after = build_tool_status(context, env_python, packages, temp_dir)
    notes.append(tool_status_after["summary"])
    cleanup_cache(build_env_path)
    result = AppEnvBuildResult(True, False, build_env_path, env_python, "build_env", build_report(context, build_env_path, env_python, "build_env", notes, "", title="Build Tool Install Report"), "", pip_cache_dir=pip_cache)
    write_build_env_tools_report(context, result)
    update_build_env_cache_metadata(build_env_path, {"build_tools": tool_status_after})
    return result


def pip_cache_dir(context: StudioContext) -> Path:
    return planned_pip_cache_dir(context)


def build_env_cache_metadata_path(build_env_path: Path) -> Path:
    return build_env_path / "toolhub_build_env_cache.json"


def build_env_cache_key_parts(
    context: StudioContext,
    requirements_path: Path,
    install_path: Path | None,
    base_python: Path,
    base_python_version: str,
    build_profile_hash: str,
    build_tools_packages: list[str],
) -> dict[str, Any]:
    if install_path and install_path.is_file():
        requirements_hash = file_sha256(install_path)
        requirements_source = str(install_path)
    else:
        requirements_hash = ""
        requirements_source = "none"
    return {
        "schema_version": BUILD_ENV_CACHE_SCHEMA_VERSION,
        "app_id": context.app_id,
        "requirements_path": str(requirements_path),
        "requirements_install_source": requirements_source,
        "requirements_hash": requirements_hash,
        "python_executable": str(base_python.resolve()),
        "python_version": base_python_version,
        "build_tools_packages": [package.strip() for package in build_tools_packages if package.strip()],
        "build_profile_hash": build_profile_hash,
    }


def build_env_cache_key(key_parts: dict[str, Any]) -> str:
    payload = json.dumps(key_parts, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def validate_build_env_cache(
    context: StudioContext,
    build_env_path: Path,
    expected_cache_key: str,
    expected_key_parts: dict[str, Any],
    temp_dir: Path,
) -> tuple[bool, str]:
    env_python = app_env_python(build_env_path)
    if not env_python.is_file():
        return False, "build_env python is missing"
    metadata_path = build_env_cache_metadata_path(build_env_path)
    if not metadata_path.is_file():
        return False, "cache metadata is missing"
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except Exception:
        return False, "cache metadata is invalid JSON"
    if metadata.get("schema_version") != BUILD_ENV_CACHE_SCHEMA_VERSION:
        return False, "cache metadata schema_version mismatch"
    if metadata.get("cache_key") != expected_cache_key:
        return False, "cache key mismatch"
    if metadata.get("key_parts") != expected_key_parts:
        return False, "cache key parts mismatch"
    pip_probe = run_command([str(env_python), "-m", "pip", "--version"], context.repo_root, temp_dir, pip_cache_dir=pip_cache_dir(context))
    if pip_probe.returncode != 0:
        return False, "cached build_env pip probe failed"
    env_version = python_version_text(env_python, context.repo_root, temp_dir)
    if env_version != expected_key_parts.get("python_version"):
        return False, "cached build_env python version mismatch"
    return True, ""


def update_build_env_cache_metadata(build_env_path: Path, updates: dict[str, Any]) -> None:
    metadata_path = build_env_cache_metadata_path(build_env_path)
    if not metadata_path.is_file():
        return
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except Exception:
        return
    metadata.update(updates)
    metadata["updated_at"] = now_iso()
    write_json(metadata_path, metadata)


def python_version_text(python_path: Path, cwd: Path, temp_dir: Path) -> str:
    completed = run_command([str(python_path), "--version"], cwd, temp_dir)
    text = (completed.stdout or completed.stderr).strip()
    return text if completed.returncode == 0 and text else "unknown"


def build_tool_status(context: StudioContext, env_python: Path, packages: list[str], temp_dir: Path) -> dict[str, Any]:
    script = "\n".join(
        [
            "import importlib.metadata as metadata",
            "import json",
            "import sys",
            "result = {}",
            "for name in sys.argv[1:]:",
            "    try:",
            "        result[name] = metadata.version(name)",
            "    except metadata.PackageNotFoundError:",
            "        result[name] = None",
            "print(json.dumps(result, sort_keys=True))",
        ]
    )
    package_names = [package_name_from_spec(package) for package in packages]
    probe = run_command([str(env_python), "-c", script, *package_names], context.repo_root, temp_dir, pip_cache_dir=pip_cache_dir(context))
    versions: dict[str, str | None] = {}
    if probe.returncode == 0:
        try:
            versions = json.loads(probe.stdout.strip() or "{}")
        except Exception:
            versions = {}
    details = []
    satisfied = probe.returncode == 0
    for spec in packages:
        name = package_name_from_spec(spec)
        version = versions.get(name)
        ok = bool(version) and version_satisfies(str(version), spec)
        if not ok:
            satisfied = False
        details.append({"spec": spec, "package": name, "installed_version": version or "", "satisfied": ok})
    return {
        "satisfied": satisfied,
        "packages": details,
        "probe_exit_code": probe.returncode,
        "summary": "build tool version check: " + json.dumps(details, ensure_ascii=False, sort_keys=True),
    }


def package_name_from_spec(spec: str) -> str:
    return re.split(r"\s*(?:===|==|~=|!=|<=|>=|<|>|;|\[)", spec.strip(), maxsplit=1)[0].strip()


def version_satisfies(version: str, spec: str) -> bool:
    constraints = spec[len(package_name_from_spec(spec)):].strip()
    if not constraints:
        return True
    for raw_part in constraints.split(","):
        part = raw_part.strip()
        if not part or part.startswith(";"):
            continue
        match = re.match(r"(===|==|<=|>=|<|>|~=)\s*(.+)", part)
        if not match:
            return False
        operator, expected = match.groups()
        comparison = compare_versions(version, expected)
        if operator in {"==", "==="} and comparison != 0:
            return False
        if operator == ">=" and comparison < 0:
            return False
        if operator == ">" and comparison <= 0:
            return False
        if operator == "<=" and comparison > 0:
            return False
        if operator == "<" and comparison >= 0:
            return False
        if operator == "~=" and comparison < 0:
            return False
    return True


def compare_versions(left: str, right: str) -> int:
    left_parts = version_parts(left)
    right_parts = version_parts(right)
    max_len = max(len(left_parts), len(right_parts))
    left_parts.extend([0] * (max_len - len(left_parts)))
    right_parts.extend([0] * (max_len - len(right_parts)))
    if left_parts == right_parts:
        return 0
    return 1 if left_parts > right_parts else -1


def version_parts(value: str) -> list[int]:
    parts = [int(part) for part in re.findall(r"\d+", value)]
    return parts or [0]


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


def create_venv_with_pip(base_python: Path, env_path: Path, cwd: Path, temp_dir: Path, notes: list[str]) -> str:
    create_command = [str(base_python), "-m", "venv", str(env_path)]
    create = run_command(create_command, cwd, temp_dir)
    notes.append(command_summary("venv create", create_command, create))
    if create.returncode == 0:
        return ""

    combined = f"{create.stdout}\n{create.stderr}"
    if "ensurepip" not in combined:
        return "venv creation failed"

    if env_path.exists():
        shutil.rmtree(env_path, ignore_errors=True)
    retry_command = [str(base_python), "-m", "venv", "--without-pip", str(env_path)]
    retry = run_command(retry_command, cwd, temp_dir)
    notes.append(command_summary("venv create without pip", retry_command, retry))
    if retry.returncode != 0:
        return "venv creation failed"

    env_python = app_env_python(env_path)
    if not env_python.is_file():
        return "venv python missing after --without-pip fallback"

    ensurepip_command = [str(env_python), "-m", "ensurepip", "--upgrade", "--default-pip"]
    ensurepip = run_command(ensurepip_command, cwd, temp_dir)
    notes.append(command_summary("ensurepip bootstrap", ensurepip_command, ensurepip))
    if ensurepip.returncode != 0:
        return "pip bootstrap failed"
    return ""


def has_installable_requirements(path: Path) -> bool:
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip().lstrip("\ufeff")
        if stripped and not stripped.startswith("#"):
            return True
    return False


def run_command(
    command: list[str],
    cwd: Path,
    temp_dir: Path | None = None,
    pip_cache_dir: Path | None = None,
    disable_pip_cache: bool = True,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONNOUSERSITE"] = "1"
    if temp_dir is not None:
        temp_dir.mkdir(parents=True, exist_ok=True)
        env["TEMP"] = str(temp_dir)
        env["TMP"] = str(temp_dir)
        env["TMPDIR"] = str(temp_dir)
        if pip_cache_dir is not None:
            pip_cache_dir.mkdir(parents=True, exist_ok=True)
            env["PIP_CACHE_DIR"] = str(pip_cache_dir)
            env.pop("PIP_NO_CACHE_DIR", None)
        elif disable_pip_cache:
            env["PIP_NO_CACHE_DIR"] = "1"
        patch_dir = python_startup_patch_dir(temp_dir)
        existing_pythonpath = env.get("PYTHONPATH")
        env["PYTHONPATH"] = str(patch_dir) if not existing_pythonpath else str(patch_dir) + os.pathsep + existing_pythonpath
    return subprocess.run(command, cwd=str(cwd), text=True, encoding="utf-8", errors="replace", stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, env=env)


def python_startup_patch_dir(temp_dir: Path) -> Path:
    patch_dir = temp_dir / "python_startup_patch"
    patch_dir.mkdir(parents=True, exist_ok=True)
    patch = patch_dir / "sitecustomize.py"
    if os.name == "nt":
        patch.write_text(
            "\n".join(
                [
                    "import os",
                    "_toolhub_original_mkdir = os.mkdir",
                    "",
                    "def _toolhub_mkdir(path, mode=0o777, *args, **kwargs):",
                    "    return _toolhub_original_mkdir(path, 0o777, *args, **kwargs)",
                    "",
                    "os.mkdir = _toolhub_mkdir",
                    "",
                ]
            ),
            encoding="utf-8",
        )
    elif not patch.exists():
        patch.write_text("# ToolHub App Studio build_env startup hook.\n", encoding="utf-8")
    return patch_dir


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
