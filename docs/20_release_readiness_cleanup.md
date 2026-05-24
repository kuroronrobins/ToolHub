# Release Readiness Cleanup

This document tracks Phase 6 cleanup and formal release readiness work for ToolHub app management.

Phase 6 started as an inventory and ordering phase. After owner confirmation, the four disabled stale entries listed in
this document were cleaned from `release/app_manifest.json`. App Packs for all seven source apps were regenerated and
`release/app_manifest.json` now points at the generated zip files with matching SHA256 values. Runtime packaging
operations are scripted for local archives, and this checkout now has Python/Web runtime files expanded from local
runtime sources. The archives and expanded runtime files remain Git-ignored release artifacts.
Phase 6 cleanup itself did not delete source-present apps or build installers. Later Beta Phase 1-A work generated the
current installer artifact and staging manifest. Later release work published `v0.1.5`; VM install / launch / app-card /
registered-app / bundled-runtime behavior is recorded in `docs/06_acceptance_checklist.md`, while current-profile
install/uninstall remains intentionally unrun.

## Current Report Command

Use the read-only report script:

```powershell
.\scripts\report_release_readiness.ps1
.\scripts\report_release_readiness.ps1 -Json
```

The script classifies existing warnings into cleanup work, packaging work, release-build work, intentional warnings,
blocked local-environment items, and Beta Ready readiness items. It does not write files.

## Current Snapshot

The current repository snapshot from `.\scripts\report_release_readiness.ps1` is:

- manifest entries: 6
- app sources: 6
- enabled with source: 6
- enabled missing source: 0
- disabled with source: 0
- disabled stale: 0
- source missing from manifest: 0
- package path missing: 0
- sha256 mismatch: 0
- App Pack rebuild candidates: 0
- installer build required: 0
- beta ready blockers: 0

Enabled apps with source:

- `app_20251123_excelbatchreplace`
- `app_20260201_agendasnap`
- `pdf_workbench`
- `run_3dx_create_ids`
- `run_3dx_download_pdfs`
- `run_xcgate_upload`

Disabled apps with source:

- none

Disabled stale entries:

- none

## Classification Rules

Do not treat every warning as a deletion request.

| Finding | Classification | Reason |
| --- | --- | --- |
| `enabled=true` and source missing | blocked / hide candidate | Launcher-visible state is unsafe. Restore source or hide first. |
| `enabled=false` and source missing | delete candidate | Stale release index/history. Remove only after owner confirmation. |
| source exists but App Pack zip missing | App Pack rebuild | The app source remains valid; regenerate generated artifact. |
| App Studio frozen-folder source missing `runtime.requirements_lock` target | source repair / App Pack blocker | The source app is not deletion-target material, but packaging and release verification must fail until `requirements.lock` is restored or regenerated. |
| shared runtime missing | runtime packaging required | Runtime is shared infrastructure, not app-owned cleanup. |
| installer missing | installer build required | Installer is release output, not app-owned cleanup. |
| app-specific `runtime/app_envs/<app_id>` missing | intentional warning / check adjustment candidate | Current normal App Studio frozen-folder registration does not use app_env as app source, but `verify_release.ps1 -Strict` currently escalates it to fail. |
| Visual Studio C++ tools missing | blocked local build environment | Required for local Windows release builds, not repo cleanup. |

## Cleaned Delete Candidates

The owner confirmed these disabled stale entries could be fully deleted. They were removed from
`release/app_manifest.json`. No source-present app was deleted, and no App Pack/staging/runtime/backup artifact existed
for these app ids in this checkout.

| app_id | Previous state | Cleanup performed | Repo-local generated artifacts found | Exclusions |
| --- | --- | --- | --- | --- |
| `app_20251123_excelbatchreplace` | disabled stale | manifest entry removed | none | external source, user data, shared runtime |
| `run_3dx_create_ids` | disabled stale | manifest entry removed | none | external source, user data, shared runtime |
| `test` | disabled stale | manifest entry removed | none | external source, user data, shared runtime |
| `test11` | disabled stale | manifest entry removed | none | external source, user data, shared runtime |

Current delete candidates:

- none

## Do Not Delete Candidates

These should not be treated as cleanup deletion targets in Phase 6:

