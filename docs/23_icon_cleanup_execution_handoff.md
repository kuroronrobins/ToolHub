# App Studio icon cleanup execution handoff

Status: icon cleanup execution tracker. Phase 0 through Phase 7 are complete for the planned cleanup scope. Future work should treat this document as guardrails for maintaining the cleaned boundaries, not as a pending implementation handoff.

Date: 2026-05-09

## Purpose

This file records the completed App Studio icon cleanup phases and the guardrails that
future changes must preserve.

The cleanup preserved the current visible behavior:

- AI image API candidates remain the only generated candidates.
- Uploaded icon, when present, remains the highest-priority icon source.
- Adopted AI candidate remains the selected app icon.
- If no uploaded/adopted icon exists, ToolHub common default icon remains `icon.png`.
- Local generated fallback images must not return as candidates.
- `display.icon: icon.png` compatibility must be preserved.
- Existing saved proposals with legacy fallback fields should remain readable.

## Fallback term policy

Use these meanings consistently:

- `local fallback image candidate`: deprecated and removed. Do not regenerate local PNG/SVG alternatives and do not show them as candidates.
- `ToolHub common default icon`: the current icon written to `icon.png` when no uploaded icon or adopted AI candidate exists. It is not a candidate, not AI-generated, and not scored.
- `legacy fallback fields`: old proposal/manifest fields such as `fallback_png`, `provisional_fallback_png`, `fallback_candidate_count`, and old fallback candidates. They are accepted only for saved proposal compatibility.
- `deterministic text/prompt fallback`: deterministic prompt/concept text used when a text model is skipped or unavailable. This is not an image fallback candidate.
- `icon_work/icon_fallback.svg`: legacy SVG compatibility artifact only. Current icon selection is PNG-first and uses uploaded PNG, adopted API PNG, or the ToolHub common default icon.

Current Phase 3 through Phase 4 residuals to keep under control:

- `deterministic_icon_concepts` may remain as text concept generation fallback; it must not create images.
- `local-deterministic-fallback` may appear only as legacy input. New reports should prefer explicit text/image placeholder names.
- Deprecated fallback counters/reasons may be read from old manifests but should not be emitted by new writers.
- Pseudo quality fields may remain on candidate detail records, but normal UI must not rank or present them as a visual quality guarantee.
- `test/ToolHub_AppStudio_Output/...` contains old generated outputs. Treat these as legacy/generated artifacts unless a test explicitly references them.

## Phase 3-4 residual classification

Checked after Phase 3-4 cleanup on 2026-05-09. No residual requires returning
local fallback image candidates. Phase 5 has since isolated module boundaries
and compatibility handling; Phase 6 should keep using those boundaries.

| Residual term | Classification | Current action |
| --- | --- | --- |
| `fallback_icon_concepts` | docs history / search checklist only | No code action. Current code uses `deterministic_icon_concepts`. |
| `local-deterministic-fallback` | legacy input/read/display compatibility | Keep tolerant reads and UI display normalization. Do not emit as the new image model label. |
| `fallback_candidate_count` | legacy manifest/type compatibility, tests that assert new output omits it, generated legacy output | Keep reads optional. Do not emit in new `image_api_summary`. |
| `fallback_created_reason` / `fallbackCreatedReason` | legacy TypeScript summary compatibility / docs history | Keep optional fields only. Use `failure_class`, `failure_message`, and `admin_next_action` for current diagnosis. |
| `icon_provisional_fallback_used` | docs history only | No code action. Current `import_plan.json` output does not write it. |
| `icon_fallback.svg` | app.yaml/display fallback compatibility and legacy proposal artifact | Keep as legacy SVG compatibility artifact; do not show as an AI candidate. |
| `prompt_concept_only` | legacy manifest fixture / docs history | Keep only for old manifest tolerance. New candidate default is `rule_based_prompt_and_manifest`. |
| `fallback_rule_based` | legacy manifest status compatibility / docs history | Map old status to `deterministic_png_check` in current summaries. |
| pseudo quality fields | report/manifest detail only | Normal UI must show these only as "reference information" and must not rank or recommend by pseudo score. |

## Phase 5 implementation result

Implemented on 2026-05-09 as a mechanical module split with behavior preserved:

