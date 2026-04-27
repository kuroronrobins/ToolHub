
import csv, os
from datetime import datetime

HEADER = ["timestamp","file","destination","result","error_summary","screenshot","html"]

def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def append_row(csv_path: str, row: dict):
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)
    exists = os.path.exists(csv_path)
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=HEADER, extrasaction="ignore")
        if not exists:
            w.writeheader()
        w.writerow(row)
