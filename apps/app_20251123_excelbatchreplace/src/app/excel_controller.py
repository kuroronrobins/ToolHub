"""
Excel COM controller.

Responsible for creating and managing the internal (hidden) Excel instance used
for template loading and target workbook operations. All COM interactions
should stay within this module to avoid threading/COM issues.
"""

import contextlib
import os
import shutil
import tempfile
from typing import Optional

import win32com.client  # type: ignore


class ExcelController:
    def __init__(self) -> None:
        self.app: Optional[object] = None

    def start(self) -> None:
        """Spin up a hidden Excel instance for batch operations."""
        if self.app is not None:
            return
        app = win32com.client.DispatchEx("Excel.Application")
        app.Visible = False
        app.DisplayAlerts = False
        # Reduce UI flicker and speed up bulk operations.
        app.ScreenUpdating = False
        app.EnableEvents = False
        try:
            app.Calculation = -4135  # xlCalculationManual
        except Exception:
            pass
        self.app = app

    def quit(self) -> None:
        """Quit and release the Excel instance."""
        if self.app is None:
            return
        with contextlib.suppress(Exception):
            self.app.Quit()
        self.app = None

    def open_workbook(self, path: str, read_only: bool = False):
        """Open a workbook via COM. Caller must close it."""
        if self.app is None:
            raise RuntimeError("Excel application not started")
        return self._open_with_reuse(path, read_only=read_only, allow_copy_on_fail=False)

    def open_template(self, path: str, read_only: bool = True):
        """Open template workbook (read-only by default)."""
        if self.app is None:
            raise RuntimeError("Excel application not started")
        return self._open_with_reuse(path, read_only=read_only, allow_copy_on_fail=True)

    # Internal helpers
    def _ensure_closed(self, path: str) -> None:
        """If a workbook with the same FullName is already open in this instance, close it."""
        if self.app is None:
            return
        target = os.path.abspath(path).lower()
        try:
            for wb in list(self.app.Workbooks):
                try:
                    if os.path.abspath(wb.FullName).lower() == target:
                        with contextlib.suppress(Exception):
                            wb.Close(SaveChanges=False)
                except Exception:
                    continue
        except Exception:
            pass

    def _open_with_reuse(self, path: str, read_only: bool, allow_copy_on_fail: bool):
        """Close existing same-path workbook then open, retrying once if needed."""
        if self.app is None:
            raise RuntimeError("Excel application not started")
        self._ensure_closed(path)
        try:
            return self.app.Workbooks.Open(
                path,
                ReadOnly=read_only,
                IgnoreReadOnlyRecommended=True,
                AddToMru=False,
                UpdateLinks=0,
            )
        except Exception:
            # one more attempt after forcing close
            self._ensure_closed(path)
            try:
                return self.app.Workbooks.Open(
                    path,
                    ReadOnly=read_only,
                    IgnoreReadOnlyRecommended=True,
                    AddToMru=False,
                    UpdateLinks=0,
                )
            except Exception as exc:
                if not allow_copy_on_fail:
                    raise
                # Fallback: copy to a temp file to avoid external locks, then open the copy.
                tmp_dir = tempfile.mkdtemp(prefix="excelbatch_tpl_")
                tmp_path = os.path.join(tmp_dir, os.path.basename(path))
                shutil.copy2(path, tmp_path)
                return self.app.Workbooks.Open(
                    tmp_path,
                    ReadOnly=True,
                    IgnoreReadOnlyRecommended=True,
                    AddToMru=False,
                    UpdateLinks=0,
                )
