from __future__ import annotations

from pathlib import Path

from ..errors import EngineError
from .pdf_fonts import PDF_WORKBENCH_FALLBACK_FONT, text_insert_kwargs
from .pdf_document import open_fitz_document


def replace_text_with_overlay(
    input_file: Path,
    output_file: Path,
    search: str,
    replace: str,
    password: str = "",
) -> dict[str, int | str]:
    if not search:
        raise EngineError("invalid_search", "検索文字列を入力してください。")

    doc = open_fitz_document(input_file, password=password)
    replacements = 0
    try:
        for page in doc:
            areas = page.search_for(search)
            for rect in areas:
                page.add_redact_annot(rect, fill=(1, 1, 1))
            if areas:
                page.apply_redactions()
                for rect in areas:
                    try:
                        page.insert_text(
                            (rect.x0, rect.y1 - 2),
                            replace,
                            fontsize=11,
                            color=(0, 0, 0),
                            **text_insert_kwargs(),
                        )
                    except Exception:
                        try:
                            page.insert_text(
                                (rect.x0, rect.y1 - 2),
                                replace,
                                fontsize=11,
                                color=(0, 0, 0),
                                fontname=PDF_WORKBENCH_FALLBACK_FONT,
                            )
                        except Exception:
                            page.insert_text(
                                (rect.x0, rect.y1 - 2),
                                replace,
                                fontsize=11,
                                color=(0, 0, 0),
                            )
                replacements += len(areas)

        output_file.parent.mkdir(parents=True, exist_ok=True)
        doc.save(str(output_file), garbage=4, deflate=True)
    finally:
        doc.close()

    return {"outputPath": str(output_file), "replacements": replacements}
