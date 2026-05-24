#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse
import datetime
import os
import re
import sys
from typing import Any
from pathlib import Path

from .web.browser import BrowserCtx
from .io.config_loader import load_config
from .io.flow_settings import (
    get_flow_overrides,
    prompt_editable_vars,
    set_flow_overrides,
)
from .engine.parser import parse
from .engine.runtime import eval_expr
from .engine.executor import run
from .engine.actions import act_goto
from .web.utils import save_screenshot, save_html
from .flows.handlers import get_flow_handler


class _RestartWithUpdatedSettings(Exception):
    pass


def read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _runtime_root_dir() -> str:
    env_root = os.environ.get("XCGATE_RUNTIME_DIR", "").strip()
    if env_root:
        try:
            return str(Path(env_root).resolve())
        except Exception:
            return os.path.abspath(env_root)
    if getattr(sys, "frozen", False):
        try:
            return str(Path(sys.executable).resolve().parent)
        except Exception:
            pass
    return os.getcwd()


def _runtime_path(raw_path: str | None, runtime_root: str) -> str | None:
    if raw_path is None:
        return None
    text = str(raw_path).strip()
    if not text:
        return text
    return os.path.abspath(text if os.path.isabs(text) else os.path.join(runtime_root, text))


def _prepare_logging_paths(cfg: dict, flow_name: str) -> None:
    logging_cfg = cfg.setdefault("logging", {})
    options_cfg = cfg.setdefault("options", {})
    runtime_root = _runtime_root_dir()
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    flow_tag = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(flow_name).stem or "flow")

    raw_logs_dir = str(logging_cfg.get("shots_dir") or "logs")
    logs_dir = raw_logs_dir if os.path.isabs(raw_logs_dir) else os.path.join(runtime_root, raw_logs_dir)
    logs_dir = os.path.abspath(logs_dir)
    os.makedirs(logs_dir, exist_ok=True)
    logging_cfg["shots_dir"] = logs_dir
    logging_cfg["runtime_root"] = runtime_root

    raw_csv = str(logging_cfg.get("csv_path") or "logs/upload_log.csv")
    csv_base = raw_csv if os.path.isabs(raw_csv) else os.path.join(runtime_root, raw_csv)
    csv_base = os.path.abspath(csv_base)
    csv_dir = os.path.dirname(csv_base) or logs_dir
    os.makedirs(csv_dir, exist_ok=True)
    base_name = os.path.basename(csv_base)
    stem, ext = os.path.splitext(base_name)
    if not ext:
        ext = ".csv"
    stem = stem or "upload_log"
    run_csv = os.path.join(csv_dir, f"{stem}_{flow_tag}_{stamp}{ext}")
    logging_cfg["csv_path"] = run_csv
    logging_cfg["run_stamp"] = stamp

    raw_doc_log = str(logging_cfg.get("doc_log_path") or os.path.join("logs", "doc_ids.txt"))
    doc_log_path = raw_doc_log if os.path.isabs(raw_doc_log) else os.path.join(runtime_root, raw_doc_log)
    doc_log_path = os.path.abspath(doc_log_path)
    os.makedirs(os.path.dirname(doc_log_path) or runtime_root, exist_ok=True)
    logging_cfg["doc_log_path"] = doc_log_path

    storage_state_path = _runtime_path(options_cfg.get("storage_state_path"), runtime_root)
    if storage_state_path:
        os.makedirs(os.path.dirname(storage_state_path) or runtime_root, exist_ok=True)
        options_cfg["storage_state_path"] = storage_state_path

    user_data_dir = _runtime_path(options_cfg.get("user_data_dir"), runtime_root)
    if user_data_dir:
        options_cfg["user_data_dir"] = user_data_dir

    logging_cfg["har_path"] = _runtime_path(logging_cfg.get("har_path") or os.path.join("logs", "network.har"), runtime_root)
    logging_cfg["trace_path"] = _runtime_path(logging_cfg.get("trace_path") or os.path.join("logs", "trace.zip"), runtime_root)

    print(f"[LOG] runtime_root: {runtime_root}")
    print(f"[LOG] csv_path: {run_csv}")
    print(f"[LOG] shots_dir: {logs_dir}")


def pick_files_gui(multi=True):
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    paths = filedialog.askopenfilenames(title="アップロードするファイルを選択してください")
    root.destroy()
    return list(paths) if paths else []


