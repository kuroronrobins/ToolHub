from __future__ import annotations

from typing import Any

from ..schemas import as_path
from ..services.pdf_document import inspect_pdf


def handle(request: dict[str, Any]) -> dict[str, Any]:
    source = as_path(request.get("sourcePath"), "sourcePath")
    password = request.get("password") if isinstance(request.get("password"), str) else ""
    return inspect_pdf(source, password=password)
