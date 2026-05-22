"""
Lightweight persistence for template options.

Stores JSON under the project cache directory, keyed by template filename
to avoid touching the template Excel files themselves.
"""

import json
import os
from dataclasses import asdict
from typing import Any, Dict, Optional

from app.batch_logic import TemplateOption
from app.config import DEFAULT_STATE_FILE
from app.paths import user_cache_dir


class SettingsStore:
    def __init__(self) -> None:
        self.base_dir = str(user_cache_dir())
        os.makedirs(self.base_dir, exist_ok=True)
        self.default_path = os.path.join(self.base_dir, DEFAULT_STATE_FILE)

    def _read_json(self, path: Optional[str] = None) -> Dict[str, Any]:
        target = path or self.default_path
        try:
            with open(target, "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            return {}
        except Exception:
            return {}

    def _write_json(self, data: Dict[str, Any], path: Optional[str] = None) -> None:
        target = path or self.default_path
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _key(self, template_path: str) -> str:
        return os.path.basename(template_path).lower()

    # Template option helpers
    def remember_template_option(self, option: TemplateOption) -> None:
        data = self._read_json()
        tpl_map = data.get("template_options", {})
        tpl_map[self._key(option.path)] = asdict(option)
        data["template_options"] = tpl_map
        self._write_json(data)

    def get_template_option(self, path: str) -> Optional[TemplateOption]:
        data = self._read_json()
        tpl_map = data.get("template_options", {})
        entry = tpl_map.get(self._key(path))
        if not entry:
            return None
        entry["path"] = path  # override in case path changed
        try:
            entry["row_adjust"] = int(entry.get("row_adjust", 0))
        except Exception:
            entry["row_adjust"] = 0
        try:
            return TemplateOption(**entry)  # type: ignore[arg-type]
        except Exception:
            return None