| Module | Responsibility |
| --- | --- |
| `icon_generator.py` | compatibility facade for existing imports only |
| `icon_pipeline.py` | initial icon generation, icon regeneration, file/report orchestration, and API call flow |
| `icon_prompt.py` | user-request-first prompt assembly, style settings, deterministic text concepts, and concept prompt parsing |
| `icon_candidates.py` | candidate path selection, API candidate checks, image result conversion, and legacy manifest fallback entry detection |
| `icon_diagnostics.py` | image API summary, failure diagnostics, report parsing, and report-friendly diagnosis output |
| `icon_quality.py` | deterministic PNG checks and rule-based reference score fields for API candidates |
| `icon_compat.py` | legacy fallback field/source/status normalization only |

Compatibility boundary:

- New output must continue to omit fallback candidate counters/reasons and must not create local fallback image candidates.
- `fallback_png`, `provisional_fallback_png`, `fallback_candidate_count`, `fallback_created_reason`, `fallback_rule_based`, and `prompt_concept_only` are accepted only through compatibility handling or legacy fixtures/docs.
- The ToolHub common default icon remains a current icon source for `icon.png`, not a candidate and not a score target.
- `icon_work/icon_fallback.svg` remains a legacy SVG compatibility artifact and was not renamed in Phase 5.

## Non-goals

Do not use the cleanup as an excuse to redesign unrelated App Studio flows.

Do not change:

- `app.yaml` public schema.
- App Pack spec.
- runner public interface.
- release manifest compatibility.
- existing apps under `apps/`.
- generated data under `data/`, `release/`, `runtime/`, `target/`, `dist/`, `logs/`, or app output folders.
- OpenAI image model selection behavior.
- AI API cost behavior unless the user explicitly asks.

## Current high-risk files

Review these before changing code:

- `tools/app_studio/app_studio/icon_generator.py`
- `tools/app_studio/app_studio/openai_client.py`
- `tools/app_studio/app_studio/exporter.py`
- `tools/app_studio/app_studio/icon_override.py`
- `tools/app_studio/app_studio/default_icon.py`
- `tools/app_studio/app_studio/models.py`
- `tools/app_studio/main.py`
- `launcher/src-tauri/src/app_studio_commands.rs`
- `launcher/src/components/admin/appstudio/AppStudioAiProposalPanel.tsx`
- `launcher/src/components/admin/appstudio/AppStudioImportWizard.tsx`
- `launcher/src/components/admin/appstudio/AppStudioLauncherPreview.tsx`
- `launcher/src/lib/appStudioTypes.ts`
- `launcher/src/lib/imageApiHealth.ts`
- `launcher/src/styles/app.css`
- `tools/app_studio/tests/`
- `docs/13_app_studio.md`
- `docs/14_admin_and_ai_settings.md`
- `docs/22_icon_generation_simplification_plan.md`

## Implementation order

### Phase 0: characterization before edits

Purpose:

- Confirm the current references before removing anything.
- Avoid deleting compatibility code that is still used by saved proposal readers.

Required checks:

```powershell
rg -n "generate_local_png|generate_local_svg|fallback_icon_concepts|local-deterministic-fallback|fallback_png|provisional_fallback_png|icon_fallback|fallback_candidate|fallbackCreatedReason|fallback_candidate_count|prompt_concept_only|fallback_rule_based" tools launcher docs scripts test
rg -n "selected_icon_source|icon_status|default_icon|uploaded_png|candidate_png|ai_candidate" tools launcher docs test
rg -n "display.icon|icon.png|icon.svg|icon_fallback" tools scripts docs launcher
```

Expected result:

- Local fallback image rendering should have no current production role except legacy tests/docs/compatibility.
- Default icon path should remain production-critical.
- Rust and TypeScript readers may still need legacy fallback parsing.

Stop if:

- A local fallback renderer is still required for `final_app/icon.png`.
- Removing a field would break saved proposal loading.
- `display.icon: icon.png` cannot be preserved.

### Phase 1: stale docs and stale labels only

Purpose:

- Remove contradictory documentation and UI wording without changing runtime behavior.

Allowed changes:

- Replace old "local fallback placeholder" docs with "ToolHub common default icon".
- Mark legacy fallback fields as compatibility-only.
- Remove or rename stale text that implies fallback is an AI candidate.

Do not:

