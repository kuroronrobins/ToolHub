# App Delete Execution Plan

## 1. Purpose

This document is the planning and governance document for ToolHub app deletion work.

Future Codex work on App Studio Delete, app hide/show, delete plans, deletion rehearsal, or full-delete execution must
read this document first. The task prompt should state which phase is being advanced. If a future task changes the
roadmap, update this document before or alongside the implementation and record the reason in the Plan Revision Log.

This document intentionally separates the plan from implementation. It does not mean full-delete execution is already
implemented.

## 2. Final Goal

The final App Studio Delete tab handles only two operations:

1. Hide
   - Set the target entry in `release/app_manifest.json` to `enabled=false`.
   - Keep `apps/<app_id>/`, App Pack zip files, release staging artifacts, runtime app_env, and history untouched.
   - Show again by setting `enabled=true`.

2. Full delete
   - No restore feature.
   - No backup-based soft delete.
   - No confirmation input.
   - Remove ToolHub repo-managed app-owned targets without leaving app-specific repository garbage.
   - Never delete external source folders, external output mirrors, user data, logs, browser profiles, app_state,
     shared runtime folders, or other user-owned data.

The final UI should remain simple: hide/show for visibility and full delete for permanent repo-local cleanup.

## 3. Current State

Implemented or established:

- `apps/<app_id>/` is the source of truth for an app.
- `release/app_manifest.json` is treated as a release index that can be checked and rebuilt from `apps/`.
- The Delete tab has been simplified to hide, show, and deletion-plan display.
- The full-delete button is disabled.
- `scripts/plan_app_delete.ps1 -AppId <id> -DryRun` exists.
- Tauri/Rust command `app_studio_delete_plan` exists.
- `scripts/test_app_delete_plan.ps1` validates PowerShell delete-plan target classification.
- `scripts/test_app_delete_plan_parity.ps1` compares PowerShell delete-plan output with the Tauri/Rust helper output.
- `scripts/rehearse_app_delete.ps1` creates a temporary app, validates the dry-run plan, and cleans up temporary data.
- `scripts/rebuild_app_manifest.ps1 -DryRun` previews release index rebuilds from `apps/`.
- `scripts/check_all.ps1` includes delete-plan, parity, and rehearsal validation.
- `scripts/execute_app_delete.ps1 -Apply -AllowTemporaryAppApply -ProjectRoot <temp-fixture>` can execute full delete
  only for temporary fixture apps.
- `scripts/test_app_full_delete_e2e.ps1` proves temporary-app full delete removes managed targets and preserves
  exclusions.
- Tauri/Rust command `app_studio_full_delete_apply` implements production full delete behind an authenticated admin
  session, fresh-plan validation, snapshot comparison, and repo-root safety checks.
- The Delete tab enables the full-delete button only after a deletion plan is displayed and passes UI-side safety
  conditions.

Not implemented:

- PowerShell production `-Apply`; the script remains dry-run plus temporary-fixture E2E only.
- Automated production-root delete tests against real apps.

## 4. Architecture Decisions

Source of truth:

- `apps/<app_id>/`

Derived app data:

- `release/app_manifest.json`
- `release/app_packs/`
- `release/staging/`
- `runtime/app_envs/<app_id>/`

History and management-generated data:

- `backups/app_studio/**/<app_id>/`
- legacy `backups/app_lifecycle/**/<app_id>/`

Shared data:

- `runtime/python/`
- `runtime/web_automation_runtime/`

Delete exclusions:

- external source folders
- external App Studio output mirrors
- user data
- logs
- browser profiles
- app_state
- shared runtime folders

Manifest entry deletion means removing only the target app entry from `release/app_manifest.json`. It does not mean
deleting `release/app_manifest.json` itself.

## 5. Roadmap

### Phase 0: Planning Governance

Purpose:

- Create this document.
- Make the delete execution roadmap explicit.
- Make future Codex prompts refer to a stable plan.

Completion conditions:

