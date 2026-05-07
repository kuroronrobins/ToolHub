# Full Delete Executor Design

## 1. Purpose

This document defines the Phase 3 design for the future ToolHub full-delete executor.

The executor's job is to turn an already validated delete plan into ordered cleanup of repo-managed app-owned targets.
Phase 3 defined the execution contract and dry-run entry point. Phase 4 adds a guarded Apply mode only for temporary
fixture roots so a temporary app can be deleted end to end before production deletion is enabled.

## 2. Scope

Full delete may remove only ToolHub repo-managed targets that belong to the selected app.

Delete targets:

- `apps/<app_id>/`
- the target entry in `release/app_manifest.json`
- `release/app_packs/<app_id>-*.zip`
- the App Pack path recorded in the manifest `package` field
- strict staging targets from `release/staging/`
- `runtime/app_envs/<app_id>/`
- `backups/app_studio/**/<app_id>/`
- legacy `backups/app_lifecycle/**/<app_id>/`

Delete exclusions:

- external source folders
- external App Studio output mirrors
- `%LOCALAPPDATA%/ToolHub/data/`
- logs
- browser profiles
- app_state
- `runtime/python/`
- `runtime/web_automation_runtime/`
- staging candidates
- shared runtime folders
- repo-external paths

`release/app_manifest.json` is never a file-level delete target. Full delete may remove only the target app entry inside
that JSON file.

## 3. Execution Modes

### Plan

Plan mode builds the existing deletion plan only. It is represented today by:

```powershell
.\scripts\plan_app_delete.ps1 -AppId <id> -DryRun
```

It does not order the future executor steps and does not delete files.

### DryRun

DryRun mode uses a fresh plan and prints the exact execution order that a future apply mode would follow. It must not
write files, remove files, rewrite manifests, or modify app state.

The Phase 3 skeleton is:

```powershell
.\scripts\execute_app_delete.ps1 -AppId <id> -DryRun
```

If no mode is specified, the script defaults to DryRun. The default is intentionally non-destructive so an omitted switch
cannot become destructive.

### Apply

Apply mode performs deletion only for a temporary fixture in Phase 4. Production Apply remains unimplemented.

```powershell
.\scripts\execute_app_delete.ps1 -AppId <temp_id> -ProjectRoot <temp_fixture> -Apply -AllowTemporaryAppApply
```

Without the temporary gate, `-Apply` is refused. With the gate, it is still refused unless every temporary-only safety
condition passes.

Temporary-only gate:

- `-Apply` must be explicit.
- `-AllowTemporaryAppApply` must be explicit.
- `-ProjectRoot` must be explicit.
- `ProjectRoot` must not be the production repository root.
- `ProjectRoot` must be under the system temp directory.
- `app_id` must start with `__delete_e2e_` or `delete_e2e_`.
- The regenerated plan must have no safety errors.
- Every file-system delete target must resolve under `ProjectRoot`.
- `release/app_manifest.json` may only be changed by removing the target entry.
- staging candidates and excluded targets must not be deleted.

## 4. Delete Ordering

The executor should use this order:

1. Regenerate the plan immediately before execution.
2. Validate that the plan is safe and current.
3. Confirm excluded targets are not present in delete targets.
4. Delete generated/cache/history targets:
   - App Pack zip files.
   - strict staging targets.
   - `runtime/app_envs/<app_id>/`.
   - app-specific backup/history folders.
5. Delete the app source `apps/<app_id>/`.
6. Remove the app entry from `release/app_manifest.json`.
7. Save `release/app_manifest.json`.
8. Run `scripts/diagnose_app_manifest.ps1`.
9. Run `scripts/rebuild_app_manifest.ps1 -DryRun`.
10. Run `scripts/verify_release.ps1`.
11. Run `scripts/check_all.ps1`.

The manifest entry is removed after repo-local artifacts so a failed early cleanup still leaves visibility and diagnosis
through the manifest. If a later run sees already-missing generated targets, it treats them as already clean.

## 5. Plan Freshness

Apply must never rely on a stale UI snapshot alone. Before deleting, the executor must rebuild the plan and compare the
operator-visible snapshot against fresh state.

Freshness fields:

