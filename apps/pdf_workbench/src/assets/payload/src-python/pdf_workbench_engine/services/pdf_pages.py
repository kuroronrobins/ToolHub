from __future__ import annotations

from pathlib import Path
from typing import Any

from ..errors import EngineError
from .pdf_document import _import_pypdf, open_pdf_reader


def write_page_sequence(
    pages: list[dict[str, Any]],
    output_file: Path,
    password_map: dict[str, str] | None = None,
) -> Path:
    if not pages:
        raise EngineError("empty_output", "出力するページがありません。")

    _, PdfWriter = _import_pypdf()
    password_map = password_map or {}
    writer = PdfWriter()
    readers: dict[str, Any] = {}

    for item in pages:
        source = Path(str(item["sourcePath"]))
        page_number = int(item["pageNumber"])
        key = str(source.resolve())
        if key not in readers:
            readers[key] = open_pdf_reader(source, password=password_map.get(key, ""))
        reader = readers[key]
        if page_number < 1 or page_number > len(reader.pages):
            raise EngineError("invalid_page", f"不正なページ番号です: {page_number}", target=str(source))
        writer.add_page(reader.pages[page_number - 1])

    output_file.parent.mkdir(parents=True, exist_ok=True)
    with output_file.open("wb") as fp:
        writer.write(fp)
    return output_file


def merge_pdfs(input_files: list[Path], output_file: Path, password_map: dict[str, str] | None = None) -> Path:
    pages: list[dict[str, Any]] = []
    for input_file in input_files:
        reader = open_pdf_reader(input_file, password=(password_map or {}).get(str(input_file.resolve()), ""))
        for index in range(len(reader.pages)):
            pages.append({"sourcePath": str(input_file), "pageNumber": index + 1})
    return write_page_sequence(pages, output_file, password_map=password_map)
