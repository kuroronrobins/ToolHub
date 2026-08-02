# PDF Workbench ToolHub Launcher

This folder is the ToolHub registration source for PDF Workbench.

PDF Workbench itself remains a Tauri desktop application. This Python layer is
only a ToolHub-compatible entry point that launches the staged Tauri release
payload from `assets/payload/`.

The launcher intentionally does not fall back to development build paths. A
registration source is valid only when `assets/payload/pdf-workbench.exe` and
its release resources are present.

## Refresh Latest Payload

After changing the app, refresh the ToolHub payload with the release build and
stage script:

```powershell
npm run tauri build
npm run stage:toolhub
```

`npm run stage:toolhub` updates both this template's `assets/payload/` folder
and the generated registration tree under
`build/toolhub-registration/pdf_workbench/`. The script compares SHA256 hashes
between the release executable, template payload, and staged payload, then
writes the result to `toolhub-stage-manifest.json`.

Do not edit `build/toolhub-registration/` directly. Regenerate it from this
folder whenever ToolHub needs a fresh registration source.

## Commands

```powershell
python main.py --toolhub-smoke
python main.py --window main
python main.py
```

`--toolhub-smoke` does not open the GUI. It asks the staged Tauri executable to
verify the bundled Python runtime, the active `src-python` worker package, and
the worker `ping` command.

When ToolHub App Studio performs a shared-env startup probe, the launcher also
uses this smoke path instead of opening the real desktop window. Normal ToolHub
runtime launches still open the main window.

## Runtime Notes

- Microsoft Office is required for Word, Excel, and PowerPoint conversion.
- Office conversion uses Microsoft Office COM only.
- The Tauri payload owns PDF processing, session cache cleanup, and worker
  orchestration.
- Temporary PDF cache files are session-only and must not be registered as
  durable ToolHub app data.
