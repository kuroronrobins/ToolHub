# run_xcgate_upload.py
# XCgate upload launcher.

from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

from xcgate_launcher import (
    ensure_resources,
    flow_args,
    flows_root,
    run_embedded_flow,
    run_toolhub_smoke,
    runtime_root,
)


def pause_if_no_tty(msg: str = "終了するには Enter を押してください...") -> None:
    try:
        if not sys.stdin or not sys.stdin.isatty():
            input(msg)
    except Exception:
        pass


def _load_runtime_modules(flows_dir: Path):
    sys.path.insert(0, str(flows_dir))
    from src.io import profiles
    from src.io import windows_credentials

    return profiles, windows_credentials


def _profile_label(profile_key: str, profile: dict[str, str]) -> str:
    return f"{profile.get('label') or profile_key} ({profile_key})"


def _prompt_profile_key(store: dict, prompt: str = "対象を選択してください") -> str:
    profiles = store.get("profiles") or {}
    keys = [k for k in ("prod", "test") if k in profiles]
    if not keys:
        keys = list(profiles.keys())
    for idx, key in enumerate(keys, start=1):
        profile = profiles[key]
        label = profile.get("label") if isinstance(profile, dict) else key
        print(f"  {idx}. {label} ({key})")
    while True:
        raw = input(f"{prompt}: ").strip()
        try:
            index = int(raw)
            if 1 <= index <= len(keys):
                return keys[index - 1]
        except Exception:
            pass
        if raw in profiles:
            return raw
        print("正しい番号を入力してください。")


def _edit_profile_url(profiles_mod, store: dict, profile_key: str) -> dict:
    profile = profiles_mod.get_profile(store, profile_key)
    print("")
    print(f"[接続先URL変更] {_profile_label(profile_key, profile)}")
    print(f"現在: {profile.get('url', '')}")
    raw = input("新しいURLを入力してください（空欄なら変更なし）: ").strip()
    if not raw:
        return store
    store = profiles_mod.update_profile_url(store, profile_key, raw)
    path = profiles_mod.save_profiles(store)
    print(f"[設定] 保存しました: {path}")
    return store


def _select_profile(args, profiles_mod) -> tuple[str, dict[str, str], dict]:
    store = profiles_mod.load_profiles()
    profiles = store.get("profiles") or {}

    if args.profile:
        profile_key = args.profile
        store = profiles_mod.set_last_profile(store, profile_key)
        profiles_mod.save_profiles(store)
        return profile_key, profiles_mod.get_profile(store, profile_key), store

    while True:
        store = profiles_mod.load_profiles()
        profiles = store.get("profiles") or {}
        last_key = store.get("last_profile", "prod")
        print("")
        print("XCgate 自動アップロード")
        print("")
        print("接続先:")
        for idx, key in enumerate(("prod", "test"), start=1):
            if key not in profiles:
                continue
            marker = " (前回)" if key == last_key else ""
            print(f"  {idx}. {_profile_label(key, profiles_mod.get_profile(store, key))}{marker}")
        print("  3. 接続先URLを編集")
        print("  4. 保存済み資格情報を更新")
        print("")
        raw = input(f"選択してください [前回: {last_key}]: ").strip()
        if raw == "":
            raw = last_key
        if raw == "1":
            raw = "prod"
        elif raw == "2":
            raw = "test"

        if raw in ("prod", "test"):
            store = profiles_mod.set_last_profile(store, raw)
            profiles_mod.save_profiles(store)
            return raw, profiles_mod.get_profile(store, raw), store

        if raw == "3":
            key = _prompt_profile_key(store, "URLを変更する接続先")
            store = _edit_profile_url(profiles_mod, store, key)
            continue

        if raw == "4":
            key = _prompt_profile_key(store, "資格情報を更新する接続先")
            store = profiles_mod.set_last_profile(store, key)
            profiles_mod.save_profiles(store)
            profile = profiles_mod.get_profile(store, key)
            profile["_force_credential_update"] = "1"
            return key, profile, store

        print("1, 2, 3, 4 のいずれかを入力してください。")


def _prompt_credentials(default_username: str = "") -> tuple[str, str]:
    while True:
        username = input(f"ユーザー名 [{default_username}]: ").strip() or default_username
        if username:
            break
        print("ユーザー名を入力してください。")
    password = getpass.getpass("パスワード: ")
    return username, password


