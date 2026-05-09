# App Studio icon generation simplification plan

Status: investigation plus implementation record. The 2026-05-08 default icon phase, local fallback rendering cleanup, and Phase 3-4 terminology/metadata cleanup have been implemented.

Date: 2026-05-09

## Scope

This document inventories App Studio icon generation after the AI image diagnostics work and proposes a staged removal plan for local fallback icon generation.

The target direction is:

- Uploaded icon is a first-class icon input.
- AI image API candidates are the only generated candidates.
- If neither uploaded icon nor adopted AI candidate exists, ToolHub writes the common default app icon to `icon.png`.
- API failure should show diagnosis and next action, not create local pseudo-production candidates.
- The ToolHub common default icon is a compatibility icon, not an AI candidate, fallback candidate, recommended candidate, or scored candidate.

## 2026-05-08 implementation update

Implemented in this phase:

- Local fallback PNG candidates are no longer created when the image API is disabled, blocked, or failed.
- `candidate_manifest.json` writes API image candidates only. The default icon is not stored as a candidate.
- `icon_work/icon_final.png` and `final_app/icon.png` use `tools/app_studio/assets/default_app_icon.png` when no uploaded/adopted PNG exists.
- `icon_work/icon_final.svg` and `final_app/icon.svg` use the fixed default SVG asset.
- `selected_icon_source: default_icon`, `default_icon_used`, `default_icon_reason`, and `icon_status` are written to report/import metadata.
- The App Studio UI no longer shows fallback candidate grids, fallback adoption buttons, hidden fallback buttons, or dead fallback UI blocks.
- Existing saved proposals that still contain fallback candidates remain readable at the Rust proposal layer, but normal UI filters them out of the AI candidate list.

## 2026-05-08 cleanup update

Implemented in this cleanup phase:

- Removed the unused local PNG/SVG fallback rendering block from `icon_generator.py`.
- Removed the test that asserted local fallback PNG generation as a feature.
- Kept the ToolHub common default icon path and assets.
- Kept `final_app/icon.png`, `icon_work/icon_final.png`, `final_app/icon.svg`, and legacy `icon_work/icon_fallback.svg` output behavior for compatibility.
- Kept saved proposal read compatibility for legacy fallback fields.

## 2026-05-09 Phase 3-4 cleanup update

Implemented in this cleanup phase:

- Renamed `fallback_icon_concepts` to `deterministic_icon_concepts`; it remains text concept generation only and does not create image candidates.
- Replaced new internal placeholder model labels with `deterministic-text-prompt-fallback` and `image-model-not-configured`; `local-deterministic-fallback` remains accepted as legacy input.
- Stopped emitting fallback candidate counters/reasons in new `image_api_summary` output.
- Kept legacy `fallback_png` / `provisional_fallback_png` / old fallback candidate reads tolerant in Python/Rust/TypeScript.
- Removed pseudo quality recommendation summary fields from new `image_api_summary`; normal UI no longer sorts candidates by pseudo score.
- Renamed the PNG rule-based check status from `fallback_rule_based` to `deterministic_png_check` for new outputs.
- Documented `icon_work/icon_fallback.svg` as a legacy SVG compatibility artifact, not a current candidate.

## Pre-implementation self review

Confirmed before proposing removal:

- App Studio-generated `app.yaml` currently writes `display.icon: icon.png` and `display.icon_fallback: icon.svg`.
- App Pack packaging and release verification require the file referenced by `display.icon` to exist.
- The launcher manifest loader requires the `display.icon` field to be present, but if the file is missing it can return an app without PNG/SVG icon data rather than immediately failing.
- Current Python export writes `final_app/icon.png` even when no API candidate exists, because the ToolHub common default PNG is used as `icon_final_png`.
- Rust and React types still model `fallback_png`, `final_png`, fallback candidates, and fallback counts as normal proposal data.
- Removing fallback generation in one step would risk producing App Studio outputs that packaging and release verification reject.

Therefore, the recommended path remains staged: remove unused local fallback rendering first, then rename misleading fallback concept plumbing, then shrink fallback-specific types and report fields while keeping old proposal readers tolerant.

## Current icon generation flow

Current file-based flow:

1. `tools/app_studio/main.py` calls `generate_icon_assets_with_candidates(...)`.
2. `tools/app_studio/app_studio/icon_generator.py` builds:
   - initial icon prompt,
   - optional user revision prompt,
   - the fixed ToolHub default SVG/PNG from `default_icon.py`,
   - API candidates via `generate_icon_candidates`.
