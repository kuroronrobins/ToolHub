"""Runtime path helpers for writable AgendaSnap user data."""

from __future__ import annotations

import os
from pathlib import Path


DATA_DIR_ENV_VAR = "AGENDASNAP_DATA_DIR"


def default_user_data_dir() -> Path:
    override = os.environ.get(DATA_DIR_ENV_VAR)
    if override:
        return Path(override).expanduser()

    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        return Path(local_appdata) / "AgendaSnap"

    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / "AgendaSnap"

    return Path.home() / ".local" / "share" / "AgendaSnap"


def resolve_user_data_path(value: object, *, default_name: str) -> Path:
    text = str(value or default_name).strip() or default_name
    path = Path(text).expanduser()
    if path.is_absolute():
        return path
    return default_user_data_dir() / path


def resolve_session_root(value: object = "sessions") -> Path:
    return resolve_user_data_path(value, default_name="sessions")
