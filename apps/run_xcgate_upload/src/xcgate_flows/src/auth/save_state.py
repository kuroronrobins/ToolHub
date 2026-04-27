# src/auth/save_state.py
import argparse, os
from pathlib import Path
from playwright.sync_api import sync_playwright

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="https://mega.nz/fm")
    ap.add_argument("--channel", default="msedge")
    ap.add_argument("--user-data-dir", required=False, default=None,
                    help="既存プロファイルを使う場合に指定（失敗する場合は未指定推奨）")
    ap.add_argument("--profile-dir", default=None)
    ap.add_argument("--storage-state", default=".auth/mega_state.json")
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--devtools", action="store_true")
    args = ap.parse_args()

    Path(os.path.dirname(args.storage_state)).mkdir(parents=True, exist_ok=True)

    with sync_playwright() as pw:
        # 既存プロファイルが不安定な場合は、user_data_dir を指定しないで OK（空の一時プロファイルで起動）
        if args.user_data_dir:
            kwargs = {
                "user_data_dir": args.user_data_dir,
                "headless": args.headless,
            }
            if args.channel: kwargs["channel"] = args.channel
            if args.profile_dir:
                kwargs["args"] = [f"--profile-directory={args.profile_dir}"]
            ctx = pw.chromium.launch_persistent_context(**kwargs)
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
        else:
            browser = pw.chromium.launch(channel=args.channel, headless=args.headless, devtools=args.devtools)
            ctx = browser.new_context()
            page = ctx.new_page()

        print(f"[LOGIN] Opening {args.url}")
        page.goto(args.url, wait_until="domcontentloaded", timeout=120000)
        print("[LOGIN] ここで手動ログインしてください。完了後 Enter を押すと状態を保存します。")
        try:
            input()
        except EOFError:
            pass

        # 保存
        ctx.storage_state(path=args.storage_state)
        print(f"[LOGIN] Saved storage_state to {args.storage_state}")

        ctx.close()
        if "browser" in locals():
            browser.close()

if __name__ == "__main__":
    main()
