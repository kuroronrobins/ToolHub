#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path


def emit(event_type: str, message: str, progress: int | None = None) -> None:
    payload = {"type": event_type, "message": message}
    if progress is not None:
        payload["progress"] = progress
    print(json.dumps(payload, ensure_ascii=False), flush=True)


def write_demo_page() -> Path:
    profile_hint = os.environ.get("TOOLHUB_BROWSER_PROFILE_DIR", "")
    html = f"""<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <title>Web操作サンプル</title>
  <style>
    body {{ font-family: sans-serif; margin: 40px; color: #1f2937; }}
    main {{ max-width: 520px; }}
    button {{ padding: 10px 16px; }}
  </style>
</head>
<body>
  <main>
    <h1>Web操作サンプル</h1>
    <p id="status">準備完了</p>
    <button id="run">処理する</button>
    <small>{profile_hint}</small>
  </main>
  <script>
    document.getElementById('run').addEventListener('click', () => {{
      document.getElementById('status').textContent = '完了';
    }});
  </script>
</body>
</html>"""
    path = Path(tempfile.gettempdir()) / "toolhub_web_operation_sample.html"
    path.write_text(html, encoding="utf-8")
    return path


def main() -> int:
    emit("status", "起動準備をしています", 10)
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except Exception as exc:
        print(repr(exc), file=sys.stderr, flush=True)
        emit("error", "必要な実行環境が未準備です。管理者に連絡してください。", 0)
        return 1

    try:
        page_path = write_demo_page()
        emit("status", "画面を準備しています", 40)
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(page_path.as_uri())
            page.click("#run")
            status = page.text_content("#status")
            browser.close()
        if status != "完了":
            emit("error", "処理結果を確認できませんでした。", 80)
            return 1
        emit("success", "完了しました", 100)
        return 0
    except Exception as exc:
        print(repr(exc), file=sys.stderr, flush=True)
        emit("error", "処理中に問題が発生しました。管理者に連絡してください。", 80)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
