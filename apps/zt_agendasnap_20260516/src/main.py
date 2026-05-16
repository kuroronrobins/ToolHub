#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Launcher entry point for AgendaSnap UI."""

from __future__ import annotations

import runpy
import sys
from pathlib import Path


def _ensure_package_path() -> None:
    root = Path(__file__).resolve().parent
    pkg_parent = None
    for candidate in (root, root / "agendasnap"):
        pkg_dir = candidate / "agendasnap"
        if (pkg_dir / "__init__.py").exists():
            pkg_parent = candidate
            break
    if pkg_parent is None:
        pkg_parent = root
    if str(pkg_parent) not in sys.path:
        sys.path.insert(0, str(pkg_parent))


def main() -> None:
    _ensure_package_path()
    runpy.run_module("agendasnap.ui.mock_ui", run_name="__main__")


if __name__ == "__main__":
    main()