- `docs/18_app_delete_execution_plan.md` exists.
- Related docs link to this plan.
- Future prompts can reference this document.

Status:

- Done after this document is added and validated.

### Phase 1: Delete Plan Accuracy

Purpose:

- Make delete-plan target detection precise enough to support a future destructive executor.

Current state:

- Mostly implemented.
- App Pack matching uses the manifest package path plus `release/app_packs/<app_id>-*.zip`.
- Staging target and staging candidate are separated.
- External reference, user data, and shared runtime exclusions are represented.

Completion conditions:

- App Pack detection is strict.
- Staging target and candidate are separated.
- External reference, user data, and shared runtime are excluded.
- app_id substring matches do not pull in unrelated app artifacts.
- `scripts/test_app_delete_plan.ps1` passes.

### Phase 2: Parity and Rehearsal

Purpose:

- Compare PowerShell and Tauri/Rust delete-plan output.
- Rehearse future deletion using a temporary app without executing deletion.

Current state:

- Mostly implemented.
- `scripts/test_app_delete_plan_parity.ps1` exists.
- `scripts/rehearse_app_delete.ps1` exists.
- `scripts/check_all.ps1` runs both in dry-run form.

Completion conditions:

- `scripts/test_app_delete_plan_parity.ps1` passes.
- `scripts/rehearse_app_delete.ps1` passes.
- The checks are included in `scripts/check_all.ps1`.
- Temporary app source, manifest changes, App Pack placeholder, staging, runtime app_env, and backup artifacts are
  removed after rehearsal.

### Phase 3: Full Delete Executor Design

Purpose:

- Design the destructive executor before implementation.

Completion conditions:

- Dry-run and apply behavior are separated.
- Delete ordering is defined.
- Failure handling is defined.
- Exclusion guarantees are documented.
- The executor can be tested using temporary apps only.
- No real app deletion is required for design validation.

Current state:

- Done for the design stage.
- `docs/19_full_delete_executor_design.md` defines modes, ordering, freshness, failure handling, idempotency, safety
  checks, and temporary-app E2E requirements.
- `scripts/execute_app_delete.ps1` provides a dry-run-only executor entry point.
- `scripts/test_app_delete_executor_design.ps1` verifies dry-run output and confirms `-Apply` is rejected.
- At the end of Phase 3, full delete Apply remained unimplemented.

Resolved design decisions:

- Apply must rebuild the plan at execution time and compare it with any operator-visible snapshot.
- Stale or unsafe plans are refused before deletion.
- Missing generated targets are treated as already clean.
- Manifest work is entry removal inside `release/app_manifest.json`, never deletion of the manifest file.
- Cleanup is verified with diagnosis, manifest rebuild dry-run, release verification, and check_all.

Phase 4 start conditions:

- Keep `-Apply` disabled for production use.
- Add Apply only behind a temporary-app E2E guard.
- Use the ordering and safety checks from `docs/19_full_delete_executor_design.md`.
- Prove that a temporary app can be fully removed while excluded targets remain.

### Phase 4: Temporary App Full Delete E2E

Purpose:

- Execute full delete only against a temporary app and prove safety.

Current state:

- Done for the temporary-app scope.
- `scripts/test_app_full_delete_e2e.ps1` creates a temp fixture root outside the production repo.
- `scripts/execute_app_delete.ps1 -Apply` is accepted only with `-AllowTemporaryAppApply`, explicit temp `-ProjectRoot`,
  and a temporary app id prefix.
- Production root and unsafe app ids are rejected.
- The E2E verifies managed target deletion, exclusion preservation, manifest entry removal, idempotent re-run, and
  cleanup.

Completion conditions:

- Temporary `apps/<app_id>/` is deleted.
- Temporary manifest entry is deleted.
- Temporary App Pack zip is deleted.
- Temporary staging target is deleted.
- Temporary runtime app_env is deleted.
- Temporary backup/history is deleted.
- External reference, user data, and shared runtime remain.
- After cleanup, `git status --short` has no temporary artifacts.
- `scripts/check_all.ps1` passes.

