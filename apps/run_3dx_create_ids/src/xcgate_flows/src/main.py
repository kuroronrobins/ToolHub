#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse, re, os
import datetime
from .web.browser import BrowserCtx
from .io.config_loader import load_config
from .engine.parser import parse
from .engine.executor import run
from .web.utils import save_screenshot, save_html
from .flows.handlers import get_flow_handler


def read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def pick_files_gui(multi=True):
    import tkinter as tk
    from tkinter import filedialog
    root = tk.Tk(); root.withdraw(); root.attributes("-topmost", True)
    # 日本語タイトル（UTF-8）
    paths = filedialog.askopenfilenames(title="アップロードするファイルを選択してください")
    root.destroy()
    return list(paths) if paths else []


def _infer_start_url(flow_text: str, ast: dict, cli_vars: dict) -> str | None:
    # 優先度: --dest > vars.site / vars.destination_url > フロー先頭の goto（URL）
    if "destination_url" in cli_vars:
        return cli_vars["destination_url"]
    for k in ("site", "destination_url"):
        if k in (ast.get("vars") or {}):
            return ast["vars"][k]
    m = re.search(r"^\s*goto\s+(\S+)", flow_text, re.MULTILINE)
    if m and m.group(1).startswith(("http://", "https://")):
        return m.group(1)
    return None



def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--flow", default="flows/mega_upload.flow")
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--files", nargs="*", default=[])
    ap.add_argument("--pick-files", action="store_true")
    ap.add_argument("--dest", default=None)
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--keep-open", action="store_true")
    ap.add_argument("--devtools", action="store_true")
    ap.add_argument("--slowmo", type=int, default=None)
    # 手動キックオフモード（'go' と入力するまで開始しない）
    ap.add_argument(
        "--manual-kickoff",
        action="store_true",
        help="ユーザーが 'go' と入力するまで開始しません",
    )

    args = ap.parse_args()
    flow_name = os.path.basename(args.flow)
    handler = get_flow_handler(flow_name)

    cfg = load_config(args.config)
    if args.headless:
        cfg["options"]["headless"] = True
    if args.devtools:
        cfg["options"]["devtools"] = True
    if args.slowmo is not None:
        cfg["options"]["slowmo_ms"] = args.slowmo

    flow_text = read_text(args.flow)
    ast = parse(flow_text)

    cli_vars = {}
    default_title = "AUTO TEST TITLE"
    cli_vars["title_text"] = default_title
    if args.pick_files:
        chosen = pick_files_gui(multi=True)
        if not chosen:
            print("No files were selected. Aborting.")
            return
        cli_vars["files"] = list(chosen)
        cli_vars["title_text"] = cli_vars["files"][0]
    elif args.files:
        cli_vars["files"] = args.files
        if args.files:
            cli_vars["title_text"] = args.files[0]
    else:
        cli_vars["files"] = [default_title]
    if not cli_vars.get("files"):
        cli_vars["files"] = [cli_vars.get("title_text", default_title)]
    if args.dest:
        cli_vars["destination_url"] = args.dest
        cli_vars["site"] = args.dest

    with BrowserCtx(
        headless=cfg["options"]["headless"],
        channel=cfg["options"].get("channel"),
        ignore_https_errors=cfg["options"].get("ignore_https_errors", False),
        slowmo_ms=cfg["options"].get("slowmo_ms", 0),
        devtools=cfg["options"].get("devtools", False),
        user_data_dir=cfg["options"].get("user_data_dir"),
        user_data_profile=cfg["options"].get("user_data_profile"),
        trace=cfg["options"].get("trace", False),
        har=cfg["options"].get("har", False),
        storage_state_path=cfg["options"].get("storage_state_path"),
        prefer_persistent=cfg["options"].get("prefer_persistent", False),
    ) as b:
        error = None
        run_started_at = datetime.datetime.now()
        try:
            skip_first_goto = False
            cfg['_browser_ctx'] = b

            if args.manual_kickoff:
                # 事前にログイン/遷移などを行う猶予を与える
                start_url = _infer_start_url(flow_text, ast, cli_vars)
                if start_url:
                    from .engine.actions import act_goto
                    act_goto(
                        b.active_page,
                        start_url,
                        timeout_ms=cfg["options"]["timeout_page_ms"],
                        retries=cfg["options"].get("goto_retries", 0),
                        delay_ms=cfg["options"].get("goto_retry_delay_ms", 1000),
                        log=cfg["options"].get("log_actions", False),
                    )
                    skip_first_goto = True
                print("\n[MANUAL] ここでログイン/必要な画面遷移を行ってください。準備ができたら 'go' と入力して Enter を押してください。")
                while True:
                    cmd = input("> ").strip().lower()
                    if cmd == "go":
                        print("[MANUAL] 'go' を受信。これから実行を開始します。")
                        break
                    print("  'go' と入力すると開始します。")

            run(ast, b.active_page, cfg, cli_vars=cli_vars, skip_first_goto=skip_first_goto)

        except Exception as e:
            error = e
            try:
                shot = save_screenshot(b.active_page, cfg["logging"]["shots_dir"], "error")
                html = save_html(b.active_page, cfg["logging"]["shots_dir"], "error")
                print(f"[ERROR] screenshot: {shot}, html: {html}")
            except Exception:
                pass
            print(f"[ERROR] {e.__class__.__name__}: {e}")
        finally:
            try:
                handler.on_finish(b, cfg, run_started_at)
            except Exception:
                pass
            cfg.pop('_browser_ctx', None)
            if args.keep_open or cfg["options"].get("keep_open", False):
                print("\n実行が終了しました。ブラウザは開いたままです。閉じるには Enter を押してください。")
                try:
                    input()
                except EOFError:
                    pass
            # finally ブロックから return しない（SyntaxWarning 防止）


if __name__ == "__main__":
    main()
