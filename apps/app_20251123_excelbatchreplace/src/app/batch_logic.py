"""
Background batch logic.

Implements:
- Template parsing (sheet selection, base cell, range detection)
- Target workbook iteration
- Backup handling
- Copy/paste of values and/or formats (including column widths/row heights)
- Special rule: template cell with value SKIP_MARKER keeps target cell unchanged but may apply format
- Progress and logging callbacks for the UI
"""

import os
import re
import shutil
import threading
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, List, Optional, Tuple

from app.config import SKIP_MARKER, TEMPLATE_DEFAULT_SHEET, TEMPLATE_SETTINGS_SHEET
from app.excel_controller import ExcelController
from app.paths import setting_workbook_path

LogFunc = Callable[[str], None]
ProgressFunc = Callable[[int, int], None]  # current, total


@dataclass
class TemplateOption:
    path: str
    sheet_mode: str  # "AllFile" or "TemplateSheet"
    base_cell: str
    reflect_mode: str  # "value", "format", "both"
    row_adjust: int = 0
    use_regex: bool = False
    regex_pattern: str = ""
    sheet_name: str = TEMPLATE_DEFAULT_SHEET  # first sheet name (for display/use)


@dataclass
class TemplateData:
    option: TemplateOption
    workbook: object
    sheet: object
    target_sheet_name: Optional[str]  # None for AllFile, otherwise sheet name
    base_value: object
    bounds: Tuple[int, int, int, int]  # row_min, row_max, col_min, col_max


@dataclass
class JobConfig:
    targets: List[str]
    templates: List[TemplateOption]
    backup_enabled: bool
    backup_dir: Optional[str]
    fix_row_100: bool = False


