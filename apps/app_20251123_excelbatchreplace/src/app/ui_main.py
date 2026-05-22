#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Tkinter UI for Excel batch replace tool.

Features:
- Manage target files and templates (filename + path display)
- In-app template option cache (no writes to Excel files)
- Backup settings
- Save/Load full settings via menu
- Background execution with progress/log and HTML summary
"""

import json
import os
import queue
import re
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any, Dict, List, Optional

from app.batch_logic import BatchWorker, JobConfig, TemplateOption
from app.config import (
    APP_LAST_UPDATED,
    APP_LICENSE_HOLDER,
    APP_TITLE,
    APP_VERSION,
    DEFAULT_BACKUP_SUBDIR,
    SKIP_MARKER,
    TEMPLATE_DEFAULT_SHEET,
)
from app.paths import default_file_dialog_dir, user_cache_dir, user_data_root, user_templates_dir
from app.settings_store import SettingsStore


class MainApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(APP_TITLE)
        self.settings_store = SettingsStore()
        self.app_version = APP_VERSION
        self.last_updated = APP_LAST_UPDATED
        self.app_license_holder = APP_LICENSE_HOLDER

        self.targets: List[str] = []
        self.templates: List[TemplateOption] = []
        self.worker: Optional[BatchWorker] = None
        self.msg_queue: queue.Queue = queue.Queue()
        self.selected_tpl_index: Optional[int] = None
        self._suppress_editor_events = False
        self.var_target_count = tk.StringVar(value="選択: 0 / 登録: 0")

        self.var_tpl_base_cell = tk.StringVar()
        self.var_tpl_reflect = tk.StringVar(value="both")
        self.var_tpl_sheet_mode = tk.StringVar(value="AllFile")
        self.var_tpl_row_adjust = tk.StringVar(value="0")
        self.var_tpl_sheet_name = tk.StringVar(value=TEMPLATE_DEFAULT_SHEET)
        self.var_tpl_use_regex = tk.BooleanVar(value=False)
        self.var_tpl_regex_pattern = tk.StringVar(value="")
        self.var_tpl_path = tk.StringVar(value="")
        self.var_tpl_filename = tk.StringVar(value="")
        self.var_fix_row_100 = tk.BooleanVar(value=False)
        self._paused = False
        self.last_dirs: Dict[str, str] = {}

        self._load_last_dirs()
        self._setup_ui()
        self._bind_template_editor_events()
        self._update_target_counts()
        self.root.after(100, self._poll_queue)

    def _load_last_dirs(self) -> None:
        data = self.settings_store._read_json()
        prefs = data.get("prefs", {})
        default_dir = str(default_file_dialog_dir())
        default_backup_dir = str(user_data_root() / DEFAULT_BACKUP_SUBDIR)
        self.last_dirs = {
            "target_dir": prefs.get("target_dir", default_dir),
            "template_dir": prefs.get("template_dir", default_dir),
            "backup_dir": prefs.get("backup_dir", default_backup_dir),
            "settings_dir": prefs.get("settings_dir", self.settings_store.base_dir),
        }

    def _update_last_dir(self, key: str, value: str) -> None:
        self.last_dirs[key] = value
        data = self.settings_store._read_json()
        prefs = data.get("prefs", {})
        prefs[key] = value
        data["prefs"] = prefs
        self.settings_store._write_json(data)

    # UI construction
    def _setup_ui(self) -> None:
        # Menu bar
        menu_bar = tk.Menu(self.root)
        file_menu = tk.Menu(menu_bar, tearoff=0)
        file_menu.add_command(label="設定を保存...", command=self.save_app_settings)
        file_menu.add_command(label="設定を読み込み...", command=self.load_app_settings)
        file_menu.add_separator()
        file_menu.add_command(label="終了", command=self.root.quit)
        menu_bar.add_cascade(label="ファイル", menu=file_menu)
        help_menu = tk.Menu(menu_bar, tearoff=0)
        help_menu.add_command(label="バージョン情報", command=self.show_version_info)
        menu_bar.add_cascade(label="ヘルプ", menu=help_menu)
        self.root.config(menu=menu_bar)

        # Target files frame
        frm_files = ttk.LabelFrame(self.root, text="対象ファイル")
        frm_files.grid(row=0, column=0, padx=8, pady=8, sticky="nsew")
        self.lst_targets = tk.Listbox(frm_files, width=90, height=9, selectmode="extended")
        scroll_targets = ttk.Scrollbar(frm_files, orient="vertical", command=self.lst_targets.yview)
        self.lst_targets.configure(yscrollcommand=scroll_targets.set)
        self.lst_targets.grid(row=0, column=0, columnspan=4, sticky="nsew")
        scroll_targets.grid(row=0, column=4, sticky="ns")
        frm_files.columnconfigure(0, weight=1)
        frm_files.columnconfigure(1, weight=0)
        frm_files.columnconfigure(2, weight=0)
        frm_files.columnconfigure(3, weight=0)
        frm_files.columnconfigure(4, weight=0)
        ttk.Button(frm_files, text="対象ファイル追加...", command=self.add_targets).grid(
            row=1, column=0, padx=4, pady=4, sticky="w"
        )
        ttk.Label(frm_files, textvariable=self.var_target_count, foreground="#444").grid(
            row=1, column=1, padx=4, pady=4, sticky="w"
        )
        ttk.Button(frm_files, text="選択削除", command=self.remove_selected_targets).grid(
            row=1, column=2, padx=4, pady=4, sticky="w"
        )
        ttk.Button(frm_files, text="Excelで開く", command=self.open_target_in_excel).grid(
            row=1, column=3, padx=4, pady=4, sticky="w"
        )
        ttk.Button(frm_files, text="全削除", command=self.clear_targets).grid(
            row=1, column=4, padx=4, pady=4, sticky="w"
        )
        self.lst_targets.bind("<<ListboxSelect>>", lambda e: self._update_target_counts())

        # Templates frame
        frm_tpl = ttk.LabelFrame(self.root, text="テンプレート")
        frm_tpl.grid(row=1, column=0, padx=8, pady=8, sticky="nsew")
        cols = ("filename", "sheet_mode", "sheet_name", "base_cell", "reflect_mode", "row_adjust", "path")
        self.tpl_tree = ttk.Treeview(frm_tpl, columns=cols, show="headings", height=6)
        headings = {
            "filename": "ファイル名",
            "sheet_mode": "シートモード",
            "sheet_name": "シート名",
            "base_cell": "基準セル",
            "reflect_mode": "反映",
            "row_adjust": "行数調整",
            "path": "パス",
        }
        for col in cols:
            self.tpl_tree.heading(col, text=headings[col])
            width = 220 if col == "path" else 120
            self.tpl_tree.column(col, width=width)
        scroll_tpl = ttk.Scrollbar(frm_tpl, orient="vertical", command=self.tpl_tree.yview)
        self.tpl_tree.configure(yscrollcommand=scroll_tpl.set)
        self.tpl_tree.grid(row=0, column=0, columnspan=5, sticky="nsew")
        scroll_tpl.grid(row=0, column=5, sticky="ns")
        self.tpl_tree.bind("<<TreeviewSelect>>", self.on_tpl_select)
        ttk.Button(frm_tpl, text="新規テンプレート作成", command=self.create_template).grid(
            row=1, column=0, padx=4, pady=4, sticky="w"
        )
        ttk.Button(frm_tpl, text="既存テンプレート追加", command=self.add_template_file).grid(
            row=1, column=1, padx=4, pady=4, sticky="w"
        )
        ttk.Button(frm_tpl, text="Excelで開く", command=self.open_template_in_excel).grid(
            row=1, column=2, padx=4, pady=4, sticky="w"
        )
        ttk.Button(frm_tpl, text="削除", command=self.remove_template).grid(row=1, column=3, padx=4, pady=4, sticky="w")

        # Inline editor for selected template
        editor = ttk.Frame(frm_tpl, padding=6)
        editor.grid(row=2, column=0, columnspan=5, sticky="nsew")
        ttk.Label(editor, text="選択テンプレート").grid(row=0, column=0, sticky="w")
        ttk.Label(editor, textvariable=self.var_tpl_filename, foreground="#004080").grid(row=0, column=1, sticky="w")
        ttk.Label(editor, textvariable=self.var_tpl_path, wraplength=600, foreground="#004080").grid(
            row=0, column=2, columnspan=3, sticky="w"
        )

        # First row: base cell and reflect
        ttk.Label(editor, text="基準セル").grid(row=1, column=0, sticky="w", pady=2)
        ttk.Entry(editor, textvariable=self.var_tpl_base_cell, width=10).grid(row=1, column=1, sticky="w", padx=(0, 8))
        ttk.Label(editor, text=f'"{SKIP_MARKER}" でセル内容を保持', foreground="#555").grid(
            row=1, column=2, columnspan=2, sticky="w"
        )

        ttk.Label(editor, text="反映種別").grid(row=2, column=0, sticky="e", pady=2)
        ttk.Radiobutton(editor, text="値", variable=self.var_tpl_reflect, value="value").grid(row=2, column=1, sticky="w")
        ttk.Radiobutton(editor, text="書式", variable=self.var_tpl_reflect, value="format").grid(
            row=2, column=2, sticky="w"
        )
        ttk.Radiobutton(editor, text="値と書式", variable=self.var_tpl_reflect, value="both").grid(
            row=2, column=3, sticky="w"
        )

        # Second row: sheet mode and sheet name
        ttk.Label(editor, text="シートモード").grid(row=3, column=0, sticky="w", pady=2)
        ttk.Radiobutton(editor, text="AllFile (全シート)", variable=self.var_tpl_sheet_mode, value="AllFile").grid(
            row=3, column=1, sticky="w"
        )
        ttk.Radiobutton(
            editor,
            text="シート名固定",
            variable=self.var_tpl_sheet_mode,
            value="TemplateSheet",
        ).grid(row=3, column=2, sticky="w")
        ttk.Label(editor, text="シート名:").grid(row=3, column=3, sticky="e")
        ttk.Label(editor, textvariable=self.var_tpl_sheet_name, foreground="#444").grid(
            row=3, column=4, sticky="w"
        )
        ttk.Button(editor, text="再読込", command=self.refresh_template_sheet_name).grid(
            row=3, column=5, padx=(6, 0), sticky="w"
        )

        # Third row: row adjust
        ttk.Label(editor, text="行数調整 (+挿入 / -削除)").grid(row=4, column=0, sticky="w", pady=2)
        ttk.Spinbox(editor, textvariable=self.var_tpl_row_adjust, from_=-999, to=999, increment=1, width=8, justify="right").grid(row=4, column=1, sticky="w")

        # Regex option
        ttk.Checkbutton(editor, text="正規表現で検索", variable=self.var_tpl_use_regex, command=self._update_regex_state).grid(
            row=5, column=0, sticky="w", pady=2
        )
        ttk.Label(editor, text="パターン:").grid(row=5, column=1, sticky="e")
        self.ent_tpl_regex = ttk.Entry(editor, textvariable=self.var_tpl_regex_pattern, width=70)
        self.ent_tpl_regex.grid(row=5, column=2, columnspan=3, sticky="we")
        self._update_regex_state()

        frm_backup = ttk.LabelFrame(self.root, text="バックアップ")
        frm_backup.grid(row=2, column=0, padx=8, pady=8, sticky="nsew")
        self.var_backup = tk.BooleanVar(value=True)
        ttk.Checkbutton(frm_backup, text="バックアップを実施", variable=self.var_backup).grid(
            row=0, column=0, sticky="w"
        )
        default_backup_dir = self.last_dirs.get("backup_dir") or str(user_data_root() / DEFAULT_BACKUP_SUBDIR)
        self.var_backup_dir = tk.StringVar(value=default_backup_dir)
        ttk.Entry(frm_backup, textvariable=self.var_backup_dir, width=60).grid(
            row=0, column=1, padx=4, pady=4, sticky="w"
        )
        ttk.Button(frm_backup, text="参照...", command=self.choose_backup_dir).grid(
            row=0, column=2, padx=4, pady=4, sticky="w"
        )

        # Progress and control
        frm_run = ttk.LabelFrame(self.root, text="実行")
        frm_run.grid(row=3, column=0, padx=8, pady=8, sticky="nsew")
        ttk.Button(frm_run, text="開始", command=self.start_batch).grid(
            row=0, column=0, padx=4, pady=4, sticky="w"
        )
        self.btn_pause = ttk.Button(frm_run, text="一時停止", command=self.pause_resume, state="disabled")
        self.btn_pause.grid(row=0, column=1, padx=4, pady=4, sticky="w")
        self.btn_cancel = ttk.Button(frm_run, text="中止", command=self.cancel_batch, state="disabled")
        self.btn_cancel.grid(row=0, column=2, padx=4, pady=4, sticky="w")
        self.progress = ttk.Progressbar(frm_run, length=300, mode="determinate")
        self.progress.grid(row=0, column=3, padx=4, pady=4, sticky="w")
        self.lbl_status = ttk.Label(frm_run, text="待機中")
        self.lbl_status.grid(row=0, column=4, padx=4, pady=4, sticky="w")
        ttk.Checkbutton(
            frm_run,
            text="最終行を100に固定（全シート）",
            variable=self.var_fix_row_100,
        ).grid(row=1, column=0, padx=4, pady=(0, 4), sticky="w")

        # Log area
        frm_log = ttk.LabelFrame(self.root, text="ログ")
        frm_log.grid(row=4, column=0, padx=8, pady=8, sticky="nsew")
        self.txt_log = tk.Text(frm_log, width=100, height=10, state="disabled")
        self.txt_log.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(frm_log, command=self.txt_log.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.txt_log["yscrollcommand"] = scroll.set

        for i in range(5):
            self.root.grid_rowconfigure(i, weight=0)
        self.root.grid_columnconfigure(0, weight=1)

    def _bind_template_editor_events(self) -> None:
        for var in (
            self.var_tpl_base_cell,
            self.var_tpl_reflect,
            self.var_tpl_sheet_mode,
            self.var_tpl_row_adjust,
            self.var_tpl_use_regex,
            self.var_tpl_regex_pattern,
        ):
            var.trace_add("write", lambda *args: self._auto_apply_template())

    def _update_regex_state(self) -> None:
        state = "normal" if self.var_tpl_use_regex.get() else "disabled"
        try:
            self.ent_tpl_regex.configure(state=state)
        except Exception:
            pass

    def _update_target_counts(self) -> None:
        total = len(self.targets)
        selected = len(self.lst_targets.curselection())
        self.var_target_count.set(f"選択: {selected} / 登録: {total}")

    def show_version_info(self) -> None:
        info = (
            f"{APP_TITLE}\n"
            f"バージョン: {self.app_version}\n"
            f"最終更新日: {self.last_updated}\n"
            f"ライセンス保有: {self.app_license_holder}"
        )
        messagebox.showinfo("バージョン情報", info)

    def refresh_template_sheet_name(self) -> None:
        """Reload the sheet name from the template file and reflect it in the UI/store."""
        if self.selected_tpl_index is None:
            messagebox.showwarning("警告", "テンプレートを選択してください")
            return
        opt = self.templates[self.selected_tpl_index]
        path = opt.path
        if not os.path.exists(path):
            messagebox.showwarning("警告", f"テンプレートファイルが見つかりません: {path}")
            return
        try:
            new_sheet = self._get_first_sheet_name(path)
        except Exception as exc:  # noqa: BLE001
            messagebox.showwarning("警告", f"シート名の取得に失敗しました: {exc}")
            return
        if new_sheet == opt.sheet_name:
            messagebox.showinfo("情報", "シート名に変更はありません。")
            return
        opt.sheet_name = new_sheet
        self.var_tpl_sheet_name.set(new_sheet)
        self.settings_store.remember_template_option(opt)
        self._update_tpl_tree_row(self.selected_tpl_index)
        self.log(f"[INFO] テンプレートのシート名を更新しました: {new_sheet}")

    # Target files handlers
    def add_targets(self) -> None:
        initial = self.last_dirs.get("target_dir") or str(default_file_dialog_dir())
        paths = filedialog.askopenfilenames(
            filetypes=[("Excel files", "*.xls *.xlsx *.xlsm")],
            initialdir=initial,
        )
        for p in paths:
            if p not in self.targets:
                self.targets.append(p)
                self.lst_targets.insert(tk.END, p)
        if paths:
            self._update_last_dir("target_dir", os.path.dirname(paths[0]))
        self._update_target_counts()

    def remove_selected_targets(self) -> None:
        sel = list(self.lst_targets.curselection())
        for idx in reversed(sel):
            self.targets.pop(idx)
            self.lst_targets.delete(idx)
        self._update_target_counts()

    def clear_targets(self) -> None:
        self.targets.clear()
        self.lst_targets.delete(0, tk.END)
        self._update_target_counts()

    def open_target_in_excel(self) -> None:
        sel = self.lst_targets.curselection()
        if not sel:
            messagebox.showwarning("警告", "対象ファイルを選択してください")
            return
        for idx in sel:
            path = self.targets[idx]
            try:
                os.startfile(path)
            except Exception as exc:  # noqa: BLE001
                messagebox.showwarning("警告", f"Excelを起動できませんでした: {exc}")
                break

    # Template helpers
    def _get_first_sheet_name(self, path: str) -> str:
        import win32com.client  # type: ignore

        excel = win32com.client.DispatchEx("Excel.Application")
        excel.Visible = False
        excel.DisplayAlerts = False
        try:
            wb = excel.Workbooks.Open(path, ReadOnly=True)
            names = []
            for i in range(1, wb.Worksheets.Count + 1):
                names.append(wb.Worksheets(i).Name)
            name = names[0] if names else wb.Worksheets(1).Name
            wb.Close(SaveChanges=False)
        finally:
            excel.Quit()
        return name

    def create_template(self) -> None:
        base_dir = str(user_templates_dir())
        os.makedirs(base_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(base_dir, f"template_{timestamp}.xlsx")
        self._create_empty_template(path)
        option = TemplateOption(
            path=path,
            sheet_mode="AllFile",
            base_cell="A1",
            reflect_mode="both",
            row_adjust=0,
            use_regex=False,
            regex_pattern="",
            sheet_name=TEMPLATE_DEFAULT_SHEET,
        )
        self.templates.append(option)
        self.settings_store.remember_template_option(option)
        self._refresh_tpl_tree(select_index=len(self.templates) - 1)
        try:
            os.startfile(path)
        except Exception:
            messagebox.showwarning("警告", f"Excelを起動できませんでした: {path}")

    def add_template_file(self) -> None:
        initial = self.last_dirs.get("template_dir") or str(default_file_dialog_dir())
        paths = filedialog.askopenfilenames(
            filetypes=[("Excel Template", "*.xlsx")],
            initialdir=initial,
        )
        last_dir = None
        added_index = None
        for path in paths:
            if any(opt.path == path for opt in self.templates):
                continue
            stored = self.settings_store.get_template_option(path)
            if stored:
                option = stored
            else:
                first_sheet = self._get_first_sheet_name(path)
                sheet_mode = "AllFile" if first_sheet == TEMPLATE_DEFAULT_SHEET else "TemplateSheet"
                option = TemplateOption(
                    path=path,
                    sheet_mode=sheet_mode,
                    base_cell="A1",
                    reflect_mode="both",
                    row_adjust=0,
                    use_regex=False,
                    regex_pattern="",
                    sheet_name=first_sheet,
                )
            self.templates.append(option)
            self.settings_store.remember_template_option(option)
            added_index = len(self.templates) - 1
            last_dir = os.path.dirname(path)
        if paths:
            if last_dir:
                self._update_last_dir("template_dir", last_dir)
            self._refresh_tpl_tree(select_index=added_index if added_index is not None else None)

    def remove_template(self) -> None:
        sel = self.tpl_tree.selection()
        if not sel:
            return
        index = self.tpl_tree.index(sel[0])
        self.templates.pop(index)
        self._refresh_tpl_tree()
        self.on_tpl_select()

    def _refresh_tpl_tree(self, select_index: Optional[int] = None) -> None:
        for i in self.tpl_tree.get_children():
            self.tpl_tree.delete(i)
        for opt in self.templates:
            self.tpl_tree.insert(
                "",
                tk.END,
                values=(
                    os.path.basename(opt.path),
                    opt.sheet_mode,
                    opt.sheet_name,
                    opt.base_cell,
                    opt.reflect_mode,
                    opt.row_adjust,
                    opt.path,
                ),
            )
        if select_index is not None and 0 <= select_index < len(self.templates):
            item = self.tpl_tree.get_children()[select_index]
            self.tpl_tree.selection_set(item)
            self.tpl_tree.focus(item)
            self.on_tpl_select()

    def _create_empty_template(self, path: str) -> None:
        abs_path = os.path.abspath(path)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        try:
            from openpyxl import Workbook  # type: ignore

            wb = Workbook()
            ws = wb.active
            ws.title = TEMPLATE_DEFAULT_SHEET
            wb.save(abs_path)
        except Exception:
            # Fallback to COM if openpyxl is unavailable
            import win32com.client  # type: ignore

            excel = win32com.client.DispatchEx("Excel.Application")
            excel.Visible = False
            excel.DisplayAlerts = False
            try:
                wb = excel.Workbooks.Add()
                sheet = wb.Worksheets(1)
                sheet.Name = TEMPLATE_DEFAULT_SHEET
                wb.SaveAs(abs_path)
                wb.Close(SaveChanges=False)
            finally:
                excel.Quit()

    # Backup chooser
    def choose_backup_dir(self) -> None:
        initial = self.last_dirs.get("backup_dir") or self.var_backup_dir.get() or str(
            user_data_root() / DEFAULT_BACKUP_SUBDIR
        )
        d = filedialog.askdirectory(initialdir=initial)
        if d:
            self.var_backup_dir.set(d)
            self._update_last_dir("backup_dir", d)

    # Logging helpers
    def log(self, msg: str) -> None:
        self.txt_log.configure(state="normal")
        self.txt_log.insert(tk.END, msg + "\n")
        self.txt_log.see(tk.END)
        self.txt_log.configure(state="disabled")

    def _validate_templates(self) -> bool:
        for opt in self.templates:
            if not re.match(r"^[A-Za-z]+[1-9][0-9]*$", opt.base_cell):
                messagebox.showwarning("入力エラー", f"基準セルが不正です: {opt.base_cell}")
                return False
            if opt.reflect_mode not in ("value", "format", "both"):
                messagebox.showwarning("入力エラー", f"反映種別が不正です: {opt.reflect_mode}")
                return False
            if opt.sheet_mode not in ("AllFile", "TemplateSheet"):
                messagebox.showwarning("入力エラー", f"シートモードが不正です: {opt.sheet_mode}")
                return False
        return True

    # Batch start
    def start_batch(self) -> None:
        if self.worker and self.worker.is_alive():
            messagebox.showinfo("確認", "処理中です。完了をお待ちください。")
            return
        if not self.targets:
            messagebox.showwarning("警告", "対象ファイルを追加してください")
            return
        if not self.templates:
            messagebox.showwarning("警告", "テンプレートを追加してください")
            return
        if self.var_backup.get() and not self.var_backup_dir.get().strip():
            messagebox.showwarning("警告", "バックアップフォルダを指定してください")
            return
        self._auto_apply_template()
        if not self._validate_templates():
            return

        backup_dir = self.var_backup_dir.get().strip() if self.var_backup.get() else None
        if backup_dir:
            os.makedirs(backup_dir, exist_ok=True)
        job = JobConfig(
            targets=list(self.targets),
            templates=list(self.templates),
            backup_enabled=self.var_backup.get(),
            backup_dir=backup_dir,
            fix_row_100=self.var_fix_row_100.get(),
        )
        self.progress["maximum"] = len(job.targets)
        self.progress["value"] = 0
        self.lbl_status.config(text="処理中")
        self.log("[INFO] 置換処理を開始しました")
        self.btn_pause.config(state="normal", text="一時停止")
        self.btn_cancel.config(state="normal")
        self._paused = False

        def enqueue_log(msg: str) -> None:
            self.msg_queue.put(("log", msg))

        def enqueue_progress(cur: int, total: int) -> None:
            self.msg_queue.put(("progress", cur, total))

        def enqueue_done(success: bool, results: list, started_at: datetime, finished_at: datetime) -> None:
            self.msg_queue.put(("done", success, results, started_at, finished_at))

        self.worker = BatchWorker(
            job=job,
            log=enqueue_log,
            progress=enqueue_progress,
            on_done=enqueue_done,
        )
        self.worker.start()

    def pause_resume(self) -> None:
        if not self.worker:
            return
        if self._paused:
            self.worker.resume()
            self._paused = False
            self.btn_pause.config(text="一時停止")
            self.lbl_status.config(text="処理中")
            self.log("[INFO] 一時停止を解除しました")
        else:
            self.worker.pause()
            self._paused = True
            self.btn_pause.config(text="再開")
            self.lbl_status.config(text="一時停止中")
            self.log("[INFO] 一時停止しました")

    def cancel_batch(self) -> None:
        if self.worker:
            self.worker.request_cancel()
            self.log("[INFO] 中止要求を送信しました")
        self.btn_pause.config(state="disabled", text="一時停止")
        self.btn_cancel.config(state="disabled")

    def _poll_queue(self) -> None:
        try:
            while True:
                item = self.msg_queue.get_nowait()
                kind = item[0]
                if kind == "log":
                    self.log(item[1])
                elif kind == "progress":
                    _, cur, total = item
                    self.progress["value"] = cur
                    self.lbl_status.config(text=f"{cur}/{total}")
                elif kind == "done":
                    _, success, results, started_at, finished_at = item
                    self.log("[INFO] 完了しました" if success else "[WARN] 一部エラーで終了しました")
                    self.lbl_status.config(text="完了" if success else "エラー")
                    self.progress["value"] = 0
                    self.worker = None
                    self.btn_pause.config(state="disabled", text="一時停止")
                    self.btn_cancel.config(state="disabled")
                    self._paused = False
                    try:
                        self._show_summary(results, started_at, finished_at)
                    except Exception as exc:  # noqa: BLE001
                        self.log(f"[WARN] サマリー表示に失敗: {exc}")
        except queue.Empty:
            pass
        self.root.after(150, self._poll_queue)

    def _show_summary(self, results: list[dict], started_at, finished_at) -> None:
        html = self._build_summary_html(results, started_at, finished_at)
        summary_dir = user_cache_dir()
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = summary_dir / f"summary_{ts}.html"
        with path.open("w", encoding="utf-8") as fp:
            fp.write(html)
        self.log(f"[INFO] サマリーを保存しました: {path}")
        try:
            os.startfile(str(path))
        except Exception:
            pass

    # Template selection handling and editor
    def on_tpl_select(self, event: Optional[tk.Event] = None) -> None:  # noqa: ARG002
        sel = self.tpl_tree.selection()
        if not sel:
            self.selected_tpl_index = None
            self.var_tpl_path.set("")
            self.var_tpl_filename.set("")
            self.var_tpl_base_cell.set("")
            self.var_tpl_reflect.set("both")
            self.var_tpl_sheet_mode.set("AllFile")
            self.var_tpl_row_adjust.set("0")
            self.var_tpl_sheet_name.set(TEMPLATE_DEFAULT_SHEET)
            self.var_tpl_use_regex.set(False)
            self.var_tpl_regex_pattern.set("")
            return
        index = self.tpl_tree.index(sel[0])
        self.selected_tpl_index = index
        opt = self.templates[index]
        self._suppress_editor_events = True
        try:
            self.var_tpl_path.set(opt.path)
            self.var_tpl_filename.set(os.path.basename(opt.path))
            self.var_tpl_base_cell.set(opt.base_cell)
            self.var_tpl_reflect.set(opt.reflect_mode)
            self.var_tpl_sheet_mode.set(opt.sheet_mode)
            self.var_tpl_row_adjust.set(str(opt.row_adjust))
            self.var_tpl_sheet_name.set(opt.sheet_name)
            self.var_tpl_use_regex.set(getattr(opt, "use_regex", False))
            self.var_tpl_regex_pattern.set(getattr(opt, "regex_pattern", ""))
        finally:
            self._suppress_editor_events = False
        self._update_regex_state()

    def _auto_apply_template(self) -> None:
        if self._suppress_editor_events or self.selected_tpl_index is None:
            return
        base_cell = self.var_tpl_base_cell.get().strip().upper()
        reflect = self.var_tpl_reflect.get()
        sheet_mode = self.var_tpl_sheet_mode.get()
        row_adjust_raw = self.var_tpl_row_adjust.get().strip()
        try:
            row_adjust = int(row_adjust_raw or "0")
        except ValueError:
            return
        if not re.match(r"^[A-Za-z]+[1-9][0-9]*$", base_cell):
            return
        if reflect not in ("value", "format", "both"):
            return
        if sheet_mode not in ("AllFile", "TemplateSheet"):
            return
        use_regex = bool(self.var_tpl_use_regex.get())
        regex_pattern = self.var_tpl_regex_pattern.get()
        if use_regex:
            try:
                re.compile(regex_pattern)
            except re.error:
                return
        opt = self.templates[self.selected_tpl_index]
        opt.base_cell = base_cell
        opt.reflect_mode = reflect
        opt.sheet_mode = sheet_mode
        opt.row_adjust = row_adjust
        opt.use_regex = use_regex
        opt.regex_pattern = regex_pattern
        self.settings_store.remember_template_option(opt)
        self._update_tpl_tree_row(self.selected_tpl_index)

    def _update_tpl_tree_row(self, index: int) -> None:
        items = self.tpl_tree.get_children()
        if not (0 <= index < len(items)):
            return
        opt = self.templates[index]
        self.tpl_tree.item(
            items[index],
            values=(
                os.path.basename(opt.path),
                opt.sheet_mode,
                opt.sheet_name,
                opt.base_cell,
                opt.reflect_mode,
                opt.row_adjust,
                opt.path,
            ),
        )

    def open_template_in_excel(self) -> None:
        if self.selected_tpl_index is None:
            messagebox.showwarning("警告", "テンプレートを選択してください")
            return
        path = self.templates[self.selected_tpl_index].path
        try:
            os.startfile(path)
        except Exception as exc:  # noqa: BLE001
            messagebox.showwarning("警告", f"Excelを起動できませんでした: {exc}")

    # Settings save/load
    def save_app_settings(self) -> None:
        initial = self.last_dirs.get("settings_dir") or self.settings_store.base_dir
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON", "*.json")], initialdir=initial)
        if not path:
            return
        state = {
            "targets": list(self.targets),
            "templates": [opt.__dict__ for opt in self.templates],
            "backup": {"enabled": self.var_backup.get(), "dir": self.var_backup_dir.get()},
        }
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as fp:
            json.dump(state, fp, ensure_ascii=False, indent=2)
        self._update_last_dir("settings_dir", os.path.dirname(path))
        messagebox.showinfo("完了", f"設定を保存しました: {path}")

    def load_app_settings(self) -> None:
        initial = self.last_dirs.get("settings_dir") or self.settings_store.base_dir
        path = filedialog.askopenfilename(filetypes=[("JSON", "*.json")], initialdir=initial)
        if not path:
            return
        try:
            state = json.loads(Path(path).read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            messagebox.showwarning("警告", f"設定ファイルの読み込みに失敗しました: {exc}")
            return
        self._update_last_dir("settings_dir", os.path.dirname(path))
        self.targets = state.get("targets", [])
        self.lst_targets.delete(0, tk.END)
        for p in self.targets:
            self.lst_targets.insert(tk.END, p)
        self._update_target_counts()
        self.templates = []
        for opt_data in state.get("templates", []):
            try:
                opt = TemplateOption(**opt_data)
            except Exception:
                continue
            self.templates.append(opt)
            self.settings_store.remember_template_option(opt)
        backup = state.get("backup", {})
        self.var_backup.set(bool(backup.get("enabled", True)))
        if "dir" in backup:
            self.var_backup_dir.set(backup.get("dir", self.var_backup_dir.get()))
        self._refresh_tpl_tree(select_index=0 if self.templates else None)
        self.on_tpl_select()

    # Summary helpers
    def _build_summary_html(self, results: list[dict], started_at: datetime, finished_at: datetime) -> str:
        total = len(results)
        success_count = sum(1 for r in results if r.get("status") == "success")
        error_count = sum(1 for r in results if r.get("status") == "error")
        duration = finished_at - started_at
        rows_html = ""
        detail_html = ""
        has_message = any(r.get("message") for r in results)

        for idx, r in enumerate(results, start=1):
            cls = r.get("status", "")
            fname = os.path.basename(r.get("path", ""))
            full_path = os.path.abspath(r.get("path", ""))
            msg = r.get("message", "") or "-"
            rid = f"detail_{idx}"
            link = full_path.replace('\\', '/')
            msg_col = f"<td>{msg}</td>" if has_message else ""
            rows_html += (
                f"<tr class='{cls}'>"
                f"<td>{fname}</td>"
                f"<td>{r.get('status')}</td>"
                f"{msg_col}"
                f"<td><button class='link' onclick=\"openLocal('{link}')\">開く</button></td>"
                f"<td><button class='link' onclick=\"toggle('{rid}')\">詳細</button></td>"
                "</tr>"
            )
            details_by_sheet: dict[str, list[dict]] = {}
            for d in r.get("details") or []:
                sheet = d.get("sheet") or "(無名シート)"
                details_by_sheet.setdefault(sheet, []).append(d)

            if details_by_sheet:
                sheet_blocks = ""
                for s_idx, (sheet_name, matches) in enumerate(details_by_sheet.items(), start=1):
                    sid = f"{rid}_sheet_{s_idx}"
                    match_rows = "".join(
                        f"<tr>"
                        f"<td>{m.get('match_cell','')}</td>"
                        f"<td>{m.get('value_cells','')}</td>"
                        f"<td>{m.get('format_cells','')}</td>"
                        f"<td>{m.get('reflect','')}</td>"
                        f"<td>{m.get('template','')}</td>"
                        "</tr>"
                        for m in matches
                    )
                    sheet_blocks += (
                        f"<div class='sheet'>"
                        f"<button class='sheet-toggle' onclick=\"toggle('{sid}')\">{sheet_name}（{len(matches)}件）</button>"
                        f"<div id='{sid}' class='detail' style='display:none;'>"
                        f"<table class='detail-table'>"
                        f"<thead><tr><th>一致セル</th><th>値置換セル数</th><th>書式置換セル数</th><th>反映</th><th>テンプレート</th></tr></thead>"
                        f"<tbody>{match_rows}</tbody>"
                        f"</table>"
                        f"</div>"
                        f"</div>"
                    )

                detail_html += (
                    f"<div id='{rid}' class='detail-card'>"
                    f"<div class='detail-title'>{fname} の詳細</div>"
                    f"{sheet_blocks}"
                    f"</div>"
                )
            else:
                detail_html += (
                    f"<div id='{rid}' class='detail-card'><div class='detail-title'>{fname} の詳細</div>"
                    f"<p class='muted'>一致データはありません。</p></div>"
                )
        msg_header = "<th>メッセージ</th>" if has_message else ""
        msg_class = "has-msg" if has_message else ""
        return f"""<!DOCTYPE html>
