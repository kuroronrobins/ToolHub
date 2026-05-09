# ToolHub Beta VM Install Test

This is the Phase 1-B clean-environment validation path when Windows Sandbox is unavailable, such as on Windows Home / Core.

The VM flow is the closest proof that ToolHub can be installed and launched on a user PC without Python, Node.js, npm, Rust, cargo, Tauri CLI, or pip packages.

## VM Type

No VM product is required. Use any clean Windows VM, for example:

- Hyper-V VM
- VMware VM
- VirtualBox VM
- another clean Windows machine or clean Windows user profile

Use a shared folder that exposes this repository or a minimal release bundle containing:

- `release\manifest.json`
- `release\dist_installer\ToolHub_Setup_0.1.0.exe`
- `scripts\beta_vm\vm_install_test.ps1`
- a writable `scripts\beta_vm\results\` folder, or another writable results path passed with `-ResultsDir`

## Run In The VM

From the shared folder inside the VM:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\beta_vm\vm_install_test.ps1 -PauseForManualGuiChecks
```

If the shared folder path is not the repository root:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File C:\Shared\scripts\beta_vm\vm_install_test.ps1 -SharedRoot C:\Shared -ResultsDir C:\Shared\scripts\beta_vm\results -PauseForManualGuiChecks
```

Do not install Python, Node.js, Rust, npm, cargo, or Tauri CLI in the VM before the test.

## What It Checks

- developer tools are absent from `PATH`.
- `ToolHub_Setup_0.1.0.exe` exists.
- installer `sha256` and `size` match `release\manifest.json`.
- installer can run.
- `%LOCALAPPDATA%\Programs\ToolHub\ToolHub.exe` exists.
- installed payload includes `runner`, `apps`, `runtime`, `config.default`, and `release`.
- installed payload includes `runtime\python\python.exe`.
- installed payload includes `runtime\web_automation_runtime`.
- ToolHub launches.
- `%LOCALAPPDATA%\ToolHub` is created.
- uninstall can run when an uninstaller is present.
- `%LOCALAPPDATA%\ToolHub` remains after uninstall.

## Manual Checks

When `-PauseForManualGuiChecks` is passed, the script asks for:

- app cards visible in ToolHub.
- `sample_gui_app` launch result.
- `sample_playwright_app` launch result.

If you do not pass `-PauseForManualGuiChecks`, these are recorded as `manual_check`.

## Results

Results are written to:

```text
scripts\beta_vm\results\
```

Each run creates:

- `vm_install_result_<timestamp>.json`
- `vm_install_result_<timestamp>.md`
- `latest_vm_install_result.json`
- `latest_vm_install_result.md`

The results folder is ignored except for `.gitkeep`.

## Safety

- Do not run this on a host profile that contains important ToolHub user data.
- Do not select any installer or uninstaller option that deletes user data.
- Do not edit installer artifacts or release manifests in the VM.
- Keep endpoint / updater validation for the later Beta endpoint phase.
