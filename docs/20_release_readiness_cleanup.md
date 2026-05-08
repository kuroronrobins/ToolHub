# Release Readiness Cleanup

This document tracks Phase 6 cleanup and formal release readiness work for ToolHub app management.

Phase 6 started as an inventory and ordering phase. After owner confirmation, the four disabled stale entries listed in
this document were cleaned from `release/app_manifest.json`. App Packs for all seven source apps were regenerated and
`release/app_manifest.json` now points at the generated zip files with matching SHA256 values. Runtime packaging
operations are scripted for local archives, and this checkout now has Python/Web runtime files expanded from local
runtime sources. The archives and expanded runtime files remain Git-ignored release artifacts.
Phase 6 still does not delete source-present apps or build installers.

## Current Report Command

Use the read-only report script:

```powershell
.\scripts\report_release_readiness.ps1
.\scripts\report_release_readiness.ps1 -Json
```

The script classifies existing warnings into cleanup work, packaging work, release-build work, intentional warnings, and
blocked local-environment items. It does not write files.

## Current Snapshot

The current repository snapshot after App Pack regeneration is:

- manifest entries: 7
- app sources: 7
- enabled with source: 5
- enabled missing source: 0
- disabled with source: 2
- disabled stale: 0
- source missing from manifest: 0
- package path missing: 0
- sha256 mismatch: 0
- App Pack rebuild candidates: 0

Enabled apps with source:

- `sample_gui_app`
- `sample_cli_app`
- `sample_playwright_app`
- `officetopdf_toc`
- `app_20260201_agendasnap`

Disabled apps with source:

- `run_xcgate_upload`
- `addnum_pdf`

Disabled stale entries:

- none

## Classification Rules

Do not treat every warning as a deletion request.

| Finding | Classification | Reason |
| --- | --- | --- |
| `enabled=true` and source missing | blocked / hide candidate | Launcher-visible state is unsafe. Restore source or hide first. |
| `enabled=false` and source missing | delete candidate | Stale release index/history. Remove only after owner confirmation. |
| source exists but App Pack zip missing | App Pack rebuild | The app source remains valid; regenerate generated artifact. |
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

- Active source apps: `sample_gui_app`, `sample_cli_app`, `sample_playwright_app`, `officetopdf_toc`,
  `app_20260201_agendasnap`.
- Hidden but restorable source apps: `run_xcgate_upload`, `addnum_pdf`.
- Apps with valid source and regenerated App Packs.
- Runtime and installer warnings.
- Local toolchain warnings.

## App Pack Regeneration Results

These source apps were repackaged with `.\scripts\package_app_pack.ps1`. The generated zip files are local release
artifacts under `release/app_packs/`, which is ignored by Git except for `.gitkeep`.

| app_id | version | package | sha256 | enabled |
| --- | --- | --- | --- | --- |
| `addnum_pdf` | `0.1.0` | `app_packs/addnum_pdf-0.1.0.zip` | `de74ba6fc688f50c682493e0e3a5831473a51642b24611ee474e3464f0d17ceb` | `false` |
| `app_20260201_agendasnap` | `0.1.0` | `app_packs/app_20260201_agendasnap-0.1.0.zip` | `e6554b4e105e8dc23b4b37e39f85b7f0bfcb5f16d5f74b8b6858fcb9ad2982e2` | `true` |
| `officetopdf_toc` | `0.1.0` | `app_packs/officetopdf_toc-0.1.0.zip` | `04825531cfd0baafc9710f44fef83acbdaa8016e9e36b0a3e9bcbd7174c59d8c` | `true` |
| `run_xcgate_upload` | `0.1.0` | `app_packs/run_xcgate_upload-0.1.0.zip` | `44a5e93551f85787f500457b32fcc010d4b4c548f921481b57c12565cccbb13f` | `false` |
| `sample_cli_app` | `1.0.0` | `app_packs/sample_cli_app-1.0.0.zip` | `19aa0f02522babec8da842789a60abc4d41191deae593794ff663bca8ce34ccc` | `true` |
| `sample_gui_app` | `1.0.0` | `app_packs/sample_gui_app-1.0.0.zip` | `cd281ec55628dc9f39c63a214023c25654c81159cc76c76e695b85f465b17c17` | `true` |
| `sample_playwright_app` | `1.0.0` | `app_packs/sample_playwright_app-1.0.0.zip` | `1fdca7279e3d325c7bc18af19d2bb7881c9789ebd03d675f43c6081541f03487` | `true` |

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

These are shared runtime packaging tasks. They must not be resolved by deleting apps.

Current runtime packaging status:

- `scripts/prepare_runtime.ps1` accepts separate `-PythonArchive` / `-WebRuntimeArchive` inputs.
- `-PythonSha256` and `-WebRuntimeSha256` verify approved archives before extraction.
- Extraction is restricted to `runtime/python/` and `runtime/web_automation_runtime/`.
- `scripts/verify_runtime.ps1` reports normal warnings and strict `-RequireRuntime` failures.
- Local runtime archives were created under ignored `vendor/runtime/` from existing local Python 3.13.2 and Playwright
  runtime sources, then expanded with SHA256 verification.
- Runtime files under `runtime/python/`, `runtime/web_automation_runtime/`, and archives under `vendor/runtime/` remain
  Git-ignored and must be present on the release build machine.

## Installer Build Required

Current installer readiness items:

- `release/manifest.json` points to `release/dist_installer/ToolHub_Setup_0.1.0.exe`, but the file is not present.
- `release/staging/installer_payload/staging_manifest.json` is not present.

These are release build tasks. They must not be resolved by deleting apps.

## Intentional Warnings

Normal verification can warn for:

- disabled stale entries kept as history until deletion is confirmed
- hidden apps with source
- missing app-specific `runtime/app_envs/<app_id>` folders

The missing app_env warnings are intentional under the current normal App Studio model because App Studio creates
frozen-folder apps under `apps/<app_id>/`, not user runtime environments under `runtime/app_envs/<app_id>`.

## Docs / Check Adjustment Candidates

Before strict/formal release, decide the strict policy for app-specific `runtime/app_envs/<app_id>`:

- Keep as strict fail only for apps that explicitly use an app-env execution mode.
- Downgrade missing app_env to a warning for frozen-folder apps.
- Or require app.yaml metadata that distinguishes frozen-folder apps from app-env apps in release verification.

This is not an app deletion candidate. It is a validation policy decision because current normal App Studio registration
does not create `runtime/app_envs/<app_id>`.

## Blocked Items

Formal local release builds can be blocked when this shell cannot find:

- `link.exe`
- `cl.exe`

Use Developer PowerShell for Visual Studio, or install Visual Studio Build Tools with the C++ workload and Windows SDK.

## Recommended Next Order

1. Run `.\scripts\report_release_readiness.ps1` and capture the current state.
2. Preserve the generated local runtime archives or replace them with formally approved archives, then rerun
   `.\scripts\prepare_runtime.ps1` with SHA256 values if the runtime source changes.
3. Run `.\scripts\verify_runtime.ps1 -RequireRuntime` on the release build machine.
4. Build installer/release artifacts.
5. Decide and implement the strict `runtime/app_envs/<app_id>` policy for frozen-folder apps.
6. Run normal verification.
7. Move to strict/formal verification after generated artifacts and strict policy are handled.

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
- It does not build installers.
