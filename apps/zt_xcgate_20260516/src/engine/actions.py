from typing import Dict, Any, List
import time
import os
import re
import shutil
from urllib.parse import urljoin, urlparse
from playwright.sync_api import Error as PWError
from .selectors import with_fallback, resolve_selector
from ..web.utils import ensure_dir


def _log(enabled: bool, msg: str):
    if enabled:
        print(msg)


def act_goto(page, url: str, timeout_ms: int = 120000,
             retries: int = 0, delay_ms: int = 1000, log: bool = True):
    _log(log, f"[FLOW] goto: {url} (timeout={timeout_ms}ms, retries={retries})")
    last_err = None
    for attempt in range(retries + 1):
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            _log(log, "[FLOW] goto: completed")
            return
        except PWError as e:
            last_err = e
            _log(log, f"[FLOW] goto: attempt {attempt + 1} failed: {e}")
            if attempt < retries:
                time.sleep(delay_ms / 1000.0)
                continue
            raise


def act_wait(page, selector: Dict[str, Any] = None, text: str = None,
             timeout_ms: int = 30000, visible: bool = True, log: bool = True):
    target = f'text="{text}"' if text else selector
    _log(log, f"[FLOW] wait: {target} (timeout={timeout_ms}ms, state={'visible' if visible else 'hidden'})")
    if text:
        sel = {"by": "text", "value": text}
        loc = with_fallback(page, sel).first
        loc.wait_for(timeout=timeout_ms, state="visible" if visible else "hidden")
        _log(log, "[FLOW] wait: satisfied")
        return
    if selector:
        sel_items = selector if isinstance(selector, list) else [selector]
        deadline = time.monotonic() + (timeout_ms / 1000.0)
        last_err = None

        while time.monotonic() < deadline:
            for idx, sel_item in enumerate(sel_items):
                try:
                    loc = resolve_selector(page, sel_item)
                except Exception as e:
                    last_err = e
                    continue
                try:
                    cnt = loc.count()
                except Exception as e:
                    last_err = e
                    continue

                if visible:
                    if cnt <= 0:
                        continue
                    # Some 3DEX grids keep hidden template rows at index 0.
                    # Treat the wait as satisfied when any candidate row is visible.
                    hit = False
                    probe = min(cnt, 10)
                    for n in range(probe):
                        try:
                            if loc.nth(n).is_visible():
                                hit = True
                                break
                        except Exception:
                            continue
                    if hit:
                        _log(log, f"[FLOW] wait: satisfied by selector[{idx}]")
                        return
                    continue

                # hidden mode
                if cnt <= 0:
                    _log(log, f"[FLOW] wait: satisfied(hidden) by selector[{idx}]")
                    return
                probe = min(cnt, 10)
                any_visible = False
                for n in range(probe):
                    try:
                        if loc.nth(n).is_visible():
                            any_visible = True
                            break
                    except Exception:
                        continue
                if not any_visible:
                    _log(log, f"[FLOW] wait: satisfied(hidden) by selector[{idx}]")
                    return

            time.sleep(0.2)

        if last_err:
            raise last_err
        raise TimeoutError(
            f"wait timeout after {timeout_ms}ms "
            f"for selectors={selector}"
        )


def act_click(
    page,
    selector: Dict[str, Any],
    log: bool = True,
    timeout_ms: int = 5000,
    button: str = "left",
):
    _log(log, f"[FLOW] click({button}): {selector}")
    loc = with_fallback(page, selector).first

    def _dispatch_row_contextmenu():
        try:
            loc.evaluate(
                """(el) => {
                    const fireContext = (node) => {
                        if (!node) return;
                        try {
                            node.dispatchEvent(new MouseEvent('contextmenu', {
                                bubbles: true,
                                cancelable: true,
                                view: window,
                                button: 2,
                                buttons: 2,
                                detail: 1,
                            }));
                        } catch (e) {}
                    };
                    const nodes = [];
                    nodes.push(el);
                    try { nodes.push(el.parentElement); } catch (e) {}
                    try { nodes.push(el.closest("[role='row']")); } catch (e) {}
                    try { nodes.push(el.closest("li")); } catch (e) {}
                    try { nodes.push(el.closest(".wux-datagrid-row")); } catch (e) {}
                    try { nodes.push(el.closest("tr")); } catch (e) {}
                    try { nodes.push(el.closest("td")); } catch (e) {}
                    const seen = new Set();
                    for (const n of nodes) {
                        if (!n || seen.has(n)) continue;
                        seen.add(n);
                        fireContext(n);
                    }
                }"""
            )
        except Exception:
            pass

    def _mouse_context_click() -> bool:
        try:
            box = loc.bounding_box()
        except Exception:
            box = None
        if not box:
            return False
        try:
            x = float(box.get("x", 0.0)) + max(2.0, min(float(box.get("width", 1.0)) * 0.5, 40.0))
            y = float(box.get("y", 0.0)) + max(2.0, min(float(box.get("height", 1.0)) * 0.5, 18.0))
            page.mouse.move(x, y)
            page.mouse.click(x, y, button="right")
            return True
        except Exception:
            return False

    try:
        try:
            loc.scroll_into_view_if_needed(timeout=timeout_ms)
        except Exception:
            pass
        try:
            loc.hover(timeout=timeout_ms)
        except Exception:
            pass
        loc.click(timeout=timeout_ms, button=button)
        if button == "right":
            _mouse_context_click()
            try:
                loc.dispatch_event("contextmenu")
            except Exception:
                pass
            _dispatch_row_contextmenu()
        return
    except PWError as e:
        _log(log, f"[FLOW] click({button}): normal click failed, retry with force. err={e}")
        try:
            loc.click(force=True, timeout=timeout_ms, button=button)
            if button == "right":
                _mouse_context_click()
                try:
                    loc.dispatch_event("contextmenu")
                except Exception:
                    pass
                _dispatch_row_contextmenu()
            _log(log, f"[FLOW] click({button}): force click succeeded")
            return
        except PWError as e2:
            _log(log, f"[FLOW] click({button}): force click failed. err={e2}")
            try:
                if button == "right":
                    _mouse_context_click()
                    loc.dispatch_event("contextmenu")
                    _dispatch_row_contextmenu()
                else:
                    loc.evaluate("el => { el.click?.(); el.parentElement?.click?.(); const td = el.closest('td'); td?.click?.(); const tdMenu = el.closest('td.menu-button'); tdMenu?.click?.(); }")
                _log(log, f"[FLOW] click({button}): JS fallback succeeded")
                return
            except Exception as e3:
                _log(log, f"[FLOW] click({button}): JS fallback failed. err={e3}")
                try:
                    loc.dispatch_event("mousedown")
                    loc.dispatch_event("mouseup")
                    if button == "right":
                        loc.dispatch_event("contextmenu")
                    _log(log, f"[FLOW] click({button}): dispatched mouse events")
                    return
                except Exception as e4:
                    _log(log, f"[FLOW] click({button}): dispatch events failed. err={e4}")
                raise


def act_choose_file(page, open_by: Dict[str, Any], paths: List[str], log: bool = True, timeout_ms: int = 5000):
    _log(log, f"[FLOW] choose_file: open_by={open_by}, files={paths}, timeout={timeout_ms}ms")
    with page.expect_file_chooser(timeout=timeout_ms) as fc:
        act_click(page, open_by, log=log)
    file_chooser = fc.value
    file_chooser.set_files(paths if len(paths) > 1 else paths[0])
    _log(log, "[FLOW] choose_file: files set")


def act_set_input_files(page, selector: Dict[str, Any], paths: List[str], log: bool = True):
    _log(log, f"[FLOW] set_input_files: {selector} <- {paths}")
    with_fallback(page, selector).set_input_files(paths if len(paths) > 1 else paths[0])


