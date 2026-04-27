# run_xcgate_upload.py
# ダブルクリックで XC-Gate 自動アップロードを起動するランチャー
# 配置場所は XCgate_AutoUpload フォルダ直下

import os
import sys
import subprocess
from pathlib import Path


def pause_if_no_tty(msg="終了するには Enter を押してください..."):
    try:
        # コンソールがない（ダブルクリック起動）の場合のみ一時停止
        if not sys.stdin or not sys.stdin.isatty():
            input(msg)
    except Exception:
        pass


def _is_frozen() -> bool:
    return getattr(sys, "frozen", False) is True


def _guess_base_dir() -> Path:
    # 通常: このファイルのある場所
    # frozen(onefile/onedir): exe のフォルダ or _MEIPASS
    if _is_frozen():
        if hasattr(sys, "_MEIPASS"):
            return Path(getattr(sys, "_MEIPASS"))
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _run_embedded(flow_file: Path, flows_dir: Path) -> int:
    """凍結版（exe）で、同梱した src.* を使ってその場で実行する。"""
    import importlib
    import types

    # src パッケージを解決できるように sys.path を通す
    sys.path.insert(0, str(flows_dir))

    # 作業ディレクトリは xcgate_flows にしておく（config.yaml 相対参照のため）
    cwd = Path.cwd()
    try:
        os.chdir(str(flows_dir))
        # src.main を import して main() を直接呼び出す
        m = importlib.import_module("src.main")
        # 引数を組み立て（ランチャーと同等の既定値）
        sys.argv = [
            "xcgate_uploader",
            "--flow", str(flow_file),
            "--pick-files",
            "--manual-kickoff",
            "--keep-open",
            "--slowmo", "200",
        ]
        try:
            m.main()  # type: ignore[attr-defined]
            return 0
        except SystemExit as e:
            return int(e.code) if isinstance(e.code, int) else 1
    finally:
        os.chdir(str(cwd))


def main():
    base_dir = _guess_base_dir()
    flows_dir = base_dir / "xcgate_flows"
    flow_file = flows_dir / "flows" / "xcgate_upload.flow"

    # 事前チェック
    if not flows_dir.is_dir():
        print(f"[エラー] 実行ディレクトリが不正です。想定フォルダが見つかりません: {flows_dir}")
        return pause_if_no_tty()
    if not flow_file.is_file():
        print(f"[エラー] フロー定義ファイルが見つかりません: {flow_file}")
        return pause_if_no_tty()

    if _is_frozen():
        # exe 化された場合は、同梱コードを直接呼び出す
        print("[起動] 同梱モジュールを使って実行します（凍結モード）")
        rc = _run_embedded(flow_file, flows_dir)
        if rc == 0:
            print("\n[完了] 正常終了しました。")
        else:
            print(f"\n[警告] 終了コード {rc}。ログを確認してください。")
        return pause_if_no_tty()

    # 通常の Python 実行環境では、モジュールとして起動
    cmd = [
        sys.executable, "-m", "src.main",
        "--flow", str(flow_file),
        "--pick-files",
        "--manual-kickoff",
        "--keep-open",
        "--slowmo", "200",
    ]

    print("[起動] XC-Gate アップロードフローを起動します")
    print(f"[起動] 実行ディレクトリ: {flows_dir}")
    print(f"[起動] 実行コマンド : {' '.join(cmd)}")
    print("-" * 60)

    try:
        completed = subprocess.run(cmd, cwd=str(flows_dir))
        rc = completed.returncode
        if rc == 0:
            print("\n[完了] 正常終了しました。")
        else:
            print(f"\n[警告] 終了コード {rc}。ログを確認してください。")
    except FileNotFoundError:
        print("[エラー] Python または必要モジュールが見つかりませんでした。環境の Python を確認してください。")
    except Exception as e:
        print(f"[エラー] 予期しない例外が発生しました: {e}")
    finally:
        pause_if_no_tty()


if __name__ == "__main__":
    main()
