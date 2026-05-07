# App Management Model

This document defines the target model for ToolHub app management. The goal is to operate apps safely with two final
actions: hide and full delete.

## Source Of Truth

The source of truth for one app is `apps/<app_id>/`:

- `apps/<app_id>/app.yaml`
- `apps/<app_id>/README.md`
- `apps/<app_id>/requirements.txt`
- `apps/<app_id>/requirements.lock`
- `apps/<app_id>/icon.png` or `icon.svg`
- `apps/<app_id>/bin/`
- bundled assets required by the app

`release/app_manifest.json` is not the manual source of truth. It remains for compatibility, launcher visibility,
update checks, and release verification, but it is treated as a release index that can be rebuilt from `apps/`.

`enabled` is currently kept in `release/app_manifest.json` as operational visibility state. Rebuild tools preserve the
existing `enabled` value for apps that still have source.

## Derived And Shared Data

Derived/generated app data:

- `release/app_manifest.json`
- `release/app_packs/<app_id>-*.zip`
- `release/staging/**`
- `runtime/app_envs/<app_id>/`

Repository-local history:

- `backups/app_studio/**/<app_id>/`
- `backups/app_lifecycle/**/<app_id>/` legacy only

Shared runtime:

- `runtime/python/`
- `runtime/web_automation_runtime/`

The shared runtime folders are never owned by one app.

## Delete Plan Categories

Future full delete may remove these categories:

- `managed_required`: `apps/<app_id>/` and the app entry in `release/app_manifest.json`.
- `managed_generated`: App Pack zip files, release staging artifacts, and `runtime/app_envs/<app_id>/`.
- `managed_history`: App Studio backups and legacy lifecycle backups for the app.

Future full delete must exclude these categories:

- `external_reference`: external absolute paths stored in `app.yaml`, such as `build.source_entry` or
  `build.output_mirror`.
- `user_data`: `%LOCALAPPDATA%/ToolHub/data/`, logs, browser profiles, and app state.
- `shared_runtime`: `runtime/python/` and `runtime/web_automation_runtime/`.

`release/app_manifest.json` is represented as an entry-level delete target. The file itself is not a delete target.

## Delete Plan Matching Rules

The deletion plan must avoid app id substring matches. This is especially important for short app ids such as `test`.

App Pack targets are:

- the package path recorded in the manifest entry, when present
- `release/app_packs/<app_id>-*.zip`

Release staging targets are included only when a path segment clearly belongs to the app:

- a segment exactly equals `<app_id>`
- a segment exactly equals `<app_id>-<version>`
- a segment starts with `<app_id>-<version>.` or `<app_id>-<version>-`

Other staging paths that merely contain the app id are reported as `managed_generated_candidate` excluded targets with a
warning. They are not delete targets until a human or a stricter generator rule proves ownership.

External absolute paths found in `app.yaml`, including `build.source_entry` and `build.output_mirror`, are reference
information only. They are always excluded from delete targets.

## Current Delete Tab

The current App Studio Delete tab is an App Management MVP:

- Hide sets `enabled=false`.
- Show sets `enabled=true` only when `apps/<app_id>/app.yaml` exists.
- Plan displays repository-managed delete targets and excluded targets.
- Full delete execution is disabled/not implemented.

The plan view separates delete targets, excluded targets, warnings, and blocking reasons. It also labels manifest work as
an entry removal plan rather than file deletion.

Restore, backup-based soft delete, and confirmation-input flows are intentionally removed from the target model.

## Manifest Rebuild

`scripts/rebuild_app_manifest.ps1 -DryRun` rebuilds the release index from `apps/*/app.yaml` without writing files.
`-Apply` writes `release/app_manifest.json` intentionally. By default, stale entries whose source no longer exists are
not included in the rebuilt manifest. `-KeepStale` can preserve them for compatibility investigations.

If an App Pack zip exists, its SHA-256 is recalculated. If the zip is missing, the rebuilt entry uses an empty `sha256`
instead of preserving a stale hash.

Dry-run output reports added apps, changed apps, stale entries that would be removed, package-missing apps, and entries
whose rebuilt `sha256` would be empty.

## Full Delete Status

Full delete is not implemented in this phase. Before it is implemented, the deletion plan must be validated against:

- repository-managed required files
- generated release artifacts
- runtime app environments
- repository-local backups/history
- excluded external references
- excluded user data
- excluded shared runtime folders

No current command deletes existing app source, App Pack zip files, user data, or external source folders.
