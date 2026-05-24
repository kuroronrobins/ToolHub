# run_3dx_create_ids.py
# 3Dexperience 上で新規ドキュメントID（DC-xxxx）を複数発行するためのランチャー
# 配布物の直下（XCgate_AutoUpload フォルダ）に配置して実行します。

import argparse
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


def pause_if_no_tty(msg="実行を終了します。Enter を押してください…"):
    try:
        # コンソール入力がない（ダブルクリック実行等）の場合だけ一時停止
        if not sys.stdin or not sys.stdin.isatty():
            input(msg)
    except Exception:
        pass


def _prompt_titles() -> list[str]:
    print("")
    print("========================================")
    print("3Dexperience 新規ドキュメントID発行")
    print("========================================")
    print("作成したいドキュメントのタイトルを入力してください。")
    print("")
    print("入力方法:")
    print(" - 1行につき1件のタイトルを入力します。")
    print(" - Excelの1列をコピーして、そのまま貼り付けても構いません。")
    print(" - 入力が終わったら、空行のまま Enter を押します。")
    print("")
    print("入力例:")
    print("  QC工程検査表_2026年05月")
    print("  包装工程チェックシート_Aライン")
    print("  滅菌記録確認表_試作")
    print("")
    print("入力してください:")
    lines: list[str] = []
    try:
        while True:
            line = input("> ").rstrip("\r\n")
            if not line.strip():
                if lines:
                    break
                else:
                    continue
            lines.append(line.strip())
    except EOFError:
        pass
    if lines:
        print("")
        print(f"[入力確認] {len(lines)} 件のタイトルを受け付けました。")
        for idx, title in enumerate(lines, start=1):
            print(f"  {idx}. {title}")
        print("")
        print("次にブラウザが開きます。3Dexperience にログインし、開始できる画面になったら")
        print("コンソールで 'go' と入力して Enter を押してください。")
    return lines


def _run_embedded(flow_file: Path, flows_dir: Path, runtime_dir: Path, titles: list[str], use_setting: bool) -> int:
    argv = flow_args(
        flows_dir,
        flow_file,
        "--manual-kickoff",
        "--keep-open",
        "--slowmo",
        "200",
    )
    if use_setting:
        argv.append("--setting")
    if titles:
        argv += ["--files", *titles]
    return run_embedded_flow(
        program_name="3dx_id_creator",
        flows_dir=flows_dir,
        runtime_dir=runtime_dir,
        argv=argv,
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="3Dexperience document ID launcher")
    parser.add_argument("--setting", action="store_true", help="フロー設定を編集します")
    parser.add_argument(
        "--toolhub-smoke",
        action="store_true",
        help="ToolHub 登録用に依存関係と同梱ファイルだけを検証します",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if args.toolhub_smoke:
        return run_toolhub_smoke(caller_file=__file__, flow_files=["3dx_create_ids.flow"])

    runtime_dir = runtime_root(Path(__file__).stem)
    flows_dir = flows_root(__file__)
    flow_file = flows_dir / "flows" / "3dx_create_ids.flow"

    # 事前チェック
    if not ensure_resources(flows_dir, flow_file):
        pause_if_no_tty()
        return 1

    # タイトル入力を受け付け
    titles = _prompt_titles()
    if not titles:
        print("[注意] タイトルが入力されませんでした。手動入力モードで起動します。")

    print("[起動] 3Dexperience 新規ドキュメントID発行フローを開始します")
    print(f"[起動] 実行ディレクトリ: {flows_dir}")
    print(f"[起動] ログ保存先: {runtime_dir}")
    print("-" * 60)

    try:
        rc = _run_embedded(flow_file, flows_dir, runtime_dir, titles, args.setting)
        if rc == 0:
            print("\n[結果] 正常終了しました。")
        else:
            print(f"\n[失敗] 終了コード {rc}。ログをご確認ください。")
    except Exception as e:
        print(f"[エラー] 予期しない例外が発生しました: {e}")
        rc = 1
    finally:
        pause_if_no_tty()
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
