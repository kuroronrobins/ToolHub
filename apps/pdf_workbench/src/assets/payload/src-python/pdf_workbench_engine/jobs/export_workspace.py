from __future__ import annotations

import errno
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

from ..errors import EngineError
from ..schemas import as_path
from ..services.pdf_decorations import apply_decorations
from ..services.pdf_pages import write_page_sequence
from ..services.pdf_security import encrypt_pdf

RESERVED_WINDOWS_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}
INVALID_OUTPUT_CHARS = set('<>:"/\\|?*')


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


def _file_source(file_info: dict[str, Any]) -> str:
    source = file_info.get("cachePath") or file_info.get("sourcePath")
    if not isinstance(source, str) or not source:
        raise EngineError("missing_source", "ファイルのPDFソースが見つかりません。", target=str(file_info.get("name") or "unknown"))
    if source.startswith("sample://") or source.startswith("session://"):
        raise EngineError("virtual_source", "サンプル/仮想ファイルは実出力できません。", target=source)
    return source


def _build_groups(workspace: dict[str, Any]) -> list[list[dict[str, Any]]]:
    files = workspace.get("files")
    pages_by_file = workspace.get("pagesByFile")
    if not isinstance(files, list) or not isinstance(pages_by_file, dict):
        raise EngineError("invalid_workspace", "workspace.files と workspace.pagesByFile が必要です。")

    file_map = {
        file_info.get("id"): file_info
        for file_info in files
        if isinstance(file_info, dict) and isinstance(file_info.get("id"), str)
    }
    groups: list[list[dict[str, Any]]] = [[]]
    for file_info in files:
        if not isinstance(file_info, dict) or file_info.get("excluded"):
            continue

        file_id = file_info.get("id")
        if not isinstance(file_id, str):
            continue
        pages = pages_by_file.get(file_id) or []
        if not isinstance(pages, list):
            continue

        for page in pages:
            if not isinstance(page, dict) or page.get("excluded"):
                continue
            source_file_id = page.get("sourceFileId") if isinstance(page.get("sourceFileId"), str) else file_id
            source_file_info = file_map.get(source_file_id) or file_info
            if not isinstance(source_file_info, dict):
                source_file_info = file_info
            source = _file_source(source_file_info)
            page_number = page.get("originalPageNumber") or page.get("pageNumber")
            if not isinstance(page_number, int):
                raise EngineError("invalid_page", "ページ番号が不正です。", target=str(file_info.get("name") or file_id))

            groups[-1].append(
                {
                    "sourcePath": source,
                    "pageNumber": page_number,
                    "pageId": page.get("id"),
                    "fileId": file_id,
                    "sourceFileId": source_file_id,
                    "selected": bool(page.get("selected")),
                }
            )
            if page.get("splitAfter"):
                groups.append([])

    groups = [group for group in groups if group]
    if not groups:
        raise EngineError("empty_output", "出力対象ページがありません。")
    return groups


def _is_reserved_windows_name(name: str) -> bool:
    stem = name.rstrip(" .").split(".", 1)[0].upper()
    return stem in RESERVED_WINDOWS_NAMES


def _validate_output_name(name: str) -> None:
    if not name or name != name.strip() or name.endswith(".") or name.endswith(" "):
        raise EngineError("invalid_output_name", "出力ファイル名が不正です。", target=name)
    if any(char in INVALID_OUTPUT_CHARS or ord(char) < 32 for char in name):
        raise EngineError("invalid_output_name", "出力ファイル名に使用できない文字が含まれています。", target=name)
    if _is_reserved_windows_name(name):
        raise EngineError("reserved_output_name", "Windowsの予約名は出力ファイル名に使用できません。", target=name)
    if name in {".", ".."}:
        raise EngineError("invalid_output_name", "出力ファイル名が不正です。", target=name)


def _safe_copy_to_final(source_file: Path, final_file: Path) -> None:
    final_file.parent.mkdir(parents=True, exist_ok=True)
    temp_file = final_file.parent / f".pdf-workbench-final-{uuid4().hex}-{final_file.name}"
    try:
        temp_file.write_bytes(source_file.read_bytes())
        os.replace(temp_file, final_file)
    except PermissionError as exc:
        raise EngineError(
            "output_file_locked",
            f"出力先ファイルに書き込めません。開いている場合は閉じてください: {final_file.name}",
            target=str(final_file),
            detail=str(exc),
        ) from exc
    except OSError as exc:
        code = "disk_full" if exc.errno == errno.ENOSPC else "atomic_replace_failed"
        raise EngineError(
            code,
            f"出力ファイルを保存できません: {final_file.name}",
            target=str(final_file),
            detail=str(exc),
        ) from exc
    finally:
        try:
            temp_file.unlink()
        except OSError:
            pass


def _apply_post_processing(
    output_file: Path,
    workspace: dict[str, Any],
    scratch_dir: Path,
    scratch_prefix: str,
    final_file: Path,
    index: int,
    group: list[dict[str, Any]],
    emit: Any = None,
    job_id: str | None = None,
    base_progress: int = 55,
) -> Path:
    current = output_file
    output_page_contexts = [
        {
            **page_context,
            "outputPageNumber": page_number,
            "outputPageTotal": len(group),
        }
        for page_number, page_context in enumerate(group, start=1)
    ]
    decorations = workspace.get("decorations")
    if isinstance(decorations, list) and decorations:
        _emit_progress(emit, job_id, "装飾", base_progress, f"出力{index}へ装飾を反映しています。")
        decorated = scratch_dir / f"{scratch_prefix}-decorated-{index:03}.pdf"
        current = apply_decorations(
            current,
            decorated,
            decorations,
            page_contexts=output_page_contexts,
            output_index=index,
        )

    security = workspace.get("security")
    encrypt_output = isinstance(security, dict) and bool(security.get("encryptOutput") or security.get("outputEncrypted"))
    if isinstance(security, dict) and encrypt_output:
        _emit_progress(emit, job_id, "暗号化", base_progress + 24, f"出力{index}を暗号化しています。")
        password = str(security.get("userPassword") or security.get("outputPassword") or security.get("ownerPassword") or "")
        if not password:
            raise EngineError("missing_password", "暗号化にはパスワードが必要です。")
        encrypted = scratch_dir / f"{scratch_prefix}-encrypted-{index:03}.pdf"
        current = encrypt_pdf(
            current,
            encrypted,
            user_password=password,
            owner_password=str(security.get("ownerPassword") or password),
        )

    if current != final_file:
        _safe_copy_to_final(current, final_file)
    return final_file