- Runtime and installer warnings.
- Local toolchain warnings.

## App Pack Regeneration Results

Generated zip files under `release/app_packs/` are local release artifacts and are ignored by Git except for
`.gitkeep`. Exact package paths and hashes change when apps are regenerated. Treat `release/app_manifest.json` and
`.\scripts\report_release_readiness.ps1 -Json` as the current source for release-readiness status instead of copying a
static hash table into this document.

Current App Pack rebuild candidates:

- none

Regenerate all source app packs again after source changes:

```powershell
.\scripts\package_app_pack.ps1
```

## Runtime Packaging Status

Current runtime readiness items:

- `runtime/python/python.exe` exists and passes `verify_runtime.ps1 -RequireRuntime`.
- `runtime/web_automation_runtime/` contains Web automation runtime files and passes `verify_runtime.ps1 -RequireRuntime`.

These are local release artifacts in this checkout. The read-only report alone does not prove installed behavior, but
the 2026-05-24 VM follow-up recorded in `docs/06_acceptance_checklist.md` confirms bundled Python and Web runtime use in
an installed environment. These are shared runtime packaging tasks and must not be resolved by deleting apps.

## Beta Ready Report Section

`.\scripts\report_release_readiness.ps1` now also emits a read-only `beta_ready` section in JSON:

- `blockers`: items that prevent Beta Ready, including missing installer artifact, missing staging manifest, remote
  update source/config gaps, and updater features that are still not implemented.
- `warnings`: readiness issues that should be reviewed but are not always immediate blockers.
- `manual_checks`: checks that require an installed environment or release build machine, such as real install,
  uninstall, `%LOCALAPPDATA%` placement, bundled runtime use, and registered validation app launch.
- `future_formal_only`: formal-release items such as code signing, manifest signing, rollback, and App Pack/runtime
  unit update extensions.

The report remains read-only. It does not build installers, expand runtime archives, create App Packs, download update
payloads, or inspect/delete user data beyond repository-local path checks.

Current runtime packaging status:

- `scripts/prepare_runtime.ps1` accepts separate `-PythonArchive` / `-WebRuntimeArchive` inputs.
- `-PythonSha256` and `-WebRuntimeSha256` verify approved archives before extraction.
- Extraction is restricted to `runtime/python/` and `runtime/web_automation_runtime/`.
- `scripts/verify_runtime.ps1` reports normal warnings and strict `-RequireRuntime` failures.
- Local runtime archives were created under ignored `vendor/runtime/` from existing local Python 3.13.2 and Playwright
  runtime sources, then expanded with SHA256 verification.
- Runtime files under `runtime/python/`, `runtime/web_automation_runtime/`, and archives under `vendor/runtime/` remain
  Git-ignored and must be present on the release build machine.

## Installer Artifact Status

Current installer readiness items:

- `release/manifest.json` points to `ToolHub_Setup_0.1.5.exe` as the current installer artifact.
- `release/manifest.json` records installer `sha256=d5f00c4abc6ad4cc574204a200b33a49c91faa9777d679217644fc44369e20e6` and `size=327095798`.
- `scripts/verify_release.ps1 -RequireInstaller -RequireRuntime` passes for the current generated artifact set.
- `release/staging/installer_payload/staging_manifest.json` exists and captures the installer payload.

These checks prove artifact and manifest consistency only. `docs/06_acceptance_checklist.md` carries the VM install /
first-launch / app-card / registered-app / bundled-runtime confirmation. Uninstall / reinstall and existing config
preservation remain separate manual evidence items until the latest pass result files are imported.

## Phase 1-B Install Validation Status

Current PC read-only observation:

