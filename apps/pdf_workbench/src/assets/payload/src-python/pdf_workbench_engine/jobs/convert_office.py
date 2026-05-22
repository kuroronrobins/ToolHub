from __future__ import annotations

from pathlib import Path
from typing import Any

from ..errors import EngineError
from ..schemas import as_path
from ..services.office_com import convert_to_pdf
from ..services.pdf_document import inspect_pdf


def _emit_progress(
    emit: Any,
    job_id: str | None,
    step: str,
    progress: int,
    message: str,
) -> None:
    if callable(emit):
        emit(
            {
                "type": "progress",
                "jobId": job_id,
                "step": step,
                "progress": max(0, min(99, progress)),
                "message": message,
            }
        )


def handle(request: dict[str, Any]) -> dict[str, Any]:
    source = as_path(request.get("sourcePath"), "sourcePath")
    session_dir = as_path(request.get("sessionDir"), "sessionDir")
    output_name = request.get("outputName")
    if not isinstance(output_name, str) or not output_name:
        output_name = f"{source.stem}.pdf"

    emit = request.get("_emit")
    job_id = request.get("jobId") if isinstance(request.get("jobId"), str) else None
    _emit_progress(emit, job_id, "Office変換", 12, f"{source.name} のPDF化を開始しています。")

    target = session_dir / "office-cache" / output_name
    _emit_progress(emit, job_id, "Office変換", 24, "Microsoft Office をバックグラウンドで起動しています。")
    converted = convert_to_pdf(source, target)
    inspection = inspect_pdf(converted)
    if int(inspection.get("pageCount", 0)) <= 0:
        raise EngineError(
            "office_output_invalid",
            f"Office変換後のPDFにページがありません: {source.name}",
            target=str(source),
        )
    _emit_progress(emit, job_id, "Office変換", 92, f"{source.name} のPDF化が完了しました。")

    return {
        "sourcePath": str(source),
        "cachePath": str(converted),
        "outputPath": str(converted),
        "outputName": converted.name,
        "kind": source.suffix.lower().lstrip("."),
    }