Constraints:

- Do not use real apps for this phase.
- Do not delete external source folders.
- Do not delete user data.

### Phase 5: Production Full Delete Command

Purpose:

- Implement full delete for real apps after temporary E2E safety has been proven.

Completion conditions:

- Tauri command exists.
- Delete tab Delete button is enabled only for valid plans.
- The plan is shown before execution.
- Execution removes repo-managed targets and exclusions remain untouched.
- App list refreshes after deletion.
- `scripts/check_all.ps1` passes.
- Docs are updated.

Current state:

- Done for the guarded production UI path.
- `app_studio_full_delete_apply` regenerates the plan, compares the visible snapshot when provided, rejects unsafe
  targets, deletes only repo-managed targets, removes only the target manifest entry, and returns post-check details.
- The Delete tab keeps hide/show, displays the plan, and enables full delete only for supported states with visible,
  unblocked plans.
- PowerShell production Apply remains intentionally unimplemented to avoid a second destructive production entry point.

### Phase 6: Cleanup and Release Readiness

Purpose:

- Prepare app management for formal release and strict verification.

Completion conditions:

- Strict verification failures are intentional and tracked.
- Stale entry policy is explicit.
- Full delete no longer leaves app-owned repo garbage.
- Documentation distinguishes implemented, dry-run, design-only, and unimplemented behavior.

## 6. Plan Management Rules

- Codex must read this document before app deletion work.
- Codex must state which phase is being advanced.
- If new work changes the roadmap, update this document and add a Plan Revision Log entry.
- If unexpected issues appear, do not continue with ad hoc implementation that bypasses this plan.
- After implementation, update the relevant phase status when appropriate.
- Do not claim unverified work as verified.
- If full delete is not implemented, state that it is not implemented.
- If a destructive change, schema break, app.yaml break, runner I/F break, or user-data deletion becomes necessary,
  stop and report options instead of implementing it.

## 7. Current Phase Status

| Phase | Status | Evidence | Remaining Work | Next Action |
| --- | --- | --- | --- | --- |
| Phase 0: Planning Governance | Done | This document exists and is linked from related docs. | Keep this document current. | Use this plan in future prompts. |
| Phase 1: Delete Plan Accuracy | Mostly done | `plan_app_delete.ps1`, `app_studio_delete_plan`, `test_app_delete_plan.ps1`. | Continue adding edge-case fixtures as new artifact patterns appear. | Preserve strict matching rules. |
| Phase 2: Parity and Rehearsal | Mostly done | `test_app_delete_plan_parity.ps1`, `rehearse_app_delete.ps1`, `check_all.ps1`. | Add more fixtures if production artifacts become more varied. | Treat this as the safety baseline. |
| Phase 3: Full Delete Executor Design | Done | `docs/19_full_delete_executor_design.md`, `scripts/execute_app_delete.ps1`, `scripts/test_app_delete_executor_design.ps1`. | None for design scope. | Preserve the design contract as production work starts. |
| Phase 4: Temporary App Full Delete E2E | Done | `scripts/test_app_full_delete_e2e.ps1`, temporary-only `execute_app_delete.ps1 -Apply -AllowTemporaryAppApply`. | Keep production Apply disabled. | Start Phase 5 production command design and guarded implementation. |
| Phase 5: Production Full Delete Command | Done | `app_studio_full_delete_apply`, Delete tab full-delete enablement, Rust safety tests, Phase 4 E2E regression. | Keep PowerShell production Apply disabled unless a separate reviewed need appears. | Start Phase 6 cleanup and release readiness. |
| Phase 6: Cleanup and Release Readiness | Not started | Strict cleanup policy is not complete. | Review stale entries and formal release checks now that production UI deletion exists. | Audit stale entries and formal release checks. |

## 8. Decision Log

