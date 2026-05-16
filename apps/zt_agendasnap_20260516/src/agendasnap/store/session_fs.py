"""Session folder utilities."""
from __future__ import annotations

import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

import yaml


_SESSION_LOG_LOCK = threading.RLock()
_SESSION_LOG_HANDLERS: dict[Path, logging.FileHandler] = {}


def create_session(root: Path) -> Path:
    """Create a timestamped session directory."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    session_dir = root / ts
    session_dir.mkdir(parents=True, exist_ok=True)
    return session_dir


def setup_session_logging(session_dir: Path) -> Path:
    """Add a file handler so logs are persisted to session_dir/run.log."""
    log_path = (session_dir / "run.log").resolve()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.touch(exist_ok=True)

    root = logging.getLogger()
    with _SESSION_LOG_LOCK:
        tracked = _SESSION_LOG_HANDLERS.get(log_path)
        if tracked is not None and tracked in root.handlers:
            return log_path
        _SESSION_LOG_HANDLERS.pop(log_path, None)

        for handler in root.handlers:
            if isinstance(handler, logging.FileHandler):
                try:
                    if Path(handler.baseFilename).resolve() == log_path:
                        _SESSION_LOG_HANDLERS[log_path] = handler
                        return log_path
                except Exception:
                    continue

        handler = logging.FileHandler(log_path, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
        root.addHandler(handler)
        _SESSION_LOG_HANDLERS[log_path] = handler
    return log_path


def close_session_logging(session_dir: Path) -> None:
    """Remove and close the run.log handler for a session if it is active."""
    log_path = (session_dir / "run.log").resolve()
    root = logging.getLogger()
    with _SESSION_LOG_LOCK:
        handlers: list[logging.FileHandler] = []
        tracked = _SESSION_LOG_HANDLERS.pop(log_path, None)
        if tracked is not None:
            handlers.append(tracked)

        for handler in list(root.handlers):
            if not isinstance(handler, logging.FileHandler):
                continue
            try:
                if Path(handler.baseFilename).resolve() == log_path and handler not in handlers:
                    handlers.append(handler)
            except Exception:
                continue

        for handler in handlers:
            logging.getLogger(__name__).info("Session run.log handler closing: session=%s", session_dir.name)
            root.removeHandler(handler)
            handler.close()


def init_session_artifacts(session_dir: Path, cfg: Dict[str, Any]) -> None:
    """Ensure required session artifacts exist and snapshot config."""
    session_dir.mkdir(parents=True, exist_ok=True)

    # Required artifacts (touch if missing).
    (session_dir / "transcript.jsonl").touch(exist_ok=True)
    minutes_path = session_dir / "minutes.md"
    if not minutes_path.exists():
        minutes_path.write_text("# Minutes\n\n", encoding="utf-8")

    # Config snapshot (overwrite to reflect the current run).
    snapshot_path = session_dir / "config_snapshot.yaml"
    snapshot_path.write_text(
        yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def write_device_info(session_dir: Path, device_info: Dict[str, Any]) -> Path:
    """Write device info to session_dir/device_info.yaml."""
    path = session_dir / "device_info.yaml"
    path.write_text(
        yaml.safe_dump(device_info, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    return path
