from __future__ import annotations

import argparse

from app.smoke import run_smoke_check


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Excel batch replace tool")
    parser.add_argument("--toolhub-smoke", action="store_true", help="Run ToolHub registration smoke checks")
    parser.add_argument("--window", choices=("main",), default="main", help="Window to open")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.toolhub_smoke:
        return run_smoke_check()
    if args.window == "main":
        from app.main import main as run_main_window

        run_main_window()
        return 0
    raise ValueError(f"Unsupported window: {args.window}")


if __name__ == "__main__":
    raise SystemExit(main())