def _requested_output_file(request: dict[str, Any]) -> Path:
    raw_output_path = request.get("outputPath")
    if isinstance(raw_output_path, str) and raw_output_path:
        output_file = as_path(raw_output_path, "outputPath")
    else:
        output_dir = as_path(request.get("outputDir"), "outputDir")
        output_file = output_dir / "result.pdf"

    if output_file.suffix.lower() != ".pdf":
        output_file = output_file.with_suffix(".pdf")
    _validate_output_name(output_file.name)
    return output_file


def _requested_custom_output_files(
    request: dict[str, Any],
    output_count: int,
    fallback_base_file: Path,
) -> list[Path] | None:
    raw_names = request.get("outputNames")
    if raw_names is None:
        return None
    if not isinstance(raw_names, list) or len(raw_names) != output_count:
        raise EngineError("invalid_output_names", "出力ファイル名の数が分割後の出力数と一致しません。")

    output_dir = (
        as_path(request.get("outputDir"), "outputDir")
        if request.get("outputDir")
        else fallback_base_file.parent
    )
    invalid_chars = INVALID_OUTPUT_CHARS
    seen: set[str] = set()
    output_files: list[Path] = []

    for raw_name in raw_names:
        if not isinstance(raw_name, str):
            raise EngineError("invalid_output_name", "出力ファイル名が不正です。")
        name = raw_name
        if not name.strip():
            raise EngineError("invalid_output_name", "空の出力ファイル名は使用できません。")
        if any(char in invalid_chars or ord(char) < 32 for char in name):
            raise EngineError("invalid_output_name", "出力ファイル名に使用できない文字が含まれています。", target=name)
        if not name.lower().endswith(".pdf"):
            name = f"{name}.pdf"
        _validate_output_name(name)
        stem = name[:-4].strip()
        if not stem or stem in {".", ".."}:
            raise EngineError("invalid_output_name", "出力ファイル名が不正です。", target=name)
        normalized_key = name.lower()
        if normalized_key in seen:
            raise EngineError("duplicate_output_name", "出力ファイル名が重複しています。", target=name)
        seen.add(normalized_key)
        output_files.append(output_dir / name)

    return output_files


def _final_output_file(base_file: Path, output_count: int, index: int) -> Path:
    if output_count <= 1:
        return base_file
    return base_file.with_name(f"{base_file.stem}_{index:03}.pdf")


def handle(request: dict[str, Any]) -> dict[str, Any]:
    output_file = _requested_output_file(request)
    output_dir = output_file.parent
    workspace = request.get("workspace")
    if not isinstance(workspace, dict):
        raise EngineError("invalid_workspace", "workspace を指定してください。")

    emit = request.get("_emit")
    job_id = request.get("jobId") if isinstance(request.get("jobId"), str) else None
    password_map = request.get("passwordMap") if isinstance(request.get("passwordMap"), dict) else {}
    _emit_progress(emit, job_id, "PDF解析", 8, "ワークスペースから出力対象ページを解析しています。")
    groups = _build_groups(workspace)
    _emit_progress(emit, job_id, "分割", 16, f"{len(groups)}個の出力PDFへ分割計画を作成しました。")
    custom_output_files = _requested_custom_output_files(request, len(groups), output_file)
    if custom_output_files is not None:
        output_dir = custom_output_files[0].parent
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise EngineError(
            "invalid_output_dir",
            f"出力先フォルダを作成できません: {output_dir}",
            target=str(output_dir),
            detail=str(exc),
        ) from exc

    outputs: list[str] = []
    scratch_prefix = f".pdf-workbench-{uuid4().hex}"
    try:
        for index, group in enumerate(groups, start=1):
            group_progress = 20 + int(((index - 1) / max(1, len(groups))) * 38)
            _emit_progress(
                emit,
                job_id,
                "結合",
                group_progress,
                f"出力{index}/{len(groups)}のページ列を作成しています。",
            )
            raw_output = output_dir / f"{scratch_prefix}-pages-{index:03}.pdf"
            write_page_sequence(group, raw_output, password_map={str(Path(key).resolve()): str(value) for key, value in password_map.items()})
            final_file = _apply_post_processing(
                raw_output,
                workspace,
                output_dir,
                scratch_prefix,
                custom_output_files[index - 1]
                if custom_output_files is not None
                else _final_output_file(output_file, len(groups), index),
                index,
                group,
                emit=emit,
                job_id=job_id,
                base_progress=58 + int((index / max(1, len(groups))) * 18),
            )
            outputs.append(str(final_file))
    finally:
        for scratch_file in output_dir.glob(f"{scratch_prefix}-*"):
            try:
                scratch_file.unlink()
            except OSError:
                pass

    _emit_progress(emit, job_id, "保存", 96, "出力PDFを保存しました。")
    return {
        "outputFiles": outputs,
        "outputCount": len(outputs),
    }
