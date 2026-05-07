# Release Readiness Cleanup

This document tracks Phase 6 cleanup and formal release readiness work for ToolHub app management.

Phase 6 started as an inventory and ordering phase. After owner confirmation, the four disabled stale entries listed in
this document were cleaned from `release/app_manifest.json`. Phase 6 still does not delete source-present apps, generate
App Packs, bundle runtime, or build installers.

## Current Report Command

Use the read-only report script:

```powershell
.\scripts\report_release_readiness.ps1
.\scripts\report_release_readiness.ps1 -Json
```

The script classifies existing warnings into cleanup work, packaging work, release-build work, intentional warnings, and
blocked local-environment items. It does not write files.

## Current Snapshot

The current repository snapshot after confirmed stale cleanup is:

- manifest entries: 7
- app sources: 7
- enabled with source: 5
- enabled missing source: 0
- disabled with source: 2
- disabled stale: 0
- source missing from manifest: 0

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
- Apps with missing App Packs but valid source.
- Runtime and installer warnings.
- Local toolchain warnings.

## App Pack Rebuild Candidates

These have app source but their manifest package zip is absent in `release/app_packs/`:

- `addnum_pdf`
- `app_20260201_agendasnap`
- `officetopdf_toc`
- `run_xcgate_upload`
- `sample_cli_app`
- `sample_gui_app`
- `sample_playwright_app`

Recommended action:

```powershell
.\scripts\package_app_pack.ps1 -AppId <app_id>
```

Stale entries have been cleaned, so App Pack regeneration is now the next app-specific release readiness task.

## Runtime Packaging Required

Current runtime readiness items:

- `runtime/python/python.exe` is missing.
- `runtime/web_automation_runtime/` has no bundled runtime files beyond placeholder/readme files.

These are shared runtime packaging tasks. They must not be resolved by deleting apps.

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
2. Regenerate App Packs for source apps.
3. Package shared runtime.
4. Build installer/release artifacts.
5. Decide and implement the strict `runtime/app_envs/<app_id>` policy for frozen-folder apps.
6. Run normal verification.
7. Move to strict/formal verification after generated artifacts and strict policy are handled.

## Remaining Work This Phase Does Not Do

- It does not delete source-present apps.
- It does not remove manifest entries beyond owner-confirmed disabled stale cleanup.
- It does not remove App Pack zip files.
- It does not remove staging artifacts.
- It does not remove runtime app_env folders.
- It does not remove backups.
- It does not bundle runtime.
- It does not build installers.