- `app_id`
- manifest entry existence
- manifest `version`
- manifest `package` path
- source directory existence
- delete target count
- excluded target count
- each target `comparison_key`
- each target `normalized_path`
- plan `generated_at`
- `plan_schema_version`

`plan_app_delete.ps1` and the Tauri helper already expose normalized paths and comparison keys. Phase 4 should add
`generated_at` and `plan_schema_version` before Apply is enabled.

## 6. Failure Handling

Restore and backup-based soft delete are intentionally not part of the final model.

Failure handling is therefore based on detection and idempotent re-run:

- Stop immediately when a safety check fails.
- Report which ordered step failed.
- Leave excluded targets untouched.
- After a partial failure, run the plan again to show remaining repo-managed targets.
- Allow a later run to clean the remaining targets.
- Treat missing generated targets as already clean.
- Treat a missing manifest entry as already clean only after other targets have been checked.
- Report leftover generated/history targets after post-delete validation.

The future Apply implementation should return enough detail for the Delete tab and logs to show completed, skipped, and
failed steps.

## 7. Idempotency

The executor must be safe to run again for the same app id:

- A missing App Pack zip is `already clean`.
- A missing staging target is `already clean`.
- A missing runtime app_env is `already clean`.
- A missing backup/history folder is `already clean`.
- A missing `apps/<app_id>/` source directory is `already clean`.
- A missing manifest entry is `already clean`.
- Existing excluded targets are not errors.

Idempotency does not mean ignoring unsafe targets. If a delete target resolves outside the repo, points to shared runtime,
or represents a staging candidate, the executor must fail before deletion.

## 8. Safety Checks

Required pre-delete checks:

- Validate `app_id` with the same character policy as the planner.
- Resolve every file-system delete target to a full path.
- Delete only paths inside the ToolHub repo root.
- Reject path traversal and empty paths.
- Reject external references as delete targets.
- Reject user data as delete targets.
- Reject shared runtime as delete targets.
- Reject staging candidates as delete targets.
- Reject deletion of `release/app_manifest.json` as a file.
- Allow only entry removal inside `release/app_manifest.json`.
- Ensure excluded targets have `delete_allowed=false`.
- Ensure delete targets have `delete_allowed=true`.
- Rebuild the plan immediately before Apply.

The executor must not infer ownership from app_id substring matching. It must use the planner's strict App Pack and
staging rules.

## 9. Temporary App E2E Plan

Phase 4 implements Apply only for a temporary fixture.

Temporary app E2E steps:

1. Create a temporary app such as `apps/__delete_e2e_<guid>/`.
2. Add a temporary entry to `release/app_manifest.json`.
3. Create a placeholder App Pack zip under `release/app_packs/`.
4. Create strict staging targets under `release/staging/<app_id>/` and `release/staging/<app_id>-<version>/`.
5. Create one ambiguous staging candidate and prove it is not deleted.
6. Create `runtime/app_envs/<app_id>/`.
7. Create app-specific `backups/app_studio/**/<app_id>/` and legacy `backups/app_lifecycle/**/<app_id>/`.
8. Put dummy external absolute paths in `app.yaml`.
9. Treat user-data paths as excluded references; do not create or delete real user data.
10. Run Apply against the temporary app only.
11. Verify every delete target is gone.
12. Verify external references, user-data references, shared runtime, and staging candidates remain.
13. Verify the manifest entry is gone and the manifest file remains valid JSON.
14. Re-run Apply to prove idempotency.
15. Run production-repo `diagnose_app_manifest`, `rebuild_app_manifest -DryRun`, `verify_release`, and `check_all` as
    separate validation so fixture cleanup is not confused with production state.
16. Clean up any temporary leftovers and confirm `git status --short` has no temporary artifacts.

`scripts/test_app_full_delete_e2e.ps1` is the Phase 4 regression test for this flow. Production deletion must wait until
Phase 5.

## 10. Production Command Design

Proposed future commands:

- `app_studio_full_delete_plan`
- `app_studio_full_delete_apply`
- `scripts/execute_app_delete.ps1 -AppId <id> -DryRun`
- `scripts/execute_app_delete.ps1 -AppId <id> -Apply`

Phase 4 implements temporary-fixture Apply in the script entry point. Production `-Apply` is deliberately rejected.

Phase 5 may add production Tauri command support after reviewing the temporary E2E evidence and preserving the
temporary-only test as a regression guard.
