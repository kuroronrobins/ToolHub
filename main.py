#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ToolHub bootstrap entry point.

This file intentionally contains only project startup concerns.
Individual app manifests, UI behavior, and runner-specific app logic live in
the launcher and runner layers.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional


APP_NAME = "ToolHub"
REQUIRED_DIRS = ("launcher", "runner", "apps", "config")


@dataclass
class CheckItem:
    name: str
    ok: bool
    detail: str
    required: bool = True


def project_root() -> Path:
    return Path(__file__).resolve().parent


def ensure_log_dir(root: Path) -> Path:
    log_dir = root / "data" / "logs" / "launcher"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def configure_logging(root: Path) -> Path:
    log_dir = ensure_log_dir(root)
    latest_log = log_dir / "latest.log"

    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    handler = logging.FileHandler(latest_log, encoding="utf-8")
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    logging.info("%s bootstrap started", APP_NAME)
    logging.info("project_root=%s", root)
    return latest_log


def which(command: str) -> Optional[str]:
    found = shutil.which(command)
    if found:
        return found
    if os.name == "nt" and not command.lower().endswith(".cmd"):
        return shutil.which(f"{command}.cmd")
    return None


def has_command(command: str) -> CheckItem:
    path = which(command)
    return CheckItem(command, path is not None, path or "not found")


def local_npm_bin(root: Path, command: str) -> Optional[Path]:
    bin_dir = root / "launcher" / "node_modules" / ".bin"
    candidates = [bin_dir / command]
    if os.name == "nt":
        candidates.insert(0, bin_dir / f"{command}.cmd")
        candidates.append(bin_dir / f"{command}.ps1")
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def launcher_version(root: Path) -> str:
    package_json = root / "launcher" / "package.json"
    try:
        data = json.loads(package_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "unknown"
    version = data.get("version")
    return version if isinstance(version, str) and version.strip() else "unknown"


def check_environment(root: Path) -> List[CheckItem]:
    items: List[CheckItem] = []

    for dirname in REQUIRED_DIRS:
        path = root / dirname
        items.append(CheckItem(f"directory:{dirname}", path.is_dir(), str(path)))

    launcher_package = root / "launcher" / "package.json"
    items.append(CheckItem("launcher/package.json", launcher_package.is_file(), str(launcher_package)))

    launcher_lock = root / "launcher" / "package-lock.json"
    items.append(CheckItem("launcher/package-lock.json", launcher_lock.is_file(), str(launcher_lock)))

    node_modules = root / "launcher" / "node_modules"
    items.append(
        CheckItem(
            "launcher/node_modules",
            node_modules.is_dir(),
            str(node_modules) if node_modules.is_dir() else "not found; run `cd launcher` then `npm ci`",
        )
    )

    src_tauri = root / "launcher" / "src-tauri" / "Cargo.toml"
    items.append(CheckItem("launcher/src-tauri/Cargo.toml", src_tauri.is_file(), str(src_tauri)))

    for command in ("node", "npm", "rustc", "cargo"):
        items.append(has_command(command))

    tauri_cli = local_npm_bin(root, "tauri") or (Path(which("tauri")) if which("tauri") else None)
    if tauri_cli:
        items.append(CheckItem("tauri-cli", True, str(tauri_cli)))
    else:
        items.append(
            CheckItem(
                "tauri-cli",
                False,
                "not found; run `cd launcher` then `npm ci`",
            )
        )

    return items


def print_check_result(root: Path, items: Iterable[CheckItem]) -> int:
    print("ToolHub 環境チェック")
    print(f"ToolHub version: {launcher_version(root)}")
    print("起動対象: launcher の開発中プログラム")
    print("")
    failed_required = False
    for item in items:
        marker = "OK" if item.ok else ("WARN" if not item.required else "NG")
        print(f"[{marker}] {item.name}: {item.detail}")
        logging.info("check %s ok=%s required=%s detail=%s", item.name, item.ok, item.required, item.detail)
        if item.required and not item.ok:
            failed_required = True

    print("")
    if failed_required:
        print("必須項目に不足があります。詳細は data/logs/launcher/latest.log を確認してください。")
        return 1
    print("必須項目は確認できました。")
    return 0


def dev_command() -> List[str]:
    npm = which("npm")
    if not npm:
        raise FileNotFoundError("npm")
    return [npm, "run", "tauri", "dev"]


def launch_dev(root: Path) -> int:
    launcher_dir = root / "launcher"
    failed_checks = [item for item in check_environment(root) if item.required and not item.ok]
    if failed_checks:
        detail = "; ".join(f"{item.name}: {item.detail}" for item in failed_checks)
        raise RuntimeError("missing development environment: " + detail)

    command = dev_command()
    logging.info("launcher_version=%s", launcher_version(root))
    logging.info("launching dev command: %s", command)
    print(f"ToolHub version: {launcher_version(root)}")
    print("起動対象: launcher の開発中プログラム")
    completed = subprocess.run(command, cwd=str(launcher_dir), check=False)
    logging.info("dev command finished with exit_code=%s", completed.returncode)
    return int(completed.returncode)


def print_startup_failure(latest_log: Path, detail: str) -> None:
    logging.error("startup failure: %s", detail)
    print("")
    print("ToolHubを起動できませんでした。")
    print("開発起動に必要な環境が不足している可能性があります。")
    print("")
    print("確認してください：")
    print("- Node.js / npm")
    print("- Rust / cargo")
    print("- launcher の npm 依存関係（cd launcher; npm ci）")
    print("- launcher/package.json")
    print("")
    print("詳細ログ：")
    print(latest_log)


def parse_args(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python main.py",
        description="ToolHub launcher bootstrap",
    )
    parser.add_argument("--check", action="store_true", help="環境とフォルダ構成を確認します")
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(list(argv if argv is not None else sys.argv[1:]))
    root = project_root()
    latest_log = configure_logging(root)

    if args.check:
        return print_check_result(root, check_environment(root))

    try:
        return launch_dev(root)

    except FileNotFoundError as exc:
        print_startup_failure(latest_log, f"command not found: {exc}")
        return 1
    except Exception as exc:
        logging.exception("unhandled startup error")
        print_startup_failure(latest_log, str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
