
import os
from datetime import datetime

def ts() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")

def ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)

def save_screenshot(page, dir_path: str, stem: str) -> str:
    ensure_dir(dir_path)
    out = os.path.join(dir_path, f"{stem}_{ts()}.png")
    page.screenshot(path=out, full_page=True)
    return out

def save_html(page, dir_path: str, stem: str) -> str:
    ensure_dir(dir_path)
    out = os.path.join(dir_path, f"{stem}_{ts()}.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(page.content())
    return out
