# run_3dx_create_ids.py
# 3Dexperience 上で新規ドキュメントID（DC-xxxx）を複数発行するためのランチャー
# 配布物の直下（XCgate_AutoUpload フォルダ）に配置して実行します。

import os
import sys
import subprocess
from pathlib import Path


def pause_if_no_tty(msg="実行を終了します。Enter を押してください…"):
    try:
        # コンソール入力がない（ダブルクリック実行等）の場合だけ一時停止
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


def _prompt_titles() -> list[str]:
    print("3Dexperience に登録したいドキュメントのタイトルを改行区切りで入力してください。")
    print("入力を終えるには空行のまま Enter を押します。")
    lines: list[str] = []
    try:
        while True:
            line = input().rstrip("\r\n")
            if not line.strip():
                if lines:
                    break
                else:
                    continue
            lines.append(line.strip())
    except EOFError:
        pass
    return lines


def _run_embedded(flow_file: Path, flows_dir: Path, titles: list[str]) -> int:
    """配布（exe）時、内蔵の src.* を使って同一プロセスで起動する。"""
    import importlib

    # src パッケージが見えるように sys.path を先頭に追加
    sys.path.insert(0, str(flows_dir))

    cwd = Path.cwd()
    try:
        os.chdir(str(flows_dir))
        m = importlib.import_module("src.main")
        # 起動引数を組み立て（手動キックオフ + タイトル配列）
        sys.argv = [
            "3dx_id_creator",
            "--flow", str(flow_file),
            "--manual-kickoff",
            "--keep-open",
            "--slowmo", "200",
        ]
        if titles:
            sys.argv += ["--files", *titles]
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
    flow_file = flows_dir / "flows" / "3dx_create_ids.flow"

    # 事前チェック
    if not flows_dir.is_dir():
        print(f"[エラー] 実行ディレクトリが正しくありません。フォルダが見つかりません: {flows_dir}")
        return pause_if_no_tty()
    if not flow_file.is_file():
        print(f"[エラー] フローファイルが見つかりません: {flow_file}")
        return pause_if_no_tty()

    # タイトル入力を受け付け
    titles = _prompt_titles()
    if not titles:
        print("[注意] タイトルが入力されませんでした。手動入力モードで起動します。")

    if _is_frozen():
        print("[起動] 同梱ランタイムを使って実行します（配布モード）")
        rc = _run_embedded(flow_file, flows_dir, titles)
        if rc == 0:
            print("\n[結果] 正常終了しました。")
        else:
            print(f"\n[失敗] 終了コード {rc}。ログをご確認ください。")
        return pause_if_no_tty()

    # 通常の Python 実行ではサブプロセスで起動
    cmd = [
        sys.executable, "-m", "src.main",
        "--flow", str(flow_file),
        "--manual-kickoff",
        "--keep-open",
        "--slowmo", "200",
    ]
    if titles:
        cmd += ["--files", *titles]

    print("[起動] 3Dexperience 新規ドキュメントID発行フローを開始します")
    print(f"[起動] 実行ディレクトリ: {flows_dir}")
    print(f"[起動] 実行コマンド : {' '.join(cmd)}")
    print("-" * 60)

    try:
        completed = subprocess.run(cmd, cwd=str(flows_dir))
        rc = completed.returncode
        if rc == 0:
            print("\n[結果] 正常終了しました。")
        else:
            print(f"\n[失敗] 終了コード {rc}。ログをご確認ください。")
    except FileNotFoundError:
        print("[エラー] Python もしくは必要なモジュールが見つかりません。Python の導入をご確認ください。")
    except Exception as e:
        print(f"[エラー] 予期しない例外が発生しました: {e}")
    finally:
        pause_if_no_tty()


if __name__ == "__main__":
    main()
