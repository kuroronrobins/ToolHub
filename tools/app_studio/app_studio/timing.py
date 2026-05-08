from __future__ import annotations

import json
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from .models import StudioContext
from .util import now_iso, write_json, write_text


DEFAULT_PHASE_ESTIMATES_SECONDS = {
    "preflight": 2,
    "file_inventory": 5,
    "secret_scan": 5,
    "dependency_analysis": 10,
    "metadata_ai": 5,
    "icon_generation": 10,
    "export_suggestion": 5,
    "build_env_creation": 90,
    "build_env_cache": 1,
    "dependency_install": 120,
    "requirements_lock_generation": 30,
    "build_tools_install": 60,
    "build_tools_cache": 1,
    "pyinstaller_probe": 10,
    "pyinstaller_build": 240,
    "distribution_check": 20,
    "registration_copy": 15,
    "execution_checks": 15,
    "result_refresh": 5,
}


PHASE_LABELS_JA = {
    "preflight": "事前確認",
    "file_inventory": "ファイル棚卸し",
    "secret_scan": "秘密情報検査",
    "dependency_analysis": "依存関係解析",
    "metadata_ai": "メタデータ生成",
    "icon_generation": "アイコン生成",
    "export_suggestion": "登録成果物の作成",
    "build_env_creation": "ビルド用環境の作成と依存インストール",
    "dependency_install": "依存関係インストール",
    "requirements_lock_generation": "requirements.lock 生成",
    "build_tools_install": "ビルドツールインストール",
    "pyinstaller_probe": "PyInstaller 確認",
    "pyinstaller_build": "PyInstaller frozen-folder build",
    "distribution_check": "配布物検証",
    "registration_copy": "登録コピーと App Pack 作成",
    "execution_checks": "承認前チェック",
    "result_refresh": "結果再読み込み",
}


class TimingRecorder:
    def __init__(self, context: StudioContext, action: str) -> None:
        self.context = context
        self.action = action
        self.generated_at = now_iso()
        self.started_at = time.perf_counter()
        self.phases: list[dict[str, Any]] = []
        previous_total = load_previous_total_seconds(context)
        self.prediction_source = "history" if previous_total else "heuristic"
        self.estimated_total_seconds = previous_total or estimate_initial_seconds(action)

    @contextmanager
    def phase(self, name: str, label: str | None = None) -> Iterator[None]:
        label_text = label or PHASE_LABELS_JA.get(name, name)
        started = time.perf_counter()
        self.emit_progress(name, label_text, "running", started)
        item = {
            "phase": name,
            "label": label_text,
            "status": "running",
            "started_at": now_iso(),
            "duration_seconds": None,
        }
        self.phases.append(item)
        try:
            yield
        except Exception:
            item["status"] = "fail"
            item["duration_seconds"] = round(time.perf_counter() - started, 3)
            self.emit_progress(name, label_text, "fail", started)
            raise
        else:
            item["status"] = "pass"
            item["duration_seconds"] = round(time.perf_counter() - started, 3)
            self.emit_progress(name, label_text, "pass", started)

    def mark(self, name: str, status: str, detail: str = "", duration_seconds: float = 0.0, label: str | None = None) -> None:
        self.phases.append(
            {
                "phase": name,
                "label": label or PHASE_LABELS_JA.get(name, name),
                "status": status,
                "started_at": now_iso(),
                "duration_seconds": round(duration_seconds, 3),
                "detail": detail,
            }
        )

    def total_duration_seconds(self) -> float:
        return round(sum(float(item.get("duration_seconds") or 0.0) for item in self.phases), 3)

    def wall_clock_total_seconds(self) -> float:
        return round(time.perf_counter() - self.started_at, 3)

    def to_dict(self) -> dict[str, Any]:
        cli_measured = self.total_duration_seconds()
        wall_clock = self.wall_clock_total_seconds()
        prediction_error = (
            round(wall_clock - float(self.estimated_total_seconds), 3)
            if self.estimated_total_seconds
            else None
        )
        unmeasured = round(max(wall_clock - cli_measured, 0.0), 3)
        return {
            "app_id": self.context.app_id,
            "action": self.action,
            "generated_at": self.generated_at,
            "estimated_total_seconds": self.estimated_total_seconds,
            "actual_total_seconds": wall_clock,
            "prediction_error_seconds": prediction_error,
            "prediction_source": self.prediction_source,
            "wall_clock_total_seconds": wall_clock,
            "cli_measured_total_seconds": cli_measured,
            "unmeasured_overhead_seconds": unmeasured,
            "total_duration_seconds": cli_measured,
            "phases": self.phases,
        }

    def emit_progress(self, phase: str, label: str, status: str, phase_started: float) -> None:
        elapsed = round(time.perf_counter() - self.started_at, 3)
        phase_elapsed = round(time.perf_counter() - phase_started, 3)
        remaining = max(self.estimated_total_seconds - elapsed, 0) if self.estimated_total_seconds else None
        payload = {
            "phase": phase,
            "label": label,
            "status": status,
            "elapsed_seconds": elapsed,
            "phase_elapsed_seconds": phase_elapsed,
            "estimated_total_seconds": self.estimated_total_seconds,
            "estimated_remaining_seconds": round(remaining, 3) if remaining is not None else None,
        }
        print("TOOLHUB_PROGRESS " + json.dumps(payload, ensure_ascii=False), flush=True)


