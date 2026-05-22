from __future__ import annotations

from typing import Any

from ..schemas import as_path
from ..services.pdf_document import render_thumbnail


def handle(request: dict[str, Any]) -> dict[str, Any]:
    source = as_path(request.get("sourcePath"), "sourcePath")
    session_dir = as_path(request.get("sessionDir"), "sessionDir")
    page_number = int(request.get("pageNumber") or 1)
    password = request.get("password") if isinstance(request.get("password"), str) else ""
    zoom = float(request.get("zoom") or 0.32)
    preview_zoom = request.get("previewZoom")
    return render_thumbnail(
        source,
        session_dir / "thumbnails" / source.stem,
        page_number=page_number,
        password=password,
        zoom=zoom,
        preview_zoom=float(preview_zoom) if isinstance(preview_zoom, (int, float)) else 2.25,
    )
