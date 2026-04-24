#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bootstlap.py (bootstrap / updater entry)

このファイルは「exeの入口」になる想定のブートストラップです。

やること（毎回起動時）:
1) 埋め込み設定（_app_data.json相当）を読み込む
2) GitHub stable ブランチの release/manifest.json を取得し、最新版を確認
3) GitHubが新しい場合のみ、更新するか確認してから最新exeをDL → 自己置換 → 置換後の新exeを起動
4) 更新が不要なら app.entry_script を起動

メモ:
- 自己置換は Windows 前提です（batで安全に置換→新exeを起動）
- デバッグ出力: 環境変数 GITHUBSYNC_DEBUG=1
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import runpy
import subprocess
import sys
import tempfile
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


# ここは _gitup.py がビルド時に「設定JSON文字列」を埋め込みます。
# （実行時に外部ファイルへ依存しないため）
__EMBEDDED_CONFIG_JSON__ = r"__EMBEDDED_CONFIG_JSON__"


def debug_enabled() -> bool:
    return os.environ.get("GITHUBSYNC_DEBUG", "").strip().lower() in ("1", "true", "yes", "on")


def dbg(msg: str) -> None:
    if debug_enabled():
        print(f"[DEBUG] {msg}")


def version_tuple(v: str) -> Tuple[int, int, int]:
    # "0.3.0" → (0,3,0)
    parts = [p.strip() for p in str(v).strip().split(".") if p.strip() != ""]
    nums = []
    for i in range(3):
        try:
            nums.append(int(parts[i]) if i < len(parts) else 0)
        except Exception:
            nums.append(0)
    return tuple(nums)  # type: ignore[return-value]


def is_remote_newer(local_ver: str, remote_ver: str) -> bool:
    return version_tuple(remote_ver) > version_tuple(local_ver)


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def load_embedded_config() -> Dict[str, Any]:
    s = __EMBEDDED_CONFIG_JSON__
    if "__EMBEDDED_CONFIG_JSON__" in s:
        # 埋め込み未実施のまま実行された場合（開発中など）
        dbg("Embedded config placeholder not replaced. Trying to read _app_data.json next to script.")
        cfg_path = Path(__file__).resolve().parent / "_app_data.json"
        if cfg_path.exists():
            return json.loads(cfg_path.read_text(encoding="utf-8"))
        return {}
    return json.loads(s)


def get_local_version(cfg: Dict[str, Any]) -> str:
    return str(cfg.get("version", {}).get("stable", "0.0.0"))


def get_remote_url(cfg: Dict[str, Any]) -> str:
    # 1) 設定値 2) git origin
    url = str(cfg.get("repo", {}).get("remote_url", "")).strip()
    if url:
        return url
    try:
        out = subprocess.check_output(["git", "remote", "get-url", "origin"], text=True).strip()
        return out
    except Exception:
        return ""


@dataclass
class RepoInfo:
    owner: str
    repo: str
    stable_branch: str


def parse_repo_info(remote_url: str, stable_branch: str) -> Optional[RepoInfo]:
    """
    対応例:
      - https://github.com/OWNER/REPO.git
      - https://github.com/OWNER/REPO
      - git@github.com:OWNER/REPO.git
    """
    u = remote_url.strip()
    if not u:
        return None

    # SSH
    if u.startswith("git@github.com:"):
        u2 = u[len("git@github.com:"):]
        u2 = u2[:-4] if u2.endswith(".git") else u2
        parts = u2.split("/")
        if len(parts) >= 2:
            return RepoInfo(owner=parts[0], repo=parts[1], stable_branch=stable_branch)
        return None

    # HTTPS
    if "github.com/" in u:
        u2 = u.split("github.com/", 1)[1]
        u2 = u2[:-4] if u2.endswith(".git") else u2
        parts = u2.split("/")
        if len(parts) >= 2:
            return RepoInfo(owner=parts[0], repo=parts[1], stable_branch=stable_branch)

    return None


