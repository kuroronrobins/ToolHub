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
                doc_log_path = None
                if ctx is not None:
                    doc_log_path = getattr(ctx, "doc_log_path", None)
                if not doc_log_path:
                    doc_log_path = os.path.join("logs", "doc_ids.txt")
                os.makedirs(os.path.dirname(doc_log_path) or ".", exist_ok=True)
                with open(doc_log_path, "a", encoding="utf-8") as fp:
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
        page = self._ctx._refresh_active_page()
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
        doc_log_path: Optional[str] = None,
        har_path: Optional[str] = None,
        trace_path: Optional[str] = None,
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
        self.doc_log_path = doc_log_path or os.path.join("logs", "doc_ids.txt")
        self.har_path = har_path or os.path.join("logs", "network.har")
        self.trace_path = trace_path or os.path.join("logs", "trace.zip")
        self._popup_unsubscribed = False
        self._page_proxy = None
        self._page_stack = []
        self.doc_ids = []
        self.doc_records = []

    def _page_url(self, page) -> str:
        try:
            return str(page.url or "")
        except Exception:
            return ""

    def _is_non_target_ui_page(self, page) -> bool:
        url = self._page_url(page).lower()
        if not url:
            return False
        return (
            url.startswith("edge://downloads")
            or url.startswith("chrome://downloads")
            or url.startswith("about:downloads")
        )

    def _refresh_active_page(self):
        alive = []
        for p in self._page_stack:
            try:
                if p is None or p.is_closed():
                    continue
            except Exception:
                continue
            alive.append(p)
        self._page_stack = alive

        for p in reversed(self._page_stack):
            if not self._is_non_target_ui_page(p):
                self.page = p
                self._ensure_page_proxy()
                return p
        self.page = self._page_stack[-1] if self._page_stack else None
        self._ensure_page_proxy()
        return self.page

    def _default_launch_args(self):
        # Keep browser chrome download bubble from grabbing focus during automation.
        return [
            "--disable-features=DownloadBubble,DownloadBubbleV2",
            "--no-first-run",
            "--no-default-browser-check",
        ]

    def _on_new_page(self, page):
        try:
            print(f"[BROWSER] popup/new page detected: {page.url}")
        except Exception:
            pass
        self._register_page(page)
        if self._is_non_target_ui_page(page):
            try:
                print(f"[BROWSER] ignored non-target page: {self._page_url(page)}")
            except Exception:
                pass
            self._refresh_active_page()
            return
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
            page.on("close", lambda *args: self._on_page_closed(page))
        except Exception:
            pass
        if page not in self._page_stack:
            self._page_stack.append(page)
        self._refresh_active_page()

    def _on_page_closed(self, page):
        try:
            self._page_stack = [p for p in self._page_stack if p != page]
        except Exception:
            self._page_stack = []
        self._refresh_active_page()

    def _make_non_persistent(self):
        launch_kwargs = {
            "headless": self.headless,
            "slow_mo": self.slowmo_ms if self.slowmo_ms else 0,
            "devtools": self.devtools,
            "args": self._default_launch_args(),
        }
        if self.channel:
            launch_kwargs["channel"] = self.channel
        self.browser = self._pw.chromium.launch(**launch_kwargs)

        new_ctx_kwargs = {
            "ignore_https_errors": self.ignore_https_errors,
            "accept_downloads": True,
        }
        # storage_state があれば読み込む
        if self.storage_state_path and os.path.exists(self.storage_state_path):
            new_ctx_kwargs["storage_state"] = self.storage_state_path
        if self.har:
            new_ctx_kwargs["record_har_path"] = self.har_path
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
                    "accept_downloads": True,
                }
                if self.channel:
                    kwargs["channel"] = self.channel
                args = list(self._default_launch_args())
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
                        self.context.tracing.stop(path=self.trace_path)
                        print(f"[TRACE] saved to {self.trace_path}")
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