3. If AI image API succeeds:
   - `icon_candidate_*.png` or `icon_candidate_*.url.txt` is saved under `icon_work/`.
   - `candidate_manifest.json` stores candidate metadata.
4. If AI image API is disabled, blocked, or fails:
   - no local fallback image candidate is created.
   - failure class, reason, and next action are saved in report/import metadata.
5. `main.py` sets `selected_icon_source` to `default_icon` when no explicit icon override exists.
6. `tools/app_studio/app_studio/exporter.py` writes:
   - `icon_work/icon_fallback.svg`,
   - `icon_work/icon_final.svg`,
   - `icon_work/icon_final.png`,
   - `candidate_manifest.json`,
   - `ai_generation_report.md`,
   - `ai_generation_report.json`,
   - `final_app/icon.png`,
   - `final_app/icon.svg`.
7. `launcher/src-tauri/src/app_studio_commands.rs` reads `icon_work/` into proposal structs.
8. `launcher/src/components/admin/appstudio/AppStudioAiProposalPanel.tsx` shows API candidates only as AI candidates and treats the default icon as the current compatibility icon.
9. If Apply runs without an explicit PNG override, the ToolHub common default icon remains the final `icon.png`.

## Fallback inventory

| Item | Current location | Current role | Classification |
| --- | --- | --- | --- |
| `generate_local_png` | `icon_generator.py` | Former local fallback PNG renderer | Removed in cleanup phase |
| `generate_local_svg` | `icon_generator.py` | Former local fallback/compat SVG renderer | Removed in cleanup phase; fixed default SVG asset remains |
| `deterministic_icon_concepts` | `icon_generator.py` | Creates deterministic text concepts when AI concept generation is unavailable | Keep as text-only fallback; not an image candidate |
| `local-deterministic-fallback` | legacy reports/input | Old internal placeholder label | Keep as read/display compatibility only; new reports use clearer placeholder labels |
| `provisional_fallback_png` | old `import_plan.json` | Legacy no-API-candidate marker | Read compatibility only; new output uses `default_icon` / `icon_status` |
| `fallback_png` | `icon_override.py`, Rust/TS types | Legacy selected source | Read compatibility only; new standard source is `default_icon`, `uploaded_png`, or AI candidate PNG |
| `final_png` | React/Rust/Python override flow | Can mean adopted final PNG or fallback-derived final PNG | Split into explicit selected icon source; avoid using `final_png` as a semantic source |
| `icon_final.png` | `icon_work/`, `exporter.py` | Final working PNG, currently fallback if no API/override | Keep only after explicit adoption or explicit default icon choice |
| `icon_final.svg` | `icon_work/`, `exporter.py` | Compatibility SVG, currently local fallback | Shrink to compatibility-only if still needed |
| `icon_fallback.svg` | `icon_work/`, Rust reader, UI | Fallback preview/compat SVG | Remove from proposal UI; keep only if app.yaml/display fallback still needs it |
| fallback candidate records | `candidate_manifest.json` | Saved as selectable local temporary candidates | Remove from candidate manifest after UI no longer needs fallback candidate display |
| fallback adoption UI | `AppStudioAiProposalPanel.tsx` | Lets admin adopt fallback/local provisional icon | Remove or replace with explicit "Use ToolHub default icon temporarily" if that policy is approved |
| fallback scoring | `apply_icon_candidate_quality`, `evaluate_icon_candidate_quality` | Gives pseudo quality fields to local fallback | Remove with fallback candidates; not useful for admin decision |
| fallback report fields | report JSON/MD, `ImageApiSummaryPanel` | Explains why fallback was created | Replace with `icon_status`, `failure_class`, reason, next action |
| default icon to `final_app/icon.png` | `main.py`, `exporter.py`, `icon_override.py` | Ensures packaging has an icon | Keep; this is the current compatibility policy |

## Deletion classification

Can be removed after a small UI/type migration:

- fallback candidate display and adoption UI.
- hidden fallback buttons.
- `false && ...` fallback warning/dead blocks.
- fallback candidate score display.
- fallback count/reason in primary UI.
- old pseudo quality labels such as `prompt_concept_only` and `fallback_rule_based` as admin-facing quality labels.

Cannot be removed immediately without compatibility work:

- automatic final `icon.png` creation in export.
- `fallback_png` handling in `icon_override.py`.
- Rust and TypeScript parsing of old fallback candidates.
- `icon_final.png` legacy reading.
- `display.icon: icon.png` generation in App Studio outputs.

Can be removed without app.yaml/App Pack spec change after gating is in place:

- local fallback candidate generation.
- fallback candidate records in `candidate_manifest.json`.
- fallback-specific candidate scoring fields.
- fallback sections in the proposal UI.

