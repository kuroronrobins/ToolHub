from __future__ import annotations

import os
from pathlib import Path

from .manifest import AppManifest


def build_app_env(project_root: Path, manifest: AppManifest) -> dict[str, str]:
    env = os.environ.copy()
    env["TOOLHUB_ROOT"] = str(project_root)
    env["TOOLHUB_APP_ID"] = manifest.id
    env["TOOLHUB_APP_DIR"] = str(manifest.app_dir)
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def browser_profile_dir(project_root: Path, app_id: str) -> Path:
    base = Path(os.environ.get("TOOLHUB_USER_DATA_ROOT", project_root))
    path = base / "data" / "browser_profiles" / app_id
    path.mkdir(parents=True, exist_ok=True)
    return path