def raw_url(info: RepoInfo, path: str) -> str:
    p = path.lstrip("/")
    return f"https://raw.githubusercontent.com/{info.owner}/{info.repo}/{info.stable_branch}/{p}"


def fetch_bytes(url: str, timeout: int = 20) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "GitHubSync-Updater"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def prompt_yes_no(prompt: str, default_yes: bool = True) -> bool:
    if not sys.stdin or not sys.stdin.isatty():
        # 非対話環境では安全側: 更新しない
        return False
    suffix = "[Y/n]" if default_yes else "[y/N]"
    ans = input(f"{prompt} {suffix}: ").strip().lower()
    if ans == "":
        return default_yes
    return ans in ("y", "yes")


def find_entry_script(cfg: Dict[str, Any]) -> str:
    return str(cfg.get("app", {}).get("entry_script", "main.py")).strip() or "main.py"


def run_entry(cfg: Dict[str, Any], local_ver: str) -> None:
    print(f"[BOOT] {cfg.get('app', {}).get('name', 'App')} version {local_ver}")
    entry = find_entry_script(cfg)

    candidates = []
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            candidates.append(Path(meipass) / entry)
        candidates.append(exe_dir / entry)
    candidates.append(Path(__file__).resolve().parent / entry)

    for path in candidates:
        if path.exists():
            dbg(f"Running entry script: {path}")
            runpy.run_path(str(path), run_name="__main__")
            return

    print(f"[BOOT] Entry script not found: {entry}")
    print("[BOOT] Exiting.")


def parse_manifest(b: bytes) -> Dict[str, Any]:
    """
    manifest.json 例:
    {
      "version": "0.4.0",
      "exe_path": "release/latest/MyApp.exe",
      "sha256": "....",
      "size": 12345678,
      "published_at": "2026-02-09T00:00:00Z"
    }
    """
    return json.loads(b.decode("utf-8"))


