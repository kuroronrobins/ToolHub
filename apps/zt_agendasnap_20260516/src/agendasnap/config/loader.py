"""YAML configuration loader.

The bundled ``default.yaml`` is an application default. User-specific settings
such as glossary entries and UI preferences are stored in a separate user config
and deep-merged on top of the defaults during normal startup.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

import yaml


USER_CONFIG_ENV_VAR = "AGENDASNAP_USER_CONFIG"
DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent / "default.yaml"
SENSITIVE_TOP_LEVEL_KEYS = {"secrets"}
SENSITIVE_LEAF_KEYS = {
    "api_key",
    "api_secret",
    "access_token",
    "refresh_token",
    "token",
    "password",
    "secret",
}


def default_user_config_path() -> Path:
    override = os.environ.get(USER_CONFIG_ENV_VAR)
    if override:
        return Path(override).expanduser()
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / "AgendaSnap" / "config.yaml"
    return Path.home() / ".config" / "AgendaSnap" / "config.yaml"


def is_default_config_path(path: Path) -> bool:
    try:
        return Path(path).resolve() == DEFAULT_CONFIG_PATH.resolve()
    except OSError:
        return False


def should_use_user_config(path: Path, include_user_config: bool | None = None) -> bool:
    if include_user_config is not None:
        return bool(include_user_config)
    return is_default_config_path(path)


def _read_yaml_mapping(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    if not isinstance(cfg, dict):
        raise ValueError(f"Config root must be a mapping, got {type(cfg).__name__}")
    return cfg


def _write_yaml_mapping(path: Path, cfg: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.tmp")
    tmp_path.write_text(
        yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    os.replace(tmp_path, path)


def deep_merge_config(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    result = dict(base)
    for key, value in override.items():
        existing = result.get(key)
        if isinstance(existing, dict) and isinstance(value, dict):
            result[key] = deep_merge_config(existing, value)
        else:
            result[key] = value
    return result


def load_config(
    path: Path,
    *,
    user_config_path: Path | None = None,
    include_user_config: bool | None = None,
) -> Dict[str, Any]:
    cfg = _read_yaml_mapping(Path(path))
    if not should_use_user_config(Path(path), include_user_config):
        return cfg

    user_path = user_config_path or default_user_config_path()
    if not user_path.exists():
        return cfg
    user_cfg = _read_yaml_mapping(user_path)
    return deep_merge_config(cfg, sanitize_user_config(user_cfg))


def sanitize_user_config(cfg: Dict[str, Any]) -> Dict[str, Any]:
    clean: Dict[str, Any] = {}
    for key, value in cfg.items():
        key_text = str(key)
        if key_text in SENSITIVE_TOP_LEVEL_KEYS:
            continue
        if key_text.lower() in SENSITIVE_LEAF_KEYS:
            continue
        if isinstance(value, dict):
            nested = sanitize_user_config(value)
            if nested:
                clean[key] = nested
        else:
            clean[key] = value
    return clean


def diff_config(base: Dict[str, Any], desired: Dict[str, Any]) -> Dict[str, Any]:
    patch: Dict[str, Any] = {}
    for key, value in desired.items():
        if key not in base:
            patch[key] = value
            continue
        base_value = base[key]
        if isinstance(base_value, dict) and isinstance(value, dict):
            nested = diff_config(base_value, value)
            if nested:
                patch[key] = nested
        elif value != base_value:
            patch[key] = value
    return patch


def user_config_write_path(
    base_path: Path,
    *,
    user_config_path: Path | None = None,
    include_user_config: bool | None = None,
) -> Path:
    if should_use_user_config(Path(base_path), include_user_config):
        return user_config_path or default_user_config_path()
    return Path(base_path)


def save_config(
    path: Path,
    cfg: Dict[str, Any],
    *,
    user_config_path: Path | None = None,
    include_user_config: bool | None = None,
) -> Path:
    base_path = Path(path)
    if should_use_user_config(base_path, include_user_config):
        base_cfg = _read_yaml_mapping(base_path)
        clean_cfg = sanitize_user_config(cfg)
        patch = diff_config(sanitize_user_config(base_cfg), clean_cfg)
        write_path = user_config_path or default_user_config_path()
        _write_yaml_mapping(write_path, patch)
        return write_path

    write_path = base_path
    _write_yaml_mapping(write_path, cfg)
    return write_path
