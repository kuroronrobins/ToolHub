# ToolHub Beta VM Test Package

This package is for Beta Phase 1-B validation in a clean Windows VM.

Copy the whole `ToolHub_Beta_VM_Test` folder into the VM or expose it through a VM shared folder. Do not install Python, Node.js, npm, Rust, cargo, Tauri CLI, or pip packages in the VM before running this test.

## Contents

- `release\manifest.json`
- `release\dist_installer\ToolHub_Setup_0.1.0.exe`
- `release\staging\installer_payload\staging_manifest.json`
- `vm_install_test.ps1`
- `checksums.json`
- `checksums.sha256.txt`
- `results\`

## Run In The VM

Open PowerShell in the package root and run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\vm_install_test.ps1 -SharedRoot . -ResultsDir .\results -PauseForManualGuiChecks
```

The installer and uninstaller are interactive. Do not choose any option that deletes user data.

## Expected Checks

The script records these checks automatically where possible:

- `python` is not found in `PATH`.
- `pip` is not found in `PATH`.
- `node` is not found in `PATH`.
- `npm` is not found in `PATH`.
- `rustc` is not found in `PATH`.
- `cargo` is not found in `PATH`.
- `tauri` is not found in `PATH`.
- `ToolHub_Setup_0.1.0.exe` exists.
- installer sha256 / size match `release\manifest.json`.
- installer can be executed.
- `%LOCALAPPDATA%\Programs\ToolHub\ToolHub.exe` is created.
- installed payload includes `runner`, `apps`, `runtime`, `config.default`, and `release`.
- installed payload includes `runtime\python\python.exe`.
- installed payload includes `runtime\web_automation_runtime`.
- ToolHub starts.
- `%LOCALAPPDATA%\ToolHub` is created.
- uninstall can run when an uninstaller exists.
- `%LOCALAPPDATA%\ToolHub` remains after uninstall.
- reinstall can run after uninstall.
- `%LOCALAPPDATA%\ToolHub` remains after reinstall.

## Manual Checks

When prompted, confirm these in the VM:

- app cards are visible.
- `sample_gui_app` launches.
- `sample_playwright_app` launches.
- installer / uninstaller prompts do not require deleting user data.

If a prompt offers to delete user data, do not select it. Record that prompt behavior in the result notes when reporting back.

## Results To Return

After the run, copy these files back to the host:

- `results\latest_vm_install_result.json`
- `results\latest_vm_install_result.md`
- any timestamped `results\vm_install_result_*.json`
- any timestamped `results\vm_install_result_*.md`

If the test fails, also report:

- the PowerShell console output
- screenshots of installer / uninstaller errors
- `%LOCALAPPDATA%\ToolHub` path existence
- `%LOCALAPPDATA%\Programs\ToolHub` path existence

## Notes

- This VM validation is the clean-environment proof path.
- The host PATH isolation test is only a smoke test.
- Do not edit installer artifacts or manifests inside the VM.
- Remote update endpoint validation is outside this package.
