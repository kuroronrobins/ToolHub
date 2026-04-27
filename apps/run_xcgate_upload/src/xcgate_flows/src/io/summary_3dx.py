import os
import html
from datetime import datetime

DOC_IDS_LOG = "logs/doc_ids.txt"


def _esc(val) -> str:
    return html.escape(str(val or ""))


def _extract_doc_id(message: str | None) -> str | None:
    if not message:
        return None
    for line in str(message).splitlines():
        if "Name:" in line:
            return line.split("Name:", 1)[1].strip()
    return None


def load_doc_records_from_log(log_path: str, since: datetime) -> list[dict]:
    records: list[dict] = []
    if not log_path or not os.path.exists(log_path):
        return records
    try:
        with open(log_path, "r", encoding="utf-8") as fp:
            for line in fp:
                line = line.strip()
                if not line or "\t" not in line:
                    continue
                ts_txt, msg = line.split("\t", 1)
                ts_txt = ts_txt.strip()
                ts = None
                try:
                    ts = datetime.fromisoformat(ts_txt)
                except Exception:
                    pass
                if ts and ts < since:
                    continue
                records.append(
                    {
                        "id": _extract_doc_id(msg),
                        "message": msg,
                        "timestamp": ts or ts_txt,
                        "title": None,
                    }
                )
    except Exception:
        return []
    return records


def generate_doc_id_summary(records, logs_dir: str, run_started_at: datetime) -> str | None:
    records = records or []
    target_dir = logs_dir or "logs"
    os.makedirs(target_dir, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(target_dir, f"doc_summary_{stamp}.html")

    if records:
        rows = []
        for idx, rec in enumerate(records, 1):
            ts = rec.get("timestamp")
            ts_str = ts.isoformat(sep=" ") if isinstance(ts, datetime) else _esc(ts)
            title = _esc(rec.get("title"))
            rows.append(
                f"<tr><td>{idx}</td><td>{title}</td><td>{_esc(rec.get('id'))}</td><td>{ts_str}</td></tr>"
            )
        body_rows = "".join(rows)
    else:
        body_rows = "<tr><td colspan='4'>No documents recorded.</td></tr>"

    body = f"""
    <h1>3DX Document Creation Summary</h1>
    <p>Run started at: {_esc(run_started_at.isoformat(sep=' '))}</p>
    <table>
      <thead><tr><th>#</th><th>Title</th><th>Document ID</th><th>Timestamp</th></tr></thead>
      <tbody>{body_rows}</tbody>
    </table>
    """
    html_doc = f"""<!DOCTYPE html>
<html lang="ja"><head><meta charset="utf-8"><title>3DX Document Summary</title>
<style>
body {{ font-family: "Segoe UI", sans-serif; margin: 24px; }}
table {{ border-collapse: collapse; width: 100%; }}
th, td {{ border: 1px solid #ccc; padding: 8px; text-align: left; }}
th {{ background: #f5f5f5; }}
</style>
</head><body>{body}</body></html>"""

    with open(out_path, "w", encoding="utf-8") as fp:
        fp.write(html_doc)
    return out_path