class BatchWorker(threading.Thread):
    def __init__(
        self,
        job: JobConfig,
        log: LogFunc,
        progress: ProgressFunc,
        on_done: Callable[[bool, List[dict], datetime, datetime], None],
    ) -> None:
        super().__init__(daemon=True)
        self.job = job
        self.log = log
        self.progress = progress
        self.on_done = on_done
        self._cancel_requested = False
        self._pause_event = threading.Event()
        self._pause_event.set()
        self.excel = ExcelController()
        self.templates: List[TemplateData] = []
        self.results: List[dict] = []
        self._current_details: List[dict] = []
        self._adjust_template_loaded = False
        self._adjust_template_row = None
        self._adjust_template_wb = None
        self._backup_ts: Optional[str] = None
        self._backup_root_dir: Optional[str] = None
        self.started_at: datetime = datetime.now()

    def request_cancel(self) -> None:
        self._cancel_requested = True
        self._pause_event.set()

    def pause(self) -> None:
        self._pause_event.clear()

    def resume(self) -> None:
        self._pause_event.set()

    def run(self) -> None:
        success = False
        self.started_at = datetime.now()
        if self.job.backup_enabled and self.job.backup_dir:
            # 固定のタイムスタンプで1ジョブ内のバックアップ先を統一
            self._backup_ts = self.started_at.strftime("%Y%m%d_%H%M%S")
            self._backup_root_dir = os.path.join(self.job.backup_dir, self._backup_ts)
        try:
            self.excel.start()
            self._load_templates()
            self._process_targets()
            success = not self._cancel_requested
        except Exception as exc:  # noqa: BLE001
            self.log(f"[ERROR] {exc}")
        finally:
            self._close_templates()
            self._close_adjust_template()
            self.excel.quit()
            finished_at = datetime.now()
            self.on_done(success, self.results, self.started_at, finished_at)

    def _load_templates(self) -> None:
        for opt in self.job.templates:
            if not os.path.exists(opt.path):
                raise FileNotFoundError(f"テンプレートが見つかりません: {opt.path}")
            wb = self.excel.open_template(opt.path, read_only=True)
            sheet = self._pick_template_sheet(wb)
            actual_sheet_name = sheet.Name
            opt.sheet_name = actual_sheet_name
            target_sheet_name = None
            if opt.sheet_mode == "TemplateSheet" or actual_sheet_name != TEMPLATE_DEFAULT_SHEET:
                target_sheet_name = actual_sheet_name
            bounds = self._detect_bounds(sheet, opt.base_cell)
            base_value = sheet.Range(opt.base_cell).Value
            if base_value is None or base_value == "":
                raise ValueError(f"基準セルに値がありません: {opt.path} {opt.base_cell}")
            self.templates.append(
                TemplateData(
                    option=opt,
                    workbook=wb,
                    sheet=sheet,
                    target_sheet_name=target_sheet_name,
                    base_value=base_value,
                    bounds=bounds,
                )
            )
            self.log(
                f"[INFO] テンプレート読込: {opt.path} (シート: {actual_sheet_name}, "
                f"対象シート: {target_sheet_name or 'All'})"
            )

    def _close_templates(self) -> None:
        for t in self.templates:
            try:
                t.workbook.Close(SaveChanges=False)
            except Exception:
                pass
        self.templates.clear()

    def _close_adjust_template(self) -> None:
        if self._adjust_template_wb is not None:
            try:
                self._adjust_template_wb.Close(SaveChanges=False)
            except Exception:
                pass
            self._adjust_template_wb = None
        self._adjust_template_loaded = False
        self._adjust_template_row = None

    def _process_targets(self) -> None:
        total = len(self.job.targets)
        for idx, path in enumerate(self.job.targets, start=1):
            if self._cancel_requested:
                self.log("[INFO] Cancel requested. Stopping.")
                break
            self._pause_event.wait()
            self.log(f"[INFO] 処理開始: {path}")
            path_started = datetime.now()
            try:
                self._process_one(path)
                self.log(f"[INFO] 処理完了: {path}")
                self.results.append({
                    "path": path,
                    "status": "success",
                    "message": "",
                    "details": list(self._current_details),
                    "started_at": path_started.isoformat(),
                    "finished_at": datetime.now().isoformat(),
                })
            except Exception as exc:  # noqa: BLE001
                self.log(f"[ERROR] {path}: {exc}")
                self.results.append({
                    "path": path,
                    "status": "error",
                    "message": str(exc),
                    "details": list(self._current_details),
                    "started_at": path_started.isoformat(),
                    "finished_at": datetime.now().isoformat(),
                })
            self.progress(idx, total)

    def _process_one(self, path: str) -> None:
        if self.job.backup_enabled:
            self._backup_file(path)
        wb = self.excel.open_workbook(path, read_only=False)
        self._current_details = []
        try:
            for t in self.templates:
                if self._cancel_requested:
                    break
                self._pause_event.wait()
                self._apply_template_to_workbook(t, wb)
            if self.job.fix_row_100:
                self._apply_fix_row_rule(wb)
            wb.Save()
        finally:
            wb.Close(SaveChanges=False)

    def _backup_file(self, path: str) -> None:
        if not self.job.backup_dir:
            raise ValueError("バックアップ先が指定されていません。")
        dest_dir = self._backup_root_dir or self.job.backup_dir
        os.makedirs(dest_dir, exist_ok=True)
        base = os.path.basename(path)
        dest = os.path.join(dest_dir, base)
        shutil.copy2(path, dest)
        self.log(f"[INFO] バックアップ作成: {dest}")

    def _apply_template_to_workbook(self, template: TemplateData, wb: object) -> None:
        sheets = []
        if template.target_sheet_name:
            try:
                sheets.append(wb.Worksheets(template.target_sheet_name))
            except Exception:
                self.log(
                    f"[WARN] 対象シートなし: {os.path.basename(wb.FullName)} -> {template.target_sheet_name}"
                )
                return
        else:
            sheets = [wb.Worksheets(i) for i in range(1, wb.Worksheets.Count + 1)]
        for sheet in sheets:
            if self._cancel_requested:
                return
            self._pause_event.wait()
            matches = self._find_matches(sheet, template)
            if not matches:
                self.log(f"[INFO] シート {sheet.Name}: 一致セルなし")
                continue
            row_shift = 0
            for (match_row, match_col) in matches:
                if self._cancel_requested:
                    return
                self._pause_event.wait()
                try:
                    adj_row = match_row + row_shift
                    fmt_cnt, val_cnt, match_a1 = self._apply_once(template, sheet, adj_row, match_col)
                    row_min, row_max, col_min, col_max = template.bounds
                    cells_changed = (row_max - row_min + 1) * (col_max - col_min + 1)
                    self._current_details.append(
                        {
                            "sheet": sheet.Name,
                            "match_cell": match_a1,
                            "cells_changed": cells_changed,
                            "format_cells": fmt_cnt,
                            "value_cells": val_cnt,
                            "reflect": template.option.reflect_mode,
                            "template": os.path.basename(template.option.path),
                        }
                    )
                    row_shift += template.option.row_adjust
                except Exception as exc:  # noqa: BLE001
                    self.log(f"[WARN] シート {sheet.Name} の適用失敗 (行{match_row},列{match_col}): {exc}")


    def _apply_fix_row_rule(self, wb: object) -> None:
        # パターン: "*移動 名前:xxx"（B列で検索）
        pattern = re.compile(r"^\*\u79fb\u52d5 \u540d\u524d:.*$")
        for i in range(1, wb.Worksheets.Count + 1):
            sheet = wb.Worksheets(i)
            try:
                self._apply_fix_row_to_sheet(sheet, pattern)
            except Exception as exc:  # noqa: BLE001
                self.log(f"[WARN] 最終行の100行固定に失敗しました ({sheet.Name}): {exc}")

    def _load_adjust_template(self) -> None:
        if self._adjust_template_loaded:
            return
        path = str(setting_workbook_path())
        if not os.path.exists(path):
            raise FileNotFoundError(f"Setting.xlsx が見つかりません: {path}")
        wb = self.excel.open_template(path, read_only=True)
        try:
            sheet = wb.Worksheets("AdjustLine")
        except Exception as exc:  # noqa: BLE001
            wb.Close(SaveChanges=False)
            raise ValueError(f"Setting.xlsx に AdjustLine シートがありません: {exc}")
        used = sheet.UsedRange
        start_col = used.Column
        cols = used.Columns.Count
        rng = sheet.Range(sheet.Cells(1, start_col), sheet.Cells(1, start_col + cols - 1))
        values = self._to_matrix(rng.Value, rows=1, cols=cols)[0]
        formulas = self._to_matrix(rng.Formula, rows=1, cols=cols)[0]
        self._adjust_template_loaded = True
        self._adjust_template_wb = wb
        self._adjust_template_row = {
            "sheet": sheet,
            "range": rng,
            "start_col": start_col,
            "cols": cols,
            "values": values,
            "formulas": formulas,
        }

    def _apply_fix_row_to_sheet(self, sheet: object, pattern: re.Pattern[str]) -> None:
        used = sheet.UsedRange
        rows = used.Rows.Count
        start_row = used.Row
        end_row = start_row + rows - 1

        # B列を下から上へスキャン（UsedRange の開始列に依存しない）
        match_row_abs = None
        for r in range(end_row, start_row - 1, -1):
            val = sheet.Cells(r, 2).Value  # column B is absolute index 2
            if val is None:
                continue
            if pattern.match(str(val)):
                match_row_abs = r
                break
        if match_row_abs is None or match_row_abs == 100:
            return
        if not self._adjust_template_loaded:
            self._load_adjust_template()
        adjust = self._adjust_template_row
        if not adjust:
            return
        start_col_adj = adjust["start_col"]
        cols_count = adjust["cols"]
        formulas = adjust["formulas"] or []
        values_row = adjust["values"] or []
        if match_row_abs < 100:
            need = 100 - match_row_abs
            insert_at = max(1, match_row_abs - 1)  # one row above the matched row
            # 行全体を1行ずつ挿入し、確実に既存行を下へシフト
            for _ in range(need):
                sheet.Rows(insert_at).EntireRow.Insert(Shift=1)  # xlShiftDown = 1
                try:
                    sheet.Rows(insert_at).RowHeight = 0  # 非表示で挿入
                except Exception:
                    pass
            dest_range = sheet.Range(
                sheet.Cells(insert_at, start_col_adj),
                sheet.Cells(insert_at + need - 1, start_col_adj + cols_count - 1),
            )
            rows_to_write = []
            for _ in range(need):
                row_vals = []
                for idx in range(cols_count):
                    fval = formulas[idx] if idx < len(formulas) else None
                    vval = values_row[idx] if idx < len(values_row) else None
                    row_vals.append(fval if fval not in (None, "") else vval)
                rows_to_write.append(tuple(row_vals))
            dest_range.Value = tuple(rows_to_write)
            try:
                adjust["range"].Copy()
                dest_range.PasteSpecial(Paste=-4122)  # formats
            except Exception:
                pass
        else:
            remove = match_row_abs - 100
            # 100 行目より上は守る。行数を詰めるため 100 行目以降で削除し、マーカー行を 100 行目に移動させる
            # マーカー直上の行は削除しないよう、1行上に余裕を残して削除開始（例: マーカー行105なら 99 行目から）
            start_del = max(1, match_row_abs - remove - 1)
            for _ in range(remove):
                sheet.Rows(start_del).EntireRow.Delete(Shift=1)  # xlShiftUp = 1

    def _apply_once(self, template: TemplateData, sheet: object, match_row: int, match_col: int) -> Tuple[int, int, str]:
        row_min, row_max, col_min, col_max = template.bounds
        base_cell = template.sheet.Range(template.option.base_cell)
        t_base_row, t_base_col = base_cell.Row, base_cell.Column
        row_offset = row_min - t_base_row
        col_offset = col_min - t_base_col
        dest_row_min = match_row + row_offset
        dest_col_min = match_col + col_offset
        dest_row_max = dest_row_min + (row_max - row_min)
        dest_col_max = dest_col_min + (col_max - col_min)

        if dest_row_max > sheet.Rows.Count or dest_col_max > sheet.Columns.Count:
            self.log(
                f"[WARN] 貼り付け範囲がシート外のためスキップ: {sheet.Name} ({dest_row_max}, {dest_col_max})"
            )
            return 0, 0, self._rc_to_a1(match_row, match_col)

        if template.option.row_adjust != 0:
            delta = template.option.row_adjust
            if delta > 0:
                # Insert rows immediately below the matched (base) cell.
                insert_at = match_row + 1
                # Insert one-by-one to avoid Excel occasionally inserting only a single row for large Resize().
                for _ in range(delta):
                    sheet.Rows(insert_at).EntireRow.Insert(Shift=1)  # xlShiftDown = 1
            elif delta < 0:
                # delete rows bottom-up starting from the end of the target block
                delta_abs = abs(delta)
                start_del = max(1, dest_row_max - delta_abs + 1)
                end_del = dest_row_max
                count = end_del - start_del + 1
                for row_idx in range(end_del, start_del - 1, -1):
                    sheet.Rows(row_idx).EntireRow.Delete(Shift=1)
                removed_before_min = 0
                if start_del < dest_row_min:
                    removed_before_min = min(count, dest_row_min - start_del)
                dest_row_min = max(1, dest_row_min - removed_before_min)
                dest_row_max -= count
                if dest_row_max < dest_row_min:
                    return 0, 0, self._rc_to_a1(match_row, match_col)

        src_range = template.sheet.Range(
            template.sheet.Cells(row_min, col_min), template.sheet.Cells(row_max, col_max)
        )
        dest_range = sheet.Range(sheet.Cells(dest_row_min, dest_col_min), sheet.Cells(dest_row_max, dest_col_max))

        fmt_cells = 0
        val_cells = 0

        if template.option.reflect_mode in ("format", "both"):
            src_range.Copy()
            dest_range.PasteSpecial(Paste=-4122)  # Formats
            fmt_cells = (row_max - row_min + 1) * (col_max - col_min + 1)
            self._copy_dimensions(
                template.sheet,
                sheet,
                col_min,
                col_max,
                dest_col_min,
                dest_col_max,
                row_min,
                row_max,
                dest_row_min,
                dest_row_max,
            )

        if template.option.reflect_mode in ("value", "both"):
            val_cells = self._copy_values_with_skip(src_range, dest_range)

        if self.excel.app:
            self.excel.app.CutCopyMode = False
        return fmt_cells, val_cells, self._rc_to_a1(match_row, match_col)

    def _copy_dimensions(
        self,
        src_sheet: object,
        dest_sheet: object,
        src_col_min: int,
        src_col_max: int,
        dest_col_min: int,
        dest_col_max: int,
        src_row_min: int,
        src_row_max: int,
        dest_row_min: int,
        dest_row_max: int,
    ) -> None:
        # Column widths
        for src_col, dest_col in zip(range(src_col_min, src_col_max + 1), range(dest_col_min, dest_col_max + 1)):
            try:
                width = src_sheet.Columns(src_col).ColumnWidth
                dest_sheet.Columns(dest_col).ColumnWidth = width
            except Exception:
                pass
        # Row heights
        for src_row, dest_row in zip(range(src_row_min, src_row_max + 1), range(dest_row_min, dest_row_max + 1)):
            try:
                height = src_sheet.Rows(src_row).RowHeight
                dest_sheet.Rows(dest_row).RowHeight = height
            except Exception:
                pass

    def _copy_values_with_skip(self, src_range: object, dest_range: object) -> int:
        src_vals = src_range.Value
        src_formulas = src_range.Formula
        dest_vals = dest_range.Value
        dest_formulas = dest_range.Formula
        src_matrix = self._to_matrix(src_vals)
        if not src_matrix or not src_matrix[0]:
            return 0
        rows = len(src_matrix)
        cols = len(src_matrix[0])
        src_formula_matrix = self._to_matrix(src_formulas, rows=rows, cols=cols)
        dest_matrix = self._to_matrix(dest_vals, rows=len(src_matrix), cols=len(src_matrix[0]))
        dest_formula_matrix = self._to_matrix(dest_formulas, rows=rows, cols=cols)
        dest_value_matrix = self._to_matrix(dest_vals, rows=rows, cols=cols)
        changed = 0
        for r in range(rows):
            for c in range(cols):
                src_val = src_matrix[r][c]
                if src_val == SKIP_MARKER:
                    if dest_formula_matrix and dest_formula_matrix[r][c] not in (None, ""):
                        dest_matrix[r][c] = dest_formula_matrix[r][c]
                    else:
                        dest_matrix[r][c] = dest_value_matrix[r][c] if dest_value_matrix else None
                    continue  # keep destination content as-is
                formula_val = src_formula_matrix[r][c] if src_formula_matrix else None
                if formula_val not in (None, ""):
                    dest_matrix[r][c] = formula_val
                else:
                    dest_matrix[r][c] = src_val
                changed += 1
        dest_range.Value = tuple(tuple(row) for row in dest_matrix)
        return changed

    def _rc_to_a1(self, row: int, col: int) -> str:
        letters = ""
        n = col
        while n > 0:
            n, rem = divmod(n - 1, 26)
            letters = chr(65 + rem) + letters
        return f"{letters}{row}"

    def _to_matrix(self, value_obj: object, rows: Optional[int] = None, cols: Optional[int] = None) -> List[List[object]]:
        # Excel may return scalar or tuple of tuples
        if rows is None or cols is None:
            if not isinstance(value_obj, tuple):
                return [[value_obj]]
            rows = len(value_obj)
            if rows == 0:
                return [[]]
            first_row = value_obj[0]
            cols = len(first_row) if isinstance(first_row, tuple) else 1
        matrix: List[List[object]] = [[None for _ in range(cols)] for _ in range(rows)]
        if not isinstance(value_obj, tuple):
            matrix[0][0] = value_obj
            return matrix
        for r in range(min(rows, len(value_obj))):
            row_val = value_obj[r]
            if not isinstance(row_val, tuple):
                matrix[r][0] = row_val
                continue
            for c in range(min(cols, len(row_val))):
                matrix[r][c] = row_val[c]
        return matrix

    def _adjust_rows(self, sheet: object, start_row: int, delta: int) -> None:
        if delta > 0:
            sheet.Rows(start_row).Resize(delta).Insert(Shift=1)  # xlShiftDown = 1
        elif delta < 0:
            count = min(abs(delta), sheet.Rows.Count - start_row + 1)
            sheet.Rows(start_row).Resize(count).Delete(Shift=1)

    def _find_matches(self, sheet: object, template: TemplateData) -> List[Tuple[int, int]]:
        used = sheet.UsedRange
        values = used.Value
        start_row = used.Row
        start_col = used.Column
        matches: List[Tuple[int, int]] = []
        matrix = self._to_matrix(values)
        if template.option.use_regex:
            pattern = template.option.regex_pattern or ""
            try:
                regex = re.compile(pattern)
            except re.error as exc:  # noqa: BLE001
                raise ValueError(f"正規表現が不正です: {pattern} ({exc})")
        else:
            regex = None
            base_value = template.base_value

        for r, row in enumerate(matrix):
            if self._cancel_requested:
                return []
            self._pause_event.wait()
            for c, val in enumerate(row):
                if regex:
                    if val is None:
                        continue
                    if regex.search(str(val)):
                        matches.append((start_row + r, start_col + c))
                else:
                    if val == base_value:
                        matches.append((start_row + r, start_col + c))
        return matches

    def _detect_bounds(self, sheet: object, base_cell_addr: str) -> Tuple[int, int, int, int]:
        used = sheet.UsedRange
        start_row = used.Row
        start_col = used.Column
        rows = used.Rows.Count
        cols = used.Columns.Count
        row_min = None
        row_max = None
        col_min = None
        col_max = None
        for r in range(rows):
            for c in range(cols):
                cell = used.Cells(r + 1, c + 1)
                if self._cell_has_content_or_format(cell):
                    abs_row = start_row + r
                    abs_col = start_col + c
                    row_min = abs_row if row_min is None else min(row_min, abs_row)
                    row_max = abs_row if row_max is None else max(row_max, abs_row)
                    col_min = abs_col if col_min is None else min(col_min, abs_col)
                    col_max = abs_col if col_max is None else max(col_max, abs_col)
        base_cell = sheet.Range(base_cell_addr)
        base_row, base_col = base_cell.Row, base_cell.Column
        if row_min is None or col_min is None:
            row_min = row_max = base_row
            col_min = col_max = base_col
        else:
            row_min = min(row_min, base_row)
            row_max = max(row_max, base_row)
            col_min = min(col_min, base_col)
            col_max = max(col_max, base_col)
        return row_min, row_max, col_min, col_max

    def _cell_has_content_or_format(self, cell: object) -> bool:
        try:
            val = cell.Value
            if val not in (None, ""):
                return True
        except Exception:
            pass
        try:
            if cell.HasFormula:
                return True
        except Exception:
            pass
        try:
            if cell.MergeCells:
                return True
        except Exception:
            pass
        try:
            if cell.Interior.ColorIndex not in (None, -4142):  # not None/NoFill
                return True
        except Exception:
            pass
        try:
            if cell.Font.Bold or cell.Font.Italic:
                return True
            if cell.Font.ColorIndex not in (None, -4105):
                return True
        except Exception:
            pass
        try:
            if cell.Borders.LineStyle not in (None, 0):
                return True
        except Exception:
            pass
        return False

    def _pick_template_sheet(self, wb: object) -> object:
        # Prefer first sheet that is not the settings sheet
        for i in range(1, wb.Worksheets.Count + 1):
            sh = wb.Worksheets(i)
            if sh.Name != TEMPLATE_SETTINGS_SHEET:
                return sh
        return wb.Worksheets(1)