Needs explicit product decision:

- Whether Apply should stop when icon is undecided.
- Whether Approve should stop instead of Apply.
- Whether a ToolHub common default icon is allowed as an explicit temporary icon.
- Whether existing saved proposals with fallback candidates must remain readable for a full release cycle.

Temporary placeholder candidates should not remain. If a placeholder is unavoidable, it should be a single common default icon source, not a generated candidate and not part of candidate scoring.

## icon.png required behavior

Confirmed facts:

- App Studio-generated `app.yaml` currently sets `display.icon: icon.png`.
- `tools/app_studio/app_studio/registrar.py` requires `display.icon` to refer to an existing file when packaging App Pack.
- `scripts/package_app_pack.ps1` requires the `display.icon` file to exist and be present in the App Pack zip.
- `scripts/verify_release.ps1` requires `display.icon` to be set and the referenced file to exist.
- App Pack docs allow `icon.png` or `icon.svg`, but the referenced `display.icon` must exist.
- The launcher manifest loader requires `display.icon` in YAML. It attempts PNG first, then SVG or `display.icon_fallback`. A missing icon file can result in no icon data, but packaging/release checks still fail before release quality is satisfied.

Inference:

- Existing apps should not be modified or have icons removed.
- Fallback removal should be implemented as a registration gate, not by emitting app.yaml that points to a missing icon.
- App Studio can still allow Suggest output with `icon_status: undecided`, but Apply should not write/register a final app unless the icon source is explicit.

## Options after fallback removal

| Option | Summary | Benefits | Drawbacks | Compatibility | UX |
| --- | --- | --- | --- | --- | --- |
| A | Suggest can save, Apply stops if icon is undecided | Prevents invalid app/app pack output; clear admin action | Requires UI gate before Apply | Strong; no invalid `display.icon` emitted | Best balance |
| B | Apply can proceed, Approve stops | Lets admins continue later | Creates registered draft app with unresolved icon and packaging risk | Weaker; App Pack checks may fail | Confusing because app exists but cannot approve |
| C | Use a ToolHub common default icon | Maintains `icon.png` existence | Can hide that icon is not app-specific | Compatible if explicit file is written | Acceptable only if clearly labeled and explicit |
| D | Upload or AI adoption is mandatory | Cleanest long-term model | Stricter flow; admins must provide an icon | Strong after UI support exists | Clear, but less forgiving |
| E | Change App Studio to emit SVG-only when icon undecided | Avoids PNG fallback | Still needs a real referenced file and spec review | Riskier because current app.yaml generator uses PNG | Not recommended as first step |

Recommended policy:

- Use A plus D as the primary path.
- Allow Suggest to complete with `icon_status: undecided`.
- Block Apply when there is no uploaded icon, no adopted AI API candidate, and no explicit default icon choice.
- Keep C only as an optional administrative escape hatch: "Use ToolHub default icon temporarily". It must not appear as an AI candidate, fallback candidate, or recommended candidate.

## Candidate management simplification

Keep for API candidate management:

- API candidate id.
- source: `api_generate` or `api_edit`.
- PNG file name or URL file name.
- prompt actually sent to image API.
- model, API endpoint, content type, resolution, status.
- revision source candidate id when regeneration/edit is used.

Remove or move out of UI after fallback removal:

- fallback candidate records.
- `fallback_rule_based`.
- `prompt_concept_only` as a quality claim.
- `local-deterministic-fallback`.
- `fallback_reason` on candidates.
- `fallback_candidate_count`.
- `fallback_created_reason`.
- deterministic fallback score fields.

Shrink or defer until real image evaluation exists:

- `score`, `quality_total`, `semantic_score`, `specificity_score`, `small_size_score`, `aesthetic_score`, `revision_follow_score`, `generic_risk_score`.
- `recommendedCandidateId` if it is based only on prompt/concept heuristics.
- `image_evaluation_status` unless actual image evaluation is performed.

Assessment:

- `prompt_concept_only` and `fallback_rule_based` do not prove that the image matches the prompt. They are useful as debug metadata but weak as administrator-facing quality signals.
- If retained temporarily, these fields should move to report-only detail and be hidden from normal UI.

## UI simplification

Minimum view for normal administrators:

- Icon status: Uploaded, AI candidate selected, AI generation failed, or Icon undecided.
- Current preview or "unselected" state.
- Primary actions:
  - Upload icon.
  - Generate AI icon.
  - Adopt selected AI candidate.
  - Regenerate selected candidate.
  - Use ToolHub default icon temporarily, only if that policy is approved.
