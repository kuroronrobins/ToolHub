from __future__ import annotations

import json
import sys
import traceback
from typing import Any, Callable

from .errors import EngineError
from .jobs.convert_office import handle as convert_office
from .jobs.export_workspace import handle as export_workspace
from .jobs.inspect_pdf import handle as inspect_pdf
from .jobs.render_decoration_overlay_page import (
    manifest_handle as render_export_decoration_manifest_page,
)
from .jobs.render_decoration_overlay_page import (
    overlay_handle as render_export_decoration_overlay_page,
)
from .jobs.render_decoration_overlay_page import (
    overlay_manifest_handle as render_export_decoration_overlay_manifest,
)
from .jobs.render_thumbnail import handle as render_thumbnail
from .jobs.render_thumbnails import handle as render_thumbnails
from .schemas import error, result


Handler = Callable[[dict[str, Any]], dict[str, Any]]

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


HANDLERS: dict[str, Handler] = {
    "ping": lambda request: {
        "engine": "pdf_workbench_engine",
        "version": "0.2.0",
        "ok": True,
    },
    "convert_office": convert_office,
    "inspect_pdf": inspect_pdf,
    "render_thumbnail": render_thumbnail,
    "render_thumbnails": render_thumbnails,
    "render_export_decoration_manifest_page": render_export_decoration_manifest_page,
    "render_export_decoration_overlay_page": render_export_decoration_overlay_page,
    "render_export_decoration_overlay_manifest": render_export_decoration_overlay_manifest,
    "export_workspace": export_workspace,
}


def _read_request() -> dict[str, Any]:
    raw = sys.stdin.buffer.read().decode("utf-8").strip()
    if not raw:
        raise EngineError("invalid_request", "worker request JSON is empty")
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise EngineError("invalid_request", "worker request must be a JSON object")
    return payload


def _write_event(payload: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False))
    sys.stdout.write("\n")
    sys.stdout.flush()


def _progress(job_id: str | None, step: str, progress: int, message: str) -> dict[str, Any]:
    return {
        "type": "progress",
        "jobId": job_id,
        "step": step,
        "progress": progress,
        "message": message,
    }


def main() -> int:
    job_id: str | None = None
    stream = False
    try:
        request = _read_request()
        job_id = request.get("jobId") if isinstance(request.get("jobId"), str) else None
        stream = bool(request.get("stream"))
        kind = request.get("kind")
        if not isinstance(kind, str) or not kind:
            raise EngineError("invalid_request", "kind を指定してください。")

        handler = HANDLERS.get(kind)
        if handler is None:
            raise EngineError("unsupported_job", f"未対応のworker処理です: {kind}")

        if stream:
            request["_emit"] = _write_event
            _write_event(_progress(job_id, "PDF解析", 1, "worker処理を開始しました。"))
            _write_event(result(job_id, handler(request)))
            return 0

        response = result(job_id, handler(request))
    except EngineError as exc:
        response = error(job_id, exc.to_payload())
    except json.JSONDecodeError as exc:
        response = error(
            job_id,
            {
                "code": "invalid_json",
                "message": "worker request JSONを解析できませんでした。",
                "detail": str(exc),
            },
        )
    except Exception as exc:  # pragma: no cover - final safety net for worker crashes
        response = error(
            job_id,
            {
                "code": "worker_crashed",
                "message": "Python workerで予期しないエラーが発生しました。",
                "detail": "".join(traceback.format_exception_only(type(exc), exc)).strip(),
            },
        )

    if stream:
        _write_event(response)
        return 0

    sys.stdout.write(json.dumps(response, ensure_ascii=False))
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