def estimate_initial_seconds(action: str) -> int:
    if action == "apply":
        return sum(DEFAULT_PHASE_ESTIMATES_SECONDS.values())
    if action == "suggest":
        return 45
    return 10


def load_previous_total_seconds(context: StudioContext) -> int | None:
    path = context.repo_root / "data" / "logs" / "app_studio" / f"{context.app_id}_timing_report.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    value = data.get("actual_total_seconds") or data.get("wall_clock_total_seconds") or data.get("total_duration_seconds")
    if isinstance(value, (int, float)) and value > 0:
        return max(int(value), 10)
    return None


def write_timing_reports(context: StudioContext, output_dir: Path, recorder: TimingRecorder) -> None:
    data = recorder.to_dict()
    report = timing_markdown(data)
    write_json(output_dir / "timing_report.json", data)
    write_text(output_dir / "timing_report.md", report)
    log_dir = context.repo_root / "data" / "logs" / "app_studio"
    write_json(log_dir / f"{context.app_id}_timing_report.json", data)
    write_text(log_dir / f"{context.app_id}_timing_report.md", report)
    update_import_plan_with_timing(output_dir / "import_plan.json", data)


def update_import_plan_with_timing(path: Path, data: dict[str, Any]) -> None:
    if not path.is_file():
        return
    try:
        plan = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return
    plan["timing_report"] = str(path.parent / "timing_report.json")
    plan["timing_summary"] = {
        "estimated_total_seconds": data.get("estimated_total_seconds"),
        "total_duration_seconds": data.get("total_duration_seconds"),
        "phase_count": len(data.get("phases") or []),
    }
    write_json(path, plan)


def timing_markdown(data: dict[str, Any]) -> str:
    lines = [
        "# App Studio Timing Report",
        "",
        f"- app_id: `{data.get('app_id')}`",
        f"- action: `{data.get('action')}`",
        f"- generated_at: `{data.get('generated_at')}`",
        f"- estimated_total_seconds: `{data.get('estimated_total_seconds')}`",
        f"- actual_total_seconds: `{data.get('actual_total_seconds')}`",
        f"- prediction_error_seconds: `{data.get('prediction_error_seconds')}`",
        f"- prediction_source: `{data.get('prediction_source')}`",
        f"- wall_clock_total_seconds: `{data.get('wall_clock_total_seconds')}`",
        f"- cli_measured_total_seconds: `{data.get('cli_measured_total_seconds')}`",
        f"- unmeasured_overhead_seconds: `{data.get('unmeasured_overhead_seconds')}`",
        f"- total_duration_seconds: `{data.get('total_duration_seconds')}`",
        "",
        "| Status | Phase | Duration sec | Detail |",
        "| --- | --- | ---: | --- |",
    ]
    for item in data.get("phases") or []:
        lines.append(
            f"| {item.get('status')} | {item.get('label') or item.get('phase')} | {item.get('duration_seconds')} | {item.get('detail') or ''} |"
        )
    lines.append("")
    return "\n".join(lines)