- If AI failed:
  - failure class,
  - short reason,
  - next action,
  - API candidate count.

Details view for troubleshooting:

- AI enabled.
- API key present.
- text model and image model.
- last image model test result and tested time.
- text prompt generation status.
- image generation status.
- payload secret scan status.
- image model and API endpoint.
- final image prompt preview.
- report file path.

Report-only information:

- full initial prompt, revision prompt, and final API prompt.
- function interpretation JSON.
- package secret scan finding details.
- raw candidate manifest fields.
- deterministic score breakdowns.
- timings and low-level retry details.

UI cleanup targets:

- Remove dead blocks guarded by `false && ...`.
- Remove hidden fallback buttons.
- Remove fallback candidate grid.
- Remove fallback adoption wording.
- Avoid showing `final_png` when it means fallback.
- Merge proposal run diagnosis and `imageApiHealth` cache into one status panel with clear source labels:
  - last explicit image API test,
  - current proposal image generation result.
- Clarify "load saved proposal" versus "generate new proposal":
  - loading saved proposal must not call the image API,
  - generating new proposal may call AI APIs.

## Rust and TypeScript type simplification

Current types to simplify:

- `AppStudioSelectedIconSource`
- `AppStudioIconOverride`
- `AppStudioAiIconCandidateSuggestion`
- `AppStudioAiIconCandidate`
- `AppStudioImageApiSummary`
- `AiImageGenerationTestResult`
- `AiImageModelProbeResult`
- `selected_icon_source`
- `icon_override_used`
- `icon_provisional_fallback_used`

Recommended target model:

- `AppStudioIconSource = "uploaded_png" | "ai_candidate_png" | "default_icon" | "none"`.
- `AppStudioIconSelection`:
  - `source`,
  - optional `pngDataUrl`,
  - optional `candidateId`,
  - optional `fileName`,
  - optional `selectedAt`.
- `AppStudioAiIconCandidate`:
  - id,
  - source,
  - prompt,
  - model,
  - status,
  - file/url,
  - API endpoint,
  - resolution,
  - content type,
  - optional revision source id.
- `AppStudioImageApiSummary`:
  - image generation status,
  - image model,
  - API candidate count,
  - failure class,
  - failure message,
  - admin next action,
  - payload secret scan status,
  - AI submission blocked,
  - elapsed seconds.

Migration approach:

1. Add new fields while still reading old fallback fields.
2. Hide old fallback fields in UI.
3. Stop writing fallback candidates.
4. Remove old fields after saved proposal compatibility is no longer required.

## Report and JSON source of truth

Current duplication:

- `ai_generation_report.md`: human report.
- `ai_generation_report.json`: machine-readable image generation summary.
- `candidate_manifest.json`: candidate list plus duplicate `image_api_summary`.
- `import_plan.json`: selected source, diagnostics, fallback flags, candidate counts.
- `secret_scan_report.md/json`: package secret scan.
- `imageApiHealth` local storage: last explicit image API test.
- React derives additional summary state.

Recommended source of truth:

- Human-readable run diagnosis: `icon_work/ai_generation_report.md`.
- UI run diagnosis: `icon_work/ai_generation_report.json`.
- Candidate list: `icon_work/candidate_manifest.json`, only when API candidates exist.
- Registration decision: `import_plan.json` stores only `icon_status`, `selected_icon_source`, and whether Apply is blocked by undecided icon.
- Package secret details: `secret_scan_report.md/json`.
- AI payload scan result: referenced in `ai_generation_report.json`.
- Last explicit image API test: `imageApiHealth` local storage, clearly labeled as preflight/test cache, not proposal result.

After fallback removal:

- `fallback_candidate_count` and `fallback_created_reason` should be removed.
- Failure diagnosis should remain: `failure_class`, `failure_message`, `admin_next_action`.
- `candidate_manifest.json` should not exist, or should have an empty API candidate list, when no API image candidate was saved.

## Image API cost and call policy

Confirmed facts:

- Initial icon generation default candidate count is currently 3.
- Icon regeneration default candidate count is currently 1.
- `image-test` performs a real image generation test.
- model probe tests four candidate image models by running `image-test` for each model.
- image generation/edit retries once when optional parameters such as `output_format` or `quality` are unsupported.
- API failure does not require more image calls, but current fallback generation continues locally afterward.

Recommended policy:

