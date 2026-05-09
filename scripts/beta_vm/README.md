# ToolHub Beta VM Install Test

This is the Phase 1-B clean-environment validation path when Windows Sandbox is unavailable, such as on Windows Home / Core.

The VM flow is the closest proof that ToolHub can be installed and launched on a user PC without Python, Node.js, npm, Rust, cargo, Tauri CLI, or pip packages.

## VM Type

No VM product is required. Use any clean Windows VM, for example:

- Hyper-V VM
- VMware VM
- VirtualBox VM
- another clean Windows machine or clean Windows user profile

First create the minimal VM package on the host:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\beta_vm\prepare_vm_test_package.ps1 -DryRun
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\beta_vm\prepare_vm_test_package.ps1
```

Then copy or share this generated folder with the VM:

```text
scripts\beta_vm\package\ToolHub_Beta_VM_Test\
```

The package contains:

- `release\manifest.json`
- `release\dist_installer\ToolHub_Setup_0.1.0.exe`
- `release\staging\installer_payload\staging_manifest.json`
- `vm_install_test.ps1`
- `VM_TEST_PACKAGE_README.md`
- checksum and package summary files
- a writable `results\` folder

## Run In The VM

From the package root inside the VM:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\vm_install_test.ps1 -SharedRoot . -ResultsDir .\results -PauseForManualGuiChecks
```

If using the full repository as the shared folder instead of the generated package:

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
- reinstall can run after uninstall.
- `%LOCALAPPDATA%\ToolHub` remains after reinstall.

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

After copying VM results back to the host, summarize them with:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\beta_vm\import_vm_test_result.ps1
```

## Safety

- Do not run this on a host profile that contains important ToolHub user data.
- Do not select any installer or uninstaller option that deletes user data.
- Do not edit installer artifacts or release manifests in the VM.
- Keep endpoint / updater validation for the later Beta endpoint phase.
