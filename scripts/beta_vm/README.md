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
- environment paths are recorded: `LOCALAPPDATA`, `APPDATA`, `ProgramFiles`, `ProgramFiles(x86)`, `USERPROFILE`, and user name.
- installer process start / finish, exit code, timeout state, and ToolHub processes before / after installer are recorded.
- expected install dir `%LOCALAPPDATA%\Programs\ToolHub` is checked, but the script also searches for the actual install location.
- install location discovery checks `%LOCALAPPDATA%\Programs\ToolHub`, `%LOCALAPPDATA%\ToolHub`, `%ProgramFiles%\ToolHub`, `%ProgramFiles(x86)%\ToolHub`, `%LOCALAPPDATA%\Programs\com.toolhub.launcher`, `%LOCALAPPDATA%\Programs\ToolHub*`, Start Menu shortcut targets, uninstall registry entries, and running ToolHub processes.
- every discovered `ToolHub*.exe` is recorded with path, size, and modified time.
- the ToolHub exe actually launched by the script, or already running after the installer, is recorded.
- installed payload discovery checks each discovered install dir, `resources`, and legacy Tauri `_up_\_up_` resource roots for `runner`, `apps`, `runtime`, `config.default`, and `release`.
- install dir and user data dir separation is checked so `%LOCALAPPDATA%\ToolHub` is not accepted as the install root.
- installed payload includes `runtime\python\python.exe`.
- installed payload includes `runtime\web_automation_runtime`.
- installed payload includes `release\manifest.json` and `release\app_manifest.json`.
- `%LOCALAPPDATA%\ToolHub` logs are scanned for launcher/backend errors where possible.
- `likely_failure_category` is recorded as one of `installer_not_completed`, `install_dir_unexpected`, `installed_payload_missing`, `apps_not_in_payload`, `root_resolution_failed`, `app_manifest_load_failed`, `app_yaml_load_failed`, `user_data_or_config_issue`, or `unknown`.
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
