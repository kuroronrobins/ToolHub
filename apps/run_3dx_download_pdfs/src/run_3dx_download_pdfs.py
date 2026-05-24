# run_3dx_download_pdfs.py
# 3Dexperience 上でドキュメントIDごとに PDF をダウンロードするランチャー

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
        if not sys.stdin or not sys.stdin.isatty():
            input(msg)
    except Exception:
        pass


def _prompt_doc_ids() -> list[str]:
    print("")
    print("========================================")
    print("3Dexperience PDFダウンロード")
    print("========================================")
    print("PDFをダウンロードしたいドキュメントIDを入力してください。")
    print("")
    print("入力方法:")
    print(" - 1行につき1件のドキュメントIDを入力します。")
    print(" - Excelの1列をコピーして、そのまま貼り付けても構いません。")
    print(" - 重複したIDは自動的に1件にまとめます。")
    print(" - 入力が終わったら、空行のまま Enter を押します。")
    print("")
    print("入力例:")
    print("  DC-0110257")
    print("  DC-0110258")
    print("  DC-0110260")
    print("")
    print("補足:")
    print(" - 通常は最新RevisionのPDFのみを対象にします。")
    print(" - 全Revisionを対象にしたい場合は --setting で download_all_revisions を true に変更してください。")
    print("")
    print("入力してください:")
    ids: list[str] = []
    try:
        while True:
            line = input("> ").strip()
            if not line:
                break
            ids.append(line)
    except EOFError:
        pass
    # 順序維持で重複除去
    out: list[str] = []
    seen = set()
    for doc_id in ids:
        if doc_id not in seen:
            seen.add(doc_id)
            out.append(doc_id)
    if out:
        print("")
        print(f"[入力確認] {len(out)} 件のドキュメントIDを受け付けました。")
        for idx, doc_id in enumerate(out, start=1):
            print(f"  {idx}. {doc_id}")
        print("")
        print("次にブラウザが開きます。3Dexperience にログインし、開始できる画面になったら")
        print("コンソールで 'go' と入力して Enter を押してください。")
    return out


def _run_embedded(
    flow_file: Path,
    flows_dir: Path,
    runtime_dir: Path,
    doc_ids: list[str],
    use_setting: bool,
    keep_open: bool,
) -> int:
    keep_mode = "--keep-open" if keep_open else "--no-keep-open"
    argv = flow_args(
        flows_dir,
        flow_file,
        "--manual-kickoff",
        keep_mode,
        "--slowmo",
        "200",
        "--files",
        *doc_ids,
    )
    if use_setting:
        argv.append("--setting")
    return run_embedded_flow(
        program_name="3dx_pdf_downloader",
        flows_dir=flows_dir,
        runtime_dir=runtime_dir,
        argv=argv,
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="3Dexperience PDF download launcher")
    parser.add_argument("--setting", action="store_true", help="フロー設定を編集します")
    parser.add_argument("--keep-open", action="store_true", help="実行後にブラウザを開いたままにします")
    parser.add_argument(
        "--toolhub-smoke",
        action="store_true",
        help="ToolHub 登録用に依存関係と同梱ファイルだけを検証します",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if args.toolhub_smoke:
        return run_toolhub_smoke(caller_file=__file__, flow_files=["3dx_download_pdfs.flow"])

    runtime_dir = runtime_root(Path(__file__).stem)
    flows_dir = flows_root(__file__)
    flow_file = flows_dir / "flows" / "3dx_download_pdfs.flow"

    if not ensure_resources(flows_dir, flow_file):
        pause_if_no_tty()
        return 1

    doc_ids = _prompt_doc_ids()
    if not doc_ids:
        print("[注意] ドキュメントIDが入力されなかったため、処理を中止します。")
        pause_if_no_tty()
        return 1

    print("[起動] 3Dexperience PDF ダウンロードフローを開始します")
    print(f"[起動] 実行ディレクトリ: {flows_dir}")
    print(f"[起動] ログ保存先: {runtime_dir}")
    print("-" * 60)

    try:
        rc = _run_embedded(flow_file, flows_dir, runtime_dir, doc_ids, args.setting, args.keep_open)
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
