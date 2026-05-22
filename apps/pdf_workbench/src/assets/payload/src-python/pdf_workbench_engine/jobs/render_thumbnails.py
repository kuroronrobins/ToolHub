from __future__ import annotations

from typing import Any

from ..schemas import as_path
from ..services.pdf_document import render_thumbnails


def handle(request: dict[str, Any]) -> dict[str, Any]:
    source = as_path(request.get("sourcePath"), "sourcePath")
    output_dir = as_path(request.get("outputDir"), "outputDir")
    password = request.get("password") if isinstance(request.get("password"), str) else ""
    page_numbers = request.get("pageNumbers")
    if not isinstance(page_numbers, list):
        page_numbers = []
    normalized_pages = [int(page) for page in page_numbers if isinstance(page, int)]
    thumbnail_zoom = request.get("thumbnailZoom")
    preview_zoom = request.get("previewZoom")
    return {
        "thumbnails": render_thumbnails(
            source,
            output_dir,
            normalized_pages,
            password=password,
            zoom=float(thumbnail_zoom) if isinstance(thumbnail_zoom, (int, float)) else 0.32,
            preview_zoom=float(preview_zoom) if isinstance(preview_zoom, (int, float)) else 2.25,
        )
    }
