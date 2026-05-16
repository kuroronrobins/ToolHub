#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ToolHub bootstrap entry point.

This file intentionally contains only project startup concerns.
Individual app manifests, UI behavior, and runner-specific app logic live in
the launcher and runner layers.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import logging
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional


APP_NAME = "ToolHub"
REQUIRED_DIRS = ("launcher", "runner", "apps", "config", "data")
RELEASE_CANDIDATES = (
    Path("launcher/src-tauri/target/release/toolhub.exe"),
    Path("launcher/src-tauri/target/release/ToolHub.exe"),
    Path("release/ToolHub.exe"),
    Path("dist/ToolHub.exe"),
)


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
    timestamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    run_log = log_dir / f"launch_{timestamp}.log"

    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    for path in (latest_log, run_log):
        handler = logging.FileHandler(path, encoding="utf-8")
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


def frontend_dependency_issue(root: Path) -> Optional[str]:
    launcher_dir = root / "launcher"
    package_json = launcher_dir / "package.json"
    package_lock = launcher_dir / "package-lock.json"
    node_modules = launcher_dir / "node_modules"

    if not package_json.is_file():
        return "launcher/package.json が見つかりません。"
    if not package_lock.is_file():
        return "launcher/package-lock.json が見つかりません。"
    if not node_modules.is_dir():
        return "launcher/node_modules が見つかりません。"
    if local_npm_bin(root, "tauri") or which("tauri"):
        return None
    return "Tauri CLI が見つかりません。launcher の npm 依存関係が未復元の可能性があります。"


def print_frontend_dependency_help(root: Path, latest_log: Path, detail: str) -> None:
    logging.error("frontend dependency check failed: %s", detail)
    print("")
    print("ToolHubを起動できませんでした。")
    print("フロントエンド依存関係が未準備です。")
    print("")
    print("原因:")
    print(f"- {detail}")
    print("")
    print("次のコマンドを実行してください:")
    print("")
    print("cd launcher")
    print("npm ci")
    print("cd ..")
    print("py main.py")
    print("")
    print("詳細ログ:")
    print(latest_log)


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


def print_check_result(items: Iterable[CheckItem]) -> int:
    print("ToolHub 環境チェック")
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


def validate_project_structure(root: Path) -> List[str]:
    missing = [name for name in REQUIRED_DIRS if not (root / name).is_dir()]
    if not (root / "launcher" / "package.json").is_file():
        missing.append("launcher/package.json")
    return missing


def find_release_executable(root: Path) -> Optional[Path]:
    for relative in RELEASE_CANDIDATES:
        candidate = root / relative
        logging.info("checking release candidate: %s", candidate)
        if candidate.is_file():
            return candidate
    return None


def launch_release(executable: Path, root: Path) -> int:
    logging.info("launching release executable: %s", executable)
    logging.info("passing TOOLHUB_ROOT=%s to release executable", root)
    env = os.environ.copy()
    env["TOOLHUB_ROOT"] = str(root)
    try:
        subprocess.Popen([str(executable)], cwd=str(executable.parent), env=env)
    except OSError:
        logging.exception("failed to launch release executable")
        raise
    return 0


def dev_command(root: Path) -> List[str]:
    npm = which("npm")
    if not npm:
        raise FileNotFoundError("npm")
    return [npm, "run", "tauri", "dev"]


def launch_dev(root: Path) -> int:
    launcher_dir = root / "launcher"
    missing = validate_project_structure(root)
    if missing:
        raise RuntimeError("missing project files: " + ", ".join(missing))

    dependency_issue = frontend_dependency_issue(root)
    if dependency_issue:
        latest_log = root / "data" / "logs" / "launcher" / "latest.log"
        print_frontend_dependency_help(root, latest_log, dependency_issue)
        return 1

    failed_checks = [item.name for item in check_environment(root) if item.required and not item.ok]
    if failed_checks:
        raise RuntimeError("missing development environment: " + ", ".join(failed_checks))

    command = dev_command(root)
    logging.info("launching dev command: %s", command)
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
    parser.add_argument("--dev", action="store_true", help="強制的に開発モードで起動します")
    parser.add_argument("--release", action="store_true", help="ビルド済み実行ファイルのみ起動します")
    parser.add_argument("--check", action="store_true", help="環境とフォルダ構成を確認します")
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(list(argv if argv is not None else sys.argv[1:]))
    root = project_root()
    latest_log = configure_logging(root)

    if args.check:
        return print_check_result(check_environment(root))

    try:
        if args.dev and args.release:
            print("--dev と --release は同時に指定できません。")
            return 2

        if not args.dev:
            release_exe = find_release_executable(root)
            if release_exe:
                return launch_release(release_exe, root)
            if args.release:
                logging.error("release executable not found")
                print("ビルド済みToolHub実行ファイルが見つかりません。")
                print(f"詳細ログ：{latest_log}")
                return 1

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
