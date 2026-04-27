from playwright.sync_api import sync_playwright
from playwright.sync_api import Error as PWError, TimeoutError as PWTimeoutError
from typing import Optional
import os
from datetime import datetime

def _hook_page_listeners(page, ctx=None):
    page.on("console", lambda msg: print(f"[BROWSER][console:{msg.type}] {msg.text}"))
    page.on("request", lambda req: print(f"[BROWSER][request] {req.method} {req.url}"))
    page.on("response", lambda res: print(f"[BROWSER][response] {res.status} {res.url}"))
    # Auto-dismiss unexpected dialogs/alerts safely (ignore races)
    def _on_dialog(dlg):
        try:
            print(f"[BROWSER][dialog] {dlg.type}: {dlg.message}")
            # Persist dialog messages (e.g., Name:DC-xxxx) to logs for later use
            try:
                os.makedirs("logs", exist_ok=True)
                with open("logs/doc_ids.txt", "a", encoding="utf-8") as fp:
                    fp.write(f"{datetime.now().isoformat(timespec='seconds')}\t{dlg.message}\n")
                msg = dlg.message or ""
                doc_id = None
                for line in msg.splitlines():
                    if "Name:" in line:
                        doc_id = line.split("Name:", 1)[1].strip()
                        break
                if doc_id:
                    print(f"[DOC_ID] {doc_id}")
                    if ctx is not None:
                        try:
                            ctx.doc_ids.append(doc_id)
                            ctx.doc_records.append({"id": doc_id, "message": msg, "timestamp": datetime.now()})
                        except Exception:
                            pass
            except Exception:
                pass
            dlg.dismiss()
        except Exception as e:
            try:
                print(f"[BROWSER][dialog][ignore] {e}")
            except Exception:
                pass
    try:
        page.on("dialog", _on_dialog)
    except Exception:
        pass
    def _on_req_failed(req):
        try:
            failure = getattr(req, "failure", None)
            reason = ""
            if callable(failure):
                info = failure() or {}
                reason = info.get("errorText") or info.get("error_text") or str(info)
            else:
                reason = str(failure)
        except Exception:
            reason = ""
        print(f"[BROWSER][requestfailed] {reason} {req.url}")
    page.on("requestfailed", _on_req_failed)

class _ActivePageProxy:
    def __init__(self, ctx: "BrowserCtx"):
        self._ctx = ctx

    def _target(self):
        page = self._ctx.page
        if page is None:
            raise RuntimeError("No active page available")
        return page

    def __getattr__(self, name):
        return getattr(self._target(), name)

    def __repr__(self):
        page = self._ctx.page
        return f"<ActivePageProxy target={page!r}>"

class BrowserCtx:
    def __init__(
        self,
        headless: bool = False,
        channel: Optional[str] = None,
        ignore_https_errors: bool = False,
        slowmo_ms: int = 0,
        devtools: bool = False,
        user_data_dir: Optional[str] = None,
        user_data_profile: Optional[str] = None,
        trace: bool = False,
        har: bool = False,
        storage_state_path: Optional[str] = None,
        prefer_persistent: bool = False,
    ):
        self._pw = None
        self.browser = None
        self.context = None
        self.page = None
        self.headless = headless
        self.channel = channel
        self.ignore_https_errors = ignore_https_errors
        self.slowmo_ms = slowmo_ms
        self.devtools = devtools
        self.user_data_dir = user_data_dir
        self.user_data_profile = user_data_profile
        self.trace = trace
        self.har = har
        self.storage_state_path = storage_state_path
        self.prefer_persistent = prefer_persistent
        self._popup_unsubscribed = False
        self._page_proxy = None
        self._page_stack = []
        self.doc_ids = []
        self.doc_records = []

    def _on_new_page(self, page):
        try:
            print(f"[BROWSER] popup/new page detected: {page.url}")
        except Exception:
            pass
        self._register_page(page)
        try:
            page.bring_to_front()
        except Exception:
            pass

    def _attach_popup_listener(self, ctx):
        try:
            ctx.on("page", self._on_new_page)
        except Exception:
            pass

    def _register_page(self, page):
        if page is None:
            return
        try:
            _hook_page_listeners(page, self)
        except Exception:
            pass
        try:
            page.on("close", lambda _: self._on_page_closed(page))
        except Exception:
            pass
        if page not in self._page_stack:
            self._page_stack.append(page)
        self.page = page
        self._ensure_page_proxy()

    def _on_page_closed(self, page):
        try:
            self._page_stack = [p for p in self._page_stack if p != page]
        except Exception:
            self._page_stack = []
        self.page = self._page_stack[-1] if self._page_stack else None
        self._ensure_page_proxy()

    def _make_non_persistent(self):
        launch_kwargs = {
            "headless": self.headless,
            "slow_mo": self.slowmo_ms if self.slowmo_ms else 0,
            "devtools": self.devtools,
        }
        if self.channel:
            launch_kwargs["channel"] = self.channel
        self.browser = self._pw.chromium.launch(**launch_kwargs)

        new_ctx_kwargs = {"ignore_https_errors": self.ignore_https_errors}
        # storage_state があれば読み込む
        if self.storage_state_path and os.path.exists(self.storage_state_path):
            new_ctx_kwargs["storage_state"] = self.storage_state_path
        if self.har:
            new_ctx_kwargs["record_har_path"] = "logs/network.har"
            new_ctx_kwargs["record_har_content"] = "embed"

        self.context = self.browser.new_context(**new_ctx_kwargs)
        self._attach_popup_listener(self.context)
        if self.trace:
            self.context.tracing.start(screenshots=True, snapshots=True, sources=True)

        self.page = self.context.new_page()
        self._register_page(self.page)

    def __enter__(self):
        self._pw = sync_playwright().start()

        # 1) 永続を希望 → 試す → 失敗したら落とさずフォールバック
        if self.prefer_persistent and self.user_data_dir:
            try:
                kwargs = {
                    "user_data_dir": self.user_data_dir,
                    "headless": self.headless,
                    "ignore_https_errors": self.ignore_https_errors,
                    "slow_mo": self.slowmo_ms if self.slowmo_ms else 0,
                }
                if self.channel:
                    kwargs["channel"] = self.channel
                args = []
                if self.user_data_profile:
                    args.append(f"--profile-directory={self.user_data_profile}")
                if args:
                    kwargs["args"] = args

                self.context = self._pw.chromium.launch_persistent_context(**kwargs)
                self._attach_popup_listener(self.context)
                if self.trace:
                    self.context.tracing.start(screenshots=True, snapshots=True, sources=True)
                self.page = self.context.pages[0] if self.context.pages else self.context.new_page()
                self._register_page(self.page)
                self.browser = self.context.browser
                print("[BROWSER] persistent context started")
                return self
            except PWError as e:
                print(f"[BROWSER] persistent failed: {e}. Falling back to non-persistent + storage_state.")
                # fallthrough to non-persistent

        # 2) 非永続＋storage_state（既定）
        self._make_non_persistent()
        print("[BROWSER] non-persistent context started")
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            if self.context:
                if self.trace:
                    try:
                        self.context.tracing.stop(path="logs/trace.zip")
                        print("[TRACE] saved to logs/trace.zip")
                    except Exception:
                        pass
                self.context.close()
            if self.browser:
                self.browser.close()
        finally:
            if self._pw:
                self._pw.stop()

    def _ensure_page_proxy(self):
        if self._page_proxy is None:
            self._page_proxy = _ActivePageProxy(self)

    @property
    def active_page(self):
        self._ensure_page_proxy()
        return self._page_proxy