def act_screenshot(page, output_path: str, log: bool = True, full_page: bool = False):
    try:
        ensure_dir(os.path.dirname(output_path) or ".")
        page.screenshot(path=output_path, full_page=full_page)
        _log(log, f"[FLOW] screenshot saved: {output_path} (full_page={full_page})")
    except Exception as e:
        _log(log, f"[FLOW] screenshot failed: {e}")


def act_fill(page, selector: Dict[str, Any], value: str, log: bool = True):
    _log(log, f"[FLOW] fill: {selector} = '{value}'")
    with_fallback(page, selector).fill(value)


def act_set_value(page, selector: Dict[str, Any], value: str, log: bool = True, submit: bool = False):
    _log(log, f"[FLOW] set_value(js): {selector} = '{value}' (submit={submit})")
    loc = with_fallback(page, selector).first
    loc.evaluate(
        """(el, val) => {
            try { el.removeAttribute('readonly'); } catch(e) {}
            try { el.removeAttribute('disabled'); } catch(e) {}
            try { el.readOnly = false; } catch(e) {}
            try { el.disabled = false; } catch(e) {}
            el.focus?.();
            el.value = val;
            el.dispatchEvent(new Event('input', { bubbles: true }));
            el.dispatchEvent(new Event('change', { bubbles: true }));
        }""",
        value,
    )
    if submit:
        pressed = False
        try:
            loc.press("Enter")
            pressed = True
        except Exception:
            pass
        try:
            loc.evaluate(
                """(el, alreadyPressed) => {
                    if (!alreadyPressed) {
                        try { el.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', bubbles: true, cancelable: true })); } catch(e) {}
                        try { el.dispatchEvent(new KeyboardEvent('keypress', { key: 'Enter', code: 'Enter', bubbles: true, cancelable: true })); } catch(e) {}
                        try { el.dispatchEvent(new KeyboardEvent('keyup', { key: 'Enter', code: 'Enter', bubbles: true, cancelable: true })); } catch(e) {}
                    }
                    let form = null;
                    try { form = el.closest('form'); } catch(e) {}
                    if (form) {
                        try { form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })); } catch(e) {}
                        try {
                            if (typeof form.requestSubmit === 'function') form.requestSubmit();
                            else if (typeof form.submit === 'function') form.submit();
                        } catch(e) {}
                    }
                    let root = null;
                    try { root = document.querySelector('#input_search_div'); } catch(e) {}
                    if (!root) {
                        try { root = el.parentElement; } catch(e) {}
                    }
                    if (root) {
                        const cands = [
                            "button[type='submit']",
                            "input[type='submit']",
                            "button[class*='search']",
                            "a[class*='search']",
                            "[class*='search-icon']",
                            "i[class*='search']",
                            "svg[class*='search']"
                        ];
                        for (const sel of cands) {
                            let btn = null;
                            try { btn = root.querySelector(sel); } catch(e) {}
                            if (btn) {
                                try { btn.click(); } catch(e) {}
                                break;
                            }
                        }
                    }
                }""",
                pressed,
            )
        except Exception:
            pass


def act_press(page, selector: Dict[str, Any], key: str, log: bool = True):
    _log(log, f"[FLOW] press: {selector} key={key}")
    with_fallback(page, selector).first.press(key)