- Delete is limited to two final operations: hide and full delete.
- Restore is not part of the final app-management model.
- Backup-based soft delete is not part of the final app-management model.
- Confirmation input is not required by the final model.
- Full delete removes repo-managed app-owned targets.
- Full delete excludes user data, external source, external output mirrors, logs, browser profiles, app_state, and shared
  runtime.
- `apps/<app_id>/` is the app source of truth.
- `release/app_manifest.json` is a release index, not the source of truth.
- Manifest deletion means removing an app entry, not deleting the manifest file.
- PowerShell and Tauri/Rust delete-plan outputs must remain comparable.

## 9. Risk Register

| Risk | Mitigation | Owner/Area | Current Status |
| --- | --- | --- | --- |
| Accidental deletion | Use admin session, plan-first UI, fresh plan validation, snapshot comparison, and repo-root-only deletion. Keep PowerShell production Apply disabled. | Tauri command, scripts | Mitigated for UI path; real-app delete was not run in validation. |
| app_id substring match pulls in another app | Strict App Pack and staging matching. Ambiguous staging matches are excluded candidates. | Delete plan | Mostly mitigated. |
| Manifest entry remains after source deletion | Executor removes only the target entry and reports post-check state. | Full delete executor | Implemented in Tauri path. |
| App Pack remains after source deletion | Executor deletes manifest package path and `<app_id>-*.zip` targets from the plan. | Full delete executor | Implemented in Tauri path; production real-app deletion not exercised. |
| Staging artifact remains | Executor deletes strict staging targets and leaves candidates untouched. | Full delete executor | Implemented in Tauri path; production real-app deletion not exercised. |
| User data is deleted by mistake | User data is always an excluded category and forbidden in delete targets. | Delete plan, executor | Mitigated in plan and Tauri safety checks. |
| External source is deleted by mistake | External absolute paths are reference-only excluded targets and forbidden in delete targets. | Delete plan, executor | Mitigated in plan and Tauri safety checks. |
| PowerShell and Tauri logic diverge | Use normalized comparison keys and parity tests. | Scripts, Rust helper | Mostly mitigated for representative fixture. |
| Work stalls in preparation only | Use this roadmap and require phase progress in completion reports. | Planning governance | Monitored by this document. |

## 10. Next Planned Work

Next phase:

- Phase 6: Cleanup and Release Readiness.

Next implementation planning tasks:

- Review stale entries and formal release checks under the final hide/full-delete model.
- Decide whether strict verification should require stale cleanup before packaging.
- Keep the temporary E2E and Rust safety tests as regression guards for future deletion changes.
- Continue to keep PowerShell production Apply disabled unless it gets its own safety review.

## 11. Prompt Contract

Future Codex prompts for this area must follow this contract:

- Begin by reading `docs/18_app_delete_execution_plan.md`.
- State which phase is being advanced.
- If the task changes the roadmap, update this document first or in the same work.
- Record roadmap changes in the Plan Revision Log.
- Completion reports must include phase progress.
- Completion reports must distinguish implemented, dry-run-only, design-only, unimplemented, and unverified work.
- Do not bypass the Phase 5 Tauri safety path when changing production full delete.

## 12. Plan Revision Log

| Date | Change | Reason | Impact |
| --- | --- | --- | --- |
| 2026-05-08 | Initial plan created. | Move from ad hoc preparation to governed execution. | Future prompts will reference this document and report phase progress. |
| 2026-05-08 | Phase 3 executor design and dry-run skeleton added. | Define full-delete execution boundaries before any destructive implementation. | Phase 4 can now build temporary-app-only Apply against a documented ordering and safety contract. |
| 2026-05-08 | Phase 4 temporary-app full delete E2E added. | Prove Apply behavior in an isolated fixture before production support. | Production full delete can move to Phase 5 planning while `check_all` keeps the temporary E2E as a regression guard. |
| 2026-05-08 | Phase 5 production Tauri command and Delete tab enablement added. | Move full delete into the authenticated admin UI path after temporary E2E passed. | Phase 6 can focus on stale cleanup and release readiness; PowerShell production Apply remains disabled. |
