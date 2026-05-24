from __future__ import annotations

import json
import os
from typing import Any


_STORE_VERSION = 1
_APP_DIR_NAME = "XCgate_AutoUpload"
_STORE_FILE_NAME = "flow_settings.json"


def _default_store() -> dict[str, Any]:
    return {"version": _STORE_VERSION, "flows": {}}


def _resolve_store_path(path: str | None = None) -> str:
    if path:
        return path
    appdata = os.environ.get("APPDATA")
    if not appdata:
        appdata = os.path.join(os.path.expanduser("~"), "AppData", "Roaming")
    return os.path.join(appdata, _APP_DIR_NAME, _STORE_FILE_NAME)


def load_store(path: str | None = None) -> dict[str, Any]:
    store_path = _resolve_store_path(path)
    if not os.path.exists(store_path):
        return _default_store()
    try:
        with open(store_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return _default_store()
    if not isinstance(data, dict):
        return _default_store()
    flows = data.get("flows")
    if not isinstance(flows, dict):
        data["flows"] = {}
    if "version" not in data:
        data["version"] = _STORE_VERSION
    return data


def save_store(data: dict[str, Any], path: str | None = None) -> str:
    store_path = _resolve_store_path(path)
    os.makedirs(os.path.dirname(store_path), exist_ok=True)
    payload = dict(data or {})
    flows = payload.get("flows")
    if not isinstance(flows, dict):
        payload["flows"] = {}
    if "version" not in payload:
        payload["version"] = _STORE_VERSION
    tmp_path = f"{store_path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, store_path)
    return store_path


def get_flow_overrides(flow_id: str, path: str | None = None) -> dict[str, str]:
    store = load_store(path)
    flows = store.get("flows")
    if not isinstance(flows, dict):
        return {}
    raw = flows.get(flow_id, {})
    if not isinstance(raw, dict):
        return {}
    out: dict[str, str] = {}
    for k, v in raw.items():
        if isinstance(k, str) and v is not None:
            out[k] = str(v)
    return out


def set_flow_overrides(flow_id: str, values: dict[str, Any], path: str | None = None) -> str:
    store = load_store(path)
    flows = store.setdefault("flows", {})
    if not isinstance(flows, dict):
        flows = {}
        store["flows"] = flows
    cleaned: dict[str, str] = {}
    for k, v in (values or {}).items():
        if isinstance(k, str) and v is not None:
            cleaned[k] = str(v)
    if cleaned:
        flows[flow_id] = cleaned
    else:
        flows.pop(flow_id, None)
    return save_store(store, path)


def prompt_editable_vars(
    flow_id: str,
    editable_vars: list[str],
    current_values: dict[str, Any],
) -> tuple[dict[str, str], bool]:
    keys: list[str] = []
    seen = set()
    for k in editable_vars or []:
        if isinstance(k, str) and k not in seen:
            keys.append(k)
            seen.add(k)
    if not keys:
        print(f"[SETTING] No editable vars configured for '{flow_id}'.")
        return {}, False

    print("")
    print(f"[SETTING] Flow: {flow_id}")
    print("[SETTING] Press Enter to keep the current value.")
    updated: dict[str, str] = {}
    changed = False

    for key in keys:
        cur_txt = str(current_values.get(key, "") or "")
        try:
            raw = input(f"  {key} [{cur_txt}]: ")
        except EOFError:
            raw = ""
        nxt = raw.strip() if raw is not None else ""
        if nxt == "":
            nxt = cur_txt
        updated[key] = nxt
        if nxt != cur_txt:
            changed = True
    return updated, changed