def _editable_vars(ast: dict) -> list[str]:
    settings = ast.get("settings") or {}
    raw = settings.get("editable_vars") or []
    out: list[str] = []
    seen = set()
    for key in raw:
        if isinstance(key, str) and key and key not in seen:
            seen.add(key)
            out.append(key)
    return out


def _apply_saved_overrides(flow_name: str, ast: dict, editable_vars: list[str]) -> None:
    if not editable_vars:
        return
    saved = get_flow_overrides(flow_name)
    if not saved:
        return
    vars_block = ast.setdefault("vars", {})
    for key in editable_vars:
        if key in saved:
            vars_block[key] = saved[key]


def _prompt_and_save_flow_settings(flow_name: str, ast: dict, editable_vars: list[str]) -> bool:
    if not editable_vars:
        print(f"[SETTING] Flow '{flow_name}' has no editable vars.")
        return False

    vars_block = ast.setdefault("vars", {})
    current_values = {k: vars_block.get(k, "") for k in editable_vars}
    updated_values, changed = prompt_editable_vars(flow_name, editable_vars, current_values)
    if not updated_values:
        return False

    for key, value in updated_values.items():
        vars_block[key] = value

    if changed:
        store_path = set_flow_overrides(
            flow_name,
            {k: vars_block.get(k, "") for k in editable_vars},
        )
        print(f"[SETTING] Saved: {store_path}")
    else:
        print("[SETTING] No changes detected.")
    return changed


def _resolve_url_candidate(value: Any, ctx: dict[str, Any]) -> str | None:
    if value is None:
        return None

    candidate = str(value).strip().strip('"').strip("'")
    if not candidate:
        return None

    try:
        candidate = str(eval_expr(candidate, ctx)).strip().strip('"').strip("'")
    except Exception:
        pass

    if candidate.startswith(("http://", "https://")):
        return candidate
    return None


def _first_start_goto_expr(ast: dict) -> str | None:
    start = ast.get("start") or []
    if not start:
        return None
    first = start[0]
    if isinstance(first, str):
        stmt = first.strip()
        if stmt.startswith("goto "):
            return stmt[len("goto ") :].strip()
    return None


def _infer_start_url(flow_text: str, ast: dict, cli_vars: dict[str, Any]) -> str | None:
    vars_ctx: dict[str, Any] = {}
    vars_ctx.update(ast.get("vars") or {})
    vars_ctx.update(cli_vars or {})

    for key in ("destination_url", "site"):
        if key in vars_ctx:
            url = _resolve_url_candidate(vars_ctx.get(key), vars_ctx)
            if url:
                return url

    goto_expr = _first_start_goto_expr(ast)
    if goto_expr:
        url = _resolve_url_candidate(goto_expr, vars_ctx)
        if url:
            return url

    m = re.search(r"^\s*goto\s+(.+)$", flow_text, re.MULTILINE)
    if m:
        url = _resolve_url_candidate(m.group(1).strip(), vars_ctx)
        if url:
            return url
    return None


def _parse_var_args(raw_items: list[str] | None) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in raw_items or []:
        if not raw or "=" not in raw:
            print(f"[WARN] Ignoring invalid --var value: {raw}")
            continue
        key, value = raw.split("=", 1)
        key = key.strip()
        if not key:
            print(f"[WARN] Ignoring invalid --var value: {raw}")
            continue
        out[key] = value
    return out


