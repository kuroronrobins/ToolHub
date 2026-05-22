from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from ..errors import EngineError
from ..schemas import as_path
from ..services.pdf_decorations import draw_decoration_layout, resolve_page_decoration_layout
from ..services.pdf_document import _import_fitz, open_fitz_document
from ..services.pdf_pages import write_page_sequence
from .export_workspace import _build_groups


def _source_fingerprint(workspace: dict[str, Any]) -> list[dict[str, Any]]:
    files = workspace.get("files")
    if not isinstance(files, list):
        return []

    fingerprint: list[dict[str, Any]] = []
    for file_info in files:
        if not isinstance(file_info, dict):
            continue
        raw_path = file_info.get("cachePath") or file_info.get("sourcePath")
        if not isinstance(raw_path, str) or not raw_path:
            continue
        entry: dict[str, Any] = {"path": raw_path}
        try:
            stat = Path(raw_path).stat()
            entry.update({"mtimeNs": stat.st_mtime_ns, "size": stat.st_size})
        except OSError:
            entry["missing"] = True
        fingerprint.append(entry)
    return fingerprint


def _overlay_cache_key(
    workspace: dict[str, Any],
    output_index: int,
    page_index: int,
    overlay_zoom: float,
) -> str:
    payload = {
        "workspace": workspace,
        "sources": _source_fingerprint(workspace),
        "outputIndex": output_index,
        "pageIndex": page_index,
        "overlayZoom": overlay_zoom,
        "renderer": "decoration-overlay-v1",
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _image_info(output_file: Path) -> dict[str, Any]:
    fitz = _import_fitz()
    pix = fitz.Pixmap(str(output_file))
    return {
        "overlayPath": str(output_file),
        "overlayWidth": pix.width,
        "overlayHeight": pix.height,
    }


def _requested_page(request: dict[str, Any]) -> tuple[dict[str, Any], Path, int, int, float]:
    workspace = request.get("workspace")
    if not isinstance(workspace, dict):
        raise EngineError("invalid_workspace", "workspace is required")

    output_dir = as_path(request.get("outputDir"), "outputDir")
    output_index = request.get("outputIndex")
    page_index = request.get("pageIndex")
    if not isinstance(output_index, int) or output_index < 0:
        raise EngineError("invalid_preview_page", "outputIndex must be a non-negative integer")
    if not isinstance(page_index, int) or page_index < 0:
        raise EngineError("invalid_preview_page", "pageIndex must be a non-negative integer")

    overlay_zoom = request.get("overlayZoom")
    overlay_zoom_value = float(overlay_zoom) if isinstance(overlay_zoom, (int, float)) else 2.25
    return workspace, output_dir, output_index, page_index, overlay_zoom_value


def _manifest_for_page(
    workspace: dict[str, Any],
    output_dir: Path,
    output_index: int,
    page_index: int,
    overlay_zoom: float,
    password_map: dict[str, Any],
) -> dict[str, Any]:
    groups = _build_groups(workspace)
    if output_index >= len(groups):
        raise EngineError("invalid_preview_page", "output group was not found", target=str(output_index))
    group = groups[output_index]
    if page_index >= len(group):
        raise EngineError("invalid_preview_page", "preview page was not found", target=str(page_index))

    output_dir.mkdir(parents=True, exist_ok=True)
    scratch_pdf = output_dir / f".pdf-workbench-decoration-layout-{uuid4().hex}.pdf"
    page_context = {
        **group[page_index],
        "outputPageNumber": page_index + 1,
        "outputPageTotal": len(group),
    }
    resolved_password_map = {
        str(Path(key).resolve()): str(value)
        for key, value in password_map.items()
    }

    try:
        write_page_sequence([group[page_index]], scratch_pdf, password_map=resolved_password_map)
        doc = open_fitz_document(scratch_pdf)
        try:
            if len(doc) < 1:
                raise EngineError("empty_preview", "preview page is empty", target=str(scratch_pdf))
            layout = resolve_page_decoration_layout(
                doc[0].rect,
                workspace.get("decorations") if isinstance(workspace.get("decorations"), list) else [],
                0,
                1,
                page_context,
                output_index + 1,
            )
        finally:
            doc.close()
    finally:
        try:
            if scratch_pdf.exists():
                scratch_pdf.unlink()
        except OSError:
            pass

    return {
        "outputIndex": output_index,
        "pageIndex": page_index,
        "outputPageNumber": page_index + 1,
        "outputPageTotal": len(group),
        "renderZoom": overlay_zoom,
        "cacheKey": _overlay_cache_key(workspace, output_index, page_index, overlay_zoom),
        **layout,
    }


def _render_overlay_png(manifest: dict[str, Any], output_file: Path, overlay_zoom: float) -> dict[str, Any]:
    output_file.parent.mkdir(parents=True, exist_ok=True)
    fitz = _import_fitz()
    doc = fitz.open()
    try:
        page = doc.new_page(
            width=float(manifest.get("pageWidthPt") or 1),
            height=float(manifest.get("pageHeightPt") or 1),
        )
        draw_decoration_layout(page, manifest)
        pix = page.get_pixmap(matrix=fitz.Matrix(overlay_zoom, overlay_zoom), alpha=True)
        pix.save(str(output_file))
    finally:
        doc.close()
    return _image_info(output_file)


def manifest_handle(request: dict[str, Any]) -> dict[str, Any]:
    workspace, output_dir, output_index, page_index, overlay_zoom = _requested_page(request)
    password_map = request.get("passwordMap") if isinstance(request.get("passwordMap"), dict) else {}
    return _manifest_for_page(workspace, output_dir, output_index, page_index, overlay_zoom, password_map)


def overlay_handle(request: dict[str, Any]) -> dict[str, Any]:
    workspace, output_dir, output_index, page_index, overlay_zoom = _requested_page(request)
    password_map = request.get("passwordMap") if isinstance(request.get("passwordMap"), dict) else {}
    manifest = _manifest_for_page(workspace, output_dir, output_index, page_index, overlay_zoom, password_map)
    return _overlay_from_manifest(manifest, output_dir, overlay_zoom)


def _overlay_from_manifest(
    manifest: dict[str, Any],
    output_dir: Path,
    overlay_zoom: float,
) -> dict[str, Any]:
    if not manifest.get("items"):
        return {
            **manifest,
            "overlayPath": None,
            "overlayWidth": None,
            "overlayHeight": None,
            "cached": True,
        }

    overlay_file = output_dir / "decoration-overlay" / f"overlay-{manifest['cacheKey']}.png"
    if overlay_file.exists():
        return {
            **manifest,
            **_image_info(overlay_file),
            "cached": True,
        }

    return {
        **manifest,
        **_render_overlay_png(manifest, overlay_file, overlay_zoom),
        "cached": False,
    }


def overlay_manifest_handle(request: dict[str, Any]) -> dict[str, Any]:
    output_dir = as_path(request.get("outputDir"), "outputDir")
    manifest = request.get("manifest")
    if not isinstance(manifest, dict):
        raise EngineError("invalid_manifest", "manifest is required")

    overlay_zoom = request.get("overlayZoom")
    overlay_zoom_value = (
        float(overlay_zoom)
        if isinstance(overlay_zoom, (int, float))
        else float(manifest.get("renderZoom") or 2.25)
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    cache_key = manifest.get("cacheKey")
    if not isinstance(cache_key, str) or not cache_key:
        encoded = json.dumps(manifest, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
        cache_key = hashlib.sha256(encoded).hexdigest()
    manifest = {
        **manifest,
        "cacheKey": cache_key,
        "renderZoom": overlay_zoom_value,
    }
    return _overlay_from_manifest(manifest, output_dir, overlay_zoom_value)
