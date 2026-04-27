from typing import Dict, Any, List
import time, os
from playwright.sync_api import Error as PWError
from .selectors import with_fallback
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
            _log(log, f"[FLOW] goto: attempt {attempt+1} failed: {e}")
            if attempt < retries:
                time.sleep(delay_ms / 1000.0)
                continue
            raise

def act_wait(page, selector: Dict[str,Any]=None, text: str=None,
             timeout_ms: int=30000, visible: bool=True, log: bool = True):
    target = f'text="{text}"' if text else selector
    _log(log, f"[FLOW] wait: {target} (timeout={timeout_ms}ms, state={'visible' if visible else 'hidden'})")
    if text:
        sel = {"by":"text","value":text}
        loc = with_fallback(page, sel).first        # ← .firstで唯一化
        loc.wait_for(timeout=timeout_ms,            # ← ここを関数呼び出しではなくメソッドに修正
                     state="visible" if visible else "hidden")
        _log(log, "[FLOW] wait: satisfied")
        return
    if selector:
        loc = with_fallback(page, selector).first   # ← 同上
        loc.wait_for(timeout=timeout_ms,
                     state="visible" if visible else "hidden")
        _log(log, "[FLOW] wait: satisfied")


def act_click(page, selector: Dict[str,Any], log: bool = True, timeout_ms: int = 5000):
    _log(log, f"[FLOW] click: {selector}")
    loc = with_fallback(page, selector).first
    try:
        # 事前に表示領域へスクロール＆ホバー（古いUIで必要なことがある）
        try:
            loc.scroll_into_view_if_needed(timeout=timeout_ms)
        except Exception:
            pass
        try:
            loc.hover(timeout=timeout_ms)
        except Exception:
            pass
        loc.click(timeout=timeout_ms)
        return
    except PWError as e:
        _log(log, f"[FLOW] click: normal click failed, retry with force. err={e}")
        try:
            loc.click(force=True, timeout=timeout_ms)
            _log(log, "[FLOW] click: force click succeeded")
            return
        except PWError as e2:
            _log(log, f"[FLOW] click: force click failed. err={e2}")
            # 最後の手段として JS の element.click() を試す
            try:
                loc.evaluate("el => { el.click?.(); el.parentElement?.click?.(); const td = el.closest('td'); td?.click?.(); const tdMenu = el.closest('td.menu-button'); tdMenu?.click?.(); }")
                _log(log, "[FLOW] click: JS click() fallback succeeded")
                return
            except Exception as e3:
                _log(log, f"[FLOW] click: JS click() fallback failed. err={e3}")
                # さらに mousedown/mouseup を直接投げてみる
                try:
                    loc.dispatch_event("mousedown")
                    loc.dispatch_event("mouseup")
                    _log(log, "[FLOW] click: dispatched mousedown/mouseup events")
                    return
                except Exception as e4:
                    _log(log, f"[FLOW] click: dispatch events failed. err={e4}")
                raise

def act_choose_file(page, open_by: Dict[str,Any], paths: List[str], log: bool = True, timeout_ms: int = 5000):
    _log(log, f"[FLOW] choose_file: open_by={open_by}, files={paths}, timeout={timeout_ms}ms")
    with page.expect_file_chooser(timeout=timeout_ms) as fc:
        act_click(page, open_by, log=log)
    file_chooser = fc.value
    file_chooser.set_files(paths if len(paths)>1 else paths[0])
    _log(log, "[FLOW] choose_file: files set")

def act_set_input_files(page, selector: Dict[str,Any], paths: List[str], log: bool = True):
    _log(log, f"[FLOW] set_input_files: {selector} <- {paths}")
    with_fallback(page, selector).set_input_files(paths if len(paths)>1 else paths[0])

# CSVやスクショは必要時に（元の実装があれば流用）

def act_screenshot(page, output_path: str, log: bool = True, full_page: bool = False):
    try:
        ensure_dir(os.path.dirname(output_path) or ".")
        # デフォルトは viewport のみ（高速）。full_page=True は明示指定時のみ。
        page.screenshot(path=output_path, full_page=full_page)
        _log(log, f"[FLOW] screenshot saved: {output_path} (full_page={full_page})")
    except Exception as e:
        _log(log, f"[FLOW] screenshot failed: {e}")



def act_fill(page, selector: Dict[str,Any], value: str, log: bool = True):
    _log(log, f"[FLOW] fill: {selector} = '{value}'")
    with_fallback(page, selector).fill(value)


def act_close_page(page, log: bool = True):
    _log(log, "[FLOW] close_page")
    try:
        page.close()
    except Exception as e:
        _log(log, f"[FLOW] close_page failed: {e}")

def act_select_option(page, selector: Dict[str,Any], value: str, log: bool = True):
    _log(log, f"[FLOW] select_option: {selector} -> '{value}'")
    with_fallback(page, selector).select_option(value)
