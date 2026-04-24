#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
_gitup.py - GitHub + version + exe publish helper (startup file set)

目的:
- 新しいプロジェクトフォルダに「bootstlap.py / _gitup.py / _app_data.json」だけをコピーして使えるようにする
- stable の自動更新用に、固定パスに manifest と latest exe を配置する（release/manifest.json, release/latest/*.exe）
- バージョンは Push→Stable の時に入力し、そのバージョンでビルド & publish する（ズレ防止）

大事な運用ルール:
- 自動更新に使う公開作業は「Push → Stable → Publish=Y」で行う
- メニューの Build exe はローカルテスト用（公開には使わない）

依存:
- git（PATH上）
- python + pyinstaller（exe生成する場合）
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple


ROOT = Path(__file__).resolve().parent
CFG_PATH = ROOT / "_app_data.json"
BOOT_PATH = ROOT / "_bootstrap.py"


def die(msg: str, code: int = 1) -> None:
    print(msg)
    raise SystemExit(code)


def run(cmd: List[str], check: bool = True, capture: bool = False) -> str:
    if capture:
        p = subprocess.run(cmd, check=False, text=True, cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        if check and p.returncode != 0:
            die(p.stdout)
        return p.stdout
    else:
        p = subprocess.run(cmd, check=False, cwd=str(ROOT))
        if check and p.returncode != 0:
            die(f"[ERROR] command failed: {' '.join(cmd)}")
        return ""


def run_with_code(cmd: List[str]) -> Tuple[int, str]:
    p = subprocess.run(cmd, check=False, text=True, cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return p.returncode, p.stdout


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_cfg() -> Dict[str, Any]:
    if not CFG_PATH.exists():
        die(f"[ERROR] _app_data.json not found: {CFG_PATH}")
    cfg = json.loads(CFG_PATH.read_text(encoding="utf-8"))
    return cfg


def save_cfg(cfg: Dict[str, Any]) -> None:
    CFG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def normalize_remote_url(s: str) -> str:
    s = s.strip()
    if not s:
        return s
    if s.startswith("http://") or s.startswith("https://") or s.startswith("git@"):
        return s if s.endswith(".git") else (s + ".git")
    # owner/repo だけが来たとき
    if "/" in s:
        return f"https://github.com/{s}.git"
    return s


def ensure_release_dirs(cfg: Dict[str, Any]) -> Tuple[Path, Path]:
    rel_dir = ROOT / "release"
    latest_dir = rel_dir / "latest"
    rel_dir.mkdir(exist_ok=True)
    latest_dir.mkdir(exist_ok=True)
    return rel_dir, latest_dir


def make_manifest(cfg: Dict[str, Any], version: str, exe_rel_path: str, exe_path: Path) -> Dict[str, Any]:
    st = exe_path.stat()
    return {
        "version": version,
        "exe_path": exe_rel_path.replace("\\", "/"),
        "sha256": sha256_file(exe_path),
        "size": int(st.st_size),
        "published_at": datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
    }


def git_current_branch() -> str:
    out = run(["git", "rev-parse", "--abbrev-ref", "HEAD"], capture=True).strip()
    return out


def git_status(cfg: Dict[str, Any]) -> None:
    ensure_git_ready(cfg)
    print(run(["git", "status", "-sb"], capture=True, check=False))


def stage_and_commit(message: str, paths: List[str] | None = None) -> None:
    if paths:
        run(["git", "add", "--"] + paths, check=True)
    else:
        run(["git", "add", "-A"], check=True)

    # 何も変化が無ければ commit しない
    diff = run(["git", "diff", "--cached", "--name-only"], capture=True, check=False).strip()
    if not diff:
        print("[INFO] No staged changes to commit.")
        return
    run(["git", "commit", "-m", message], check=True)


def checkout(branch: str) -> None:
    if not git_has_commit():
        run(["git", "checkout", "-B", branch], check=True)
        return
    run(["git", "checkout", branch], check=True)


def git_is_repo() -> bool:
    return (ROOT / ".git").exists()


def git_remote_heads(remote: str = "origin") -> List[str]:
    out = run(["git", "ls-remote", "--heads", remote], capture=True, check=False)
    heads: List[str] = []
    for line in out.splitlines():
        if "\trefs/heads/" in line:
            heads.append(line.split("\trefs/heads/", 1)[1].strip())
    return heads


def git_remote_default_branch(remote: str = "origin") -> str:
    out = run(["git", "ls-remote", "--symref", remote, "HEAD"], capture=True, check=False)
    for line in out.splitlines():
        if line.startswith("ref: refs/heads/"):
            return line.split("ref: refs/heads/", 1)[1].split("\t", 1)[0].strip()
    return ""


def choose_bootstrap_branch(cfg: Dict[str, Any], heads: List[str]) -> str:
    develop = str(cfg.get("repo", {}).get("develop_branch", "develop")).strip()
    stable = str(cfg.get("repo", {}).get("stable_branch", "stable")).strip()
    remote_default = git_remote_default_branch("origin")

    seen = set()
    candidates = [develop, stable, remote_default, "main", "master"]
    for b in candidates:
        if not b or b in seen:
            continue
        seen.add(b)
        if b in heads:
            return b

    if heads:
        return heads[0]
    return develop or stable or "main"


def git_has_commit() -> bool:
    rc, _ = run_with_code(["git", "rev-parse", "--verify", "HEAD"])
    return rc == 0


def ensure_git_ready(cfg: Dict[str, Any]) -> None:
    remote_url = normalize_remote_url(str(cfg.get("repo", {}).get("remote_url", "")))
    if not remote_url:
        die("[ERROR] repo.remote_url is empty. Run Configure first.")

    first_time = False
    if not git_is_repo():
        print("[INIT] First run detected: initializing local git repository")
        run(["git", "init"], check=True)
        first_time = True

    rc_origin, origin_out = run_with_code(["git", "remote", "get-url", "origin"])
    current_origin = origin_out.strip() if rc_origin == 0 else ""

    if not current_origin:
        print(f"[INIT] git remote add origin {remote_url}")
        run(["git", "remote", "add", "origin", remote_url], check=True)
    elif normalize_remote_url(current_origin) != remote_url:
        print(f"[INIT] origin URL updated -> {remote_url}")
        run(["git", "remote", "set-url", "origin", remote_url], check=True)

    if first_time or not git_has_commit():
        print("[INIT] Fetching remote branches")
        run(["git", "fetch", "origin"], check=True)
        heads = git_remote_heads("origin")
        branch = choose_bootstrap_branch(cfg, heads)

        if branch in heads:
            print(f"[INIT] Tracking branch: {branch}")
            rc, out = run_with_code(["git", "checkout", "-b", branch, "--track", f"origin/{branch}"])
            if rc != 0:
                rc2, out2 = run_with_code(["git", "checkout", "-B", branch, f"origin/{branch}"])
                if rc2 != 0:
                    die(out + "\n" + out2)
                run(["git", "branch", "--set-upstream-to", f"origin/{branch}", branch], check=False)
        else:
            print(f"[INIT] Remote has no heads. Created local branch: {branch}")
            run(["git", "checkout", "-B", branch], check=False)


def pull_flow(cfg: Dict[str, Any]) -> None:
    ensure_git_ready(cfg)
    print("[PULL] git pull")
    run(["git", "pull"], check=True)


def build_exe(cfg: Dict[str, Any], embed_version: str, extra_opts: str = "") -> Path:
    """
    PyInstallerで exe を生成する。
    - bootstlap.py を build/_bootstrap_embedded.py にコピーし、埋め込みconfigを置換して入口にする
    - entry_script を data として同梱する
    """
    entry_script = str(cfg.get("app", {}).get("entry_script", "main.py")).strip() or "main.py"
    exe_name = str(cfg.get("app", {}).get("exe_name", "MyApp")).strip() or "MyApp"
    onefile = bool(cfg.get("build", {}).get("onefile", True))
    console = bool(cfg.get("build", {}).get("console", True))
    icon_path = str(cfg.get("build", {}).get("icon_path", "")).strip()

    build_dir = ROOT / "build"
    build_dir.mkdir(exist_ok=True)
    embedded = build_dir / "_bootstrap_embedded.py"

    # configをビルド用にコピー（stable versionを埋め込む）
    cfg2 = json.loads(json.dumps(cfg))
    cfg2.setdefault("version", {})
    cfg2["version"]["stable"] = embed_version

    boot_src = BOOT_PATH.read_text(encoding="utf-8")
    config_json = json.dumps(cfg2, ensure_ascii=False)
    boot_src = boot_src.replace(r'__EMBEDDED_CONFIG_JSON__ = r"__EMBEDDED_CONFIG_JSON__"',
                                f'__EMBEDDED_CONFIG_JSON__ = r"""{config_json}"""')

    embedded.write_text(boot_src, encoding="utf-8")

    # PyInstaller command
    cmd = ["pyinstaller"]
    if onefile:
        cmd.append("--onefile")
    if not console:
        cmd.append("--noconsole")
    cmd += ["--name", exe_name]

    # icon
    if icon_path:
        cmd += ["--icon", icon_path]

    # add data: entry_script
    # Windows: src;dest  (semicolon)
    sep = ";" if os.name == "nt" else ":"
    cmd += ["--add-data", f"{entry_script}{sep}."]

    # additional options from config + prompt extra_opts
    cfg_extra = str(cfg.get("build", {}).get("additional_pyinstaller_options", "")).strip()
    all_extra = " ".join([cfg_extra, extra_opts]).strip()
    if all_extra:
        cmd += all_extra.split()

    cmd += [str(embedded)]

    print("[BUILD] Running:", " ".join(cmd))
    run(cmd, check=True)

    out_exe = ROOT / "dist" / (exe_name + (".exe" if os.name == "nt" else ""))
    if not out_exe.exists():
        die(f"[ERROR] Built exe not found: {out_exe}")
    return out_exe


def push_flow(cfg: Dict[str, Any]) -> None:
    ensure_git_ready(cfg)
    stable = str(cfg.get("repo", {}).get("stable_branch", "stable")).strip() or "stable"
    develop = str(cfg.get("repo", {}).get("develop_branch", "develop")).strip() or "develop"

    print("\nPush target:")
    print(f"[1] {stable} (release)")
    print(f"[2] {develop}")
    choice = input("Number: ").strip()

    if choice not in ("1", "2"):
        print("[INFO] canceled.")
        return

    target = stable if choice == "1" else develop

    # バージョン入力（stableのときだけ必須）
    new_ver = None
    if target == stable:
        cur = str(cfg.get("version", {}).get("stable", "0.0.0"))
        new_ver = input(f"Stable version (current {cur}) : ").strip()
        if not new_ver:
            print("[INFO] canceled.")
            return
        cfg.setdefault("version", {})
        cfg["version"]["stable"] = new_ver
        save_cfg(cfg)

    msg = input("Commit message (empty=auto): ").strip()
    if not msg:
        msg = f"update: {target}" if not new_ver else f"release: v{new_ver}"

    # publish?
    publish = False
    if target == stable:
        ans = input("Build & publish latest exe + manifest for auto-update? [y/N]: ").strip().lower()
        publish = ans in ("y", "yes")

    # 実際の処理: stable publish の場合は「version確定 → build → manifest → stage → commit → push」
    checkout(target)

    extra = input("Additional PyInstaller options (empty for none): ").strip()

    paths_to_stage: List[str] | None = None

    if publish:
        rel_dir, latest_dir = ensure_release_dirs(cfg)

        exe_name = str(cfg.get("app", {}).get("exe_name", "MyApp")).strip() or "MyApp"
        latest_exe_rel = str(cfg.get("release", {}).get("latest_exe_path", "release/latest/{exe_name}.exe"))
        latest_exe_rel = latest_exe_rel.format(exe_name=exe_name).replace("\\", "/")
        latest_exe_path = ROOT / latest_exe_rel

        built = build_exe(cfg, embed_version=new_ver or str(cfg.get("version", {}).get("stable", "0.0.0")), extra_opts=extra)
        latest_exe_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(built, latest_exe_path)

        manifest_rel = str(cfg.get("release", {}).get("manifest_path", "release/manifest.json")).replace("\\", "/")
        manifest_path = ROOT / manifest_rel

        manifest = make_manifest(cfg, version=new_ver or "0.0.0", exe_rel_path=latest_exe_rel, exe_path=latest_exe_path)
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

        # publish時だけ強制ステージ
        always = list(cfg.get("paths", {}).get("always_stage_on_publish", []))
        # 具体ファイルとして足す
        always += [manifest_rel, latest_exe_rel]
        paths_to_stage = sorted(set(always))

        # ひとつのコミットにまとめる
        stage_and_commit(message=msg, paths=paths_to_stage)
    else:
        stage_and_commit(message=msg, paths=None)

    print("[PUSH] git push")
    run(["git", "push"], check=True)


def build_flow(cfg: Dict[str, Any]) -> None:
    print("\n[BUILD] local test build (not for publishing)")
    cur = str(cfg.get("version", {}).get("stable", "0.0.0"))
    ver = input(f"Embed version for this build [{cur}]: ").strip() or cur
    extra = input("Additional PyInstaller options (empty for none): ").strip()
    exe = build_exe(cfg, embed_version=ver, extra_opts=extra)
    print(f"[BUILD] done: {exe}")


def configure_flow(cfg: Dict[str, Any]) -> None:
    print("\n[CONFIG] Minimal settings")

    name = input(f"app.name [{cfg.get('app', {}).get('name', '')}]: ").strip()
    if name:
        cfg.setdefault("app", {})["name"] = name

    exe_name = input(f"app.exe_name [{cfg.get('app', {}).get('exe_name', '')}]: ").strip()
    if exe_name:
        cfg.setdefault("app", {})["exe_name"] = exe_name

    entry = input(f"app.entry_script [{cfg.get('app', {}).get('entry_script', '')}]: ").strip()
    if entry:
        cfg.setdefault("app", {})["entry_script"] = entry

    remote = input(f"repo.remote_url [{cfg.get('repo', {}).get('remote_url', '')}]: ").strip()
    if remote:
        cfg.setdefault("repo", {})["remote_url"] = normalize_remote_url(remote)

    stable = input(f"repo.stable_branch [{cfg.get('repo', {}).get('stable_branch', 'stable')}]: ").strip()
    if stable:
        cfg.setdefault("repo", {})["stable_branch"] = stable

    develop = input(f"repo.develop_branch [{cfg.get('repo', {}).get('develop_branch', 'develop')}]: ").strip()
    if develop:
        cfg.setdefault("repo", {})["develop_branch"] = develop

    save_cfg(cfg)
    print("[CONFIG] saved.")


def main() -> None:
    cfg = load_cfg()

    while True:
        print("\n--------------------------------------")
        print("[1] Status")
        print("[2] Pull")
        print("[3] Push")
        print("[4] Build exe (local test)")
        print("[5] Configure")
        print("[6] Exit")
        n = input("Number: ").strip()

        if n == "1":
            git_status(cfg)
        elif n == "2":
            pull_flow(cfg)
        elif n == "3":
            # reload each time (reflect version changes)
            cfg = load_cfg()
            push_flow(cfg)
        elif n == "4":
            cfg = load_cfg()
            build_flow(cfg)
        elif n == "5":
            cfg = load_cfg()
            configure_flow(cfg)
        elif n == "6":
            break
        else:
            print("[INFO] invalid choice.")


if __name__ == "__main__":
    main()
