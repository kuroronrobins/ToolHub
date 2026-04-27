#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
実行結果サマリーの表示ユーティリティ。
CSV（logs/upload_log.csv）を読み込み、今回の実行分のみ集計して
非エンジニアにもわかりやすい日本語で表示します。

あわせて、見やすい HTML レポートも生成し、既定のブラウザで開けます。
"""

import os
import csv
import html as _html
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional


def _parse_ts(s: str) -> Optional[datetime]:
    """CSV の timestamp を datetime に変換（失敗時は None）。"""
    if not s:
        return None
    s = str(s).strip()
    # まず ISO 形式（例: 2024-08-01T12:34:56）を試す
    try:
        return datetime.fromisoformat(s)
    except Exception:
        pass
    # 代替形式（例: 2024-08-01 12:34:56 / 2024/08/01 12:34:56）
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S"):
        try:
            return datetime.strptime(s, fmt)
        except Exception:
            continue
    return None


def _load_rows_since(csv_path: str, since: datetime) -> List[Dict[str, str]]:
    """
    CSV から since 以降の行のみ抽出。
    timestamp が読めない行は、見落とし防止のため含めます。
    """
    rows: List[Dict[str, str]] = []
    if not csv_path or not os.path.exists(csv_path):
        return rows
    try:
        with open(csv_path, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for r in reader:
                ts = _parse_ts(r.get("timestamp"))
                if ts is None:
                    rows.append(r)
                    continue
                if ts >= since:
                    rows.append(r)
    except Exception:
        # CSV 読み込みエラー時は安全側で空を返す（本体を落とさない）
        return []
    return rows


def _abs(path: str) -> str:
    """絶対パスに変換（失敗時はそのまま返す）。"""
    try:
        return os.path.abspath(path)
    except Exception:
        return path


def summarize_and_print(csv_path: str, logs_dir: str, run_started_at: datetime) -> None:
    """
    CSV ログを読み込み、今回（run_started_at 以降）の実行結果を日本語で要約表示。
    """
    rows = _load_rows_since(csv_path, run_started_at)

    total = len(rows)
    ok_rows = [r for r in rows if (r.get("result") or "").strip().upper() == "OK"]
    ng_rows = [r for r in rows if (r.get("result") or "").strip().upper() == "NG"]

    ok = len(ok_rows)
    ng = len(ng_rows)

    abs_logs_dir = _abs(logs_dir or "logs")
    abs_csv = _abs(csv_path) if csv_path else ""

    print("\n====================================")
    print("実行結果のまとめ")
    print("====================================")
    if total == 0:
        print("今回の実行で記録された結果はありません。")
    else:
        print(f"対象ファイル数: {total} 件")
        print(f"成功: {ok} 件")
        print(f"失敗: {ng} 件")

        # 成功したファイル一覧（スクリーンショット不要）
        print("\n成功したファイル:")
        if ok == 0:
            print("  ありません")
        else:
            for r in ok_rows:
                f = r.get("file") or "(不明なファイル)"
                print(f"  - {f}")

        # 失敗したファイル一覧（スクショパスを併記）
        print("\n失敗したファイル（確認してください）:")
        if ng == 0:
            print("  ありません")
        else:
            for r in ng_rows:
                f = r.get("file") or "(不明なファイル)"
                shot = r.get("screenshot") or ""
                if shot:
                    print(f"  - {f}  詳細ログ: {_abs(shot)}")
                else:
                    print(f"  - {f}")

    print("\nログの場所")
    print(f" - フォルダ: {abs_logs_dir}")
    if abs_csv:
        print(f" - CSV: {abs_csv}")
    print("ログフォルダを開くコマンド:")
    print(f" - Windows: explorer \"{abs_logs_dir}\"")
    print(f" - macOS:   open \"{abs_logs_dir}\"")
    print(f" - Linux:   xdg-open \"{abs_logs_dir}\"\n")


def _rows_to_html(rows: List[Dict[str, str]], logs_dir: str, csv_path: Optional[str]) -> str:
    total = len(rows)
    ok_rows = [r for r in rows if (r.get("result") or "").strip().upper() == "OK"]
    ng_rows = [r for r in rows if (r.get("result") or "").strip().upper() == "NG"]

    ok = len(ok_rows)
    ng = len(ng_rows)

    abs_logs_dir = _abs(logs_dir or "logs")
    abs_csv = _abs(csv_path) if csv_path else ""

    def esc(s: str) -> str:
        return _html.escape(str(s))

    style = """
    <style>
      body { font-family: -apple-system,BlinkMacSystemFont,Segoe UI,Roboto,Helvetica,Arial,'メイリオ',sans-serif; margin: 24px; }
      .cards { display: flex; gap: 16px; margin: 8px 0 16px; }
      .card { border-radius: 10px; padding: 16px 20px; color: #fff; min-width: 160px; box-shadow: 0 2px 8px rgba(0,0,0,.08); }
      .ok { background: #2e7d32; }
      .ng { background: #c62828; }
      .total { background: #1976d2; }
      h1 { font-size: 20px; margin: 0 0 12px; }
      h2 { font-size: 16px; margin: 24px 0 8px; }
      .value { font-size: 28px; font-weight: 700; }
      table { border-collapse: collapse; width: 100%; }
      th, td { border: 1px solid #ddd; padding: 8px 10px; }
      th { background: #f5f5f5; text-align: left; }
      .muted { color: #555; }
      a { color: #1565c0; text-decoration: none; }
      a:hover { text-decoration: underline; }
      .paths { line-height: 1.8; }
      .hint { color: #333; margin-top: 8px; }
      .footer { margin-top: 16px; color: #666; font-size: 12px; }
    </style>
    """

    cards = f"""
      <div class=\"cards\">
        <div class=\"card total\"><div>対象ファイル</div><div class=\"value\">{total}</div></div>
        <div class=\"card ok\"><div>成功</div><div class=\"value\">{ok}</div></div>
        <div class=\"card ng\"><div>失敗</div><div class=\"value\">{ng}</div></div>
      </div>
    """

    # 成功一覧（失敗一覧の上に表示）
    if ok > 0:
        ok_rows_html = ["<tr><th>ファイル</th></tr>"]
        for r in ok_rows:
            f = esc(r.get("file") or "(不明なファイル)")
            ok_rows_html.append(f"<tr><td>{f}</td></tr>")
        ok_details = "<h2>成功したファイル</h2><table>" + "".join(ok_rows_html) + "</table>"
    else:
        ok_details = "<h2>成功したファイル</h2><div class='muted'>ありません</div>"

    # 失敗一覧
    if ng > 0:
        ng_rows_html = ["<tr><th>ファイル</th><th>スクリーンショット</th><th>メモ</th></tr>"]
        for r in ng_rows:
            f = esc(r.get("file") or "(不明なファイル)")
            shot = r.get("screenshot") or ""
            shot_abs = _abs(shot) if shot else ""
            try:
                shot_link = f'<a href="{Path(shot_abs).resolve().as_uri()}">開く</a>' if shot_abs else ""
            except Exception:
                shot_link = esc(shot_abs)
            memo = esc(r.get("error_summary") or "")
            ng_rows_html.append(f"<tr><td>{f}</td><td>{shot_link}</td><td class='muted'>{memo}</td></tr>")
        ng_details = "<h2>失敗したファイル</h2><table>" + "".join(ng_rows_html) + "</table>"
    else:
        ng_details = "<h2>失敗したファイル</h2><div class='muted'>ありません</div>"

    paths_html = [f"<div>フォルダ: <code>{esc(abs_logs_dir)}</code></div>"]
    if abs_csv:
        try:
            paths_html.append(f"<div>CSV: <a href='{Path(abs_csv).resolve().as_uri()}'>{esc(abs_csv)}</a></div>")
        except Exception:
            paths_html.append(f"<div>CSV: <code>{esc(abs_csv)}</code></div>")

    body = f"""
      <h1>実行結果のまとめ</h1>
      {cards}
      {ok_details}
      {ng_details}
      <h2>ログの場所</h2>
      <div class='paths'>{''.join(paths_html)}</div>
      <div class='hint'>※ 上記のパス/リンクをクリックして詳細を確認できます。</div>
      <div class='footer'>このレポートは自動生成されました</div>
    """

    return f"<meta charset='utf-8'>\n{style}\n{body}"


def generate_html_summary(csv_path: str, logs_dir: str, run_started_at: datetime) -> str:
    """HTML サマリーを logs 配下に保存し、保存パスを返す。"""
    rows = _load_rows_since(csv_path, run_started_at)
    html = _rows_to_html(rows, logs_dir, csv_path)
    out_dir = Path(logs_dir or "logs")
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = out_dir / f"summary_{stamp}.html"
    out.write_text(html, encoding="utf-8")
    return str(out)


def open_html_summary(path: str) -> None:
    """既定のブラウザで HTML を開く。"""
    try:
        uri = Path(path).resolve().as_uri()
        webbrowser.open(uri)
    except Exception:
        # 失敗しても本体の実行に影響を与えない
        pass