def act_download(page, selector: Dict[str, Any], output_path: str, log: bool = True, timeout_ms: int = 30000) -> str:
    def _unwrap_current_page(p):
        try:
            target_getter = getattr(p, "_target", None)
            if callable(target_getter):
                real = target_getter()
                if real is not None:
                    return real
        except Exception:
            pass
        return p

    page = _unwrap_current_page(page)
    output_path = os.path.abspath(output_path)
    ensure_dir(os.path.dirname(output_path) or ".")
    _log(log, f"[FLOW] download: {selector} -> {output_path}")
    ctx = page.context
    started_epoch = time.time()
    base_name = os.path.basename(output_path)
    doc_id = os.path.splitext(base_name)[0] or "unknown"
    doc_id_lower = doc_id.lower()
    safe_doc_id = re.sub(r"[^A-Za-z0-9._-]", "_", doc_id) or "unknown"
    output_parent = os.path.dirname(os.path.abspath(output_path)) or os.getcwd()
    probe_root = output_parent
    try:
        if os.path.basename(output_parent).lower() == "downloads":
            probe_root = os.path.dirname(output_parent) or output_parent
    except Exception:
        probe_root = output_parent
    probe_path = os.path.join(probe_root, f"download_probe_{safe_doc_id}.log")
    ensure_dir(os.path.dirname(probe_path) or ".")

    def _probe(msg: str):
        line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}"
        try:
            with open(probe_path, "a", encoding="utf-8") as fp:
                fp.write(line + "\n")
        except Exception:
            pass
        _log(log, f"[FLOW][probe] {msg}")

    _probe("-" * 72)
    _probe(f"download start: doc_id={doc_id} selector={selector} output={output_path}")

    native_watch_dirs: List[str] = []
    for cand in [output_parent, os.path.join(os.path.expanduser("~"), "Downloads")]:
        try:
            abs_cand = os.path.abspath(cand)
        except Exception:
            abs_cand = cand
        if not abs_cand or abs_cand in native_watch_dirs:
            continue
        if os.path.isdir(abs_cand):
            native_watch_dirs.append(abs_cand)
    _probe(f"native_watch_dirs={native_watch_dirs}")

    def _snapshot_native_files() -> Dict[str, tuple[int, int]]:
        snap: Dict[str, tuple[int, int]] = {}
        for root in native_watch_dirs:
            try:
                for ent in os.scandir(root):
                    try:
                        if not ent.is_file():
                            continue
                    except Exception:
                        continue
                    try:
                        st = ent.stat()
                    except Exception:
                        continue
                    snap[os.path.abspath(ent.path)] = (int(st.st_size), int(getattr(st, "st_mtime_ns", int(st.st_mtime * 1_000_000_000))))
            except Exception:
                continue
        return snap

    native_baseline = _snapshot_native_files()
    last_partial_path = ""
    last_partial_logged = ""

    def _header(headers: Dict[str, Any], key: str) -> str:
        for hk, hv in (headers or {}).items():
            if str(hk).lower() == key.lower():
                return str(hv or "")
        return ""

    def _normalize_url(url: str, base_url: str = "") -> str | None:
        raw = str(url or "").strip().strip('"').strip("'")
        if not raw:
            return None
        if raw.startswith(("javascript:", "about:blank", "about:srcdoc", "data:", "blob:")):
            return None
        if base_url:
            try:
                raw = urljoin(base_url, raw)
            except Exception:
                pass
        parsed = urlparse(raw)
        if parsed.scheme.lower() not in ("http", "https"):
            return None
        return raw

    def _looks_like_pdf_route(url: str) -> bool:
        low = (url or "").lower()
        if not low:
            return False
        hints = (
            ".pdf",
            "pdf",
            "download",
            "checkout",
            "trmpdfdownload.jsp",
            "/fcs/servlet/fcs/checkout/",
        )
        return any(h in low for h in hints)

    def _is_pdf_hint(url: str, headers: Dict[str, Any]) -> bool:
        low_url = (url or "").lower()
        ctype = _header(headers, "content-type").lower()
        dispo = _header(headers, "content-disposition").lower()
        if "application/pdf" in ctype:
            return True
        if ".pdf" in low_url or "format=pdf" in low_url or "type=pdf" in low_url:
            return True
        if "filename=" in dispo and ".pdf" in dispo:
            return True
        if "attachment" in dispo and (".pdf" in dispo or "octet-stream" in ctype):
            return True
        if "download" in low_url and ("pdf" in low_url or "document" in low_url):
            return True
        return False

    def _is_pdf_payload(body: bytes, headers: Dict[str, Any]) -> bool:
        if not body:
            return False
        ctype = _header(headers, "content-type").lower()
        dispo = _header(headers, "content-disposition").lower()
        if body.startswith(b"%PDF"):
            return True
        if "application/pdf" in ctype:
            return True
        if "filename=" in dispo and ".pdf" in dispo:
            return True
        if "attachment" in dispo and ".pdf" in dispo:
            return True
        return False

    def _decode_body_text(body: bytes) -> str:
        if not body:
            return ""
        for enc in ("utf-8", "cp932", "latin-1"):
            try:
                return body.decode(enc, errors="ignore")
            except Exception:
                pass
        return ""

    def _is_html_payload(body: bytes, headers: Dict[str, Any]) -> bool:
        ctype = _header(headers, "content-type").lower()
        if "text/html" in ctype:
            return True
        head = (body or b"")[:512].lstrip().lower()
        return head.startswith(b"<!doctype html") or head.startswith(b"<html") or b"<head" in head

    def _extract_followup_urls(html: str, base_url: str) -> List[str]:
        found: List[str] = []
        patterns = [
            r"http-equiv\s*=\s*['\"]?refresh['\"]?[^>]*content\s*=\s*['\"][^'\"]*url\s*=\s*([^'\"> ]+)",
            r"location(?:\.href)?\s*=\s*['\"]([^'\"]+)['\"]",
            r"location\.replace\(\s*['\"]([^'\"]+)['\"]\s*\)",
            r"window\.open\(\s*['\"]([^'\"]+)['\"]",
            r"document\.location(?:\.href)?\s*=\s*['\"]([^'\"]+)['\"]",
        ]
        for pat in patterns:
            for m in re.finditer(pat, html or "", flags=re.IGNORECASE):
                cand = _normalize_url(m.group(1), base_url=base_url)
                if cand:
                    found.append(cand)
        # preserve order + unique
        out: List[str] = []
        seen = set()
        for u in found:
            if u in seen:
                continue
            seen.add(u)
            out.append(u)
        return out

    saved_output_path = output_path
    _filename_title_cache: str | None = None

    def _sanitize_filename_part(raw: str) -> str:
        txt = str(raw or "")
        txt = txt.replace("\u00A0", " ")
        txt = re.sub(r"[\r\n\t]+", " ", txt)
        txt = re.sub(r"\s+", " ", txt).strip()
        txt = re.sub(r'[\\/:*?"<>|]', "_", txt)
        txt = txt.strip().rstrip(".")
        if not txt:
            return ""
        if len(txt) > 140:
            txt = txt[:140].rstrip(" .")
        return txt

    def _unique_path(path: str) -> str:
        if not path:
            return path
        if not os.path.exists(path):
            return path
        stem, ext = os.path.splitext(path)
        idx = 2
        while True:
            cand = f"{stem} ({idx}){ext}"
            if not os.path.exists(cand):
                return cand
            idx += 1

    def _build_output_path_for_name(source_name: str = "") -> str:
        title = _prime_title_cache()
        if not title:
            return output_path

        src_name = os.path.basename(source_name or output_path)
        m = re.match(r"^(?P<prefix>.+-Rev[^-]+)-[^.]*\.pdf$", src_name, flags=re.IGNORECASE)
        if not m:
            return output_path
        file_name = f"{m.group('prefix')}-{title}.pdf"

        file_name = re.sub(r'[\\/:*?"<>|]', "_", file_name).strip().rstrip(".")
        stem, ext = os.path.splitext(file_name)
        if not ext:
            ext = ".pdf"
        max_name_len = 180
        if len(stem) + len(ext) > max_name_len:
            stem = stem[: max_name_len - len(ext)].rstrip(" .")
        out = os.path.join(os.path.dirname(output_path), f"{stem}{ext}")
        if os.path.abspath(out) != os.path.abspath(output_path):
            out = _unique_path(out)
        return out

    def _prime_title_cache(preferred_page=None) -> str:
        nonlocal _filename_title_cache
        if _filename_title_cache:
            return _filename_title_cache
        candidate = _sanitize_filename_part(_extract_document_title(preferred_page=preferred_page))
        if candidate:
            _filename_title_cache = candidate
            _probe(f"title_cache={_filename_title_cache}")
        return _filename_title_cache or ""

    def _write_pdf(body: bytes, route: str, source: str = "", source_name: str = "") -> bool:
        nonlocal saved_output_path
        if not body:
            return False
        target_path = _build_output_path_for_name(source_name=source_name)
        ensure_dir(os.path.dirname(target_path) or ".")
        with open(target_path, "wb") as fp:
            fp.write(body)
        saved_output_path = os.path.abspath(target_path)
        _probe(
            f"saved route={route} source={source} source_name={source_name} "
            f"path={saved_output_path} size={len(body)}"
        )
        _log(log, f"[FLOW] download saved ({route}): {saved_output_path}")
        return True

    def _scan_native_downloads() -> tuple[str | None, str | None]:
        # Fallback for environments where browser-native download UI appears
        # and Playwright download/response hooks are not emitted.
        nonlocal last_partial_path, last_partial_logged
        partial_exts = (".crdownload", ".part", ".tmp", ".download")
        completed = []
        partials = []
        current = _snapshot_native_files()

        for path, cur_sig in current.items():
            prev_sig = native_baseline.get(path)
            if prev_sig == cur_sig:
                continue
            try:
                st = os.stat(path)
            except Exception:
                continue
            if st.st_mtime + 0.2 < started_epoch:
                continue

            name = os.path.basename(path)
            low_name = name.lower()
            if low_name.endswith(partial_exts):
                partials.append((st.st_mtime, path))
                continue
            if st.st_size <= 0:
                continue

            has_pdf_name = ".pdf" in low_name
            has_doc_id = bool(doc_id_lower) and doc_id_lower in low_name
            if not (has_pdf_name or has_doc_id or os.path.abspath(path) == os.path.abspath(output_path)):
                continue
            score = 0
            if has_doc_id:
                score += 2
            if has_pdf_name:
                score += 1
            if os.path.abspath(path) == os.path.abspath(output_path):
                score += 1
            completed.append((score, st.st_mtime, st.st_size, path))

        native_baseline.clear()
        native_baseline.update(current)

        if completed:
            completed.sort(key=lambda x: (x[0], x[1], x[2]), reverse=True)
            return "complete", completed[0][3]

        if partials:
            partials.sort(key=lambda x: x[0], reverse=True)
            last_partial_path = partials[0][1]
            if last_partial_logged != last_partial_path:
                last_partial_logged = last_partial_path
                _probe(f"native download in progress: {last_partial_path}")
            return "partial", last_partial_path
        return None, None

    def _finalize_native_file(src_path: str) -> bool:
        nonlocal saved_output_path
        if not src_path:
            return False
        try:
            abs_src = os.path.abspath(src_path)
        except Exception:
            abs_src = src_path

        try:
            target_path = _build_output_path_for_name(source_name=os.path.basename(abs_src))
            if os.path.abspath(target_path) == abs_src:
                with open(target_path, "rb") as fp:
                    head = fp.read(4)
                size = os.path.getsize(target_path)
                if size <= 0:
                    return False
                saved_output_path = os.path.abspath(target_path)
                _probe(
                    f"saved route=native_fs_existing source={abs_src} path={saved_output_path} size={size} "
                    f"head={head!r}"
                )
                _log(log, f"[FLOW] download saved (native_fs_existing): {saved_output_path}")
                return True
            ensure_dir(os.path.dirname(target_path) or ".")
            shutil.copy2(abs_src, target_path)
            with open(target_path, "rb") as fp:
                head = fp.read(4)
            size = os.path.getsize(target_path)
            if size <= 0:
                return False
            saved_output_path = os.path.abspath(target_path)
            _probe(
                f"saved route=native_fs_copy source={abs_src} path={saved_output_path} "
                f"size={size} head={head!r}"
            )
            _log(log, f"[FLOW] download saved (native_fs_copy): {saved_output_path}")
            return True
        except Exception as e:
            _probe(f"native finalize failed src={src_path} err={e.__class__.__name__}: {e}")
            return False

    def _candidate_pages(base_page):
        try:
            pages = [p for p in ctx.pages if not p.is_closed()]
        except Exception:
            pages = []
        ordered = []
        seen = set()
        for p in [base_page] + list(reversed(pages)):
            pid = id(p)
            if pid in seen:
                continue
            seen.add(pid)
            ordered.append(p)
        return ordered

    def _selector_items(sel_obj):
        if isinstance(sel_obj, list):
            return [s for s in sel_obj if isinstance(s, dict)]
        if isinstance(sel_obj, dict):
            return [sel_obj]
        return []

    def _fallback_pdf_locators(target_page):
        out = []
        css_candidates = [
            "td#TRMPdfDownloadCommand[title='Download PDF']",
            "td#TRMPdfDownloadCommand[title*='PDF']",
            "#TRMPdfDownloadCommand",
            "#TRMPdfDownloadCommand > img",
            "img[src*='iconPdfDownload']",
        ]
        try:
            areas = [("page", target_page)] + [
                (f"frame:{fr.name or '<unnamed>'}", fr) for fr in target_page.frames
            ]
        except Exception:
            areas = [("page", target_page)]
        for area_name, area in areas:
            for css in css_candidates:
                try:
                    loc = area.locator(css)
                    cnt = loc.count()
                except Exception:
                    continue
                if cnt <= 0:
                    continue
                out.append((area_name, css, loc.first, cnt))
        return out

    def _selector_target_pages(base_page):
        scored = []
        sel_items = _selector_items(selector)
        for p in _candidate_pages(base_page):
            matched = 0
            for s in sel_items:
                try:
                    loc = resolve_selector(p, s)
                    cnt = loc.count()
                except Exception:
                    continue
                if cnt > 0:
                    matched += cnt

            score = 0 if matched > 0 else 2
            if score > 0:
                try:
                    if _fallback_pdf_locators(p):
                        score = 1
                except Exception:
                    pass
            scored.append((score, -matched, p))
        if not scored:
            return [base_page]
        scored.sort(key=lambda t: (t[0], t[1]))
        return [p for _, _, p in scored]

    def _safe_page_url(p) -> str:
        try:
            return p.url or ""
        except Exception:
            return ""

    def _is_browser_downloads_ui_url(url: str) -> bool:
        low = str(url or "").lower()
        return (
            low.startswith("edge://downloads")
            or low.startswith("chrome://downloads")
            or low.startswith("about:downloads")
        )

    def _is_detail_popup_url(url: str) -> bool:
        return "objectid=" in str(url or "").lower()

    def _has_opener(p) -> bool:
        try:
            return p.opener() is not None
        except Exception:
            return False

    def _extract_document_title(preferred_page=None) -> str:
        labels = {"Title", "Document Title", "タイトル"}
        blocked_area_tokens = ("notice", "importantnotification", "trmnotice")
        preferred_areas = (
            "frame:dcldocumentproperties",
            "frame:pagecontent",
            "frame:detailsdisplay",
        )

        doc_code = ""
        m_doc = re.search(r"(DC-\d+)", doc_id, flags=re.IGNORECASE)
        if m_doc:
            doc_code = m_doc.group(1).upper()

        js = """
            () => {
                const titleLabels = new Set(["Title", "Document Title", "タイトル"]);
                const nameLabels = new Set(["Name", "Document Name", "名称"]);
                const norm = (v) => String(v || "")
                    .replace(/[\\u00a0\\r\\n\\t]+/g, " ")
                    .replace(/\\s+/g, " ")
                    .trim()
                    .replace(/[:：]$/, "");

                const readByLabel = (labelSet) => {
                    const rows = Array.from(document.querySelectorAll("tr"));
                    for (const tr of rows) {
                        const cells = Array.from(tr.querySelectorAll("th,td"));
                        if (cells.length < 2) continue;
                        const label = norm(cells[0].innerText || cells[0].textContent);
                        if (!labelSet.has(label)) continue;
                        for (let i = 1; i < cells.length; i++) {
                            const v = norm(cells[i].innerText || cells[i].textContent);
                            if (v) return v;
                        }
                    }
                    return "";
                };

                let calcText = "";
                let title = "";
                const calc = document.querySelector("#calc_Title");
                if (calc) {
                    const row = (calc.tagName || "").toLowerCase() === "tr" ? calc : calc.closest("tr");
                    if (row) {
                        const cells = Array.from(row.querySelectorAll("th,td"));
                        if (cells.length >= 2) {
                            const label = norm(cells[0].innerText || cells[0].textContent);
                            if (titleLabels.has(label)) {
                                for (let i = 1; i < cells.length; i++) {
                                    const v = norm(cells[i].innerText || cells[i].textContent);
                                    if (v) {
                                        title = v;
                                        break;
                                    }
                                }
                            }
                        }
                    }
                    if (!title) {
                        let anchor = calc;
                        const tag = (anchor.tagName || "").toLowerCase();
                        if (tag === "tr") {
                            anchor = anchor.querySelector("td.label,th.label,td,th") || anchor;
                        }
                        let sib = anchor.nextElementSibling;
                        while (sib) {
                            const v = norm(sib.innerText || sib.textContent);
                            if (v) {
                                title = v;
                                break;
                            }
                            sib = sib.nextElementSibling;
                        }
                    }
                    if (!title) {
                        calcText = norm(calc.innerText || calc.textContent);
                        const maybeTitle = calcText.replace(/^title\\s*[:：]?\\s*/i, "").trim();
                        if (maybeTitle && maybeTitle !== calcText) {
                            title = maybeTitle;
                        } else if (calcText && !titleLabels.has(calcText)) {
                            title = calcText;
                        }
                    }
                }

                if (!title) {
                    const direct = document.querySelector(
                        "tr#calc_Title > td.field, tr#calc_Title > th + td, " +
                        "#calc_Title td.field, #calc_Title .field, td#calc_Title + td, th#calc_Title + td"
                    );
                    const directVal = norm(direct && (direct.innerText || direct.textContent));
                    if (directVal) {
                        title = directVal;
                    }
                }

                if (!title) {
                    title = readByLabel(titleLabels);
                }

                if (!title) {
                    const xps = [
                        "//*[@id='calc_Title']/following-sibling::*[1]",
                        "//*[self::td or self::th][normalize-space()='Title']/following-sibling::*[1]",
                        "//*[self::td or self::th][normalize-space()='Document Title']/following-sibling::*[1]",
                        "//*[self::td or self::th][normalize-space()='タイトル']/following-sibling::*[1]"
                    ];
                    for (const xp of xps) {
                        try {
                            const r = document.evaluate(
                                xp,
                                document,
                                null,
                                XPathResult.FIRST_ORDERED_NODE_TYPE,
                                null
                            );
                            const node = r.singleNodeValue;
                            const v = norm(node && (node.innerText || node.textContent));
                            if (v) {
                                title = v;
                                break;
                            }
                        } catch (e) {}
                    }
                }

                let name = readByLabel(nameLabels);
                const hasPdfButton = !!document.querySelector(
                    "td#TRMPdfDownloadCommand, #TRMPdfDownloadCommand, #TRMPdfDownloadCommand > img, img[src*='iconPdfDownload']"
                );
                return {
                    title,
                    name,
                    hasPdfButton,
                    hasCalcTitle: !!calc,
                    calcText
                };
            }
        """

        preferred_scored: list[tuple[int, str, str, str]] = []
        fallback_scored: list[tuple[int, str, str, str]] = []
        pages_for_title = []
        page_seen = set()

        def _append_title_page(p):
            if p is None:
                return
            try:
                if p.is_closed():
                    return
            except Exception:
                pass
            pid = id(p)
            if pid in page_seen:
                return
            page_seen.add(pid)
            pages_for_title.append(p)

        try:
            _append_title_page(preferred_page)
            for cand in _selector_target_pages(page):
                _append_title_page(cand)
        except Exception:
            pass
        if not pages_for_title:
            try:
                _append_title_page(preferred_page)
                for cand in _candidate_pages(page):
                    _append_title_page(cand)
            except Exception:
                pass

        for p in pages_for_title:
            page_url = _safe_page_url(p)
            areas = [("page", p)]
            try:
                areas.extend([(f"frame:{fr.name or '<unnamed>'}", fr) for fr in p.frames])
            except Exception:
                pass

            for area_name, area in areas:
                area_low = str(area_name or "").lower()
                if any(tok in area_low for tok in blocked_area_tokens):
                    _probe(f"title_skip area={area_name} reason=blocked_area")
                    continue

                try:
                    payload = area.evaluate(js)
                except Exception:
                    continue

                title = ""
                name_value = ""
                has_pdf_button = False
                has_calc_title = False
                calc_text = ""
                if isinstance(payload, dict):
                    title = str(payload.get("title", "") or "").strip()
                    name_value = str(payload.get("name", "") or "").strip()
                    has_pdf_button = bool(payload.get("hasPdfButton"))
                    has_calc_title = bool(payload.get("hasCalcTitle"))
                    calc_text = str(payload.get("calcText", "") or "").strip()
                else:
                    title = str(payload or "").strip()

                if not title:
                    continue

                normalized = title.replace("\u00A0", " ")
                normalized = re.sub(r"\s+", " ", normalized).strip()
                if not normalized or normalized in labels:
                    continue

                score = 0
                is_preferred_area = any(area_low == pref for pref in preferred_areas)
                if is_preferred_area:
                    score += 220
                if has_pdf_button:
                    score += 140
                if has_calc_title:
                    score += 220
                if "objectid=" in page_url.lower():
                    score += 60
                if "ticket=" in page_url.lower():
                    score -= 20
                if doc_code and doc_code in str(name_value or "").upper():
                    score += 120
                if doc_code and doc_code in str(calc_text or "").upper():
                    score += 60

                target_list = preferred_scored if is_preferred_area else fallback_scored
                target_list.append((score, normalized, area_name, page_url))
                _probe(
                    f"title_candidate score={score} area={area_name} page={page_url} "
                    f"name={name_value} calc={calc_text} title={normalized}"
                )

        if preferred_scored:
            preferred_scored.sort(key=lambda t: t[0], reverse=True)
            best = preferred_scored[0]
            _probe(
                f"title_detected area={best[2]} page={best[3]} score={best[0]} title={best[1]}"
            )
            return best[1]

        if fallback_scored:
            fallback_scored.sort(key=lambda t: t[0], reverse=True)
            best = fallback_scored[0]
            _probe(
                f"title_detected area={best[2]} page={best[3]} score={best[0]} title={best[1]}"
            )
            return best[1]

        _probe("title_detected none")
        return ""

    def _collect_snapshot(base_page):
        snap = {"pages": {}, "frames": {}, "iframes": {}}
        for p in _candidate_pages(base_page):
            pid = id(p)
            purl = _safe_page_url(p)
            snap["pages"][pid] = purl

            try:
                frs = list(p.frames)
            except Exception:
                frs = []
            for idx, fr in enumerate(frs):
                fname = fr.name or ""
                furl = ""
                try:
                    furl = fr.url or ""
                except Exception:
                    furl = ""
                snap["frames"][(pid, idx, fname)] = furl

            try:
                srcs = p.eval_on_selector_all(
                    "iframe",
                    "els => els.map((el) => el.src || el.getAttribute('src') || '')",
                ) or []
            except Exception:
                srcs = []
            for idx, src in enumerate(srcs):
                snap["iframes"][(pid, idx)] = str(src or "")
        return snap

    def _dismiss_download_ui():
        try:
            pages_now = [p for p in ctx.pages if not p.is_closed()]
        except Exception:
            pages_now = []
        for p in pages_now:
            url = _safe_page_url(p)
            if not _is_browser_downloads_ui_url(url):
                continue
            try:
                p.close()
                _probe(f"downloads_ui_page closed url={url}")
            except Exception as e:
                _probe(f"downloads_ui_page close failed url={url} err={e.__class__.__name__}: {e}")

        for p in _candidate_pages(page):
            try:
                p.bring_to_front()
            except Exception:
                pass
            try:
                p.keyboard.press("Escape")
            except Exception:
                pass
            try:
                p.keyboard.press("Escape")
            except Exception:
                pass

    candidate_queue: List[tuple[str, str, int]] = []
    seen_candidate_urls = set()

    def _queue_candidate(url: str, source: str, depth: int = 0, base_url: str = "", force: bool = False):
        if depth > 3:
            return
        norm = _normalize_url(url, base_url=base_url)
        if not norm or norm in seen_candidate_urls:
            return
        if not force:
            src = (source or "").lower()
            allow_non_pdf_source = src.startswith(("wrapper_from_", "iframe_url_fetch:", "response_url"))
            if not allow_non_pdf_source and not _looks_like_pdf_route(norm):
                return
        seen_candidate_urls.add(norm)
        candidate_queue.append((norm, source, depth))
        _probe(f"queue[{source} depth={depth}] {norm}")

    def _queue_snapshot_changes(prev_snap, cur_snap):
        special_frames = {"pagehidden", "dummyheaderframe", "jpcharfooter"}

        for pid, cur_url in cur_snap["pages"].items():
            prev_url = prev_snap["pages"].get(pid, "")
            if cur_url and cur_url != prev_url:
                _queue_candidate(cur_url, "page_url_change")
                _probe(f"page_url_change pid={pid} from={prev_url} to={cur_url}")

        for key, cur_url in cur_snap["frames"].items():
            prev_url = prev_snap["frames"].get(key, "")
            if not cur_url or cur_url == prev_url:
                continue
            fname = key[2] or "<unnamed>"
            src = f"frame:{fname}"
            if _looks_like_pdf_route(cur_url):
                _queue_candidate(cur_url, src)
            if (key[2] or "").lower() in special_frames:
                _queue_candidate(cur_url, f"iframe_url_fetch:{fname}", force=True)
            _probe(f"frame_url_change {fname} from={prev_url} to={cur_url}")

        for key, cur_src in cur_snap["iframes"].items():
            prev_src = prev_snap["iframes"].get(key, "")
            if not cur_src or cur_src == prev_src:
                continue
            pid = key[0]
            base_url = cur_snap["pages"].get(pid, "")
            _queue_candidate(cur_src, "iframe_src_change", base_url=base_url)
            _probe(f"iframe_src_change pid={pid} idx={key[1]} from={prev_src} to={cur_src}")

    def _build_click_candidates(target_page):
        candidates = []
        seen = set()
        order = 0

        for idx, s in enumerate(_selector_items(selector)):
            label = f"selector[{idx}] {s}"
            try:
                loc = resolve_selector(target_page, s)
                cnt = loc.count()
            except Exception as e:
                _probe(
                    f"click-candidate resolve miss page={_safe_page_url(target_page)} "
                    f"label={label} err={e.__class__.__name__}: {e}"
                )
                continue
            if cnt <= 0:
                _probe(f"click-candidate skip count=0 page={_safe_page_url(target_page)} label={label}")
                continue

            value = str(s.get("value", ""))
            has_frame = bool(s.get("frame_name"))
            prefer_td = "#TRMPdfDownloadCommand" in value and "> img" not in value
            prefer_title = "Download PDF" in value
            priority = 3
            if has_frame:
                priority -= 1
            if prefer_td:
                priority -= 1
            if prefer_title:
                priority -= 1

            sig = ("selector", s.get("frame_name"), s.get("by"), value)
            if sig in seen:
                continue
            seen.add(sig)
            candidates.append((priority, order, label, loc.first))
            _probe(
                f"click-candidate add page={_safe_page_url(target_page)} "
                f"priority={priority} count={cnt} label={label}"
            )
            order += 1

        for area_name, css, loc, cnt in _fallback_pdf_locators(target_page):
            sig = ("fallback", area_name, css)
            if sig in seen:
                continue
            seen.add(sig)
            priority = 4
            if area_name.startswith("frame:"):
                priority -= 1
            if area_name.lower() in ("frame:dcldocumentproperties", "frame:pagecontent", "frame:detailsdisplay"):
                priority -= 1
            if "#TRMPdfDownloadCommand" in css and "> img" not in css:
                priority -= 1
            label = f"fallback[{area_name}] {css}"
            candidates.append((priority, order, label, loc))
            _probe(
                f"click-candidate add page={_safe_page_url(target_page)} "
                f"priority={priority} count={cnt} label={label}"
            )
            order += 1

        candidates.sort(key=lambda x: (x[0], x[1]))
        return candidates

    def _click_download_target(loc, label: str, click_timeout_ms: int):
        per_timeout = max(1200, min(click_timeout_ms, 4500))
        try:
            loc.wait_for(state="attached", timeout=per_timeout)
        except Exception:
            pass

        try:
            loc.scroll_into_view_if_needed(timeout=per_timeout)
        except Exception:
            pass
        try:
            loc.hover(timeout=per_timeout)
        except Exception:
            pass

        clicked = False
        click_err = None
        try:
            loc.click(timeout=per_timeout)
            clicked = True
            _probe(f"click-candidate playwright click ok label={label}")
        except Exception as e:
            click_err = e
            try:
                loc.click(force=True, timeout=per_timeout)
                clicked = True
                _probe(f"click-candidate force click ok label={label}")
            except Exception as e2:
                click_err = e2

        if clicked:
            return

        for ev in ("mousedown", "mouseup", "click"):
            try:
                loc.dispatch_event(ev)
            except Exception:
                pass

        try:
            loc.evaluate(
                """(el) => {
                    const fire = (node, type) => {
                        if (!node) return;
                        try {
                            node.dispatchEvent(new MouseEvent(type, {
                                bubbles: true,
                                cancelable: true,
                                view: window,
                                button: 0
                            }));
                        } catch(e) {}
                    };
                    let td = null;
                    try { td = el.closest('td'); } catch(e) {}
                    if (!td && el && el.tagName === 'TD') td = el;
                    fire(td, 'mousedown');
                    fire(td, 'mouseup');
                    fire(td, 'click');
                    try { td?.click?.(); } catch(e) {}
                }"""
            )
        except Exception:
            pass

        if not clicked and click_err:
            raise click_err

    captured_responses = []
    captured_downloads = []

    def _on_response(res):
        try:
            headers = res.headers or {}
            url = res.url or ""
            low_url = (url or "").lower()
            status = ""
            try:
                status = str(res.status)
            except Exception:
                status = "?"
            ctype = _header(headers, "content-type")
            dispo = _header(headers, "content-disposition")
            if _is_pdf_hint(url, headers) or dispo or "download" in (url or "").lower():
                _probe(f"response status={status} url={url} ctype={ctype} dispo={dispo}")
                _queue_candidate(url, "response_url")
                captured_responses.append(res)
                if "trmpdfdownload.jsp" in low_url or "/fcs/servlet/fcs/checkout/" in low_url:
                    _prime_title_cache()
                    _dismiss_download_ui()
        except Exception:
            pass

    def _on_download(download):
        try:
            _probe(f"download_event url={download.url}")
        except Exception:
            _probe("download_event url=<unknown>")
        captured_downloads.append(download)

    attached_download_pages = set()
    ctx_download_listener_attached = False

    def _attach_download_listeners():
        nonlocal ctx_download_listener_attached
        # Context-level download (if supported by runtime)
        if not ctx_download_listener_attached:
            try:
                ctx.on("download", _on_download)
                ctx_download_listener_attached = True
            except Exception:
                pass
        for p in _candidate_pages(page):
            pid = id(p)
            if pid in attached_download_pages:
                continue
            try:
                p.on("download", _on_download)
                attached_download_pages.add(pid)
            except Exception:
                pass

    def _process_response_objects() -> str | None:
        while captured_responses:
            res = captured_responses.pop(0)
            try:
                headers = res.headers or {}
            except Exception:
                headers = {}
            try:
                url = res.url or ""
            except Exception:
                url = ""
            source_name = ""
            try:
                dispo = _header(headers, "content-disposition")
                m_fn = re.search(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)"?', dispo, flags=re.IGNORECASE)
                if m_fn:
                    source_name = os.path.basename(m_fn.group(1).strip())
            except Exception:
                source_name = ""
            if not source_name:
                try:
                    source_name = os.path.basename(urlparse(url).path or "")
                except Exception:
                    source_name = ""
            body = b""
            try:
                body = res.body() or b""
            except Exception:
                body = b""

            if _is_pdf_payload(body, headers):
                if _write_pdf(body, route="response", source=url, source_name=source_name):
                    return "response"

            if _is_html_payload(body, headers):
                html = _decode_body_text(body)
                for nxt in _extract_followup_urls(html, base_url=url):
                    _queue_candidate(nxt, "wrapper_from_response", depth=1, base_url=url)
        return None

    def _process_candidate_queue(req_timeout_ms: int, max_items: int = 2) -> str | None:
        processed = 0
        while candidate_queue and processed < max_items:
            url, source, depth = candidate_queue.pop(0)
            processed += 1
            _probe(f"fetch[{source} depth={depth}] {url}")
            try:
                res = ctx.request.get(url, timeout=req_timeout_ms)
            except Exception as e:
                _probe(f"fetch failed url={url} err={e.__class__.__name__}: {e}")
                continue

            headers = {}
            try:
                headers = res.headers or {}
            except Exception:
                headers = {}
            try:
                status = res.status
            except Exception:
                status = "?"
            ctype = _header(headers, "content-type")
            dispo = _header(headers, "content-disposition")
            _probe(f"fetch result status={status} url={url} ctype={ctype} dispo={dispo}")

            body = b""
            try:
                body = res.body() or b""
            except Exception:
                body = b""

            if _is_pdf_payload(body, headers):
                route = "iframe_url_fetch" if source.startswith(("frame:", "iframe_", "iframe_url_fetch:")) else "url_fetch"
                src_name = ""
                try:
                    src_name = os.path.basename(urlparse(url).path or "")
                except Exception:
                    src_name = ""
                if _write_pdf(body, route=route, source=url, source_name=src_name):
                    return route

            if depth < 3 and _is_html_payload(body, headers):
                html = _decode_body_text(body)
                for nxt in _extract_followup_urls(html, base_url=url):
                    _queue_candidate(nxt, f"wrapper_from_{source}", depth=depth + 1, base_url=url)
        return None

    def _post_success_cleanup(target_page=None):
        if target_page is None:
            target_page = page
        try:
            target_page.bring_to_front()
        except Exception:
            pass
        # Dismiss browser-side download UI if shown (Edge download panel).
        for _ in range(2):
            try:
                target_page.keyboard.press("Escape")
            except Exception:
                pass
            time.sleep(0.05)
        _dismiss_download_ui()

    def _close_popup_after_download_start(preferred_page=None):
        try:
            pages_now = [p for p in ctx.pages if not p.is_closed()]
        except Exception:
            pages_now = []
        if len(pages_now) <= 1:
            return False

        anchor_page = page if page in pages_now else pages_now[0]
        candidates = []
        if preferred_page is not None and preferred_page in pages_now and preferred_page != anchor_page:
            purl = _safe_page_url(preferred_page)
            if not _is_browser_downloads_ui_url(purl) and (
                _is_detail_popup_url(purl) or _has_opener(preferred_page)
            ):
                candidates.append(preferred_page)
        if not candidates:
            for p in reversed(pages_now):
                if p == anchor_page:
                    continue
                purl = _safe_page_url(p)
                if _is_browser_downloads_ui_url(purl):
                    continue
                if _is_detail_popup_url(purl):
                    candidates.append(p)
        if not candidates:
            for p in reversed(pages_now):
                if p == anchor_page:
                    continue
                purl = _safe_page_url(p)
                if _is_browser_downloads_ui_url(purl):
                    continue
                if _has_opener(p):
                    candidates.append(p)
        if not candidates:
            _probe("popup close skipped: no safe popup candidate")
            return False

        for cand in candidates:
            if cand == anchor_page:
                continue
            try:
                cand_url = _safe_page_url(cand)
            except Exception:
                cand_url = ""
            try:
                cand.close()
                _probe(f"popup closed after download start page={cand_url}")
                return True
            except Exception as e:
                _probe(f"popup close failed page={cand_url} err={e.__class__.__name__}: {e}")
        return False

    def _save_download_object(download, preferred_page=None, route_label: str = "download_event") -> str | None:
        nonlocal saved_output_path

        try:
            dl_url = getattr(download, "url", "") or ""
            fetch_url = _normalize_url(dl_url, base_url=_safe_page_url(preferred_page or page))
            if fetch_url:
                _probe(f"download_url_fetch {fetch_url}")
                import ssl
                import urllib.request

                parsed_url = urlparse(fetch_url)
                headers_out = {}
                try:
                    origin = f"{parsed_url.scheme}://{parsed_url.netloc}"
                    cookies = ctx.cookies([origin])
                    cookie_header = "; ".join(
                        f"{c.get('name')}={c.get('value')}"
                        for c in (cookies or [])
                        if c.get("name") and c.get("value") is not None
                    )
                    if cookie_header:
                        headers_out["Cookie"] = cookie_header
                except Exception:
                    pass
                request = urllib.request.Request(fetch_url, headers=headers_out)
                ssl_context = ssl._create_unverified_context() if parsed_url.scheme == "https" else None
                with urllib.request.urlopen(request, timeout=5, context=ssl_context) as res:
                    headers = dict(res.headers.items())
                    body = res.read() or b""
                if _is_pdf_payload(body, headers):
                    source_name = getattr(download, "suggested_filename", "") or ""
                    if not source_name:
                        source_name = os.path.basename(urlparse(fetch_url).path or "")
                    if _write_pdf(
                        body,
                        route="download_url_fetch",
                        source=fetch_url,
                        source_name=source_name,
                    ):
                        _close_popup_after_download_start(preferred_page=preferred_page)
                        _post_success_cleanup()
                        return "download_url_fetch"
        except Exception as fetch_e:
            _probe(f"download_url_fetch failed err={fetch_e.__class__.__name__}: {fetch_e}")

        try:
            target_path = _build_output_path_for_name(
                source_name=getattr(download, "suggested_filename", "") or ""
            )
            download.save_as(target_path)
            _close_popup_after_download_start(preferred_page=preferred_page)
            try:
                saved_output_path = os.path.abspath(target_path)
            except Exception:
                saved_output_path = target_path
            _post_success_cleanup()
            _probe(f"saved route={route_label} path={saved_output_path}")
            _log(log, f"[FLOW] download saved ({route_label}): {saved_output_path}")
            return route_label
        except Exception as e:
            _probe(f"{route_label} save_as failed err={e.__class__.__name__}: {e}")
            return None

    def _try_click_download(click_timeout_ms: int) -> str | None:
        dl_wait_ms = max(1800, min(click_timeout_ms, 5500))
        for target_page in _selector_target_pages(page):
            try:
                try:
                    target_page.bring_to_front()
                except Exception:
                    pass
                candidates = _build_click_candidates(target_page)
                if not candidates:
                    _probe(f"download click skip page={_safe_page_url(target_page)} reason=no_click_candidate")
                    continue
                _prime_title_cache(preferred_page=target_page)
                for _, _, label, loc in candidates:
                    try:
                        _attach_download_listeners()
                        _click_download_target(loc, label=label, click_timeout_ms=click_timeout_ms)
                    except Exception as e:
                        _probe(
                            f"download click failed page={_safe_page_url(target_page)} "
                            f"candidate={label} err={e.__class__.__name__}: {e}"
                        )
                        continue

                    click_deadline = time.monotonic() + (dl_wait_ms / 1000.0)
                    while time.monotonic() < click_deadline:
                        _attach_download_listeners()
                        while captured_downloads:
                            route = _save_download_object(
                                captured_downloads.pop(0),
                                preferred_page=target_page,
                                route_label="download_event",
                            )
                            if route:
                                return route
                        try:
                            resp_route = _process_response_objects()
                            if resp_route:
                                _close_popup_after_download_start(preferred_page=target_page)
                                _post_success_cleanup()
                                return resp_route
                        except Exception as resp_e:
                            _probe(
                                f"response fallback after download click failed "
                                f"err={resp_e.__class__.__name__}: {resp_e}"
                            )
                        try:
                            native_state, native_path = _scan_native_downloads()
                            if native_state == "complete" and native_path and _finalize_native_file(native_path):
                                _close_popup_after_download_start(preferred_page=target_page)
                                _post_success_cleanup()
                                return "native"
                        except Exception as native_e:
                            _probe(f"native fallback after download click failed err={native_e.__class__.__name__}: {native_e}")
                        time.sleep(0.15)
                    _probe(
                        f"download_event miss page={_safe_page_url(target_page)} "
                        f"candidate={label} wait_ms={dl_wait_ms}"
                    )
            except Exception as e:
                _probe(f"download click page error page={_safe_page_url(target_page)} err={e.__class__.__name__}: {e}")
                continue
        return None

    try:
        try:
            ctx.on("response", _on_response)
        except Exception:
            pass
        _attach_download_listeners()

        initial_snap = _collect_snapshot(page)
        _probe(f"pre_snapshot pages={len(initial_snap['pages'])} frames={len(initial_snap['frames'])} iframes={len(initial_snap['iframes'])}")

        # Initial page/frame URLs are noisy and often unrelated to PDF retrieval.
        # Start from observed response/frame changes instead.

        route = None
        last_err = None
        deadline = time.monotonic() + (timeout_ms / 1000.0)
        click_timeout_ms = max(4000, min(12000, int(timeout_ms * 0.35)))
        req_timeout_ms = max(1200, min(3000, int(timeout_ms * 0.08)))
        retriggered = False
        last_reclick_at = time.monotonic()
        last_ui_dismiss_at = time.monotonic()

        try:
            route = _try_click_download(click_timeout_ms=click_timeout_ms)
            if route:
                return saved_output_path
        except Exception as e:
            last_err = e

        prev_snap = initial_snap
        while time.monotonic() < deadline:
            _attach_download_listeners()
            if (time.monotonic() - last_ui_dismiss_at) >= 0.9:
                last_ui_dismiss_at = time.monotonic()
                _dismiss_download_ui()

            try:
                native_state, native_path = _scan_native_downloads()
                if native_state == "partial":
                    _prime_title_cache()
                    _close_popup_after_download_start()
                elif native_state == "complete" and native_path:
                    if _finalize_native_file(native_path):
                        _close_popup_after_download_start()
                        _post_success_cleanup()
                        return saved_output_path
            except Exception as e:
                last_err = e
                _probe(f"native scan failed err={e.__class__.__name__}: {e}")

            while captured_downloads:
                dl = captured_downloads.pop(0)
                try:
                    route = _save_download_object(dl, preferred_page=page, route_label="download_event")
                    if route:
                        return saved_output_path
                except Exception as e:
                    last_err = e
                    _probe(f"download_event save failed err={e.__class__.__name__}: {e}")

            try:
                resp_route = _process_response_objects()
                if resp_route:
                    _close_popup_after_download_start()
                    _post_success_cleanup()
                    return saved_output_path
            except Exception as e:
                last_err = e
                _probe(f"response process failed err={e.__class__.__name__}: {e}")

            try:
                cur_snap = _collect_snapshot(page)
                _queue_snapshot_changes(prev_snap, cur_snap)
                prev_snap = cur_snap
            except Exception as e:
                last_err = e
                _probe(f"snapshot scan failed err={e.__class__.__name__}: {e}")

            try:
                fetch_route = _process_candidate_queue(req_timeout_ms=req_timeout_ms)
                if fetch_route:
                    _close_popup_after_download_start()
                    _post_success_cleanup()
                    return saved_output_path
            except Exception as e:
                last_err = e
                _probe(f"candidate fetch failed err={e.__class__.__name__}: {e}")

            # Re-attempt click periodically so we don't wait until near-timeout
            # after the frame/toolbar becomes available.
            if (time.monotonic() - last_reclick_at) >= 1.2:
                last_reclick_at = time.monotonic()
                try:
                    route = _try_click_download(click_timeout_ms=max(2000, int(click_timeout_ms * 0.7)))
                    if route:
                        return saved_output_path
                except Exception as e:
                    last_err = e
                    _probe(f"periodic reclick failed err={e.__class__.__name__}: {e}")

            if not retriggered and (time.monotonic() + 0.2) > (deadline - (timeout_ms / 2000.0)):
                retriggered = True
                try:
                    route = _try_click_download(click_timeout_ms=max(2500, int(click_timeout_ms * 0.8)))
                    if route:
                        return saved_output_path
                except Exception as e:
                    last_err = e
                    _probe(f"retrigger failed err={e.__class__.__name__}: {e}")

            time.sleep(0.25)

        reason = "timeout:no_pdf_candidate"
        if last_err:
            reason = f"{last_err.__class__.__name__}: {last_err}"
        try:
            _close_popup_after_download_start()
            _dismiss_download_ui()
        except Exception:
            pass
        _probe(f"failed reason={reason}")
        raise RuntimeError(f"PDF download failed ({reason}). probe={probe_path}")

    finally:
        try:
            ctx.remove_listener("response", _on_response)
        except Exception:
            try:
                ctx.off("response", _on_response)
            except Exception:
                pass
        try:
            ctx.remove_listener("download", _on_download)
        except Exception:
            try:
                ctx.off("download", _on_download)
            except Exception:
                pass
        for p in _candidate_pages(page):
            try:
                p.remove_listener("download", _on_download)
            except Exception:
                try:
                    p.off("download", _on_download)
                except Exception:
                    pass


