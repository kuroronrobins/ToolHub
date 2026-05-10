from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any

from .models import NORMAL_REGISTRATION_POLICY, StudioContext


APP_STUDIO_POLICY_ID = "normal_python_source_to_shared_versioned_runtime_v1"
BUILD_ENV_DIRNAME = "be"
BUILD_TMP_DIRNAME = "bt"
TRACE_KEYS = {
    "app_studio_cli_path",
    "app_studio_policy_id",
    "registration_policy",
    "repo_root",
    "git_commit",
    "main_py_hash",
    "frozen_folder_builder_hash",
    "argv",
    "normalized_options",
    "source_entry",
    "source_root",
    "source_root_origin",
    "source_root_warnings",
    "output_dir",
    "build_env_path",
    "build_env_python",
    "pyinstaller_probe_python",
    "pyinstaller_build_python",
}


def planned_build_env_path(context: StudioContext) -> Path:
    return context.output_dir / BUILD_ENV_DIRNAME


def planned_build_tmp_path(context: StudioContext) -> Path:
    return context.output_dir / BUILD_TMP_DIRNAME


def planned_pip_cache_dir(context: StudioContext) -> Path:
    return planned_build_tmp_path(context) / "pip"


def planned_build_env_python(context: StudioContext) -> Path:
    scripts = "Scripts" if os.name == "nt" else "bin"
    python = "python.exe" if os.name == "nt" else "python"
    return planned_build_env_path(context) / scripts / python


def is_runtime_app_env_path(repo_root: Path, path: Path | None) -> bool:
    if path is None:
        return False
    try:
        path.resolve().relative_to((repo_root / "runtime" / "app_envs").resolve())
        return True
    except ValueError:
        return False


def app_studio_trace(
    context: StudioContext,
    args: Any | None = None,
    *,
    build_env_python: Path | None = None,
    pyinstaller_probe_python: Path | None = None,
    pyinstaller_build_python: Path | None = None,
) -> dict[str, Any]:
    main_py = Path(__file__).resolve().parents[1] / "main.py"
    frozen_builder = Path(__file__).resolve().parent / "frozen_folder_builder.py"
    return {
        "app_studio_cli_path": str(main_py),
        "app_studio_policy_id": APP_STUDIO_POLICY_ID,
        "registration_policy": NORMAL_REGISTRATION_POLICY,
        "repo_root": str(context.repo_root),
        "git_commit": git_commit(context.repo_root),
        "main_py_hash": file_sha256_or_unknown(main_py),
        "frozen_folder_builder_hash": file_sha256_or_unknown(frozen_builder),
        "argv": list(getattr(args, "_raw_argv", []) or []),
        "normalized_options": normalized_options(args),
        "source_entry": str(context.entry),
        "source_root": str(context.source_root),
        "source_root_origin": context.source_root_origin,
        "source_root_warnings": context.source_root_warnings,
        "output_dir": str(context.output_dir),
        "build_env_path": str(planned_build_env_path(context)),
        "build_env_python": str(build_env_python or planned_build_env_python(context)),
        "pyinstaller_probe_python": str(pyinstaller_probe_python) if pyinstaller_probe_python else None,
        "pyinstaller_build_python": str(pyinstaller_build_python) if pyinstaller_build_python else None,
    }


def normalized_options(args: Any | None) -> dict[str, Any]:
    if args is None:
        return {}
    names = [
        "build_mode",
        "source_root",
        "create_app_env",
        "rebuild_app_env",
        "skip_app_env_build",
        "generate_lock",
        "skip_lock",
        "build_frozen_folder",
        "rebuild_frozen_folder",
        "skip_frozen_build",
        "verify_runtime",
    ]
    return {name: getattr(args, name, None) for name in names}


def merge_trace_into_import_plan(output_dir: Path, trace: dict[str, Any]) -> None:
    path = output_dir / "import_plan.json"
    if not path.is_file():
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return
    if not isinstance(data, dict):
        return
    data.update(trace)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def trace_with_import_plan(context: StudioContext, output_dir: Path) -> dict[str, Any]:
    trace = app_studio_trace(context)
    path = output_dir / "import_plan.json"
    if not path.is_file():
        return trace
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return trace
    if not isinstance(data, dict):
        return trace
    for key in TRACE_KEYS:
        value = data.get(key)
        if value not in (None, ""):
            trace[key] = value
    return trace


def file_sha256_or_unknown(path: Path) -> str:
    if not path.is_file():
        return "unknown"
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_commit(repo_root: Path) -> str:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(repo_root),
            text=True,
            capture_output=True,
            check=False,
            timeout=5,
        )
    except Exception:
        return "unknown"
    if completed.returncode != 0:
        return "unknown"
    return completed.stdout.strip() or "unknown"
