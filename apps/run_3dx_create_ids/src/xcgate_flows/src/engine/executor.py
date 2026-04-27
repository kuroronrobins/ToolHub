from .runtime import eval_expr, merge_vars
from .selectors import with_fallback
from .actions import (
    act_goto,
    act_wait,
    act_click,
    act_choose_file,
    act_set_input_files,
    act_fill,
    act_select_option,
    act_close_page,
)


def _log(enabled: bool, msg: str):
    if enabled:
        print(msg)


def _render_selector(sel_key_or_obj, selectors, vars_ctx, page):
    if isinstance(sel_key_or_obj, str) and sel_key_or_obj in selectors:
        sel_obj = selectors[sel_key_or_obj]
    else:
        sel_obj = sel_key_or_obj

    def _walk(d):
        out = {}
        for k, v in d.items():
            out[k] = eval_expr(v, vars_ctx) if isinstance(v, str) else v
        return out

    if isinstance(sel_obj, list):
        return [_walk(s) for s in sel_obj]
    if isinstance(sel_obj, dict):
        out = _walk(sel_obj)
        # If CSS selector contains comma-separated alternatives, expand to list for fallback
        if out.get("by") == "css":
            val = out.get("value") or ""
            if "," in val:
                alts = [v.strip() for v in val.split(",") if v.strip()]
                # Prefer input[...] alternatives first to avoid matching unrelated buttons/links
                alts.sort(key=lambda x: 0 if x.lower().startswith("input") else 1)
                return [{"by": "css", "value": v} for v in alts]
        return out
    if isinstance(sel_obj, str):
        if sel_obj.startswith("text:"):
            val = sel_obj.split("text:", 1)[1].strip().strip('"').strip("'")
            try:
                val = eval_expr(val, vars_ctx)
            except Exception:
                pass
            return {"by": "text", "value": val}
        if sel_obj.startswith(("css:", "#", ".", "//")):
            return {"by": "css", "value": sel_obj.replace("css:", "", 1)}
        return {"by": "text", "value": sel_obj}
    raise ValueError(f"Invalid selector: {sel_key_or_obj}")


