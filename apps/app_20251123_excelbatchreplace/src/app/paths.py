from __future__ import annotations

import os
from pathlib import Path

APP_DATA_DIR_NAME = "ExcelBatchReplace"
TOOLHUB_APP_DIR_ENV = "TOOLHUB_APP_DIR"


def app_root() -> Path:
    """Return the read-only application source/package root."""
    toolhub_app_dir = os.environ.get(TOOLHUB_APP_DIR_ENV)
    if toolhub_app_dir:
        return Path(toolhub_app_dir).resolve()
    return Path(__file__).resolve().parents[1]


def _local_app_data_base() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data)
    return Path.home() / "AppData" / "Local"


def user_data_root(create: bool = True) -> Path:
    path = _local_app_data_base() / APP_DATA_DIR_NAME
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def user_cache_dir(create: bool = True) -> Path:
    path = user_data_root(create=create) / "cache"
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def user_templates_dir(create: bool = True) -> Path:
    path = user_data_root(create=create) / "templates"
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def default_file_dialog_dir() -> Path:
    documents = Path.home() / "Documents"
    if documents.exists():
        return documents
    return Path.home()


def setting_workbook_path() -> Path:
    return app_root() / "Setting.xlsx"
