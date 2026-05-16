from __future__ import annotations

import json
import os
from copy import deepcopy
from typing import Any


_APP_DIR_NAME = "XCgate_AutoUpload"
_STORE_FILE_NAME = "xcgate_profiles.json"
_STORE_VERSION = 1

DEFAULT_PROFILES: dict[str, Any] = {
    "version": _STORE_VERSION,
    "last_profile": "prod",
    "profiles": {
        "prod": {
            "label": "本番環境",
            "url": "http://10.9.220.35/xcent/app/C1000/login/?companyCd=C1000",
            "credential_target": "XCgate_AutoUpload/prod/C1000",
        },
        "test": {
            "label": "テスト環境",
            "url": "http://192.168.1.35/xcent/app/C1000/login/?companyCd=C1000",
            "credential_target": "XCgate_AutoUpload/test/C1000",
        },
    },
}


def resolve_profiles_path(path: str | None = None) -> str:
    if path:
        return path
    appdata = os.environ.get("APPDATA")
    if not appdata:
        appdata = os.path.join(os.path.expanduser("~"), "AppData", "Roaming")
    return os.path.join(appdata, _APP_DIR_NAME, _STORE_FILE_NAME)


def _default_store() -> dict[str, Any]:
    return deepcopy(DEFAULT_PROFILES)


def _normalize_store(data: dict[str, Any] | None) -> dict[str, Any]:
    base = _default_store()
    if not isinstance(data, dict):
        return base

    profiles = data.get("profiles")
    if isinstance(profiles, dict):
        for key, value in profiles.items():
            if not isinstance(key, str) or not isinstance(value, dict):
                continue
            current = base["profiles"].setdefault(key, {})
            for item_key in ("label", "url", "credential_target"):
                item_value = value.get(item_key)
                if item_value is not None:
                    current[item_key] = str(item_value)

    last_profile = data.get("last_profile")
    if isinstance(last_profile, str) and last_profile in base["profiles"]:
        base["last_profile"] = last_profile
    for built_in_key in ("prod", "test"):
        if built_in_key in base["profiles"] and built_in_key in DEFAULT_PROFILES["profiles"]:
            base["profiles"][built_in_key]["label"] = DEFAULT_PROFILES["profiles"][built_in_key]["label"]
    base["version"] = _STORE_VERSION
    return base


def load_profiles(path: str | None = None) -> dict[str, Any]:
    store_path = resolve_profiles_path(path)
    if not os.path.exists(store_path):
        return _default_store()
    try:
        with open(store_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception:
        return _default_store()
    return _normalize_store(raw)


def save_profiles(data: dict[str, Any], path: str | None = None) -> str:
    store = _normalize_store(data)
    store_path = resolve_profiles_path(path)
    os.makedirs(os.path.dirname(store_path), exist_ok=True)
    tmp_path = f"{store_path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(store, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, store_path)
    return store_path


def get_profile(data: dict[str, Any], profile_key: str) -> dict[str, str]:
    store = _normalize_store(data)
    profiles = store.get("profiles") or {}
    profile = profiles.get(profile_key)
    if not isinstance(profile, dict):
        raise KeyError(f"Unknown profile: {profile_key}")
    return {
        "label": str(profile.get("label") or profile_key),
        "url": str(profile.get("url") or ""),
        "credential_target": str(profile.get("credential_target") or ""),
    }


def set_last_profile(data: dict[str, Any], profile_key: str) -> dict[str, Any]:
    store = _normalize_store(data)
    if profile_key not in (store.get("profiles") or {}):
        raise KeyError(f"Unknown profile: {profile_key}")
    store["last_profile"] = profile_key
    return store


def update_profile_url(data: dict[str, Any], profile_key: str, url: str) -> dict[str, Any]:
    store = _normalize_store(data)
    if profile_key not in (store.get("profiles") or {}):
        raise KeyError(f"Unknown profile: {profile_key}")
    store["profiles"][profile_key]["url"] = str(url or "").strip()
    return store