def get_release_info(cfg: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    stable_branch = str(cfg.get("repo", {}).get("stable_branch", "stable")).strip() or "stable"
    remote = get_remote_url(cfg)
    info = parse_repo_info(remote, stable_branch)
    if not info:
        dbg("remote_url is missing or not parseable; update check skipped.")
        return None

    manifest_path = str(cfg.get("release", {}).get("manifest_path", "release/manifest.json")).strip()
    url = raw_url(info, manifest_path)
    dbg(f"GET {url}")
    try:
        mb = fetch_bytes(url)
        return {"repo": info, "manifest": parse_manifest(mb)}
    except Exception as e:
        dbg(f"manifest fetch failed: {e!r}")
        return None


def replace_and_restart_windows(dst: Path, new_bytes: bytes, log_path: Path) -> None:
    """
    安全な自己置換（Windows）:
      - new を dst.new.exe に書く
      - 現行プロセス終了後に .bat で move/rename
      - 置換後、.bat が新しい exe を「直実行」する（start/Start-Process を使わない）
    """
    dst = dst.resolve()
    dstdir = dst.parent
    dstnew = dstdir / (dst.name + ".new")
    dstold = dstdir / (dst.name + ".old")

    dstdir.mkdir(parents=True, exist_ok=True)
    dstnew.write_bytes(new_bytes)

    bat = Path(tempfile.gettempdir()) / "githubsync_update.bat"

    # バッチは「置換→新exe直実行」方式（環境依存を最小化）
    bat_text = f"""@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul

set "DST={dst}"
set "DSTNEW={dstnew}"
set "DSTOLD={dstold}"
set "LOG={log_path}"

echo [BAT] updater started >> "%LOG%"
echo [BAT] DST=%DST% >> "%LOG%"
echo [BAT] DSTNEW=%DSTNEW% >> "%LOG%"

REM wait a moment for parent to exit
timeout /t 1 /nobreak >nul

REM retry rename/copy a few times
set /a RET=0
:RETRY
set /a RET+=1

REM backup old
if exist "%DSTOLD%" del /f /q "%DSTOLD%" >nul 2>&1

move /y "%DST%" "%DSTOLD%" >nul 2>&1
if errorlevel 1 (
  if !RET! GEQ 20 (
    echo [BAT][ERR] move DST->DSTOLD failed after retries >> "%LOG%"
    goto :FAIL
  )
  timeout /t 1 /nobreak >nul
  goto :RETRY
)

move /y "%DSTNEW%" "%DST%" >nul 2>&1
if errorlevel 1 (
  echo [BAT][ERR] move DSTNEW->DST failed >> "%LOG%"
  REM try rollback
  move /y "%DSTOLD%" "%DST%" >nul 2>&1
  goto :FAIL
)

echo [BAT] replaced successfully >> "%LOG%"
echo [BAT] launching updated exe (inline) >> "%LOG%"

REM Inline launch (most reliable)
"%DST%"
set "EC=%ERRORLEVEL%"
echo [BAT] updated exe exited with code %EC% >> "%LOG%"
exit /b %EC%

:FAIL
echo [BAT] updater failed >> "%LOG%"
exit /b 1
"""

    bat.write_text(bat_text, encoding="utf-8", errors="ignore")

    # bat を起動して自分は終了（置換を成立させる）
    # ここではウィンドウ表示/非表示は環境次第だが、ログに全て残る
    subprocess.Popen(["cmd.exe", "/c", str(bat)], close_fds=True)


def try_self_update(cfg: Dict[str, Any], local_ver: str) -> bool:
    rel = get_release_info(cfg)
    if not rel:
        return False

    manifest = rel["manifest"]
    remote_ver = str(manifest.get("version", "0.0.0"))
    dbg(f"Local version={local_ver}, Remote version={remote_ver}")

    if not is_remote_newer(local_ver, remote_ver):
        return False

    # 更新前に確認
    if not prompt_yes_no(f"[UPDATE] New version available: {local_ver} -> {remote_ver}. Update now?", default_yes=True):
        return False

    exe_path = str(manifest.get("exe_path", "")).strip()
    if not exe_path:
        dbg("manifest.exe_path is missing; cannot update.")
        return False

    info: RepoInfo = rel["repo"]
    exe_url = raw_url(info, exe_path)
    dbg(f"Downloading exe: {exe_url}")

    try:
        exe_bytes = fetch_bytes(exe_url, timeout=60)
    except Exception as e:
        dbg(f"download failed: {e!r}")
        return False

    # sha256 check (recommended)
    require_sha = bool(cfg.get("release", {}).get("require_sha256", True))
    expected = str(manifest.get("sha256", "")).strip().lower()
    if expected:
        got = sha256_bytes(exe_bytes).lower()
        if got != expected:
            print("[UPDATE] Downloaded exe sha256 mismatch. Update aborted.")
            dbg(f"expected={expected}, got={got}")
            return False
    elif require_sha:
        dbg("manifest missing sha256 but require_sha256=true; aborting.")
        print("[UPDATE] Manifest missing sha256. Update aborted.")
        return False

    dst = Path(sys.executable if getattr(sys, "frozen", False) else "dist/" + str(cfg.get("app", {}).get("exe_name", "app")) + ".exe")
    log_path = Path(tempfile.gettempdir()) / "githubsync_update.log"
    log_path.write_text("", encoding="utf-8", errors="ignore")

    print("[UPDATE] Applying update and restarting...")
    replace_and_restart_windows(dst, exe_bytes, log_path)
    return True


def main() -> None:
    _ = argparse.ArgumentParser(add_help=False).parse_args([])

    cfg = load_embedded_config()
    local_ver = get_local_version(cfg) if cfg else "0.0.0"

    updated = False
    if cfg and getattr(sys, "frozen", False):
        updated = try_self_update(cfg, local_ver)

    if updated:
        # 置換のために終了（.bat側で新exeを起動）
        sys.exit(0)

    run_entry(cfg or {}, local_ver)


if __name__ == "__main__":
    main()
