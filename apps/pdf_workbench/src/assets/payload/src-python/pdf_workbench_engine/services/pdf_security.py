from __future__ import annotations

from pathlib import Path

from .pdf_document import _import_pypdf, open_pdf_reader


def encrypt_pdf(input_file: Path, output_file: Path, user_password: str, owner_password: str = "", open_password: str = "") -> Path:
    reader = open_pdf_reader(input_file, password=open_password)
    _, PdfWriter = _import_pypdf()
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)

    writer.encrypt(user_password=user_password, owner_password=owner_password or None)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with output_file.open("wb") as fp:
        writer.write(fp)
    return output_file