<html lang='ja'>
<head>
<meta charset='utf-8'>
<title>Excel一括置換 結果</title>
<style>
body{{font-family:'Segoe UI','Meiryo',sans-serif;background:#f7f9fb;color:#1f2933;padding:24px;}}
.cards{{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:12px;}}
.card{{background:#fff;border-radius:10px;padding:12px 14px;box-shadow:0 4px 12px rgba(0,0,0,0.08);border-left:6px solid #2563eb;}}
.card.success{{border-color:#16a34a;}}
.card.error{{border-color:#dc2626;}}
.muted{{color:#4b5563;font-size:12px;}}
table{{width:100%;border-collapse:collapse;background:#fff;box-shadow:0 4px 12px rgba(0,0,0,0.08);}}
th,td{{padding:10px 12px;border-bottom:1px solid #e5e7eb;text-align:left;}}
th{{background:#eef2ff;}}
tr.success td{{color:#166534;}}
tr.error td{{color:#b91c1c;}}
.link{{background:none;border:none;color:#2563eb;cursor:pointer;text-decoration:underline;padding:0;}}
.detail-card{{display:none;margin:12px 0 18px 0;background:#fff;border-radius:10px;padding:10px 12px;box-shadow:0 4px 12px rgba(0,0,0,0.08);}}
.detail-title{{font-weight:bold;margin:4px 0 8px 0;}}
.sheet{{margin-bottom:8px;}}
.sheet-toggle{{background:#f1f5f9;border:1px solid #e2e8f0;border-radius:6px;padding:6px 10px;cursor:pointer;font-weight:600;}}
.detail{{margin-top:6px;}}
.detail-table{{width:100%;border-collapse:collapse;}}
.detail-table th,.detail-table td{{padding:6px 8px;border-bottom:1px solid #e5e7eb;text-align:left;}}
.has-msg td:nth-child(3){{width:30%;}}
</style>
<script>
function openLocal(path) {{
  const url = 'ms-excel:ofe|u|file:///' + encodeURI(path);
  window.location.href = url;
}}
function toggle(id) {{
  const el = document.getElementById(id);
  if (!el) return;
  el.style.display = (el.style.display === 'block') ? 'none' : 'block';
}}
</script>
</head>
<body>
<h2>Excel一括置換 結果</h2>
<div class='cards'>
  <div class='card total'>対象: {total}</div>
  <div class='card success'>成功: {success_count}</div>
  <div class='card error'>失敗: {error_count}</div>
</div>
<p class='muted'>開始: {started_at.strftime('%Y-%m-%d %H:%M:%S')}　終了: {finished_at.strftime('%Y-%m-%d %H:%M:%S')}　経過: {duration}</p>
<table class='{msg_class}'>
  <thead><tr><th>ファイル</th><th>結果</th>{msg_header}<th>開く</th><th>詳細</th></tr></thead>
  <tbody>{rows_html}</tbody>
</table>
{detail_html}
<p class='muted'>テンプレート保持マーカー: "{SKIP_MARKER}" のセルは元の値や式を保持します。</p>
</body>
</html>"""

    def _show_summary(self, results: list[dict], started_at, finished_at) -> None:
        html = self._build_summary_html(results, started_at, finished_at)
        summary_dir = user_cache_dir()
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = summary_dir / f"summary_{ts}.html"
        with path.open("w", encoding="utf-8") as fp:
            fp.write(html)
        self.log(f"[INFO] サマリーを保存しました: {path}")
        try:
            os.startfile(str(path))
        except Exception:
            pass

    # Template selection handling and editor
    def on_tpl_select(self, event: Optional[tk.Event] = None) -> None:  # noqa: ARG002
        sel = self.tpl_tree.selection()
        if not sel:
            self.selected_tpl_index = None
            self.var_tpl_path.set("")
            self.var_tpl_filename.set("")
            self.var_tpl_base_cell.set("")
            self.var_tpl_reflect.set("both")
            self.var_tpl_sheet_mode.set("AllFile")
            self.var_tpl_row_adjust.set("0")
            self.var_tpl_sheet_name.set(TEMPLATE_DEFAULT_SHEET)
            self.var_tpl_use_regex.set(False)
            self.var_tpl_regex_pattern.set("")
            return
        index = self.tpl_tree.index(sel[0])
        self.selected_tpl_index = index
        opt = self.templates[index]
        self._suppress_editor_events = True
        try:
            self.var_tpl_path.set(opt.path)
            self.var_tpl_filename.set(os.path.basename(opt.path))
            self.var_tpl_base_cell.set(opt.base_cell)
            self.var_tpl_reflect.set(opt.reflect_mode)
            self.var_tpl_sheet_mode.set(opt.sheet_mode)
            self.var_tpl_row_adjust.set(str(opt.row_adjust))
            self.var_tpl_sheet_name.set(opt.sheet_name)
            self.var_tpl_use_regex.set(getattr(opt, "use_regex", False))
            self.var_tpl_regex_pattern.set(getattr(opt, "regex_pattern", ""))
        finally:
            self._suppress_editor_events = False
        self._update_regex_state()

    def _auto_apply_template(self) -> None:
        if self._suppress_editor_events or self.selected_tpl_index is None:
            return
        base_cell = self.var_tpl_base_cell.get().strip().upper()
        reflect = self.var_tpl_reflect.get()
        sheet_mode = self.var_tpl_sheet_mode.get()
        row_adjust_raw = self.var_tpl_row_adjust.get().strip()
        try:
            row_adjust = int(row_adjust_raw or "0")
        except ValueError:
            return
        if not re.match(r"^[A-Za-z]+[1-9][0-9]*$", base_cell):
            return
        if reflect not in ("value", "format", "both"):
            return
        if sheet_mode not in ("AllFile", "TemplateSheet"):
            return
        use_regex = bool(self.var_tpl_use_regex.get())
        regex_pattern = self.var_tpl_regex_pattern.get()
        if use_regex:
            try:
                re.compile(regex_pattern)
            except re.error:
                return
        opt = self.templates[self.selected_tpl_index]
        opt.base_cell = base_cell
        opt.reflect_mode = reflect
        opt.sheet_mode = sheet_mode
        opt.row_adjust = row_adjust
        opt.use_regex = use_regex
        opt.regex_pattern = regex_pattern
        self.settings_store.remember_template_option(opt)
        self._update_tpl_tree_row(self.selected_tpl_index)

    def _update_tpl_tree_row(self, index: int) -> None:
        items = self.tpl_tree.get_children()
        if not (0 <= index < len(items)):
            return
        opt = self.templates[index]
        self.tpl_tree.item(
            items[index],
            values=(
                os.path.basename(opt.path),
                opt.sheet_mode,
                opt.sheet_name,
                opt.base_cell,
                opt.reflect_mode,
                opt.row_adjust,
                opt.path,
            ),
        )

    def open_template_in_excel(self) -> None:
        if self.selected_tpl_index is None:
            messagebox.showwarning("警告", "テンプレートを選択してください")
            return
        path = self.templates[self.selected_tpl_index].path
        try:
            os.startfile(path)
        except Exception as exc:  # noqa: BLE001
            messagebox.showwarning("警告", f"Excelを起動できませんでした: {exc}")

    # Settings save/load
    def save_app_settings(self) -> None:
        initial = self.last_dirs.get("settings_dir") or self.settings_store.base_dir
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON", "*.json")], initialdir=initial)
        if not path:
            return
        state = {
            "targets": list(self.targets),
            "templates": [opt.__dict__ for opt in self.templates],
            "backup": {"enabled": self.var_backup.get(), "dir": self.var_backup_dir.get()},
        }
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as fp:
            json.dump(state, fp, ensure_ascii=False, indent=2)
        self._update_last_dir("settings_dir", os.path.dirname(path))
        messagebox.showinfo("完了", f"設定を保存しました: {path}")

    def load_app_settings(self) -> None:
        initial = self.last_dirs.get("settings_dir") or self.settings_store.base_dir
        path = filedialog.askopenfilename(filetypes=[("JSON", "*.json")], initialdir=initial)
        if not path:
            return
        try:
            state = json.loads(Path(path).read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            messagebox.showwarning("警告", f"設定ファイルの読み込みに失敗しました: {exc}")
            return
        self._update_last_dir("settings_dir", os.path.dirname(path))
        self.targets = state.get("targets", [])
        self.lst_targets.delete(0, tk.END)
        for p in self.targets:
            self.lst_targets.insert(tk.END, p)
        self.templates = []
        for opt_data in state.get("templates", []):
            try:
                opt = TemplateOption(**opt_data)
            except Exception:
                continue
            self.templates.append(opt)
            self.settings_store.remember_template_option(opt)
        backup = state.get("backup", {})
        self.var_backup.set(bool(backup.get("enabled", True)))
        if "dir" in backup:
            self.var_backup_dir.set(backup.get("dir", self.var_backup_dir.get()))
        self._refresh_tpl_tree(select_index=0 if self.templates else None)
        self.on_tpl_select()

    # Summary helpers
    def _build_summary_html(self, results: list[dict], started_at: datetime, finished_at: datetime) -> str:
        total = len(results)
        success_count = sum(1 for r in results if r.get("status") == "success")
        error_count = sum(1 for r in results if r.get("status") == "error")
        duration = finished_at - started_at
        rows_html = ""
        detail_html = ""
        has_message = any(r.get("message") for r in results)

        for idx, r in enumerate(results, start=1):
            cls = r.get("status", "")
            fname = os.path.basename(r.get("path", ""))
            full_path = os.path.abspath(r.get("path", ""))
            msg = r.get("message", "") or "-"
            rid = f"detail_{idx}"
            link = full_path.replace('\\', '/')
            msg_col = f"<td>{msg}</td>" if has_message else ""
            rows_html += (
                f"<tr class='{cls}'>"
                f"<td>{fname}</td>"
                f"<td>{r.get('status')}</td>"
                f"{msg_col}"
                f"<td><button class='link' onclick=\"openLocal('{link}')\">開く</button></td>"
                f"<td><button class='link' onclick=\"toggle('{rid}')\">詳細</button></td>"
                "</tr>"
            )
            details_by_sheet: dict[str, list[dict]] = {}
            for d in r.get("details") or []:
                sheet = d.get("sheet") or "(無名シート)"
                details_by_sheet.setdefault(sheet, []).append(d)

            if details_by_sheet:
                sheet_blocks = ""
                for s_idx, (sheet_name, matches) in enumerate(details_by_sheet.items(), start=1):
                    sid = f"{rid}_sheet_{s_idx}"
                    match_rows = "".join(
                        f"<tr>"
                        f"<td>{m.get('match_cell','')}</td>"
                        f"<td>{m.get('value_cells','')}</td>"
                        f"<td>{m.get('format_cells','')}</td>"
                        f"<td>{m.get('reflect','')}</td>"
                        f"<td>{m.get('template','')}</td>"
                        "</tr>"
                        for m in matches
                    )
                    sheet_blocks += (
                        f"<div class='sheet'>"
                        f"<button class='sheet-toggle' onclick=\"toggle('{sid}')\">{sheet_name}（{len(matches)}件）</button>"
                        f"<div id='{sid}' class='detail' style='display:none;'>"
                        f"<table class='detail-table'>"
                        f"<thead><tr><th>一致セル</th><th>値置換セル数</th><th>書式置換セル数</th><th>反映</th><th>テンプレート</th></tr></thead>"
                        f"<tbody>{match_rows}</tbody>"
                        f"</table>"
                        f"</div>"
                        f"</div>"
                    )

                detail_html += (
                    f"<div id='{rid}' class='detail-card'>"
                    f"<div class='detail-title'>{fname} の詳細</div>"
                    f"{sheet_blocks}"
                    f"</div>"
                )
            else:
                detail_html += (
                    f"<div id='{rid}' class='detail-card'><div class='detail-title'>{fname} の詳細</div>"
                    f"<p class='muted'>一致データはありません。</p></div>"
                )
        msg_header = "<th>メッセージ</th>" if has_message else ""
        msg_class = "has-msg" if has_message else ""
        return f"""<!DOCTYPE html>
<html lang='ja'>
<head>
<meta charset='utf-8'>
<title>Excel一括置換 結果</title>
<style>
body{{font-family:'Segoe UI','Meiryo',sans-serif;background:#f7f9fb;color:#1f2933;padding:24px;}}
.cards{{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:12px;}}
.card{{background:#fff;border-radius:10px;padding:12px 14px;box-shadow:0 4px 12px rgba(0,0,0,0.08);border-left:6px solid #2563eb;}}
.card.success{{border-color:#16a34a;}}
.card.error{{border-color:#dc2626;}}
.muted{{color:#4b5563;font-size:12px;}}
table{{width:100%;border-collapse:collapse;background:#fff;box-shadow:0 4px 12px rgba(0,0,0,0.08);}}
th,td{{padding:10px 12px;border-bottom:1px solid #e5e7eb;text-align:left;}}
th{{background:#eef2ff;}}
tr.success td{{color:#166534;}}
tr.error td{{color:#b91c1c;}}
.link{{background:none;border:none;color:#2563eb;cursor:pointer;text-decoration:underline;padding:0;}}
.detail-card{{display:none;margin:12px 0 18px 0;background:#fff;border-radius:10px;padding:10px 12px;box-shadow:0 4px 12px rgba(0,0,0,0.08);}}
.detail-title{{font-weight:bold;margin:4px 0 8px 0;}}
.sheet{{margin-bottom:8px;}}
.sheet-toggle{{background:#f1f5f9;border:1px solid #e2e8f0;border-radius:6px;padding:6px 10px;cursor:pointer;font-weight:600;}}
.detail{{margin-top:6px;}}
.detail-table{{width:100%;border-collapse:collapse;}}
.detail-table th,.detail-table td{{padding:6px 8px;border-bottom:1px solid #e5e7eb;text-align:left;}}
.has-msg td:nth-child(3){{width:30%;}}
</style>
<script>
function openLocal(path) {{
  const url = 'ms-excel:ofe|u|file:///' + encodeURI(path);
  window.location.href = url;
}}
function toggle(id) {{
  const el = document.getElementById(id);
  if (!el) return;
  el.style.display = (el.style.display === 'block') ? 'none' : 'block';
}}
</script>
</head>
<body>
<h2>Excel一括置換 結果</h2>
<div class='cards'>
  <div class='card total'>対象: {total}</div>
  <div class='card success'>成功: {success_count}</div>
  <div class='card error'>失敗: {error_count}</div>
</div>
<p class='muted'>開始: {started_at.strftime('%Y-%m-%d %H:%M:%S')}　終了: {finished_at.strftime('%Y-%m-%d %H:%M:%S')}　経過: {duration}</p>
<table class='{msg_class}'>
  <thead><tr><th>ファイル</th><th>結果</th>{msg_header}<th>開く</th><th>詳細</th></tr></thead>
  <tbody>{rows_html}</tbody>
</table>
{detail_html}
<p class='muted'>テンプレート保持マーカー: "{SKIP_MARKER}" のセルは元の値や式を保持します。</p>
</body>
</html>"""
