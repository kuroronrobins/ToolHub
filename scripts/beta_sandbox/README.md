# ToolHub Beta Sandbox Install Test

This folder contains the Phase 1-B Windows Sandbox flow for validating that `ToolHub_Setup_0.1.0.exe` can install and launch ToolHub in a clean Windows environment without developer tools.

## What This Does

- Mounts the host ToolHub checkout into Windows Sandbox as read-only at `C:\ToolHubRepo`.
- Mounts only `scripts\beta_sandbox\results` as writable at `C:\ToolHubBetaResults`.
- Runs `sandbox_install_test.ps1` when Sandbox logs in.
- Writes JSON and Markdown results back to the host results folder.
- Leaves host `%LOCALAPPDATA%\ToolHub` untouched.
- Does not edit release artifacts, manifests, runtime, app packs, or installer binaries.

## Prerequisites

Windows Sandbox requires Windows Pro, Enterprise, or Education, virtualization support, and the Windows Sandbox optional feature.

Check availability from the host:

```powershell
Get-Command WindowsSandbox.exe
Get-WindowsOptionalFeature -Online -FeatureName Containers-DisposableClientVM
```

If the feature is disabled, enable it from an elevated PowerShell session:

```powershell
Enable-WindowsOptionalFeature -Online -FeatureName Containers-DisposableClientVM -All
```

If Windows Sandbox is unavailable, run the same installer validation in a Hyper-V VM or a clean Windows user profile.

## Dry Run

Run this before launching Sandbox:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\beta_sandbox\run_sandbox_test.ps1 -DryRun
```

The dry run verifies:

- `release\manifest.json` exists.
- `release\dist_installer\ToolHub_Setup_0.1.0.exe` exists.
- installer size and sha256 match the release manifest.
- `release\staging\installer_payload\staging_manifest.json` exists.
- the `.wsb` maps the repo read-only and results writable.
- Windows Sandbox command / feature availability can be inspected.

## Launch

After dry run passes:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\beta_sandbox\run_sandbox_test.ps1
```

You can also open `ToolHub_Beta_Install_Test.wsb` directly.

The `.wsb` file currently targets this checkout path:

```text
C:\Users\kuroron\Documents\RD\20260426_Toolhub
```

If the checkout is moved, update `ToolHub_Beta_Install_Test.wsb` before launching.

## Sandbox Flow

The Sandbox script checks that these developer tools are not available from `PATH`:

- `python`
- `pip`
- `pip3`
- `node`
- `npm`
- `rustc`
- `cargo`

It then verifies the installer file, starts the installer, waits for it to finish, checks the installed payload, launches `ToolHub.exe`, checks user data/log creation, and attempts uninstall if an uninstaller executable is found.

The installer is intentionally run interactively. The silent installer option is not assumed because it has not been verified for this artifact. Complete the installer UI inside Sandbox. If an uninstaller prompt asks about user data, do not select any option that deletes user data.

The default `.wsb` command passes `-PauseForManualGuiChecks`. After `ToolHub.exe` starts, the PowerShell window waits while you confirm app cards and launch registered validation apps from the ToolHub GUI. Answer the prompts to record `pass`, `fail`, or `manual_check` in the result files.

## Results

Results are written on the host under:

```text
scripts\beta_sandbox\results\
```

Each run creates timestamped files and latest aliases:

- `sandbox_install_result_<timestamp>.json`
- `sandbox_install_result_<timestamp>.md`
- `latest_sandbox_install_result.json`
- `latest_sandbox_install_result.md`

The result status values are:

- `pass`: checked automatically and passed.
- `fail`: checked automatically and failed.
- `warning`: checked automatically but not conclusive.
- `manual_check`: requires GUI confirmation or human judgment.
- `not_run`: skipped because a prerequisite failed or the step was intentionally skipped.

## Manual Checks

The script can prompt for these checks when launched from the provided `.wsb` file:

- app cards are visible in ToolHub.
- a deliberately registered validation app launches from the installed ToolHub GUI.
- any installer / uninstaller prompt behavior that cannot be safely automated.

Do not mark Phase 1-B complete until the JSON / Markdown result files and GUI observations have been reviewed.
