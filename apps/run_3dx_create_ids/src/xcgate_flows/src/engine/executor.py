from .runtime import eval_expr, merge_vars
from .selectors import with_fallback, resolve_selector
from .actions import (
    act_goto,
    act_wait,
    act_click,
    act_choose_file,
    act_set_input_files,
    act_fill,
    act_set_value,
    act_press,
    act_select_option,
    act_download,
    act_close_page,
    act_close_popup,
)
import os


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

    def _resolve_ctx_ref(expr: str):
        import re as _re

        txt = str(expr or "").strip()
        if not txt:
            return None
        if txt.startswith("${") and txt.endswith("}"):
            txt = txt[2:-1].strip()
        if not txt:
            return None

        try:
            cur = ctx
            parts = txt.split(".")
            for part in parts:
                token = part.strip()
                if not token:
                    continue
                m_name = _re.match(r"^([^\[\]]+)", token)
                if not m_name:
                    return None
                name = m_name.group(1)
                if isinstance(cur, dict):
                    cur = cur[name]
                else:
                    cur = getattr(cur, name)
                idx_tokens = _re.findall(r"\[(\d+)\]", token)
                for idx_txt in idx_tokens:
                    cur = cur[int(idx_txt)]
            return cur
        except Exception:
            return ctx.get(txt)

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
                resolved = _resolve_ctx_ref(arr_expr)
                if isinstance(resolved, tuple):
                    items = list(resolved)
                elif isinstance(resolved, list):
                    items = resolved
                elif resolved is None or isinstance(resolved, (str, bytes, dict)):
                    items = []
                else:
                    try:
                        items = list(resolved)
                    except Exception:
                        items = []
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
                except Exception as e:
                    ctx["_last_error"] = f"{e.__class__.__name__}: {e}"
                    exec_items(catch_steps)
                return
            raise ValueError(f"Unknown block: {item}")

        s = str(item).strip()
        if skip_first_goto and not getattr(exec_item, "_skipped_first_goto", False) and s.startswith("goto "):
            _log(log_actions, f"[FLOW] (skip first goto due to manual kickoff): {s}")
            exec_item._skipped_first_goto = True
            return
        _exec_stmt(page, s, ctx, cfg, time_to_ms)

    try:
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
    finally:
        exec_items(flow_ast.get("finally", []))