def run(flow_ast: dict, page, cfg: dict, cli_vars: dict = None, skip_first_goto: bool = False):
    vars_ctx = merge_vars(flow_ast.get("vars", {}), cli_vars or {})
    ctx = {"_selectors": flow_ast.get("selectors", {}), **vars_ctx}
    log_actions = cfg["options"].get("log_actions", False)

    def time_to_ms(val: str) -> int:
        if val is None:
            return cfg["options"].get("timeout_page_ms", 30000)
        s = str(val).strip()
        try:
            s = eval_expr(s, ctx)
        except Exception:
            pass
        if s.endswith("ms"):
            s = s[:-2]
            return int(s)
        if s.endswith("s"):
            s = s[:-1]
            return int(float(s) * 1000)
        if s.endswith("m"):
            s = s[:-1]
            return int(float(s) * 60_000)
        return int(float(s))

    def summarize_step(it) -> str:
        if isinstance(it, dict):
            if "foreach" in it:
                spec = it["foreach"]
                return f"foreach {spec.get('var')} in {spec.get('arr')}"
            if "retry" in it:
                spec = it["retry"]
                return f"retry {spec.get('tries')} every {spec.get('interval')}"
            if "try" in it:
                return "try/catch"
            return str(it)
        return str(it)

    def exec_items(items):
        items = items or []
        for idx, it in enumerate(items):
            ctx["_next_step_preview"] = summarize_step(items[idx + 1]) if idx + 1 < len(items) else None
            exec_item(it)
        ctx.pop("_next_step_preview", None)

    def exec_item(item):
        if isinstance(item, dict):
            if "foreach" in item:
                spec = item["foreach"]
                var = spec.get("var")
                arr_expr = spec.get("arr") or ""
                arr_var = arr_expr.strip().strip("${}")
                items = ctx.get(arr_var, [])
                for it in items:
                    ctx[var] = it
                    exec_items(spec.get("steps") or [])
                return
            if "retry" in item:
                spec = item["retry"]
                tries_expr = spec.get("tries")
                interval_expr = spec.get("interval")
                steps = spec.get("steps") or []
                try:
                    tries_val = int(eval_expr(str(tries_expr), ctx).strip(" ${}"))
                except Exception:
                    tries_val = 0
                interval_ms = time_to_ms(str(interval_expr)) if interval_expr else 0
                last_err = None
                for attempt in range(tries_val + 1):
                    try:
                        exec_items(steps)
                        return
                    except Exception as e:
                        last_err = e
                        if attempt < tries_val and interval_ms > 0:
                            import time as _t
                            _t.sleep(interval_ms / 1000.0)
                            continue
                        raise last_err
            if "try" in item:
                spec = item["try"]
                try_steps = spec.get("steps") or []
                catch_steps = spec.get("catch") or []
                try:
                    exec_items(try_steps)
                except Exception:
                    exec_items(catch_steps)
                return
            raise ValueError(f"Unknown block: {item}")

        s = str(item).strip()
        if skip_first_goto and not getattr(exec_item, "_skipped_first_goto", False) and s.startswith("goto "):
            _log(log_actions, f"[FLOW] (skip first goto due to manual kickoff): {s}")
            exec_item._skipped_first_goto = True
            return
        _exec_stmt(page, s, ctx, cfg, time_to_ms)

    # --- start ---
    exec_items(flow_ast.get("start", []))

    # --- whens ---
    whens = flow_ast.get("whens") or []
    if isinstance(whens, dict):
        whens = [whens]

    for when in whens:
        cond = (when.get("condition") or "").strip().rstrip(":")
        _log(True, f"[FLOW] when: 条件 '{cond}' を待機します …")
        matched = True
        try:
            if cond.startswith("text:"):
                txt = cond.split("text:", 1)[1].strip().strip('"').strip("'")
                txt = eval_expr(txt, ctx)
                _log(True, f"[FLOW] wait(text): '{txt}' が表示されるまで待機 (timeout={cfg['options']['timeout_page_ms']}ms)")
                act_wait(page, text=txt, timeout_ms=cfg["options"]["timeout_page_ms"], log=log_actions)
            else:
                selectors = ctx.get("_selectors", {})
                sel = _render_selector(cond, selectors, ctx, page)
                if isinstance(sel, list):
                    sel = sel[0]
                _log(True, f"[FLOW] wait(selector): {sel} が可視になるまで待機 (timeout={cfg['options']['timeout_page_ms']}ms)")
                act_wait(page, selector=sel, timeout_ms=cfg["options"]["timeout_page_ms"], log=log_actions)
        except Exception as e:
            matched = False
            _log(True, f"[FLOW] when: 待機に失敗（スキップ）: {e}")
        if matched:
            steps = when.get("steps", [])
            if steps:
                _log(True, f"[FLOW] when: 条件成立。次のステップ: {summarize_step(steps[0])}")
            exec_items(steps)


