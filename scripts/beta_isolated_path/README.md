# ToolHub Beta Isolated PATH Test

This is a Phase 1-B helper test for the current development PC when Windows Sandbox is unavailable.

It is not proof of a clean PC. It only proves that, for the launched process, ToolHub can start while common developer tools are hidden from `PATH`.

## What It Checks

- `python` is not visible from the isolated `PATH`.
- `pip` is not visible from the isolated `PATH`.
- `node` is not visible from the isolated `PATH`.
- `npm` is not visible from the isolated `PATH`.
- `rustc` is not visible from the isolated `PATH`.
- `cargo` is not visible from the isolated `PATH`.
- `tauri` is not visible from the isolated `PATH`.
- `ToolHub.exe` can be found from an installed location or local release build output.
- `runtime/python/python.exe` exists near the payload or repo.
- `runtime/web_automation_runtime` exists near the payload or repo.
- When not using `-DryRun`, `ToolHub.exe` starts with the isolated `PATH`.
- When not using `-DryRun`, `LOCALAPPDATA` and `APPDATA` are pointed at this helper's ignored `results` folder so host user data is not intentionally modified.

## Dry Run

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\beta_isolated_path\run_isolated_path_test.ps1 -DryRun
```

The dry run does not launch ToolHub. It checks PATH hiding, ToolHub.exe discovery, and runtime presence.

## Execute

Use this only after confirming you want to launch the local ToolHub executable:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\beta_isolated_path\run_isolated_path_test.ps1
```

To force a specific executable:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\beta_isolated_path\run_isolated_path_test.ps1 -ToolHubExePath "C:\Users\<you>\AppData\Local\Programs\ToolHub\ToolHub.exe"
```

## Results

Results are written to:

```text
scripts\beta_isolated_path\results\
```

The folder is ignored except for `.gitkeep`.

## Limitations

- This does not remove Python, Node.js, Rust, npm, cargo, or Tauri CLI from the host.
- This does not prove a clean Windows PC install.
- This does not run the installer.
- This does not prove the installed app uses only bundled runtime files.
- Full Phase 1-B proof still requires a clean Windows VM using `scripts\beta_vm\`.
