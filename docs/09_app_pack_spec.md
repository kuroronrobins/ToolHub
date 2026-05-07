# App Pack Spec

App Pack is a generated zip for distributing one ToolHub app. It is not the source of truth for an app.

## Source Of Truth

The app source of truth is `apps/<app_id>/`:

- `app.yaml`
- `README.md`
- `requirements.txt`
- `requirements.lock`
- `icon.png` or `icon.svg`
- `bin/`
- bundled assets required by the app

`release/app_manifest.json` remains for compatibility, launcher visibility, and update checks, but it is a release
index. It must be diagnosable and rebuildable from `apps/<app_id>/app.yaml`.

Generated or derived locations:

- `release/app_manifest.json`
- `release/app_packs/<app_id>-<version>.zip`
- `release/staging/`
- `runtime/app_envs/<app_id>/`

History locations:

- `backups/app_studio/**/<app_id>/`
- `backups/app_lifecycle/**/<app_id>/` legacy only

External source paths recorded in `app.yaml`, user data, logs, browser profiles, app state, and shared runtime folders
are not App Pack sources and are not deletion targets.

## Zip Layout

```text
<app_id>/
  app.yaml
  README.md
  requirements.txt
  requirements.lock
  icon.png or icon.svg
  bin/
  pack_manifest.json
  assets/
```

`scripts/package_app_pack.ps1` copies `apps/<app_id>/`, removes cache files, adds `pack_manifest.json`, then creates
the zip.

## Manifest Entry

Each `release/app_manifest.json` entry keeps the existing schema:

- `version`
- `package`
- `sha256`
- `required_core`
- `required_runner`
- `required_runtime`
- `enabled`

The version should come from `apps/<app_id>/app.yaml` `admin.version`. `required_runtime` should come from
`runtime.required_runtime` when present. `enabled` is operational state and is preserved when rebuilding the index.

If the App Pack zip exists, rebuild tools calculate `sha256` from the zip. If the zip does not exist, the rebuild plan
uses an empty `sha256`; a missing generated zip should not be hidden by preserving an old hash.

An empty `sha256` means the App Pack has not been generated or is not available in this checkout. Normal verification
warns when the package is missing or the hash is empty. Formal release checks should use `-RequireAppPacks` and strict
review so missing generated App Packs are not shipped accidentally.

## Entry State Rules

| State | Meaning | Normal verification | Strict/formal release |
| --- | --- | --- | --- |
| `enabled=true` and source exists | Active app | pass when metadata and package checks pass | pass only when package/runtime checks pass |
| `enabled=true` and source missing | Dangerous inconsistency | fail | fail |
| `enabled=false` and source exists | Hidden or not yet approved app | warn/pass depending package state | may fail until reviewed |
| `enabled=false` and source missing | Stale release index/history | warn | fail or require cleanup decision |
| source exists but manifest missing | App source not listed in release index | warn | fail |

Normal verification keeps disabled stale entries as warnings so old history does not block local development. Strict
verification can fail them before formal release.

## Packaging

Package all source apps:

```powershell
.\scripts\package_app_pack.ps1
```

Without `-AppId`, packaging uses `apps/*/app.yaml` as the target list and skips manifest-only stale entries. If a source
app is not listed in `release/app_manifest.json`, the script adds a disabled manifest entry derived from `app.yaml`.

Package one app:

```powershell
.\scripts\package_app_pack.ps1 -AppId sample_cli_app
```

Explicit packaging fails when `apps/<app_id>/app.yaml` is missing.

## Manifest Rebuild

Dry-run a rebuild from `apps/`:

```powershell
.\scripts\rebuild_app_manifest.ps1 -DryRun
```

Apply a rebuild intentionally:

```powershell
.\scripts\rebuild_app_manifest.ps1 -Apply
```

Default rebuild output excludes stale entries whose source no longer exists. Use `-KeepStale` only when compatibility
or investigation requires preserving those entries.

## Delete Plan

Preview future full deletion targets:

```powershell
.\scripts\plan_app_delete.ps1 -AppId addnum_pdf -DryRun
```

The plan lists:

- `managed_required`: `apps/<app_id>/` and the manifest entry
- `managed_generated`: App Pack zip, staging artifacts, `runtime/app_envs/<app_id>/`
- `managed_history`: App Studio and legacy lifecycle backups
- `external_reference`: excluded external paths from `app.yaml`
- `user_data`: excluded `%LOCALAPPDATA%/ToolHub/...` paths
- `shared_runtime`: excluded shared runtime folders

The script never deletes files.

App Pack matching uses the manifest package path plus `release/app_packs/<app_id>-*.zip`. Release staging matching does
not use plain substring matching: a staging path is a delete target only when a path segment equals `<app_id>`, equals
`<app_id>-<version>`, or starts with `<app_id>-<version>.` / `<app_id>-<version>-`. Ambiguous partial matches are shown
as excluded candidates and must not be deleted by an automated full-delete implementation.

`scripts/test_app_delete_plan_parity.ps1` compares the PowerShell planner and the Tauri/Rust helper on the same
temporary fixture. `scripts/rehearse_app_delete.ps1` creates a temporary repo-local app and generated/history artifacts,
checks that App Pack and staging targets are included only by the strict rules above, and then restores the manifest and
removes the temporary files. Both scripts are dry-run validation; they do not delete real App Pack or staging artifacts.

## Verification

```powershell
.\scripts\verify_release.ps1
.\scripts\diagnose_app_manifest.ps1
.\scripts\diagnose_app_manifest.ps1 -Strict
```
