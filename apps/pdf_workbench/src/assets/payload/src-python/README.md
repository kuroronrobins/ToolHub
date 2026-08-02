# PDF Workbench Python Engine

Active Python worker for PDF Workbench processing.

This code is the runtime processing location. Do not import or execute files from `archive/`.

## Runtime

The Tauri app launches this worker with:

```powershell
python -m pdf_workbench_engine.cli
```

Requests are JSON on stdin. Responses are JSON on stdout.

## Dependencies

- `pypdf` for PDF page assembly and encryption
- `PyMuPDF` for page rendering, thumbnails, and decoration overlays
- `pywin32` for Microsoft Office COM conversion on Windows

Microsoft Office is a runtime requirement for Word/Excel/PowerPoint conversion.
