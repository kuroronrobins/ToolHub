
import yaml

DEFAULTS = {
    "options": {
        "headless": False,
        "timeout_page_ms": 30000,
        "timeout_complete_ms": 120000,
        "log_actions": True,
    },
    "logging": {
        "csv_path": "logs/upload_log.csv",
        "shots_dir": "logs",
    },
}

def load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        user = yaml.safe_load(f) or {}
    cfg = DEFAULTS.copy()
    for k, v in user.items():
        if isinstance(v, dict) and k in cfg:
            cfg[k].update(v)
        else:
            cfg[k] = v
    return cfg
