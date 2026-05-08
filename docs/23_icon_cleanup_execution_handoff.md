# App Studio icon cleanup execution handoff

Status: implementation handoff plus execution tracker. Phase 0 through Phase 2 have been executed in the cleanup pass that removed local fallback rendering.

Date: 2026-05-08

## Purpose

This file is a compact execution checklist for the next Codex implementation step.
It exists so the cleanup can continue while the user is away without losing the original goal.

The next implementation should clean up App Studio icon-related code while preserving the
current visible behavior:

- AI image API candidates remain the only generated candidates.
- Uploaded icon, when present, remains the highest-priority icon source.
- Adopted AI candidate remains the selected app icon.
- If no uploaded/adopted icon exists, ToolHub common default icon remains `icon.png`.
- Local generated fallback images must not return as candidates.
- `display.icon: icon.png` compatibility must be preserved.
- Existing saved proposals with legacy fallback fields should remain readable.

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
rg -n "generate_local_png|generate_local_svg|fallback_icon_concepts|local-deterministic-fallback|fallback_png|provisional_fallback_png|icon_fallback|fallback_candidate|fallbackCreatedReason|fallback_candidate_count|prompt_concept_only|fallback_rule_based" tools launcher docs scripts
rg -n "selected_icon_source|icon_status|default_icon|uploaded_png|candidate_png|ai_candidate" tools launcher
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

Purpose:

- Separate "AI concept fallback" from "image fallback candidate".

Preferred direction:

- Rename `fallback_icon_concepts` to a non-image-fallback name such as `deterministic_icon_concepts`.
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

Purpose:

- Make React components consume a normalized icon proposal shape.

Preferred direction:

- Add one normalizer for raw proposal icon data.
- Keep legacy fallback parsing inside the normalizer.
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

Run after any code cleanup phase that touches Python plus frontend/Rust:

```powershell
python -m py_compile tools/app_studio/app_studio/openai_client.py tools/app_studio/app_studio/icon_generator.py tools/app_studio/app_studio/exporter.py tools/app_studio/app_studio/icon_override.py tools/app_studio/main.py
python -m unittest discover -s tools/app_studio/tests
cd launcher
npm run build
cd src-tauri
cargo check
cd ..\..
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/check_all.ps1
```

If any command cannot run because of the local environment, report the exact reason.

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

## Recommended next implementation prompt

Use this as the next instruction if the goal is to continue after the local fallback renderer cleanup:

```text
AGENTS.md のルールに従って、1 回の作業で実装・セルフレビュー・検証まで実施してください。

目的:
ToolHub App Studio のアイコン生成まわりを、現行挙動を変えずに cleanup してください。
次は Phase 3 から Phase 4 を対象にします。

実施内容:
- fallback / local icon rendering 関連の参照を再確認する。
- `fallback_icon_concepts` を、画像fallbackではなく deterministic concept fallback だと分かる名前へ変更する。
- `local-deterministic-fallback` の残存表示・report用途を確認し、現行挙動を変えずに誤解の少ない名前または表示へ寄せる。
- fallback candidate 用の deprecated report/type fields を、新規出力と通常UIからさらに縮小できるか確認する。
- local fallback image candidate を復活させない。
- ToolHub common default icon の挙動は維持する。
- `display.icon: icon.png` と `final_app/icon.png` の互換性を維持する。
- saved proposal の `fallback_png` / `provisional_fallback_png` 読み取り互換は残す。
- stale docs / stale labels を current default icon 方針に合わせる。
- tests を更新する。

禁止:
- app.yaml 仕様変更。
- App Pack 仕様変更。
- runner 公開 I/F 変更。
- existing apps / release / runtime / data / generated outputs の変更。
- fallback candidate UI の復活。
- default icon を AI candidate として扱うこと。
- 画像モデル自動切替。

検証:
- python -m py_compile tools/app_studio/app_studio/openai_client.py tools/app_studio/app_studio/icon_generator.py tools/app_studio/app_studio/exporter.py tools/app_studio/app_studio/icon_override.py tools/app_studio/main.py
- python -m unittest discover -s tools/app_studio/tests
- launcher を触った場合は npm run build
- Rust を触った場合は cargo check
- powershell -NoProfile -ExecutionPolicy Bypass -File scripts/check_all.ps1

完了報告:
- 変更ファイル
- 削除/隔離したもの
- 残した互換処理
- default icon / app.yaml 互換維持の根拠
- 実装前/後セルフレビュー
- 検証結果
- 未確認事項
```