def _exec_stmt(page, stmt: str, ctx, cfg, _time_to_ms=None):
    s = stmt.strip()
    log_actions = cfg["options"].get("log_actions", False)
    if s.startswith("fill_secret "):
        _log(log_actions, "[FLOW] step: fill_secret <hidden>")
    else:
        _log(log_actions, f"[FLOW] step: {s}")

    def _artifact_path(path: str) -> str:
        p = str(path or "").strip()
        if not p:
            return p
        if os.path.isabs(p):
            return p
        root = (cfg.get("logging") or {}).get("runtime_root")
        if root:
            return os.path.abspath(os.path.join(str(root), p))
        return os.path.abspath(p)

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

    # pick_rows_by_revision <selector>, out:<var>, all:true|false[, revision_col:<id>][, revision_index:<token>]
    if s.startswith("pick_rows_by_revision "):
        import re as _re, time as _t

        def _to_bool(v) -> bool:
            txt = str(v or "").strip().lower()
            return txt in ("1", "true", "yes", "y", "on", "はい", "真")

        body = s[len("pick_rows_by_revision ") :].strip()
        key = body.split(",", 1)[0].strip()
        out_var = "selected_rows"
        include_all = False
        revision_col = "9"
        revision_index = "ds6wg:revision"

        m_out = _re.search(r"out:([^,\s]+)", body)
        if m_out:
            out_var = m_out.group(1).strip()

        m_all = _re.search(r"all:([^,\s]+)", body)
        if m_all:
            raw = m_all.group(1).strip().strip('"').strip("'")
            try:
                raw = eval_expr(raw, ctx)
            except Exception:
                pass
            include_all = _to_bool(raw)

        m_col = _re.search(r"revision_col:([^,\s]+)", body)
        if m_col:
            revision_col = m_col.group(1).strip().strip('"').strip("'")
            try:
                revision_col = str(eval_expr(revision_col, ctx))
            except Exception:
                pass

        m_idx = _re.search(r"revision_index:([^,\s]+)", body)
        if m_idx:
            revision_index = m_idx.group(1).strip().strip('"').strip("'")
            try:
                revision_index = str(eval_expr(revision_index, ctx))
            except Exception:
                pass

        sel = _render_selector(key, ctx["_selectors"], ctx, page)
        sel_items = sel if isinstance(sel, list) else [sel]

        best_loc = None
        best_count = -1
        best_sel = None
        last_err = None
        row_wait_ms = 60000
        try:
            row_wait_ms = int(float(ctx.get("search_timeout_ms", row_wait_ms)))
        except Exception:
            pass
        row_wait_ms = max(5000, min(row_wait_ms, 120000))

        # Keep declared selector priority. Using max-count can pick a too-broad fallback
        # and break row_id mapping for later right-click targeting.
        wait_deadline = _t.monotonic() + (row_wait_ms / 1000.0)
        while _t.monotonic() < wait_deadline:
            for sdef in sel_items:
                try:
                    loc = resolve_selector(page, sdef)
                    cnt = loc.count()
                    if cnt <= 0:
                        continue
                    best_loc = loc
                    best_count = cnt
                    best_sel = sdef
                    break
                except Exception as e:
                    last_err = e
            if best_loc is not None and best_count > 0:
                break
            _t.sleep(0.25)

        if best_loc is not None and best_count > 0:
            _log(True, f"[FLOW] pick_rows_by_revision: using selector={best_sel} count={best_count}")
        else:
            _log(
                True,
                f"[FLOW] pick_rows_by_revision: selector '{key}' not ready within {row_wait_ms}ms; "
                "continuing with DOM scan fallback",
            )

        doc_id = str(ctx.get("doc_id", "") or "").strip()
        rows = []
        seen = set()

        def _row_sig(row_id: str, identifier: str, row_uuid: str = "") -> str:
            ru = str(row_uuid or "").strip()
            if ru:
                return f"uuid:{ru}"
            return f"id:{str(row_id or '').strip()}||{str(identifier or '').strip()}"

        if best_loc is not None and best_count > 0:
            for idx in range(best_count):
                cell = best_loc.nth(idx)
                try:
                    data = cell.evaluate(
                        """(el, arg) => {
                            const norm = (v) => String(v || "")
                                .replace(/\\u00a0/g, " ")
                                .replace(/[\\r\\n\\t]+/g, " ")
                                .replace(/\\s+/g, " ")
                                .trim();
                            const rowId =
                                el.getAttribute("virtual-row-id") ||
                                el.getAttribute("row-id") ||
                                el.getAttribute("data-row-id") ||
                                "";
                            const rowUuid = el.getAttribute("wux-uuid") || "";
                            const identifier = norm(el.innerText || el.textContent || "");
                            let revision = "";
                            const cands = [];
                            if (rowId) {
                                cands.push(`div[data-index*='revision'][virtual-row-id='${rowId}']`);
                                cands.push(`div[data-index*='revision'][row-id='${rowId}']`);
                                if (arg.revisionCol) {
                                    cands.push(`div[column-id='${arg.revisionCol}'][virtual-row-id='${rowId}']`);
                                    cands.push(`div[column-id='${arg.revisionCol}'][row-id='${rowId}']`);
                                }
                                if (arg.revisionIndex) {
                                    cands.push(`div[data-index='${arg.revisionIndex}'][virtual-row-id='${rowId}']`);
                                    cands.push(`div[data-index='${arg.revisionIndex}'][row-id='${rowId}']`);
                                }
                            }
                            for (const css of cands) {
                                const node = document.querySelector(css);
                                if (!node) continue;
                                revision = norm(node.innerText || node.textContent || "");
                                if (revision) break;
                            }
                            if (!revision) {
                                const row = el.closest("li, tr, [role='row'], .wux-datagrid-row");
                                if (row) {
                                    const fallback = [
                                        row.querySelector("div[data-index*='revision']"),
                                        row.querySelector(arg.revisionIndex ? `div[data-index='${arg.revisionIndex}']` : ""),
                                        row.querySelector(arg.revisionCol ? `div[column-id='${arg.revisionCol}']` : ""),
                                    ];
                                    for (const node of fallback) {
                                        if (!node) continue;
                                        revision = norm(node.innerText || node.textContent || "");
                                        if (revision) break;
                                    }
                                }
                            }
                            return {
                                row_id: rowId || "",
                                row_uuid: rowUuid || "",
                                identifier,
                                revision: revision || "",
                            };
                        }""",
                        {"revisionCol": revision_col, "revisionIndex": revision_index},
                    )
                except Exception:
                    continue

                if not isinstance(data, dict):
                    continue

                identifier = str(data.get("identifier", "") or "").strip()
                if doc_id:
                    if doc_id not in identifier and doc_id.replace(" ", "") not in identifier.replace(" ", ""):
                        continue

                row_id = str(data.get("row_id", "") or "").strip()
                if not row_id:
                    row_id = str(idx)
                row_uuid = str(data.get("row_uuid", "") or "").strip()
                sig = _row_sig(row_id, identifier, row_uuid)
                if sig in seen:
                    continue
                seen.add(sig)

                revision = str(data.get("revision", "") or "").strip()
                rows.append(
                    {
                        "row_id": row_id,
                        "row_uuid": row_uuid,
                        "revision": revision or "?",
                        "identifier": identifier or doc_id,
                        "_order": idx,
                    }
                )

        if not rows:
            _log(
                True,
                f"[FLOW] pick_rows_by_revision: primary extraction returned 0 row(s) for doc_id={doc_id}; trying DOM scan fallback",
            )
            scan_js = """(arg) => {
                const norm = (v) => String(v || "")
                    .replace(/\\u00a0/g, " ")
                    .replace(/[\\r\\n\\t]+/g, " ")
                    .replace(/\\s+/g, " ")
                    .trim();
                const compact = (v) => norm(v).replace(/\\s+/g, "");
                const docId = norm(arg.docId || "");
                const docIdCompact = compact(docId);
                const includeAll = !!arg.includeAll;
                const maxSteps = Math.max(1, Number(arg.maxSteps || 80));
                const out = [];
                const seen = new Set();
                const cellSelector = "div.wux-datagrid-cell[data-index*='identifier'], div.wux-datagrid-cell[column-id='6']";

                const findScroller = () => {
                    const seeds = Array.from(
                        document.querySelectorAll("div.wux-tree-treelistview, div.wux-layouts-treeview, div.wux-datagrid, #table")
                    );
                    const probes = seeds.length ? seeds : Array.from(document.querySelectorAll("div"));
                    for (const seed of probes) {
                        let n = seed;
                        for (let k = 0; k < 6 && n; k++, n = n.parentElement) {
                            try {
                                if ((n.scrollHeight || 0) <= ((n.clientHeight || 0) + 8)) continue;
                                if ((n.clientHeight || 0) < 40) continue;
                                if (n.querySelector(cellSelector) || seed.querySelector(cellSelector)) {
                                    return n;
                                }
                            } catch (e) {}
                        }
                    }
                    return null;
                };

                const collectVisible = () => {
                    let foundNow = 0;
                    const allCells = Array.from(document.querySelectorAll(cellSelector));
                    for (let i = 0; i < allCells.length; i++) {
                        const el = allCells[i];
                        const identifier = norm(el.innerText || el.textContent || "");
                        if (!identifier) continue;
                        if (docId) {
                            const idCompact = compact(identifier);
                            if (!identifier.includes(docId) && !idCompact.includes(docIdCompact)) {
                                continue;
                            }
                        }

                        let rowId =
                            el.getAttribute("virtual-row-id") ||
                            el.getAttribute("row-id") ||
                            el.getAttribute("data-row-id") ||
                            "";
                        const rowUuid = el.getAttribute("wux-uuid") || "";
                        if (!rowId) {
                            const rowNode = el.closest("[virtual-row-id],[row-id]");
                            if (rowNode) {
                                rowId =
                                    rowNode.getAttribute("virtual-row-id") ||
                                    rowNode.getAttribute("row-id") ||
                                    "";
                            }
                        }
                        if (!rowId) rowId = String(i);

                        let revision = "";
                        const revCandidates = [];
                        revCandidates.push(`div[data-index*='revision'][virtual-row-id='${rowId}']`);
                        revCandidates.push(`div[data-index*='revision'][row-id='${rowId}']`);
                        if (arg.revisionCol) {
                            revCandidates.push(`div[column-id='${arg.revisionCol}'][virtual-row-id='${rowId}']`);
                            revCandidates.push(`div[column-id='${arg.revisionCol}'][row-id='${rowId}']`);
                        }
                        if (arg.revisionIndex) {
                            revCandidates.push(`div[data-index='${arg.revisionIndex}'][virtual-row-id='${rowId}']`);
                            revCandidates.push(`div[data-index='${arg.revisionIndex}'][row-id='${rowId}']`);
                        }
                        for (const css of revCandidates) {
                            const node = document.querySelector(css);
                            if (!node) continue;
                            revision = norm(node.innerText || node.textContent || "");
                            if (revision) break;
                        }
                        if (!revision) {
                            const row = el.closest("li, tr, [role='row'], .wux-datagrid-row");
                            if (row) {
                                const fallback = [
                                    row.querySelector("div[data-index*='revision']"),
                                    row.querySelector(arg.revisionIndex ? `div[data-index='${arg.revisionIndex}']` : ""),
                                    row.querySelector(arg.revisionCol ? `div[column-id='${arg.revisionCol}']` : ""),
                                ];
                                for (const node of fallback) {
                                    if (!node) continue;
                                    revision = norm(node.innerText || node.textContent || "");
                                    if (revision) break;
                                }
                            }
                        }

                        const sig = rowUuid ? `uuid:${rowUuid}` : `${rowId}||${identifier}`;
                        if (seen.has(sig)) continue;
                        seen.add(sig);
                        out.push({
                            row_id: rowId,
                            row_uuid: rowUuid,
                            identifier: identifier,
                            revision: revision || "",
                            order: out.length,
                        });
                        foundNow++;
                    }
                    return foundNow;
                };

                const scroller = findScroller();
                if (scroller) {
                    try { scroller.scrollTop = 0; } catch (e) {}
                }
                let foundTotal = 0;
                let idleAfterFound = 0;

                for (let step = 0; step < maxSteps; step++) {
                    const foundNow = collectVisible();
                    if (foundNow > 0) {
                        foundTotal += foundNow;
                        idleAfterFound = 0;
                    } else if (foundTotal > 0) {
                        idleAfterFound += 1;
                        if (includeAll && idleAfterFound >= 3) break;
                    }
                    if (foundNow > 0 && !includeAll) break;
                    if (!scroller) break;

                    const prev = Number(scroller.scrollTop || 0);
                    const maxTop = Math.max(0, Number(scroller.scrollHeight || 0) - Number(scroller.clientHeight || 0));
                    if (maxTop <= 0 || prev >= (maxTop - 2)) break;

                    const delta = Math.max(120, Math.floor(Number(scroller.clientHeight || 200) * 0.75));
                    const next = Math.min(maxTop, prev + delta);
                    try { scroller.scrollTop = next; } catch (e) {}
                    if (Number(scroller.scrollTop || 0) <= prev) break;
                }
                return out;
            }"""
            scan_targets = [("page", page)]
            try:
                scan_targets.extend([(f"frame:{fr.name or '<unnamed>'}", fr) for fr in page.frames])
            except Exception:
                pass

            scan_deadline = _t.monotonic() + (row_wait_ms / 1000.0)
            scan_attempt = 0
            while _t.monotonic() < scan_deadline and not rows:
                scan_attempt += 1
                for area_name, area in scan_targets:
                    try:
                        scanned = area.evaluate(
                            scan_js,
                            {
                                "docId": doc_id,
                                "revisionCol": revision_col,
                                "revisionIndex": revision_index,
                                "includeAll": include_all,
                                "maxSteps": 140,
                            },
                        ) or []
                    except Exception as e:
                        _log(True, f"[FLOW] pick_rows_by_revision: DOM scan failed area={area_name}: {e}")
                        continue
                    if not isinstance(scanned, list) or not scanned:
                        continue
                    _log(
                        True,
                        f"[FLOW] pick_rows_by_revision: DOM scan area={area_name} found {len(scanned)} row(s) "
                        f"(attempt={scan_attempt})",
                    )
                    for idx2, item in enumerate(scanned):
                        if not isinstance(item, dict):
                            continue
                        row_id = str(item.get("row_id", "") or "").strip()
                        if not row_id:
                            row_id = str(idx2)
                        row_uuid = str(item.get("row_uuid", "") or "").strip()
                        identifier = str(item.get("identifier", "") or "").strip() or doc_id
                        sig = _row_sig(row_id, identifier, row_uuid)
                        if sig in seen:
                            continue
                        seen.add(sig)
                        rows.append(
                            {
                                "row_id": row_id,
                                "row_uuid": row_uuid,
                                "revision": str(item.get("revision", "") or "").strip() or "?",
                                "identifier": identifier,
                                "_order": int(item.get("order", idx2) or idx2),
                            }
                        )
                    if rows:
                        break
                if rows:
                    break
                _t.sleep(0.35)

        if not rows:
            raise RuntimeError(f"pick_rows_by_revision: no rows found for doc_id='{doc_id}'")

        def _rev_key(rev_text: str):
            txt = str(rev_text or "").strip()
            m = _re.search(r"-?\d+", txt)
            if m:
                try:
                    return (1, int(m.group(0)), txt.upper())
                except Exception:
                    pass
            return (0, -1, txt.upper())

        for r in rows:
            rk = _rev_key(r.get("revision"))
            r["_rk"] = rk
        rows.sort(key=lambda r: (r["_rk"][0], r["_rk"][1], r["_rk"][2], -int(r["_order"])), reverse=True)

        if not include_all:
            rows = rows[:1]

        out_rows = []
        for r in rows:
            out_rows.append(
                {
                    "row_id": r.get("row_id"),
                    "row_uuid": r.get("row_uuid"),
                    "revision": r.get("revision"),
                    "identifier": r.get("identifier"),
                }
            )
        ctx[out_var] = out_rows

        picked = ", ".join([f"{x.get('row_id')}|Rev{x.get('revision')}" for x in out_rows])
        _log(True, f"[FLOW] pick_rows_by_revision: doc_id={doc_id} all={include_all} -> {len(out_rows)} row(s) [{picked}]")
        return

    # click
    if s.startswith("click "):
        name = s[len("click "):].strip()
        sel = _render_selector(name, ctx["_selectors"], ctx, page)
        _log(True, f"[FLOW] クリック: {sel}")
        act_click(page, sel, log=log_actions)
        return

    # right_click
    if s.startswith("right_click "):
        name = s[len("right_click "):].strip()
        sel = _render_selector(name, ctx["_selectors"], ctx, page)
        _log(True, f"[FLOW] 右クリック: {sel}")
        act_click(page, sel, log=log_actions, button="right")
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
        out_path = _artifact_path(out_path)
        # optional full:true|false
        m_full = _re.search(r"full:(true|false)", s, _re.IGNORECASE)
        full_flag = False
        if m_full:
            full_flag = m_full.group(1).lower() == 'true'
        from .actions import act_screenshot
        act_screenshot(page, out_path, log=log_actions, full_page=full_flag)
        return

    # download <selector>, path:<...>[, timeout:<...>]
    if s.startswith("download "):
        import re as _re
        body = s[len("download ") :].strip()
        key = body.split(",", 1)[0].strip()
        m_path = _re.search(r"path:([^,]+)", body)
        if not m_path:
            raise ValueError(f"Invalid download syntax (missing path): {s}")
        out_path = eval_expr(m_path.group(1).strip().strip('"').strip("'"), ctx)
        out_path = _artifact_path(out_path)
        timeout_ms = cfg["options"]["timeout_page_ms"]
        m_to = _re.search(r"timeout:([^,\s]+)", body)
        if m_to and _time_to_ms:
            timeout_ms = _time_to_ms(m_to.group(1))
        sel = _render_selector(key, ctx["_selectors"], ctx, page)
        ctx["_last_download_path"] = ""
        ctx["_last_download_consumed"] = True
        try:
            saved_path = act_download(page, sel, out_path, log=log_actions, timeout_ms=timeout_ms)
        except Exception as e:
            print(
                f"[FLOW][download][error] selector={sel} path={out_path} "
                f"reason={e.__class__.__name__}: {e}"
            )
            raise
        try:
            saved_path = os.path.abspath(saved_path)
        except Exception:
            pass
        ctx["_last_download_path"] = saved_path
        ctx["_last_download_consumed"] = False
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
        for path_key in ("screenshot", "html", "saved_path"):
            if path_key in data and data[path_key]:
                data[path_key] = _artifact_path(str(data[path_key]))
        if not data.get("saved_path"):
            last_download = ctx.get("_last_download_path") or ""
            consumed = bool(ctx.get("_last_download_consumed", True))
            if last_download and not consumed:
                data["saved_path"] = _artifact_path(str(last_download))
                ctx["_last_download_consumed"] = True
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
        act_fill(page, sel, value, log=log_actions)
        if key == "title_input":
            ctx["_current_title"] = value
        return

    # fill_secret <selector>, value:<text>
    if s.startswith("fill_secret "):
        body = s[len("fill_secret ") :]
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
        _log(True, f"[FLOW] fill_secret: {sel} = <hidden>")
        act_fill(page, sel, value, log=False)
        return

    # set_value <selector>, value:<text>[, submit:true|false]
    if s.startswith("set_value "):
        body = s[len("set_value ") :]
        import re as _re
        if "," in body and "value:" in body:
            key = body.split(",", 1)[0].strip()
            val_part = body.split("value:", 1)[1].strip()
        else:
            parts = body.split(" ", 1)
            key = parts[0].strip()
            val_part = parts[1].strip() if len(parts) > 1 else ""
        submit = False
        m_submit = _re.search(r"(?:,\s*|\s+)submit:(true|false)\s*$", val_part, _re.IGNORECASE)
        if m_submit:
            submit = m_submit.group(1).lower() == "true"
            val_part = val_part[:m_submit.start()].strip().rstrip(",")
        val_part = val_part.strip().strip("\"\'")
        value = eval_expr(val_part, ctx)
        sel = _render_selector(key, ctx["_selectors"], ctx, page)
        act_set_value(page, sel, value, log=log_actions, submit=submit)
        return

    # press <selector>, key:<key>
    if s.startswith("press "):
        body = s[len("press ") :]
        if "," in body and "key:" in body:
            key_name = body.split(",", 1)[0].strip()
            key_part = body.split("key:", 1)[1].strip()
        else:
            parts = body.split(" ", 1)
            key_name = parts[0].strip()
            key_part = parts[1].strip() if len(parts) > 1 else "Enter"
        key_part = key_part.strip().strip("\"\'")
        key_value = eval_expr(key_part, ctx)
        sel = _render_selector(key_name, ctx["_selectors"], ctx, page)
        act_press(page, sel, key_value, log=log_actions)
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

    if s.startswith("pause"):
        msg = s[len("pause") :].strip()
        if (msg.startswith('"') and msg.endswith('"')) or (msg.startswith("'") and msg.endswith("'")):
            msg = msg[1:-1]
        if msg:
            try:
                msg = eval_expr(msg, ctx)
            except Exception:
                pass
        else:
            msg = "Press Enter to continue."
        print(f"\n[FLOW][pause] {msg}")
        try:
            input("> ")
        except EOFError:
            pass
        return

    if s.startswith("fail"):
        msg = s[len("fail") :].strip()
        if (msg.startswith('"') and msg.endswith('"')) or (msg.startswith("'") and msg.endswith("'")):
            msg = msg[1:-1]
        if msg:
            try:
                msg = eval_expr(msg, ctx)
            except Exception:
                pass
        else:
            msg = "Flow failed."
        raise RuntimeError(msg)

    if s.strip() == "close_page":
        act_close_page(page, log=log_actions)
        return

    if s.strip() == "close_popup":
        act_close_popup(page, log=log_actions)
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
        start_count = int(ctx.get("_doc_dialog_cursor", 0) or 0)
        deadline = _t.monotonic() + (timeout_ms / 1000.0)
        while _t.monotonic() < deadline:
            doc_ids = getattr(browser_ctx, "doc_ids", []) or []
            cur = len(doc_ids)
            if cur > start_count:
                doc_id = doc_ids[start_count]
                ctx["_last_doc_id"] = doc_id
                ctx["_doc_dialog_cursor"] = start_count + 1
                title_value = ctx.get("_current_title")
                records = getattr(browser_ctx, "doc_records", None)
                if records:
                    try:
                        records[start_count]["title"] = title_value
                    except Exception:
                        pass
                return
            _t.sleep(0.2)
        raise TimeoutError(f"wait_doc_dialog timeout after {timeout_ms}ms (no new doc id)")

    raise ValueError(f"Unknown statement: {s}")