- `%LOCALAPPDATA%\Programs\ToolHub\` does not currently exist in this profile.
- `%LOCALAPPDATA%\ToolHub\` already exists in this profile.

Because existing user data is present, this current profile is not a clean install target. Do not run uninstall against
this profile as a destructive validation unless the data is backed up and a human explicitly approves current-profile
testing. Use a clean Windows user profile or VM for Phase 1-B.

Windows Sandbox support for Phase 1-B now exists under `scripts/beta_sandbox/`:

- `ToolHub_Beta_Install_Test.wsb` maps the host checkout read-only and maps only `scripts/beta_sandbox/results/`
  as writable.
- `run_sandbox_test.ps1 -DryRun` checks the installer artifact, release manifest, staging manifest, WSB mount
  boundaries, and Windows Sandbox availability without launching Sandbox.
- `sandbox_install_test.ps1` runs inside Sandbox, records developer-tool absence, installer preflight, install
  placement, bundled runtime, first launch, user data/log creation, and possible uninstall results to JSON / Markdown.
- GUI observations, including app cards and registered validation app launch, remain `manual_check` items until reviewed from the
  Sandbox session and result files.

The current PC is Windows Home / Core, so Windows Sandbox cannot be used here because `Containers-DisposableClientVM`
is unavailable. Keep the Sandbox flow for machines that support it, but use the fallback Phase 1-B flow on this PC:

- `scripts/beta_isolated_path/run_isolated_path_test.ps1` hides Python / pip / Node.js / npm / Rust / cargo / Tauri CLI
  from PATH only inside the script process and can launch ToolHub with `LOCALAPPDATA` redirected to ignored results.
  This is a useful dependency-smoke test, not proof of a clean user PC.
- The isolated PATH test has been run without `-DryRun`. The latest result is `overall_status=pass`: ToolHub stayed
  running for 15 seconds with the isolated PATH and created a user data directory under
  `scripts/beta_isolated_path/results/localappdata_20260510_005517/ToolHub`. The log/json file check remains a warning
  because first launch created `data/logs/` but no `.log` or `.json` file.
- `scripts/beta_vm/vm_install_test.ps1` is the clean-environment proof path. Run it inside a clean Windows VM via a
  shared folder. It records developer-tool absence, installer sha256 / size, installer execution, install directory,
  user data directory, bundled runtime, ToolHub launch, manual app checks, uninstall, and user data preservation.
- `scripts/beta_vm/prepare_vm_test_package.ps1` creates the ignored VM copy package under
  `scripts/beta_vm/package/ToolHub_Beta_VM_Test/`. It validates installer sha256 / size against `release/manifest.json`
  before copying and writes package checksum / summary files. The latest docs status treats the old package result under
  `scripts/beta_vm/package/.../results/` as stale unless a newer pass result is imported.
- The 2026-05-24 follow-up confirmed VM install / first launch / app card / registered app launch / bundled runtime
  behavior for the current release path. The repo-local `scripts/beta_vm/package/ToolHub_Beta_VM_Test/results/`
  snapshot may still contain an older dirty-VM failure and must not be used as the latest pass evidence.
- An initial VM run launched the ToolHub window but exposed an install-dir / user-data collision. Keep this as historical
  root-cause evidence only; it was followed by the install-dir hook and resource-root fixes.
- `scripts/beta_vm/vm_install_test.ps1` now records install location discovery, discovered `ToolHub*.exe` candidates,
  the launched/running process path, payload layout under discovered dirs and `resources`, launcher log matches, and a
  `likely_failure_category` value.
- The returned VM diagnostics identified the actual install dir / launched exe as `%LOCALAPPDATA%\ToolHub\toolhub.exe`,
  which collides with the planned user data root. They also showed likely Tauri relative resources under `_up_\_up_`.
  The next installer build maps resources to stable target paths, uses an NSIS hook to set the per-user install dir to
  `%LOCALAPPDATA%\Programs\ToolHub`, and keeps root resolution compatible with both the stable and legacy layouts.
- A later dirty VM rerun confirmed the new installer hash, but the installer still attempted to write under
  `%LOCALAPPDATA%\ToolHub\apps\...`. Generated NSIS showed Tauri inserts `NSIS_HOOK_PREINSTALL` after its initial
  `SetOutPath $INSTDIR`, so the hook now resets `SetOutPath $INSTDIR` after forcing `$INSTDIR` to
  `%LOCALAPPDATA%\Programs\ToolHub`.
- VM diagnostics now record pre-install old/new ToolHub path residue, tester-recorded installer write error paths, and
  `dirty_vm_previous_install_residue`. Old `%LOCALAPPDATA%\ToolHub` is treated as user data / previous residue and must
  not be deleted by the validation flow.
- Phase 1-B keeps the Beta installer target to NSIS only because the required artifact is `ToolHub_Setup.exe`; MSI
  generation is deferred outside the Beta blocker path.
- `scripts/beta_vm/import_vm_test_result.ps1` summarizes a returned `latest_vm_install_result.json`, including
  `discovered_install_dirs`, `discovered_toolhub_exes`, `launched_toolhub_exe`, `payload_layout_summary`, and the
  checklist reflection candidate without requiring the VM to exist on the host.

## Intentional Warnings
Normal verification can warn for:

- disabled stale entries kept as history until deletion is confirmed
- hidden apps with source
- missing app-specific `runtime/app_envs/<app_id>` folders

The missing app_env warnings are intentional under the current normal App Studio model because App Studio creates
shared-env apps under `apps/<app_id>/` and uses `runtime/envs/<env_id>`, not per-app environments under
`runtime/app_envs/<app_id>`.

## Docs / Check Adjustment Candidates

Before strict/formal release, decide the strict policy for app-specific `runtime/app_envs/<app_id>`:

- Keep as strict fail only for apps that explicitly use an app-env execution mode.
- Downgrade missing app_env to a warning for normal shared-env apps.
- Or require app.yaml metadata that distinguishes shared-env apps from app-env apps in release verification.

This is not an app deletion candidate. It is a validation policy decision because current normal App Studio registration
does not create `runtime/app_envs/<app_id>`.

## Blocked Items

Formal local release builds can be blocked when this shell cannot find:

- `link.exe`
- `cl.exe`

Use Developer PowerShell for Visual Studio, or install Visual Studio Build Tools with the C++ workload and Windows SDK.
For Codex or normal PowerShell sessions, run the read-only diagnosis first:

```powershell
.\scripts\diagnose_build_shell.ps1
```

If `VsDevCmd.bat` exists, run release-build commands through the wrapper so the Visual Studio Developer environment is
loaded in the same command session:

```powershell
.\scripts\run_in_vs_dev_shell.ps1 -Command "where.exe cl && where.exe link"
```

```powershell
.\scripts\run_in_vs_dev_shell.ps1 -Command "cargo check --manifest-path .\launcher\src-tauri\Cargo.toml"
```

The wrapper fixes missing MSVC PATH / INCLUDE / LIB setup. It does not bypass Windows Application Control. If
`rustc.exe` is blocked by policy, choose an allowlisted Rust toolchain path, run manually from an approved Developer
PowerShell, or use another release build machine.

## Recommended Next Order

1. Run `.\scripts\report_release_readiness.ps1` and capture the current state.
2. Preserve the generated local runtime archives or replace them with formally approved archives, then rerun
   `.\scripts\prepare_runtime.ps1` with SHA256 values if the runtime source changes.
3. Run `.\scripts\verify_runtime.ps1 -RequireRuntime` on the release build machine.
4. Preserve the current installer artifact set or rebuild it if source/runtime/app packs change.
5. If Windows Sandbox is available, run `.\scripts\beta_sandbox\run_sandbox_test.ps1 -DryRun`, then run the Sandbox
   install flow. On Windows Home / Core, run `.\scripts\beta_isolated_path\run_isolated_path_test.ps1 -DryRun` as a
   smoke test, then run the clean VM flow in `scripts/beta_vm/`.
6. Decide and implement the strict `runtime/app_envs/<app_id>` policy for normal shared-env apps.
7. Exercise the installed updater command against the `v0.1.5` endpoint for remote check, download, mismatch, cache
   boundary, and verified launch gating.
8. Generate a certificate-signed installer artifact and run `verify_release.ps1 -RequireInstallerSignature` when the
   release channel requires formal trust.
9. Move to strict/formal verification after generated artifacts, install validation, updater command checks, and strict
   policy are handled.

## Remaining Work This Phase Does Not Do

- It does not delete source-present apps.
- It does not remove manifest entries beyond owner-confirmed disabled stale cleanup.
- It does not remove App Pack zip files.
- It does not regenerate App Packs again unless source changes.
- It does not remove staging artifacts.
- It does not remove runtime app_env folders.
- It does not remove backups.
- It does not download runtime from the internet.
- It does not commit runtime archives or expanded runtime binaries to Git.
- The cleanup phase itself does not build installers; Beta Phase 1-A generated the current installer artifacts separately.
