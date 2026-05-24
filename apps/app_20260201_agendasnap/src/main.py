#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Launcher entry point for AgendaSnap UI."""

from __future__ import annotations

import argparse
import contextlib
import importlib
import importlib.metadata
import runpy
import sys
from pathlib import Path


DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent / "agendasnap" / "config" / "default.yaml"
WINDOW_MODULES = {
    "main": "agendasnap.ui.mock_ui",
    "settings": "agendasnap.ui.settings_window",
    "caption": "agendasnap.ui.caption_window",
    "captions": "agendasnap.ui.caption_window",
    "minutes": "agendasnap.ui.minutes_window",
}
REQUIRED_RUNTIME_IMPORTS = {
    "flet": "flet",
    "pyaudiowpatch": "pyaudiowpatch",
    "numpy": "numpy",
    "PyYAML": "yaml",
    "websockets": "websockets",
    "soundfile": "soundfile",
}
REQUIRED_RUNTIME_DISTRIBUTIONS = ("flet-desktop",)


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


def _parse_launcher_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AgendaSnap launcher")
    parser.add_argument("--toolhub-smoke", "--smoke", dest="toolhub_smoke", action="store_true")
    parser.add_argument(
        "--window",
        choices=sorted(WINDOW_MODULES.keys()),
        default="main",
        help="Window to open.",
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    args, forwarded_args = parser.parse_known_args(argv)
    args.forwarded_args = forwarded_args
    return args


def _check_runtime_dependencies() -> None:
    missing: list[str] = []
    for package_name, module_name in REQUIRED_RUNTIME_IMPORTS.items():
        try:
            importlib.import_module(module_name)
        except ImportError:
            missing.append(package_name)
    for distribution_name in REQUIRED_RUNTIME_DISTRIBUTIONS:
        try:
            importlib.metadata.version(distribution_name)
        except importlib.metadata.PackageNotFoundError:
            missing.append(distribution_name)
    if missing:
        missing_text = ", ".join(sorted(missing))
        raise RuntimeError(f"Missing runtime dependency: {missing_text}")


def _run_smoke(config_path: Path) -> int:
    _ensure_package_path()
    _check_runtime_dependencies()

    from agendasnap.config.ai_providers import (
        normalize_api_key_priority,
        resolve_stt_runtime,
        resolve_text_runtime,
    )
    from agendasnap.config.loader import load_config
    from agendasnap.config.validate import validate_config

    cfg = load_config(config_path, include_user_config=False)
    validate_config(cfg)

    fallback_priority = normalize_api_key_priority(cfg.get("secrets", {}).get("priority"))
    resolve_stt_runtime(cfg.get("stt", {}), fallback_priority=fallback_priority)
    translation_cfg = cfg.get("translation")
    if isinstance(translation_cfg, dict):
        resolve_text_runtime(
            translation_cfg,
            fallback_priority=fallback_priority,
            purpose="translation",
        )
    minutes_cfg = cfg.get("minutes")
    if isinstance(minutes_cfg, dict) and isinstance(minutes_cfg.get("llm"), dict):
        resolve_text_runtime(
            minutes_cfg["llm"],
            fallback_priority=fallback_priority,
            purpose="minutes",
        )

    print("AgendaSnap smoke check OK")
    print(f"config: {config_path}")
    print("recording/audio devices/Teams/OpenAI API/GUI: not started")
    return 0


@contextlib.contextmanager
def _module_argv(module_name: str, argv: list[str]):
    previous = sys.argv[:]
    sys.argv = [module_name, *argv]
    try:
        yield
    finally:
        sys.argv = previous


def _window_forwarded_args(args: argparse.Namespace) -> list[str]:
    forwarded = list(args.forwarded_args)
    if args.window in {"caption", "captions", "settings"}:
        forwarded = ["--config", str(args.config), *forwarded]
    return forwarded


def _run_window(args: argparse.Namespace) -> int:
    module_name = WINDOW_MODULES[args.window]
    with _module_argv(module_name, _window_forwarded_args(args)):
        runpy.run_module(module_name, run_name="__main__")
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    launcher_args = _parse_launcher_args(argv)
    if launcher_args.toolhub_smoke:
        return _run_smoke(launcher_args.config)

    _ensure_package_path()
    return _run_window(launcher_args)


if __name__ == "__main__":
    raise SystemExit(main())
