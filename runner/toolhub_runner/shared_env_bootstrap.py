from __future__ import annotations

import runpy
import site
import sys
from pathlib import Path


def find_site_packages(env_root: Path) -> Path:
    windows_site_packages = env_root / "Lib" / "site-packages"
    if windows_site_packages.is_dir():
        return windows_site_packages
    matches = sorted((env_root / "lib").glob("python*/site-packages"))
    if matches:
        return matches[0]
    return windows_site_packages


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) < 2:
        print("usage: shared_env_bootstrap.py <env-root> <entry> [args...]", file=sys.stderr)
        return 2

    env_root = Path(args[0]).resolve()
    entry = Path(args[1]).resolve()
    app_args = args[2:]

    site_packages = find_site_packages(env_root)
    if not site_packages.is_dir():
        print(f"shared env site-packages not found: {site_packages}", file=sys.stderr)
        return 103
    if not entry.is_file():
        print(f"entry file not found: {entry}", file=sys.stderr)
        return 104

    site.addsitedir(str(site_packages))
    sys.argv = [str(entry), *app_args]
    sys.path.insert(0, str(entry.parent))
    runpy.run_path(str(entry), run_name="__main__")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
