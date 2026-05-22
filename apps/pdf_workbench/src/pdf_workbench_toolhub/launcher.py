from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path


DEFAULT_STARTUP_WAIT_SECONDS = 5.0
SOURCE_PAYLOAD_RELATIVE = Path("assets") / "payload"
REGISTERED_PAYLOAD_RELATIVE = Path("src") / SOURCE_PAYLOAD_RELATIVE


def app_root() -> Path:
    toolhub_app_dir = os.environ.get("TOOLHUB_APP_DIR")
    if toolhub_app_dir:
        return Path(toolhub_app_dir)
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def payload_root(root: Path) -> Path:
    for candidate in payload_candidates(root):
        if (candidate / "pdf-workbench.exe").is_file():
            return candidate
    return root / SOURCE_PAYLOAD_RELATIVE


def payload_candidates(root: Path) -> list[Path]:
    return [
        root / SOURCE_PAYLOAD_RELATIVE,
        root / REGISTERED_PAYLOAD_RELATIVE,
    ]


def resolve_exe(payload: Path) -> Path:
    candidate = payload / "pdf-workbench.exe"
    if candidate.is_file():
        return candidate
    candidates = "\n".join(
        f"  - {root / 'pdf-workbench.exe'}" for root in payload_candidates(app_root())
    )
    raise FileNotFoundError(
        "PDF Workbench executable was not found. Run scripts/stage-toolhub-app.ps1 "
        "after building the Tauri release payload.\n"
        f"Checked:\n{candidates}"
    )


def build_env(payload: Path) -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("PDF_WORKBENCH_DISABLE_PYTHON_FALLBACK", "1")
    env.setdefault("PDF_WORKBENCH_RESOURCE_DIR", str(payload))
    return env


def run_smoke(exe_path: Path, payload: Path, timeout: float) -> int:
    completed = subprocess.run(
        [str(exe_path), "--toolhub-smoke"],
        cwd=payload,
        env=build_env(payload),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )
    if completed.stdout:
        print(completed.stdout, end="")
    if completed.stderr:
        print(completed.stderr, end="", file=sys.stderr)
    return completed.returncode


def launch_main_window(exe_path: Path, payload: Path, startup_wait_seconds: float) -> int:
    process = subprocess.Popen(
        [str(exe_path)],
        cwd=payload,
        env=build_env(payload),
        close_fds=True,
    )
    deadline = time.monotonic() + startup_wait_seconds
    while time.monotonic() < deadline:
        return_code = process.poll()
        if return_code is not None:
            print(
                f"PDF Workbench exited during ToolHub startup verification: {return_code}",
                file=sys.stderr,
            )
            return return_code or 1
        time.sleep(0.2)
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Launch PDF Workbench from ToolHub.")
    parser.add_argument("--toolhub-smoke", action="store_true")
    parser.add_argument("--window", choices=["main"], default="main")
    parser.add_argument(
        "--startup-wait-seconds",
        type=float,
        default=DEFAULT_STARTUP_WAIT_SECONDS,
    )
    parser.add_argument("--smoke-timeout-seconds", type=float, default=30.0)
    return parser.parse_args(argv)


def is_app_studio_startup_probe() -> bool:
    return (
        bool(os.environ.get("VIRTUAL_ENV"))
        and os.environ.get("PYTHONDONTWRITEBYTECODE") == "1"
        and not os.environ.get("TOOLHUB_APP_DIR")
        and not os.environ.get("TOOLHUB_SHARED_ENV_ID")
    )


def main(argv: list[str] | None = None) -> int:
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    args = parse_args(raw_argv)
    root = app_root()
    payload = payload_root(root)
    exe_path = resolve_exe(payload)

    if args.toolhub_smoke or (not raw_argv and is_app_studio_startup_probe()):
        return run_smoke(exe_path, payload, args.smoke_timeout_seconds)
    return launch_main_window(exe_path, payload, args.startup_wait_seconds)