- Initial generation default should become 1 API candidate.
- Additional candidates should be explicit admin action.
- Regeneration default can remain 1.
- Image model probe should remain explicit and should clearly say it can call up to four real image generations.
- Consider "stop after first successful model" as an option, but do not automatically switch the configured model without admin action.
- Keep the single compatibility retry for unsupported `output_format` or `quality`.
- Use `edit_image` only when the admin explicitly regenerates from an existing uploaded or AI candidate image.
- Do not use local fallback generation after API failure.

## Uploaded icon integration

Confirmed facts:

- A dedicated final icon upload UI was not found in the App Studio components.
- Existing `iconOverride` can carry PNG data URLs for generated candidates.
- `iconRevisionImage` exists in request plumbing, but no UI path was found that sets it as a final uploaded icon.
- Launcher preview can show an icon override PNG when present.

Recommended design:

- Add uploaded icon as the highest-priority icon input.
- If an uploaded icon exists and the admin does not request AI alternatives, skip AI image generation.
- Use uploaded PNG directly as `final_app/icon.png` after validation.
- Keep uploaded icon outside `candidate_manifest.json`.
- Let AI regeneration optionally use uploaded icon as an edit reference only when the admin explicitly requests it.
- If AI fails, guide the admin to upload an icon or test/fix the image API.

## Recommended staged implementation

| Phase | Purpose | Files | Change | Compatibility risk | Stop condition | Validation | Expected diff | User decision |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A | Remove dead/hidden fallback UI and reduce primary noise | `AppStudioAiProposalPanel.tsx`, `app.css` | Delete `false &&` blocks, hidden buttons, duplicate fallback warnings; move debug metadata behind details | Low | If old saved proposals become unreadable | frontend build/typecheck | Small | No |
| B | Stop presenting fallback as a selectable candidate | React components, TS types read path only | Hide fallback candidate grid and fallback adopt action; show icon undecided or explicit default option | Medium | If Apply still depends on fallback selection | frontend build, Python tests | Small to medium | Yes for default icon option |
| C | Add icon status and Apply gate | `main.py`, `exporter.py`, Rust commands, React wizard | Introduce `icon_status: undecided`; block Apply unless uploaded/API/default source exists | Medium | If app.yaml/App Pack would point to missing icon | Python tests, cargo check, frontend build, check_all | Medium | Yes |
| D | Stop writing fallback candidates | `icon_generator.py`, `models.py`, tests | On API failure, write diagnosis only; no fallback candidate PNGs in manifest | Medium | If existing tests require fallback candidates for success | Python unit tests | Medium | No after Phase C |
| E | Simplify candidate manifest and reports | `icon_generator.py`, `exporter.py`, Rust reader, TS types | Make manifest API-candidate-only; move diagnosis to report JSON; remove pseudo score fields from UI | Medium | If saved proposal compatibility must be kept longer | Python tests, frontend build, cargo check | Medium to large | No, unless compatibility window changes |
| F | Simplify icon override and selected source types | `icon_override.py`, Rust/TS types, metadata cleaning tests | Replace `fallback_png/final_png/candidate_png` with `uploaded_png/ai_candidate_png/default_icon/none` | High | If existing saved overrides must remain writable | Python tests, TS tests, cargo check | Medium | Yes |
| G | Remove or shrink local fallback generation | `icon_generator.py`, `exporter.py`, docs/tests | `generate_local_png`/`generate_local_svg` removal, `deterministic_icon_concepts` rename, and new-output fallback counter shrink are complete; remaining work is deeper type/module simplification | Medium | If saved proposal compatibility breaks | full check_all plus package tests | Medium | No |
| H | Docs and scripts alignment | `docs/13_app_studio.md`, `docs/14_admin_and_ai_settings.md`, `docs/21_app_registration_improvement_plan.md`, scripts diagnostics | Replace fallback-as-normal docs with icon-undecided/default-icon policy | Low | If implementation phases are not complete | docs review, check_all | Small | No |

## Next implementation prompt recommendation

Recommended next prompt:

> AGENTS.md に従って、現行挙動を変えずに App Studio icon modules を機械的に分割し、legacy fallback 読み取り互換を normalizer/compat 層へ隔離してください。画像fallback候補は復活させず、ToolHub common default icon、`display.icon: icon.png`、saved proposal 読み取り互換は維持してください。変更後に Python tests、必要に応じて frontend build/cargo check、check_all を実行してください。

## Items not yet confirmed by this document

- Exact desired wording for the optional ToolHub common default icon.
- Whether Apply or Approve should be the first hard stop in product policy. This document recommends Apply.
- How long saved proposals with fallback candidates must remain fully readable.
- Whether uploaded icon should accept only PNG or also SVG/JPEG with conversion.
- Whether model probe should test all models or stop after first success.
