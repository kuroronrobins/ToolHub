from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path
from typing import Iterable, Sequence


APP_DIR_NAME = "XCgate_AutoUpload"


def is_frozen() -> bool:
    return getattr(sys, "frozen", False) is True


def source_root(caller_file: str | os.PathLike[str]) -> Path:
    if is_frozen():
        if hasattr(sys, "_MEIPASS"):
            return Path(getattr(sys, "_MEIPASS")).resolve()
        return Path(sys.executable).resolve().parent
    return Path(caller_file).resolve().parent


def flows_root(caller_file: str | os.PathLike[str]) -> Path:
    return source_root(caller_file) / "xcgate_flows"


def user_data_root(entry_name: str | None = None) -> Path:
    override = os.environ.get("XCGATE_USER_DATA_DIR", "").strip()
    if override:
        root = Path(override)
    else:
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        if base:
            root = Path(base) / APP_DIR_NAME
        else:
            root = Path.home() / ".local" / "share" / APP_DIR_NAME

    if entry_name:
        root = root / entry_name
    return root.resolve()


def runtime_root(entry_name: str | None = None) -> Path:
    override = os.environ.get("XCGATE_RUNTIME_DIR", "").strip()
    if override:
        return Path(override).resolve()

    toolhub_app_id = os.environ.get("TOOLHUB_APP_ID", "").strip()
    if toolhub_app_id:
        return user_data_root(toolhub_app_id)

    return user_data_root(entry_name)


def ensure_resources(flows_dir: Path, flow_file: Path) -> bool:
    ok = True
    if not flows_dir.is_dir():
        print(f"[エラー] 実行ディレクトリが見つかりません: {flows_dir}")
        ok = False
    if not flow_file.is_file():
        print(f"[エラー] フロー定義ファイルが見つかりません: {flow_file}")
        ok = False
    return ok


def add_flow_import_path(flows_dir: Path) -> None:
    item = str(flows_dir)
    if item not in sys.path:
        sys.path.insert(0, item)


def flow_args(
    flows_dir: Path,
    flow_file: Path,
    *extra_args: str,
) -> list[str]:
    return [
        "--flow",
        str(flow_file),
        "--config",
        str((flows_dir / "config.yaml").resolve()),
        *extra_args,
    ]


def run_embedded_flow(
    *,
    program_name: str,
    flows_dir: Path,
    runtime_dir: Path,
    argv: Sequence[str],
) -> int:
    add_flow_import_path(flows_dir)
    cwd = Path.cwd()
    prev_runtime = os.environ.get("XCGATE_RUNTIME_DIR")
    prev_argv = sys.argv[:]

    try:
        runtime_dir.mkdir(parents=True, exist_ok=True)
        os.environ["XCGATE_RUNTIME_DIR"] = str(runtime_dir)
        os.chdir(str(runtime_dir))
        main_mod = importlib.import_module("src.main")
        sys.argv = [program_name, *argv]
        try:
            main_mod.main()  # type: ignore[attr-defined]
            return 0
        except SystemExit as exc:
            return int(exc.code) if isinstance(exc.code, int) else 1
    finally:
        sys.argv = prev_argv
        if prev_runtime is None:
            os.environ.pop("XCGATE_RUNTIME_DIR", None)
        else:
            os.environ["XCGATE_RUNTIME_DIR"] = prev_runtime
        os.chdir(str(cwd))


def run_toolhub_smoke(
    *,
    caller_file: str | os.PathLike[str],
    flow_files: Iterable[str],
) -> int:
    flows_dir = flows_root(caller_file)
    add_flow_import_path(flows_dir)

    checks: list[tuple[str, bool, str]] = []
    checks.append(("flows_dir", flows_dir.is_dir(), str(flows_dir)))
    config_path = flows_dir / "config.yaml"
    checks.append(("config", config_path.is_file(), str(config_path)))

    for flow_name in flow_files:
        path = flows_dir / "flows" / flow_name
        checks.append((f"flow:{flow_name}", path.is_file(), str(path)))

    try:
        import yaml  # noqa: F401
        checks.append(("import:yaml", True, "PyYAML"))
    except Exception as exc:
        checks.append(("import:yaml", False, repr(exc)))

    try:
        import playwright.sync_api  # noqa: F401
        checks.append(("import:playwright", True, "playwright.sync_api"))
    except Exception as exc:
        checks.append(("import:playwright", False, repr(exc)))

    try:
        importlib.import_module("src.main")
        checks.append(("import:src.main", True, "src.main"))
    except Exception as exc:
        checks.append(("import:src.main", False, repr(exc)))

    try:
        loader = importlib.import_module("src.io.config_loader")
        cfg = loader.load_config(str(config_path))
        checks.append(("load_config", isinstance(cfg, dict), str(config_path)))
    except Exception as exc:
        checks.append(("load_config", False, repr(exc)))

    try:
        parser = importlib.import_module("src.engine.parser")
        for flow_name in flow_files:
            path = flows_dir / "flows" / flow_name
            if path.is_file():
                parser.parse(path.read_text(encoding="utf-8"))
        checks.append(("parse_flows", True, ", ".join(flow_files)))
    except Exception as exc:
        checks.append(("parse_flows", False, repr(exc)))

    failed = False
    print("[SMOKE] ToolHub registration smoke check")
    for name, ok, detail in checks:
        status = "OK" if ok else "NG"
        print(f"[SMOKE][{status}] {name}: {detail}")
        failed = failed or not ok
    return 1 if failed else 0