def _ensure_credential(creds_mod, target: str, force_update: bool = False):
    if force_update:
        try:
            creds_mod.delete_credential(target)
        except Exception as e:
            print(f"[資格情報] 既存資格情報の削除をスキップしました: {e}")

    credential = creds_mod.read_credential(target)
    if credential and not force_update:
        print("[資格情報] Windows Credential Manager から読み込みました。")
        return credential

    print("")
    print("[資格情報] Windows Credential Manager に保存する資格情報を入力してください。")
    default_username = credential.username if credential else ""
    username, password = _prompt_credentials(default_username)
    creds_mod.write_credential(target, username, password)
    print("[資格情報] 保存しました。")
    return creds_mod.read_credential(target)


def _run_embedded(
    flow_file: Path,
    flows_dir: Path,
    runtime_dir: Path,
    profile_key: str,
    profile: dict[str, str],
    credential,
    use_setting: bool,
) -> int:
    argv = flow_args(
        flows_dir,
        flow_file,
        "--dest",
        str(profile["url"]),
        "--repeat-pick-files",
        "--no-storage-state",
        "--no-keep-open",
        "--slowmo",
        "200",
        "--var",
        f"xcgate_profile={profile_key}",
        "--var",
        f"xcgate_username={credential.username}",
        "--var",
        f"xcgate_password={credential.password}",
    )
    if use_setting:
        argv.append("--setting")
    return run_embedded_flow(
        program_name="xcgate_uploader",
        flows_dir=flows_dir,
        runtime_dir=runtime_dir,
        argv=argv,
    )


def _parse_args():
    parser = argparse.ArgumentParser(description="XCgate automatic upload launcher")
    parser.add_argument("--profile", choices=["prod", "test"], help="接続先プロファイルを指定します")
    parser.add_argument("--setting", action="store_true", help="フロー設定を編集します")
    parser.add_argument("--reset-credentials", action="store_true", help="保存済み資格情報を更新します")
    parser.add_argument(
        "--toolhub-smoke",
        action="store_true",
        help="ToolHub 登録用に依存関係と同梱ファイルだけを検証します",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if args.toolhub_smoke:
        return run_toolhub_smoke(caller_file=__file__, flow_files=["xcgate_upload.flow"])

    runtime_dir = runtime_root(Path(__file__).stem)
    flows_dir = flows_root(__file__)
    flow_file = flows_dir / "flows" / "xcgate_upload.flow"

    if not ensure_resources(flows_dir, flow_file):
        pause_if_no_tty()
        return 1

    profiles_mod, creds_mod = _load_runtime_modules(flows_dir)
    rc = 0
    try:
        profile_key, profile, _ = _select_profile(args, profiles_mod)
        if not profile.get("url"):
            store = profiles_mod.load_profiles()
            store = _edit_profile_url(profiles_mod, store, profile_key)
            profile = profiles_mod.get_profile(store, profile_key)
        credential = _ensure_credential(
            creds_mod,
            profile["credential_target"],
            force_update=args.reset_credentials or profile.pop("_force_credential_update", "") == "1",
        )
        if credential is None:
            raise RuntimeError("資格情報を取得できませんでした。")

        while True:
            print("")
            print(f"[起動] 接続先: {_profile_label(profile_key, profile)}")
            print(f"[起動] URL: {profile['url']}")
            print("[起動] 資格情報: Windows Credential Manager")
            rc = _run_embedded(
                flow_file=flow_file,
                flows_dir=flows_dir,
                runtime_dir=runtime_dir,
                profile_key=profile_key,
                profile=profile,
                credential=credential,
                use_setting=args.setting,
            )
            if rc == 0:
                print("\n[完了] 正常終了しました。")
                break

            print(f"\n[警告] 終了コード {rc} で終了しました。")
            try:
                raw = input("資格情報を更新して再実行しますか？ [y/N]: ").strip().lower()
            except EOFError:
                raw = ""
            if raw not in ("y", "yes"):
                break
            credential = _ensure_credential(
                creds_mod,
                profile["credential_target"],
                force_update=True,
            )
    except Exception as e:
        print(f"[エラー] {e}")
        rc = 1
    finally:
        pause_if_no_tty()
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
