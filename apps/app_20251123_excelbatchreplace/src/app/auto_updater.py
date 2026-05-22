"""
Lightweight launcher-side updater for the ExcelBatchReplace binary.

Workflow:
- On launcher start, call `ensure_latest_binary` to compare the local binary
  version against the latest *stable* GitHub release.
- If the stable release is newer, download its Windows asset, replace the local
  binary under `app_bin/`, and write the release tag into `VERSION`.
- Afterward, use `launch_installed_binary` to start the freshly installed app.

Notes:
- Only non-pre-release GitHub releases are considered, so review/pre-release
  uploads will not trigger auto-update.
- Network errors fall back to the locally installed binary.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

# ========================
# Configurable parameters
# ========================

GITHUB_REPO = "kuroronrobins/ExcelBatchReplace"  # owner/repo
BINARY_NAME = "ExcelBatchReplace.exe"  # main app binary name
INSTALL_SUBDIR = "app_bin"  # where the binary is placed relative to this file
VERSION_FILENAME = "VERSION"
ASSET_KEYWORDS = ("win", "windows", "stable")  # used to pick the right asset
DOWNLOAD_TIMEOUT = 45  # seconds
USER_AGENT = "ExcelBatchReplace-Updater"
ALLOWED_DOWNLOAD_HOSTS = {"github.com"}


def _open_validated_url(req: urllib.request.Request, *, allowed_hosts: set[str], timeout: int):
    parsed = urlparse(req.full_url)
    if parsed.scheme != "https" or parsed.netloc.lower() not in allowed_hosts:
        raise ValueError("Unexpected update URL")
    return urllib.request.urlopen(req, timeout=timeout)  # nosec B310

# Env flags:
# - EBR_SKIP_UPDATE=1   -> skip network update, just run existing binary if any
# - EBR_ASSET_NAME=...  -> exact asset name to download (override)


@dataclass
class ReleaseInfo:
    version: str
    asset_name: str
    asset_url: str


class AutoUpdater:
    def __init__(self) -> None:
        # When frozen by PyInstaller, keep binaries next to the launcher exe.
        if getattr(sys, "frozen", False):
            base_dir = Path(sys.executable).resolve().parent
        else:
            base_dir = Path(__file__).resolve().parent

        self.install_dir = base_dir / INSTALL_SUBDIR
        self.install_dir.mkdir(parents=True, exist_ok=True)
        self.binary_path = self.install_dir / BINARY_NAME
        self.version_file = self.install_dir / VERSION_FILENAME
        self.asset_override = os.environ.get("EBR_ASSET_NAME")
        self.skip_update = os.environ.get("EBR_SKIP_UPDATE") == "1"

    # ===========
    # Versioning
    # ===========

    def get_local_version(self) -> str:
        if not self.version_file.exists():
            return "0.0.0"
        try:
            return self.version_file.read_text(encoding="utf-8").strip() or "0.0.0"
        except Exception:
            return "0.0.0"

    @staticmethod
    def _version_tuple(ver: str) -> tuple[int, ...]:
        parts: list[int] = []
        for token in ver.split("."):
            try:
                parts.append(int(token))
            except ValueError:
                break
        return tuple(parts) or (0,)

    # ===============
    # GitHub helpers
    # ===============

    def fetch_latest_release(self) -> Optional[ReleaseInfo]:
        """
        Fetch the latest *stable* GitHub release (pre-releases are ignored).
        """
        url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with _open_validated_url(req, allowed_hosts={"api.github.com"}, timeout=DOWNLOAD_TIMEOUT) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as e:
            print(f"[auto-update] Failed to contact GitHub: {e}")
            return None
        except Exception as e:
            print(f"[auto-update] Unexpected error while fetching release info: {e}")
            return None

        tag = (data.get("tag_name") or data.get("name") or "").strip()
        assets = data.get("assets") or []
        asset = self._select_asset(assets)
        if not tag or not asset:
            print("[auto-update] Latest release missing tag or downloadable asset.")
            return None

        return ReleaseInfo(version=tag, asset_name=asset["name"], asset_url=asset["browser_download_url"])

    def _select_asset(self, assets: Iterable[dict]) -> Optional[dict]:
        """
        Choose an asset that likely targets Windows. Override via env.
        """
        candidates: list[dict] = []
        for asset in assets:
            name = asset.get("name") or ""
            if self.asset_override and self.asset_override != name:
                continue
            candidates.append(asset)

        if self.asset_override:
            for asset in candidates:
                if asset.get("name") == self.asset_override:
                    return asset
            print(f"[auto-update] Asset override '{self.asset_override}' not found in release assets.")
            return None

        ranked: list[dict] = []
        for asset in candidates or assets:
            name = (asset.get("name") or "").lower()
            score = 0
            if name.endswith(".zip"):
                score += 2
            if name.endswith(".exe"):
                score += 1
            if any(keyword in name for keyword in ASSET_KEYWORDS):
                score += 3
            if score > 0:
                ranked.append((score, asset))

        if not ranked:
            return None

        ranked.sort(key=lambda x: x[0], reverse=True)
        return ranked[0][1]

    # =================
    # Download/install
    # =================

    def _download_asset(self, url: str) -> Optional[Path]:
        fd, tmp_path = tempfile.mkstemp(prefix="ebr_dl_", suffix=".bin")
        os.close(fd)
        tmp_file = Path(tmp_path)
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with _open_validated_url(req, allowed_hosts=ALLOWED_DOWNLOAD_HOSTS, timeout=DOWNLOAD_TIMEOUT) as resp, tmp_file.open(
                "wb"
            ) as out:
                shutil.copyfileobj(resp, out)
            return tmp_file
        except Exception as e:
            print(f"[auto-update] Download failed: {e}")
            tmp_file.unlink(missing_ok=True)
            return None

    def _extract_binary(self, package_path: Path) -> Optional[Path]:
        """
        Return a path to the binary inside the package.
        - If the package is an .exe, return itself.
        - If it's a .zip, extract to temp and search for the binary name.
        """
        if package_path.suffix.lower() == ".exe":
            return package_path

        if package_path.suffix.lower() != ".zip":
            print(f"[auto-update] Unsupported package format: {package_path.name}")
            return None

        temp_dir = Path(tempfile.mkdtemp(prefix="ebr_pkg_"))
        try:
            with zipfile.ZipFile(package_path, "r") as zf:
                zf.extractall(temp_dir)
        except Exception as e:
            print(f"[auto-update] Failed to extract archive: {e}")
            shutil.rmtree(temp_dir, ignore_errors=True)
            return None

        for path in temp_dir.rglob("*"):
            if path.is_file() and path.name.lower() == BINARY_NAME.lower():
                return path

        print("[auto-update] Extracted archive but could not find the expected binary.")
        shutil.rmtree(temp_dir, ignore_errors=True)
        return None

    def _install_binary(self, new_binary: Path, version: str) -> bool:
        try:
            self.install_dir.mkdir(parents=True, exist_ok=True)
            if self.binary_path.exists():
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                backup = self.binary_path.with_suffix(f".bak_{timestamp}")
                shutil.copy2(self.binary_path, backup)
            shutil.copy2(new_binary, self.binary_path)
            self.version_file.write_text(version, encoding="utf-8")
            return True
        except Exception as e:
            print(f"[auto-update] Failed to install binary: {e}")
            return False

    # =========
    # Public API
    # =========

    def ensure_latest_binary(self) -> Path:
        """
        Check and install the latest stable binary if newer.
        Returns the path to the installed binary (may be non-existent if download failed).
        """
        local_version = self.get_local_version()
        if self.skip_update:
            print("[auto-update] Skipping update because EBR_SKIP_UPDATE=1.")
            return self.binary_path

        release = self.fetch_latest_release()
        if not release:
            print("[auto-update] Using existing binary (no release info).")
            return self.binary_path

        if self._version_tuple(release.version) <= self._version_tuple(local_version):
            print(f"[auto-update] Already up to date (local {local_version}, remote {release.version}).")
            return self.binary_path

        print(f"[auto-update] Updating to {release.version} from {local_version} ...")
        package = self._download_asset(release.asset_url)
        if not package:
            return self.binary_path

        new_binary = self._extract_binary(package)
        if not new_binary:
            package.unlink(missing_ok=True)
            return self.binary_path

        if self._install_binary(new_binary, release.version):
            print(f"[auto-update] Installed version {release.version}.")
        else:
            print("[auto-update] Installation failed; keeping existing binary.")

        # Clean temp files; new_binary may live in a temp dir, so remove it after copy.
        try:
            if new_binary.exists() and new_binary.parent.name.startswith("ebr_pkg_"):
                shutil.rmtree(new_binary.parent, ignore_errors=True)
            package.unlink(missing_ok=True)
        except Exception:
            pass

        return self.binary_path

    def launch_installed_binary(self, args: Optional[list[str]] = None) -> bool:
        """
        Start the installed binary in a detached process.
        Returns True if launch was attempted.
        """
        if not self.binary_path.exists():
            print("[auto-update] No installed binary found to launch.")
            return False
        cmd = [str(self.binary_path)]
        if args:
            cmd.extend(args)
        try:
            subprocess.Popen(cmd, cwd=self.binary_path.parent)
            return True
        except Exception as e:
            print(f"[auto-update] Failed to launch binary: {e}")
            return False


def run_with_update(fallback_callable) -> None:
    """
    Convenience helper:
    - Ensure latest binary
    - Launch it if present
    - Fallback to callable (e.g., in-source app.main) when launch fails
    """
    updater = AutoUpdater()
    binary_path = updater.ensure_latest_binary()
    launched = updater.launch_installed_binary()
    if not launched and callable(fallback_callable):
        fallback_callable()


if __name__ == "__main__":
    # Manual test hook: run update then start python app if binary missing.
    from app.main import main as app_main

    run_with_update(app_main)