def _apply_file_vars(cli_vars: dict[str, Any], files: list[str]) -> dict[str, Any]:
    out = dict(cli_vars or {})
    default_title = "AUTO TEST TITLE"
    try:
        items = [str(x).strip() for x in (files or []) if str(x).strip()]
    except Exception:
        items = []

    if not items:
        out["files"] = [default_title]
        out["title_text"] = default_title
        return out

    out["files"] = items
    out["title_text"] = items[0]
    batch_size = 5
    batches: list[dict[str, Any]] = []
    total = (len(items) + batch_size - 1) // batch_size
    for i in range(0, len(items), batch_size):
        chunk = items[i : i + batch_size]
        query = " OR ".join([f"(\"{x}\")" for x in chunk])
        batches.append(
            {
                "index": (i // batch_size) + 1,
                "total": total,
                "size": len(chunk),
                "files": chunk,
                "search_query": query,
            }
        )
    out["search_batches"] = batches
    out["search_query"] = batches[0]["search_query"]
    out["search_batch_size"] = batch_size
    return out


def _build_cli_vars(args, defer_files: bool = False) -> dict[str, Any]:
    cli_vars: dict[str, Any] = {}
    default_title = "AUTO TEST TITLE"
    cli_vars["title_text"] = default_title

    if args.dest:
        cli_vars["destination_url"] = args.dest
        cli_vars["site"] = args.dest

    cli_vars.update(_parse_var_args(getattr(args, "vars", [])))

    if defer_files:
        return cli_vars

    if args.pick_files:
        chosen = pick_files_gui(multi=True)
        if not chosen:
            print("No files were selected. Aborting.")
            return {}
        return _apply_file_vars(cli_vars, list(chosen))

    if args.files:
        return _apply_file_vars(cli_vars, list(args.files))

    return _apply_file_vars(cli_vars, [default_title])


def _create_browser_ctx(cfg: dict) -> BrowserCtx:
    return BrowserCtx(
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
        doc_log_path=(cfg.get("logging") or {}).get("doc_log_path"),
        har_path=(cfg.get("logging") or {}).get("har_path"),
        trace_path=(cfg.get("logging") or {}).get("trace_path"),
    )


def _prompt_yes_no(message: str, default_yes: bool = True) -> bool:
    suffix = "[Y/n]" if default_yes else "[y/N]"
    while True:
        try:
            raw = input(f"{message} {suffix} ").strip().lower()
        except EOFError:
            return default_yes
        if not raw:
            return default_yes
        if raw in ("y", "yes"):
            return True
        if raw in ("n", "no"):
            return False
        print("Please answer y or n.")


def _prompt_repeat_choice() -> str:
    print("")
    print("[NEXT] アップロードが完了しました。")
    print("  1. 続けて別ファイルをアップロードする")
    print("  2. ブラウザを残して終了する")
    print("  3. ブラウザも閉じて終了する")
    while True:
        try:
            raw = input("> ").strip()
        except EOFError:
            return "close"
        if raw in ("", "1"):
            return "again"
        if raw == "2":
            return "keep"
        if raw == "3":
            return "close"
        print("1, 2, 3 のいずれかを入力してください。")


def _run_once(
    args,
    cfg: dict,
    flow_name: str,
    flow_text: str,
    ast: dict,
    cli_vars: dict[str, Any],
    editable_vars: list[str],
    handler,
    allow_access_recovery: bool,
) -> tuple[bool, bool]:
    """
    Returns (retry_requested, failed).
    """
    with _create_browser_ctx(cfg) as b:
        run_started_at = datetime.datetime.now()
        last_run_started_at = run_started_at
        finish_reported = False
        retry_requested = False
        failed = False
        try:
            skip_first_goto = False
            cfg["_browser_ctx"] = b

            first_start_is_goto = _first_start_goto_expr(ast) is not None
            should_pre_goto = args.manual_kickoff or first_start_is_goto
            if should_pre_goto:
                start_url = _infer_start_url(flow_text, ast, cli_vars)
                if start_url:
                    try:
                        act_goto(
                            b.active_page,
                            start_url,
                            timeout_ms=cfg["options"]["timeout_page_ms"],
                            retries=cfg["options"].get("goto_retries", 0),
                            delay_ms=cfg["options"].get("goto_retry_delay_ms", 1000),
                            log=cfg["options"].get("log_actions", False),
                        )
                        skip_first_goto = first_start_is_goto
                    except Exception as e:
                        print(f"[ACCESS] Initial access failed: {e.__class__.__name__}: {e}")
                        if allow_access_recovery and editable_vars:
                            if _prompt_yes_no("[ACCESS] Edit flow settings now?", default_yes=True):
                                changed = _prompt_and_save_flow_settings(flow_name, ast, editable_vars)
                                if changed:
                                    print("[ACCESS] Settings updated. Retrying with a new browser session.")
                                    raise _RestartWithUpdatedSettings()
                        raise

            if args.manual_kickoff:
                print("\n[MANUAL] ここでログイン/必要な画面遷移を行ってください。準備ができたら 'go' と入力して Enter を押してください。")
                while True:
                    cmd = input("> ").strip().lower()
                    if cmd == "go":
                        print("[MANUAL] 'go' を受信。これから実行を開始します。")
                        break
                    print("  'go' と入力すると開始します。")

            run_index = 0
            while True:
                current_cli_vars = cli_vars
                if getattr(args, "repeat_pick_files", False):
                    if run_index > 0:
                        print("")
                        print("[NEXT] ブラウザで次のアップロード先を準備してから Enter を押してください。")
                        try:
                            input("> ")
                        except EOFError:
                            pass
                    chosen = pick_files_gui(multi=True)
                    if not chosen:
                        print("[NEXT] ファイルが選択されなかったため終了します。")
                        break
                    current_cli_vars = _apply_file_vars(cli_vars, list(chosen))

                last_run_started_at = datetime.datetime.now()
                finish_reported = False
                run(ast, b.active_page, cfg, cli_vars=current_cli_vars, skip_first_goto=skip_first_goto)
                try:
                    handler.on_finish(b, cfg, last_run_started_at)
                    finish_reported = True
                except Exception:
                    pass

                if not getattr(args, "repeat_pick_files", False):
                    break

                choice = _prompt_repeat_choice()
                if choice == "again":
                    run_index += 1
                    skip_first_goto = True
                    continue
                if choice == "keep":
                    args.keep_open = True
                break

        except _RestartWithUpdatedSettings:
            retry_requested = True
        except Exception as e:
            failed = True
            try:
                shot = save_screenshot(b.active_page, cfg["logging"]["shots_dir"], "error")
                html = save_html(b.active_page, cfg["logging"]["shots_dir"], "error")
                print(f"[ERROR] screenshot: {shot}, html: {html}")
            except Exception:
                pass
            print(f"[ERROR] {e.__class__.__name__}: {e}")
        finally:
            if retry_requested:
                cfg.pop("_browser_ctx", None)
            else:
                if not finish_reported:
                    try:
                        handler.on_finish(b, cfg, last_run_started_at)
                    except Exception:
                        pass
                cfg.pop("_browser_ctx", None)
                if args.keep_open or cfg["options"].get("keep_open", False):
                    print("\n実行が終了しました。ブラウザは開いたままです。閉じるには Enter を押してください。")
                    try:
                        input()
                    except EOFError:
                        pass
        return retry_requested, failed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--flow", default="flows/mega_upload.flow")
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--files", nargs="*", default=[])
    ap.add_argument("--pick-files", action="store_true")
    ap.add_argument("--repeat-pick-files", action="store_true")
    ap.add_argument("--var", dest="vars", action="append", default=[])
    ap.add_argument("--dest", default=None)
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--keep-open", action="store_true")
    ap.add_argument(
        "--no-keep-open",
        action="store_true",
        help="設定ファイルの keep_open=true を無効化して、実行後すぐ終了します",
    )
    ap.add_argument("--devtools", action="store_true")
    ap.add_argument("--slowmo", type=int, default=None)
    ap.add_argument(
        "--setting",
        action="store_true",
        help="flow が定義した編集可能変数を対話で変更し、保存します",
    )
    ap.add_argument(
        "--manual-kickoff",
        action="store_true",
        help="ユーザーが 'go' と入力するまで開始しません",
    )

    ap.add_argument("--no-storage-state", action="store_true")

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
    if args.no_keep_open:
        cfg["options"]["keep_open"] = False
    if args.no_storage_state:
        cfg["options"]["storage_state_path"] = None
        cfg["options"]["prefer_persistent"] = False
        cfg["options"]["user_data_dir"] = None
        cfg["options"]["user_data_profile"] = None
    _prepare_logging_paths(cfg, flow_name)

    flow_text = read_text(args.flow)
    ast = parse(flow_text)

    editable_vars = _editable_vars(ast)
    _apply_saved_overrides(flow_name, ast, editable_vars)

    if args.setting:
        _prompt_and_save_flow_settings(flow_name, ast, editable_vars)

    cli_vars = _build_cli_vars(args, defer_files=args.repeat_pick_files)
    if not cli_vars:
        return

    allow_access_recovery = True
    failed = False
    while True:
        should_retry, run_failed = _run_once(
            args=args,
            cfg=cfg,
            flow_name=flow_name,
            flow_text=flow_text,
            ast=ast,
            cli_vars=cli_vars,
            editable_vars=editable_vars,
            handler=handler,
            allow_access_recovery=allow_access_recovery,
        )
        failed = failed or run_failed
        if should_retry and allow_access_recovery:
            allow_access_recovery = False
            continue
        break

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
