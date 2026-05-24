#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import csv
import html as _html
import os
import webbrowser
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional


Row = Dict[str, str]


@dataclass(frozen=True)
class SummaryProfile:
    title: str
    total_label: str
    success_heading: str
    failure_heading: str
    empty_message: str
    success_headers: list[str]
    failure_headers: list[str]
    success_cells: Callable[[Row], list[str]]
    failure_cells: Callable[[Row], list[str]]
    show_download_dirs: bool = False


def _parse_ts(s: str | None) -> Optional[datetime]:
    if not s:
        return None
    text = str(s).strip()
    try:
        return datetime.fromisoformat(text)
    except Exception:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt)
        except Exception:
            continue
    return None


def _load_rows_since(csv_path: str, since: datetime) -> List[Row]:
    rows: List[Row] = []
    if not csv_path or not os.path.exists(csv_path):
        return rows
    try:
        with open(csv_path, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                ts = _parse_ts(row.get("timestamp"))
                if ts is None or ts >= since:
                    rows.append({k: str(v or "") for k, v in row.items()})
    except Exception:
        return []
    return rows


def _abs(path: str) -> str:
    try:
        return os.path.abspath(path)
    except Exception:
        return path


def _esc(value) -> str:
    return _html.escape(str(value or ""))


def _file_link(path: str, label: str | None = None) -> str:
    if not path:
        return ""
    abs_path = _abs(path)
    text = label or abs_path
    try:
        return f'<a href="{Path(abs_path).resolve().as_uri()}">{_esc(text)}</a>'
    except Exception:
        return f"<code>{_esc(text)}</code>"


def _split_doc_revision(row: Row) -> tuple[str, str]:
    doc_id = row.get("document_id") or ""
    revision = row.get("revision") or ""
    name = row.get("file") or ""
    if (not doc_id or not revision) and "-Rev" in name:
        left, right = name.rsplit("-Rev", 1)
        doc_id = doc_id or left
        revision = revision or right
    return doc_id or name, revision


def _timestamp(row: Row) -> str:
    return row.get("timestamp") or ""


def _error(row: Row) -> str:
    return row.get("error_summary") or ""


def _xcgate_profile() -> SummaryProfile:
    return SummaryProfile(
        title="XCgateアップロード結果",
        total_label="対象Excel数",
        success_heading="アップロード成功",
        failure_heading="アップロード失敗",
        empty_message="今回の実行で記録されたアップロード結果はありません。",
        success_headers=["Excelファイル", "結果", "時刻"],
        failure_headers=["Excelファイル", "エラー内容", "スクリーンショット", "時刻"],
        success_cells=lambda r: [_esc(r.get("file") or ""), "OK", _esc(_timestamp(r))],
        failure_cells=lambda r: [
            _esc(r.get("file") or ""),
            _esc(_error(r)),
            _file_link(r.get("screenshot") or "", "開く"),
            _esc(_timestamp(r)),
        ],
    )


def _pdf_profile() -> SummaryProfile:
    def success_cells(row: Row) -> list[str]:
        doc_id, revision = _split_doc_revision(row)
        return [_esc(doc_id), _esc(revision), _file_link(row.get("saved_path") or ""), _esc(_timestamp(row))]

    def failure_cells(row: Row) -> list[str]:
        doc_id, revision = _split_doc_revision(row)
        return [
            _esc(doc_id),
            _esc(revision),
            _esc(_error(row)),
            _file_link(row.get("screenshot") or "", "開く"),
            _esc(_timestamp(row)),
        ]

    return SummaryProfile(
        title="3DX PDFダウンロード結果",
        total_label="対象PDF数",
        success_heading="ダウンロード成功",
        failure_heading="ダウンロード失敗",
        empty_message="今回の実行で記録されたPDFダウンロード結果はありません。",
        success_headers=["文書ID", "Revision", "保存先", "時刻"],
        failure_headers=["文書ID", "Revision", "エラー内容", "スクリーンショット", "時刻"],
        success_cells=success_cells,
        failure_cells=failure_cells,
        show_download_dirs=True,
    )


def _doc_create_profile() -> SummaryProfile:
    return SummaryProfile(
        title="3DX文書作成結果",
        total_label="対象タイトル数",
        success_heading="作成成功",
        failure_heading="作成失敗",
        empty_message="今回の実行で記録された文書作成結果はありません。",
        success_headers=["タイトル", "Document ID", "結果", "時刻"],
        failure_headers=["タイトル", "Document ID", "エラー内容", "時刻"],
        success_cells=lambda r: [
            _esc(r.get("file") or ""),
            _esc(r.get("document_id") or ""),
            "OK",
            _esc(_timestamp(r)),
        ],
        failure_cells=lambda r: [
            _esc(r.get("file") or ""),
            _esc(r.get("document_id") or ""),
            _esc(_error(r)),
            _esc(_timestamp(r)),
        ],
    )


def _generic_profile() -> SummaryProfile:
    return SummaryProfile(
        title="実行結果",
        total_label="対象数",
        success_heading="成功",
        failure_heading="失敗",
        empty_message="今回の実行で記録された結果はありません。",
        success_headers=["対象", "保存先", "時刻"],
        failure_headers=["対象", "エラー内容", "スクリーンショット", "時刻"],
        success_cells=lambda r: [
            _esc(r.get("file") or ""),
            _file_link(r.get("saved_path") or ""),
            _esc(_timestamp(r)),
        ],
        failure_cells=lambda r: [
            _esc(r.get("file") or ""),
            _esc(_error(r)),
            _file_link(r.get("screenshot") or "", "開く"),
            _esc(_timestamp(r)),
        ],
        show_download_dirs=True,
    )


def _profile(summary_kind: str | None) -> SummaryProfile:
    key = (summary_kind or "").strip().lower()
    if key == "xcgate":
        return _xcgate_profile()
    if key == "3dx_pdf":
        return _pdf_profile()
    if key == "3dx_doc":
        return _doc_create_profile()
    return _generic_profile()


def _partition(rows: list[Row]) -> tuple[list[Row], list[Row]]:
    ok_rows = [r for r in rows if (r.get("result") or "").strip().upper() == "OK"]
    ng_rows = [r for r in rows if (r.get("result") or "").strip().upper() == "NG"]
    return ok_rows, ng_rows


def _plain_cells(cells: list[str]) -> str:
    import re

    vals = []
    for cell in cells:
        text = re.sub(r"<[^>]+>", "", str(cell or ""))
        text = _html.unescape(text).replace("\n", " ").strip()
        vals.append(text)
    return " / ".join(v for v in vals if v)


def summarize_and_print(
    csv_path: str,
    logs_dir: str,
    run_started_at: datetime,
    summary_kind: str | None = None,
) -> None:
    rows = _load_rows_since(csv_path, run_started_at)
    profile = _profile(summary_kind)
    ok_rows, ng_rows = _partition(rows)

    abs_logs_dir = _abs(logs_dir or "logs")
    abs_csv = _abs(csv_path) if csv_path else ""

    print("\n====================================")
    print(profile.title)
    print("====================================")
    if not rows:
        print(profile.empty_message)
    else:
        print(f"{profile.total_label}: {len(rows)} 件")
        print(f"成功: {len(ok_rows)} 件")
        print(f"失敗: {len(ng_rows)} 件")

        print(f"\n{profile.success_heading}:")
        if ok_rows:
            for row in ok_rows:
                print(f"  - {_plain_cells(profile.success_cells(row))}")
        else:
            print("  ありません")

        print(f"\n{profile.failure_heading}:")
        if ng_rows:
            for row in ng_rows:
                print(f"  - {_plain_cells(profile.failure_cells(row))}")
        else:
            print("  ありません")

    print("\nログの場所")
    print(f" - フォルダ: {abs_logs_dir}")
    if abs_csv:
        print(f" - CSV: {abs_csv}")
    print(f" - Windows: explorer \"{abs_logs_dir}\"\n")


def _table(headers: list[str], rows: list[Row], cell_fn: Callable[[Row], list[str]], empty: str) -> str:
    if not rows:
        return f"<div class='muted'>{_esc(empty)}</div>"
    head = "".join(f"<th>{_esc(h)}</th>" for h in headers)
    body_rows = []
    for row in rows:
        cells = cell_fn(row)
        body_rows.append("<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>")
    return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(body_rows)}</tbody></table>"