- Change JSON schema yet.
- Delete code yet.

Validation:

```powershell
python -m unittest discover -s tools/app_studio/tests
```

### Phase 2: remove unused local fallback rendering

Status: completed in the first cleanup pass.

Purpose:

- Delete local generated icon rendering that no longer contributes to current behavior.

Completed removals after Phase 0 confirmed no production references:

- `generate_local_png`
- `generate_local_svg`
- local drawing helpers used only by those functions
- local palette/variant constants used only by those functions
- tests that assert local fallback image generation as a feature

Do not remove:

- `default_icon.py`
- default icon assets
- `icon_final.png` writing
- `final_app/icon.png` writing
- legacy saved proposal parsing

Compatibility rule:

- `icon_work/icon_fallback.svg` may be renamed only in a later phase. If still emitted for compatibility, keep it but document it as legacy.

Validation:

```powershell
python -m py_compile tools/app_studio/app_studio/openai_client.py tools/app_studio/app_studio/icon_generator.py tools/app_studio/app_studio/exporter.py tools/app_studio/app_studio/icon_override.py tools/app_studio/main.py
python -m unittest discover -s tools/app_studio/tests
```

### Phase 3: rename misleading fallback concept plumbing

Status: completed in the Phase 3-4 cleanup pass.

Purpose:

- Separate "AI concept fallback" from "image fallback candidate".

Preferred direction:

- Rename `fallback_icon_concepts` to `deterministic_icon_concepts`.
- Replace report/UI wording that suggests local images were generated.
- Keep generated prompt behavior unchanged.

Stop if:

- Prompt generation output changes substantially.
- Tests become snapshot-sensitive in a way that hides behavior drift.

Validation:

```powershell
python -m unittest discover -s tools/app_studio/tests
```

### Phase 4: simplify candidate metadata without breaking readers

Status: completed in the Phase 3-4 cleanup pass for new output and normal UI. Legacy readers still tolerate old fields.

Purpose:

- Keep candidate manifests focused on API candidates.
- Keep legacy readers tolerant of old manifests.

Allowed changes:

- Stop writing deprecated fallback counters in new reports if tests are updated.
- Move pseudo score fields to report-only or hide from normal UI.
- Keep old-field read compatibility in Rust/TS/Python.

Do not:

- Remove old-field parsing in the same step unless fixture coverage proves it is safe.
- Change `selected_icon_source` meanings without updating all readers.

Validation:

```powershell
python -m unittest discover -s tools/app_studio/tests
cd launcher
npm run build
cd src-tauri
cargo check
```

### Phase 5: split large icon modules

Status: implemented on 2026-05-09. `icon_generator.py` is now a compatibility facade, and the implementation is split into `icon_pipeline.py`, `icon_prompt.py`, `icon_candidates.py`, `icon_diagnostics.py`, `icon_quality.py`, and `icon_compat.py`.

Purpose:

- Reduce `icon_generator.py` complexity after dead code is gone.

Suggested module boundaries:

- `icon_prompt.py`: user-request-first prompt assembly.
- `icon_pipeline.py`: initial generation and regeneration orchestration.
- `icon_candidates.py`: candidate manifest objects and write/read helpers.
- `icon_diagnostics.py`: image API summary and report-friendly diagnosis.
- `icon_quality.py`: real PNG metadata only, not pseudo quality claims.

Rules:

- Move code mechanically first.
- Avoid behavior changes in the same phase.
- Keep public imports stable or update all references in one pass.

Validation:

```powershell
python -m py_compile tools/app_studio/app_studio/*.py tools/app_studio/main.py
python -m unittest discover -s tools/app_studio/tests
```

### Phase 6: UI normalization

Status: completed on 2026-05-10.
Result: `AppStudioImportWizard` revision prompt summary now reads through
`appStudioIconProposal.ts`, and normal UI no longer branches on
`candidate.fallback`. Legacy fallback source labels normalize to the ToolHub
common default icon label instead of exposing old fallback wording.

Purpose:

- Make React components consume a normalized icon proposal shape.

Preferred direction:

- Add one normalizer for raw proposal icon data.
- Keep legacy fallback parsing inside the normalizer.
- Use `launcher/src/lib/appStudioIconProposal.ts` as the UI boundary for current icon source, API candidates, hidden legacy fallback compatibility, default icon state, image API failure diagnosis, and reference-only quality metadata.
- Components should render:
  - current icon source,
  - API candidates,
  - failure reason,
  - next action,
  - default icon state.

