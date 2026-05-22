from __future__ import annotations

from pathlib import Path
from typing import Any

from ..errors import EngineError, dependency_missing


def _import_pypdf() -> Any:
    try:
        from pypdf import PdfReader, PdfWriter
    except ImportError as exc:  # pragma: no cover - depends on local env
        raise dependency_missing("pypdf", "PDFの読み書き") from exc
    return PdfReader, PdfWriter


def _silence_fitz_diagnostics(fitz: Any) -> None:
    tools = getattr(fitz, "TOOLS", None)
    if tools is None:
        return

    # Keep the worker stdout JSON-only. Some recoverable MuPDF diagnostics are
    # otherwise printed before the JSON response and break Rust-side parsing.
    for method_name in ("mupdf_display_errors", "mupdf_display_warnings"):
        method = getattr(tools, method_name, None)
        if callable(method):
            try:
                method(False)
            except Exception:
                pass


def _import_fitz() -> Any:
    try:
        import fitz
    except ImportError as exc:  # pragma: no cover - depends on local env
        raise dependency_missing("PyMuPDF", "PDFの描画") from exc
    _silence_fitz_diagnostics(fitz)
    return fitz


def ensure_input_file(path: Path) -> None:
    if not path.exists():
        raise EngineError("input_not_found", f"入力ファイルが存在しません: {path}", target=str(path))
    if not path.is_file():
        raise EngineError("input_not_file", f"入力パスがファイルではありません: {path}", target=str(path))


    try:
        stat = path.stat()
    except OSError as exc:
        raise EngineError(
            "input_not_readable",
            f"入力ファイルを確認できません: {path.name}",
            target=str(path),
            detail=str(exc),
        ) from exc
    if stat.st_size == 0:
        raise EngineError("empty_input_file", f"入力ファイルが空です: {path.name}", target=str(path))
    try:
        with path.open("rb") as handle:
            handle.read(1)
    except PermissionError as exc:
        raise EngineError(
            "input_not_readable",
            f"入力ファイルを読み取る権限がありません: {path.name}",
            target=str(path),
            detail=str(exc),
        ) from exc
    except OSError as exc:
        raise EngineError(
            "input_not_readable",
            f"入力ファイルを読み取れません: {path.name}",
            target=str(path),
            detail=str(exc),
        ) from exc


def open_pdf_reader(path: Path, password: str = "") -> Any:
    ensure_input_file(path)
    PdfReader, _ = _import_pypdf()
    try:
        reader = PdfReader(str(path))
    except Exception as exc:
        raise EngineError(
            "pdf_inspect_failed",
            f"PDFを解析できません: {path.name}",
            target=str(path),
            detail=str(exc),
        ) from exc
    if reader.is_encrypted:
        decrypt_password = password
        if not decrypt_password:
            try:
                if reader.decrypt("") != 0:
                    return reader
            except Exception:
                pass
            raise EngineError(
                "pdf_password_required",
                f"PDFパスワードが必要です: {path.name}",
                target=str(path),
            )
        status = reader.decrypt(decrypt_password)
        if status == 0:
            raise EngineError("pdf_password_invalid", f"PDFパスワードが正しくありません: {path.name}", target=str(path))
    return reader


def open_fitz_document(path: Path, password: str = "") -> Any:
    ensure_input_file(path)
    fitz = _import_fitz()
    try:
        doc = fitz.open(str(path))
    except Exception as exc:
        raise EngineError(
            "pdf_open_failed",
            f"PDFを開けません: {path.name}",
            target=str(path),
            detail=str(exc),
        ) from exc
    if doc.needs_pass:
        authenticate_password = password
        if not authenticate_password:
            try:
                if doc.authenticate(""):
                    return doc
            except Exception:
                pass
            doc.close()
            raise EngineError(
                "pdf_password_required",
                f"PDFパスワードが必要です: {path.name}",
                target=str(path),
            )
        if not doc.authenticate(authenticate_password):
            doc.close()
            raise EngineError("pdf_password_invalid", f"PDFパスワードが正しくありません: {path.name}", target=str(path))
    return doc


def _render_pixmap(page: Any, fitz: Any, zoom: float, input_file: Path, page_number: int) -> Any:
    try:
        return page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
    except Exception as exc:
        raise EngineError(
            "pdf_render_failed",
            f"PDFページを描画できません: {input_file.name} p{page_number}",
            target=f"{input_file} p{page_number}",
            detail=str(exc),
        ) from exc