def _exec_stmt(page, stmt: str, ctx, cfg, _time_to_ms=None):
    s = stmt.strip()
    log_actions = cfg["options"].get("log_actions", False)
    _log(log_actions, f"[FLOW] step: {s}")

    # goto
    if s.startswith("goto "):
        url = eval_expr(s[len("goto "):].strip(), ctx)
        act_goto(
            page,
            url,
            timeout_ms=cfg["options"]["timeout_page_ms"],
            retries=cfg["options"].get("goto_retries", 0),
            delay_ms=cfg["options"].get("goto_retry_delay_ms", 1000),
            log=log_actions,
        )
        return

    # wait
    if s.startswith("wait "):
        arg = s[len("wait "):].strip()
        import re as _re
        timeout_ms = cfg["options"]["timeout_page_ms"]
        visible = True
        if arg.startswith("text:"):
            m_to = _re.search(r"timeout:([^\s]+)", arg)
            if m_to and _time_to_ms:
                timeout_ms = _time_to_ms(m_to.group(1))
            m_vis = _re.search(r"visible:(true|false)", arg, _re.IGNORECASE)
            if m_vis:
                visible = m_vis.group(1).lower() == "true"
            text = arg.split("text:", 1)[1].strip()
            text = _re.sub(r"timeout:[^\s]+", "", text)
            text = _re.sub(r"visible:(true|false)", "", text, flags=_re.IGNORECASE).strip()
            text = text.strip().strip('"').strip("'")
            text = eval_expr(text, ctx)
            nxt = ctx.get("_next_step_preview")
            _log(True, f"[FLOW] 待機: テキスト '{text}' (timeout={timeout_ms}ms, visible={visible}). 次に実行: {nxt}")
            act_wait(page, text=text, timeout_ms=timeout_ms, visible=visible, log=log_actions)
        else:
            m_to = _re.search(r"timeout:([^\s]+)", arg)
            if m_to and _time_to_ms:
                timeout_ms = _time_to_ms(m_to.group(1))
                arg = arg[: m_to.start()].strip()
            m_vis = _re.search(r"visible:(true|false)", arg, _re.IGNORECASE)
            if m_vis:
                visible = m_vis.group(1).lower() == "true"
                arg = arg.replace(m_vis.group(0), "").strip()
            name = arg.strip()
            sel = _render_selector(name, ctx["_selectors"], ctx, page)
            if isinstance(sel, list):
                sel = sel[0]
            nxt = ctx.get("_next_step_preview")
            _log(True, f"[FLOW] 待機: セレクタ {sel} (timeout={timeout_ms}ms, visible={visible}). 次に実行: {nxt}")
            act_wait(page, selector=sel, timeout_ms=timeout_ms, visible=visible, log=log_actions)
        return

    # wait_any [a, b, ...] timeout:NN visible:true|false
    if s.startswith("wait_any "):
        import re as _re, time as _t
        body = s[len("wait_any "):].strip()
        timeout_ms = cfg["options"]["timeout_page_ms"]
        visible = True
        # parse timeout/visible flags
        m_to = _re.search(r"timeout:([^\s]+)", body)
        if m_to and _time_to_ms:
            timeout_ms = _time_to_ms(m_to.group(1))
            body = body[: m_to.start()].strip()
        m_vis = _re.search(r"visible:(true|false)", body, _re.IGNORECASE)
        if m_vis:
            visible = m_vis.group(1).lower() == "true"
            body = body.replace(m_vis.group(0), "").strip()
        # extract list inside brackets
        m_arr = _re.search(r"\[(.*)\]", body)
        if not m_arr:
            raise ValueError(f"Invalid wait_any syntax (missing [..]): {s}")
        raw_list = m_arr.group(1).strip()
        # split by commas at top level (no nesting expected here)
        parts = [p.strip() for p in raw_list.split(",") if p.strip()]
        if not parts:
            raise ValueError(f"wait_any requires at least one target: {s}")

        # render selectors
        alts = []
        for p in parts:
            sel = _render_selector(p, ctx["_selectors"], ctx, page)
            alts.append(sel)

        nxt = ctx.get("_next_step_preview")
        _log(True, f"[FLOW] 待機(OR): {parts} (timeout={timeout_ms}ms, visible={visible}). 次に実行: {nxt}")
        deadline = _t.monotonic() + (timeout_ms / 1000.0)
        last_err = None
        while _t.monotonic() < deadline:
            for idx, sel in enumerate(alts):
                try:
                    loc = with_fallback(page, sel).first
                    ok = loc.is_visible() if visible else (loc.count() == 0 or not loc.is_visible())
                    if ok:
                        ctx["_last_match_index"] = idx
                        try:
                            ctx["_last_match"] = parts[idx]
                        except Exception:
                            ctx["_last_match"] = str(parts[idx])
                        _log(True, f"[FLOW] wait_any: matched index={idx} target={parts[idx]}")
                        return
                except Exception as e:
                    last_err = e
            _t.sleep(0.2)
        # timeout
        if last_err:
            raise last_err
        raise TimeoutError(f"wait_any timeout after {timeout_ms}ms for targets: {parts}")

    # click
    if s.startswith("click "):
        name = s[len("click "):].strip()
        sel = _render_selector(name, ctx["_selectors"], ctx, page)
        if isinstance(sel, list):
            sel = sel[0]
        _log(True, f"[FLOW] クリック: {sel}")
        act_click(page, sel, log=log_actions)
        return

    # choose_file
    if s.startswith("choose_file "):
        import re as _re
        m_open = _re.search(r"open_by:\((.+?)\)", s)
        m_set = _re.search(r"set:(.+)$", s)
        open_key = None
        set_val = None
        if m_open and m_set:
            open_key = m_open.group(1).strip()
            set_val = m_set.group(1).strip()
        else:
            body = s[len("choose_file ") :].strip()
            parts = body.split(" ")
            if parts:
                open_key = parts[0].strip().rstrip(",")
                m_file = _re.search(r"file:(.+)$", s)
                if m_file:
                    set_val = m_file.group(1).strip()
        if not open_key or set_val is None:
            raise ValueError(f"Invalid choose_file syntax: {s}")
        set_val = set_val.strip().strip("[ ]")
        paths = [eval_expr(x.strip().strip(","), ctx) for x in set_val.split(",") if x.strip()]
        sel = _render_selector(open_key, ctx["_selectors"], ctx, page)
        if isinstance(sel, list):
            sel = sel[0]
        _log(True, f"[FLOW] ファイル選択: {paths} を {sel} から選択(FileChooser)")
        fc_timeout = cfg["options"].get("timeout_file_chooser_ms", 5000)
        act_choose_file(page, sel, paths, log=log_actions, timeout_ms=fc_timeout)
        return

    # screenshot path:<...>
    if s.startswith("screenshot "):
        import re as _re
        m = _re.search(r"path:([^,]+)", s)
        if not m:
            raise ValueError(f"Invalid screenshot syntax: {s}")
        out_path = eval_expr(m.group(1).strip().strip('"').strip("'"), ctx)
        # optional full:true|false
        m_full = _re.search(r"full:(true|false)", s, _re.IGNORECASE)
        full_flag = False
        if m_full:
            full_flag = m_full.group(1).lower() == 'true'
        from .actions import act_screenshot
        act_screenshot(page, out_path, log=log_actions, full_page=full_flag)
        return

    # log_csv { key: value, ... }
    if s.startswith("log_csv "):
        body = s[len("log_csv "):].strip()
        if body.startswith("{") and body.endswith("}"):
            inner = body[1:-1].strip()
        else:
            inner = body
        # split on top-level commas
        parts = []
        buf = []
        quoted = None
        depth_br = 0
        for ch in inner:
            if quoted:
                buf.append(ch)
                if ch == quoted:
                    quoted = None
                continue
            # quote start
            if ch in ('"', "'"):
                quoted = ch
                buf.append(ch)
                continue
            if ch == '{':
                depth_br += 1
            elif ch == '}':
                depth_br = max(0, depth_br - 1)
            if ch == ',' and depth_br == 0:
                parts.append(''.join(buf))
                buf = []
                continue
            buf.append(ch)
        if buf:
            parts.append(''.join(buf))
        data = {}
        from .runtime import BUILTINS
        for p in parts:
            if ':' not in p:
                continue
            k, v = p.split(':', 1)
            key = k.strip().strip('"').strip("'")
            val = v.strip()
            if val == 'now()':
                data[key] = BUILTINS['now']()
            else:
                # strip quotes then eval_expr (to resolve ${...})
                val = val.strip().strip('"').strip("'")
                data[key] = eval_expr(val, ctx)
        try:
            from ..io.csv_logger import append_row
            csv_path = cfg["logging"]["csv_path"]
            append_row(csv_path, data)
            _log(log_actions, f"[FLOW] log_csv: wrote to {csv_path}: {data}")
        except Exception as e:
            _log(log_actions, f"[FLOW] log_csv failed: {e}")
        return

    # set_input_files
    if s.startswith("set_input_files "):
        body = s[len("set_input_files ") :]
        key = body.split(",", 1)[0].strip()
        files_part = body.split("files:", 1)[1].strip().strip("[ ]")
        paths = [eval_expr(x.strip().strip(","), ctx) for x in files_part.split(",") if x.strip()]
        sel = _render_selector(key, ctx["_selectors"], ctx, page)
        if isinstance(sel, list):
            sel = sel[0]
        _log(True, f"[FLOW] ファイル設定: {paths} を {sel} にセット")
        act_set_input_files(page, sel, paths, log=log_actions)
        return

    # fill <selector>, value:<text>
    if s.startswith("fill "):
        body = s[len("fill ") :]
        # format: <selector>, value:<...>
        if "," in body and "value:" in body:
            key = body.split(",", 1)[0].strip()
            val_part = body.split("value:", 1)[1].strip()
        else:
            # fallback: fill <selector> <value>
            parts = body.split(" ", 1)
            key = parts[0].strip()
            val_part = parts[1].strip() if len(parts) > 1 else ""
        # strip quotes and eval
        val_part = val_part.strip().strip("\"\'")
        value = eval_expr(val_part, ctx)
        sel = _render_selector(key, ctx["_selectors"], ctx, page)
        if isinstance(sel, list):
            sel = sel[0]
        act_fill(page, sel, value, log=log_actions)
        if key == "title_input":
            ctx["_current_title"] = value
        return

    # select_option <selector>, value:<value>
    if s.startswith("select_option "):
        body = s[len("select_option ") :]
        if "," in body and "value:" in body:
            key = body.split(",", 1)[0].strip()
            val_part = body.split("value:", 1)[1].strip()
        else:
            parts = body.split(" ", 1)
            key = parts[0].strip()
            val_part = parts[1].strip() if len(parts) > 1 else ""
        val_part = val_part.strip().strip("\"\'")
        value = eval_expr(val_part, ctx)
        sel = _render_selector(key, ctx["_selectors"], ctx, page)
        if isinstance(sel, list):
            sel = sel[0]
        act_select_option(page, sel, value, log=log_actions)
        return

    # log
    if s.startswith("log "):
        msg = s[len("log ") :].strip()
        if (msg.startswith('"') and msg.endswith('"')) or (msg.startswith("'") and msg.endswith("'")):
            msg = msg[1:-1]
        try:
            msg = eval_expr(msg, ctx)
        except Exception:
            pass
        print(f"[FLOW][log] {msg}")
        return

    if s.strip() == "close_page":
        act_close_page(page, log=log_actions)
        return

    if s.startswith("wait_doc_dialog"):
        import re as _re, time as _t
        browser_ctx = cfg.get("_browser_ctx")
        if not browser_ctx:
            _log(True, "[FLOW] wait_doc_dialog skipped (no browser context)")
            return
        body = s[len("wait_doc_dialog") :].strip()
        timeout_ms = cfg["options"]["timeout_page_ms"]
        if body.startswith("timeout:"):
            arg = body.split("timeout:", 1)[1].strip()
            try:
                timeout_ms = _time_to_ms(arg) if _time_to_ms else int(arg)
            except Exception:
                pass
        start_count = len(getattr(browser_ctx, "doc_ids", []) or [])
        deadline = _t.monotonic() + (timeout_ms / 1000.0)
        while _t.monotonic() < deadline:
            cur = len(getattr(browser_ctx, "doc_ids", []) or [])
            if cur > start_count:
                title_value = ctx.get("_current_title")
                records = getattr(browser_ctx, "doc_records", None)
                if records:
                    try:
                        records[-1]["title"] = title_value
                    except Exception:
                        pass
                return
            _t.sleep(0.2)
        raise TimeoutError(f"wait_doc_dialog timeout after {timeout_ms}ms (no new doc id)")

    raise ValueError(f"Unknown statement: {s}")