def act_close_page(page, log: bool = True):
    _log(log, "[FLOW] close_page")
    try:
        page.close()
    except Exception as e:
        _log(log, f"[FLOW] close_page failed: {e}")


def act_close_popup(page, log: bool = True):
    def _safe_page_url(p) -> str:
        try:
            return p.url or ""
        except Exception:
            return ""

    def _is_browser_downloads_ui_url(url: str) -> bool:
        low = str(url or "").lower()
        return (
            low.startswith("edge://downloads")
            or low.startswith("chrome://downloads")
            or low.startswith("about:downloads")
        )

    def _is_detail_popup_url(url: str) -> bool:
        return "objectid=" in str(url or "").lower()

    def _has_opener(p) -> bool:
        try:
            return p.opener() is not None
        except Exception:
            return False

    def _unwrap_current_page(p):
        try:
            target_getter = getattr(p, "_target", None)
            if callable(target_getter):
                real = target_getter()
                if real is not None:
                    return real
        except Exception:
            pass
        return p

    try:
        pages = [p for p in page.context.pages if not p.is_closed()]
    except Exception:
        pages = []
    current = _unwrap_current_page(page)

    for p in list(pages):
        try:
            u = _safe_page_url(p)
        except Exception:
            u = ""
        if not _is_browser_downloads_ui_url(u):
            continue
        try:
            p.close()
            _log(log, f"[FLOW] close_popup: closed downloads ui page ({u})")
            pages = [x for x in pages if x != p]
        except Exception as e:
            _log(log, f"[FLOW] close_popup: failed to close downloads ui page ({u}): {e}")

    if len(pages) <= 1:
        current_url = ""
        try:
            nav_page = pages[0] if pages else current
            current_url = nav_page.url or ""
        except Exception:
            current_url = ""
        # Some 3DEX flows open detail in the same tab instead of popup.
        # In that case, try history back so the next ID can be processed.
        if "objectid=" in current_url.lower():
            try:
                nav_page = pages[0] if pages else current
                nav_page.go_back(wait_until="domcontentloaded", timeout=6000)
                _log(log, "[FLOW] close_popup: fallback back-navigation succeeded")
                return True
            except Exception as e:
                _log(log, f"[FLOW] close_popup: fallback back-navigation failed: {e}")
                try:
                    prev_url = current_url
                    nav_page.evaluate("() => { try { history.back(); } catch (e) {} }")
                    nav_page.wait_for_timeout(1200)
                    new_url = _safe_page_url(nav_page)
                    if new_url and new_url != prev_url:
                        _log(log, "[FLOW] close_popup: JS history.back fallback succeeded")
                        return True
                except Exception as e2:
                    _log(log, f"[FLOW] close_popup: JS history.back fallback failed: {e2}")
        _log(log, "[FLOW] close_popup skipped (single page context)")
        return False

    pages_non_ui = [p for p in pages if not _is_browser_downloads_ui_url(_safe_page_url(p))]
    if not pages_non_ui:
        _log(log, "[FLOW] close_popup skipped (no non-ui pages)")
        return False

    root_pages = [p for p in pages_non_ui if not _has_opener(p)]
    main_page = root_pages[0] if root_pages else pages_non_ui[0]
    target = None

    # safest: close current page if it is clearly a detail popup
    current_url = _safe_page_url(current)
    if current in pages_non_ui and current != main_page and _is_detail_popup_url(current_url):
        target = current

    if target is None:
        for p in reversed(pages_non_ui):
            if p == main_page:
                continue
            if _is_detail_popup_url(_safe_page_url(p)):
                target = p
                break

    if target is None:
        for p in reversed(pages_non_ui):
            if p == main_page:
                continue
            if _has_opener(p):
                target = p
                break

    if target is None:
        _log(log, "[FLOW] close_popup skipped (no safe popup candidate)")
        return False

    try:
        target.close()
        _log(log, "[FLOW] close_popup: closed popup page")
        return True
    except Exception as e:
        _log(log, f"[FLOW] close_popup failed: {e}")
        return False


def act_select_option(page, selector: Dict[str, Any], value: str, log: bool = True):
    _log(log, f"[FLOW] select_option: {selector} -> '{value}'")
    with_fallback(page, selector).select_option(value)