def _save_pixmap(pix: Any, out_path: Path, input_file: Path, page_number: int) -> None:
    try:
        pix.save(str(out_path))
    except Exception as exc:
        raise EngineError(
            "thumbnail_write_failed",
            f"プレビュー画像を保存できません: {input_file.name} p{page_number}",
            target=str(out_path),
            detail=str(exc),
        ) from exc


def inspect_pdf(input_file: Path, password: str = "") -> dict[str, Any]:
    reader = open_pdf_reader(input_file, password=password)
    metadata = {}
    for key, value in dict(reader.metadata or {}).items():
        metadata[str(key).lstrip("/")] = str(value)

    return {
        "path": str(input_file),
        "pageCount": len(reader.pages),
        "encrypted": reader.is_encrypted,
        "metadata": metadata,
    }


def render_thumbnail(
    input_file: Path,
    output_dir: Path,
    page_number: int,
    password: str = "",
    zoom: float = 0.32,
    preview_zoom: float | None = 2.25,
) -> dict[str, Any]:
    if page_number < 1:
        raise EngineError("invalid_page", "pageNumber は1以上を指定してください。", target=str(input_file))

    doc = open_fitz_document(input_file, password=password)
    try:
        if page_number > len(doc):
            raise EngineError(
                "invalid_page",
                f"ページ番号がPDFのページ数を超えています: {page_number}",
                target=str(input_file),
            )
        page = doc[page_number - 1]
        fitz = _import_fitz()
        pix = _render_pixmap(page, fitz, zoom, input_file, page_number)
        output_dir.mkdir(parents=True, exist_ok=True)
        out_path = output_dir / f"{input_file.stem}-p{page_number}.png"
        _save_pixmap(pix, out_path, input_file, page_number)
        result = {
            "thumbnailPath": str(out_path),
            "pageNumber": page_number,
            "width": pix.width,
            "height": pix.height,
        }
        if preview_zoom and preview_zoom > zoom:
            preview_pix = _render_pixmap(page, fitz, preview_zoom, input_file, page_number)
            preview_path = output_dir / "preview" / f"{input_file.stem}-p{page_number}.png"
            preview_path.parent.mkdir(parents=True, exist_ok=True)
            _save_pixmap(preview_pix, preview_path, input_file, page_number)
            result.update(
                {
                    "previewPath": str(preview_path),
                    "previewWidth": preview_pix.width,
                    "previewHeight": preview_pix.height,
                }
            )
        return result
    finally:
        doc.close()


def render_thumbnails(
    input_file: Path,
    output_dir: Path,
    page_numbers: list[int],
    password: str = "",
    zoom: float = 0.32,
    preview_zoom: float | None = 2.25,
) -> list[dict[str, Any]]:
    if not page_numbers:
        return []

    doc = open_fitz_document(input_file, password=password)
    try:
        fitz = _import_fitz()
        output_dir.mkdir(parents=True, exist_ok=True)
        thumbnails: list[dict[str, Any]] = []
        for page_number in page_numbers:
            if page_number < 1:
                raise EngineError("invalid_page", "pageNumber は1以上を指定してください。", target=str(input_file))
            if page_number > len(doc):
                raise EngineError(
                    "invalid_page",
                    f"ページ番号がPDFのページ数を超えています: {page_number}",
                    target=str(input_file),
                )
            page = doc[page_number - 1]
            pix = _render_pixmap(page, fitz, zoom, input_file, page_number)
            out_path = output_dir / f"{input_file.stem}-p{page_number}.png"
            _save_pixmap(pix, out_path, input_file, page_number)
            item = {
                "thumbnailPath": str(out_path),
                "pageNumber": page_number,
                "width": pix.width,
                "height": pix.height,
            }
            if preview_zoom and preview_zoom > zoom:
                preview_pix = _render_pixmap(page, fitz, preview_zoom, input_file, page_number)
                preview_path = output_dir / "preview" / f"{input_file.stem}-p{page_number}.png"
                preview_path.parent.mkdir(parents=True, exist_ok=True)
                _save_pixmap(preview_pix, preview_path, input_file, page_number)
                item.update(
                    {
                        "previewPath": str(preview_path),
                        "previewWidth": preview_pix.width,
                        "previewHeight": preview_pix.height,
                    }
                )
            thumbnails.append(item)
        return thumbnails
    finally:
        doc.close()