def _download_dirs(rows: list[Row], logs_dir: str) -> list[str]:
    dirs: list[str] = []
    seen: set[str] = set()
    for row in rows:
        saved = row.get("saved_path") or ""
        if not saved:
            continue
        folder = _abs(os.path.dirname(saved))
        if folder and folder not in seen:
            seen.add(folder)
            dirs.append(folder)
    if not dirs and any((r.get("destination") or "").strip().upper() == "3DX PDF" for r in rows):
        dirs.append(_abs(os.path.join(_abs(logs_dir or "logs"), "downloads")))
    return dirs


def _rows_to_html(
    rows: List[Row],
    logs_dir: str,
    csv_path: Optional[str],
    summary_kind: str | None = None,
) -> str:
    profile = _profile(summary_kind)
    ok_rows, ng_rows = _partition(rows)
    abs_logs_dir = _abs(logs_dir or "logs")
    abs_csv = _abs(csv_path) if csv_path else ""

    style = """
    <style>
      body { font-family: -apple-system,BlinkMacSystemFont,Segoe UI,Roboto,Helvetica,Arial,'Meiryo',sans-serif; margin: 24px; color: #222; }
      .cards { display: flex; flex-wrap: wrap; gap: 12px; margin: 8px 0 18px; }
      .card { border-radius: 8px; padding: 14px 18px; color: #fff; min-width: 150px; box-shadow: 0 2px 8px rgba(0,0,0,.08); }
      .total { background: #1976d2; }
      .ok { background: #2e7d32; }
      .ng { background: #c62828; }
      h1 { font-size: 22px; margin: 0 0 12px; }
      h2 { font-size: 16px; margin: 24px 0 8px; }
      .value { font-size: 28px; font-weight: 700; }
      table { border-collapse: collapse; width: 100%; }
      th, td { border: 1px solid #ddd; padding: 8px 10px; vertical-align: top; }
      th { background: #f5f5f5; text-align: left; }
      .muted { color: #666; }
      a { color: #1565c0; text-decoration: none; }
      a:hover { text-decoration: underline; }
      code { background: #f6f6f6; padding: 1px 4px; border-radius: 4px; }
      .paths { line-height: 1.8; }
      .footer { margin-top: 16px; color: #666; font-size: 12px; }
    </style>
    """

    cards = f"""
      <div class="cards">
        <div class="card total"><div>{_esc(profile.total_label)}</div><div class="value">{len(rows)}</div></div>
        <div class="card ok"><div>成功</div><div class="value">{len(ok_rows)}</div></div>
        <div class="card ng"><div>失敗</div><div class="value">{len(ng_rows)}</div></div>
      </div>
    """

    success_table = _table(profile.success_headers, ok_rows, profile.success_cells, "ありません")
    failure_table = _table(profile.failure_headers, ng_rows, profile.failure_cells, "ありません")

    paths_html = [f"<div>ログフォルダ: <code>{_esc(abs_logs_dir)}</code></div>"]
    if profile.show_download_dirs:
        for folder in _download_dirs(ok_rows, logs_dir):
            paths_html.append(f"<div>ダウンロード保存先: {_file_link(folder)}</div>")
    if abs_csv:
        paths_html.append(f"<div>CSV: {_file_link(abs_csv)}</div>")

    body = f"""
      <h1>{_esc(profile.title)}</h1>
      {cards}
      <h2>{_esc(profile.success_heading)}</h2>
      {success_table}
      <h2>{_esc(profile.failure_heading)}</h2>
      {failure_table}
      <h2>ログの場所</h2>
      <div class="paths">{''.join(paths_html)}</div>
      <div class="footer">このレポートは自動生成されました。</div>
    """
    return f"<!DOCTYPE html><html lang='ja'><head><meta charset='utf-8'><title>{_esc(profile.title)}</title>{style}</head><body>{body}</body></html>"


def generate_html_summary(
    csv_path: str,
    logs_dir: str,
    run_started_at: datetime,
    summary_kind: str | None = None,
) -> str:
    rows = _load_rows_since(csv_path, run_started_at)
    html = _rows_to_html(rows, logs_dir, csv_path, summary_kind=summary_kind)
    out_dir = Path(logs_dir or "logs")
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    out = out_dir / f"summary_{stamp}.html"
    out.write_text(html, encoding="utf-8")
    return str(out)


def open_html_summary(path: str) -> None:
    try:
        webbrowser.open(Path(path).resolve().as_uri())
    except Exception:
        pass