Do not:

- Reintroduce fallback adoption UI.
- Show default icon as an AI candidate.
- Show pseudo score as a quality guarantee.

Validation:

```powershell
cd launcher
npm run build
```

### Phase 7: final full check

Status: completed on 2026-05-10, with the full `check_all.ps1` run blocked by the local Rust execution environment.

Final classification:

- `generate_local_png` / `generate_local_svg`: no active implementation path found; remaining mentions are cleanup-history docs only.
- `deterministic_icon_concepts`: active deterministic text/prompt concept helper. This is not an image fallback candidate.
- `local-deterministic-fallback`: compatibility/prompt fallback identifier only; it must not be used as an image candidate source.
- `fallback_png` / `provisional_fallback_png` / fallback counters and reasons: legacy input/read compatibility only through compat or UI normalization boundaries.
- `icon_fallback.svg`: legacy SVG compatibility artifact only; it is not an AI image candidate.
- `prompt_concept_only` / `fallback_rule_based`: legacy values normalized to current reference-only metadata.
- `deterministic_png_check`: current rule-based PNG/reference metadata check, not a quality guarantee.
- `launcher/src/lib/appStudioIconProposal.ts`: UI source of truth for normalized icon proposal display, including hidden legacy fallback compatibility.

Final guardrails:

- Do not reintroduce local fallback image candidates.
- Do not store or display the ToolHub common default icon as an AI candidate.
- Keep legacy fallback parsing inside `icon_compat.py` and `appStudioIconProposal.ts` boundaries.
- Keep pseudo quality/reference metadata out of normal UI ranking and quality-guarantee wording.
- Preserve `display.icon: icon.png` and `final_app/icon.png` compatibility.

Validation run:

```powershell
python -m py_compile tools/app_studio/app_studio/*.py tools/app_studio/main.py
python -m unittest discover -s tools/app_studio/tests
cd launcher
npm test -- --run
npm run build
cd ..\..
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/check_all.ps1
```

Results:

- Python compile: passed.
- App Studio Python tests: passed, 117 tests.
- Launcher Vitest: passed, 7 files / 22 tests.
- Launcher build: passed.
- `check_all.ps1`: failed in the existing App delete plan parity test because `cargo` was blocked by Windows application control policy with OS error 4551. The same run also reported missing MSVC `link.exe` / `cl.exe` / C++ workload warnings. These are local environment issues, not icon cleanup regressions.

## Source-of-truth policy

Target shape:

- `candidate_manifest.json`: API image candidates only.
- `ai_generation_report.json`: detailed image API diagnostics.
- `ai_generation_report.md`: human-readable report.
- `import_plan.json`: minimal registration/apply facts only.
- UI local storage: only explicit image API test result cache, not proposal diagnosis.

Do not duplicate fallback candidate facts into new outputs.

## Compatibility policy

New output:

- No local fallback image candidates.
- No default icon as a candidate.
- `selected_icon_source: default_icon` when the common icon is used.
- `icon_status` should remain explicit.

Old input:

- Continue reading old `fallback_png` and `provisional_fallback_png`.
- Continue tolerating old fallback candidates in manifests.
- Filter old fallback candidates out of normal AI candidate UI.

## Review checklist for the implementing Codex

Before editing:

- Confirm `AGENTS.md`.
- Confirm user request is implementation cleanup, not behavior redesign.
- Check `git status --short` and avoid unrelated dirty files.
- Confirm no generated/user data will be touched.
- Confirm `display.icon: icon.png` compatibility.
- Confirm saved proposal read compatibility.

After editing:

- Search for old terms again.
- Confirm no fallback candidate creation path remains unless explicitly legacy-read-only.
- Confirm default icon is not a candidate.
- Confirm imports, types, and tests are consistent.
- Confirm docs match implemented behavior.
- Run the validation commands for touched layers.

## Maintenance note

No further cleanup implementation prompt is queued from this handoff. If icon work
continues, start from the current module and normalizer boundaries, keep compatibility
read paths isolated, and avoid changing Python generation behavior unless the next task
explicitly requests a behavior change.
