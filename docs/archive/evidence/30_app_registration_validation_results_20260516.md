# App Registration Validation Results 2026-05-16

検証日: 2026-05-16

## Summary

`C:\Users\kuroron\Documents\RD` 配下の代表的な Python アプリについて、App Studio の通常登録フローで `main.py` を指定し、共有ランタイムを自動作成または再利用して ToolHub に登録できるかを検証した。

PDFApplication は編集中のため対象外とした。

結論として、現在の ToolHub は「零ストレスでアプリ登録できる」とはまだ判定できない。共有ランタイムの作成自体は複数ケースで動作したが、依存抽出、source root 推定、禁止 payload 除外、失敗時の registry 更新、release verify の検出範囲に実用上の詰まりが残っている。

## Environment

- ToolHub repo: `C:\Users\kuroron\Documents\RD\20260426_Toolhub`
- App Studio policy observed: `normal_python_source_to_shared_versioned_runtime_v1`
- Normal registration mode: `shared-env`
- Base runtime Python: `runtime/python/python.exe`
- Validation app id prefix: `zt_*_20260516`

## Candidate Results

| Candidate | Entry | Source root mode | Apply | Runtime | Launch / execution | Result | Main reason |
| --- | --- | --- | --- | --- | --- | --- | --- |
| RealtimeTranslator | `20250608_RealtimeTranslator\RealtimeTranslator_Clean2\main.py` | entry parent | fail | fail | not run | C / fail | UTF-8 Japanese comments in requirements caused pip to decode with CP932 and fail. |
| Calibook | `20250916_Calibook\py\main.py` | entry parent | fail | created | startup smoke fail | C / fail | Import-derived dependency `nfc` was not installed; `ModuleNotFoundError: No module named 'nfc'`. |
| ExcelBatchReplace | `20251123_ExcelBatchReplace\main.py` | entry parent | fail | fail | not run | C / fail | App Studio picked a nested Python helper as `requirements.txt`; pip failed on `"""`. |
| AgendaSnap | `20260201_AgendaSnap\main.py` | entry parent | partial | created | runner launch ok, approval blocked | C / fail | App registered and runner launched, but registered payload included `__pycache__` / `.pyc`, so approval was blocked. |
| XCgateAutoUpload | `20251103_XCgateAutoUpload\xcgate_flows\src\main.py` | blank / auto | pass | reused wrong empty env | manual launch not run | C / fail | Auto source root missed `xcgate_flows\requirements.txt`; approval was allowed even though Playwright was absent from the runtime. |
| XCgateAutoUpload | same | explicit `xcgate_flows` | pass | created | manual launch not run | A / conditional | Explicit source root produced a Playwright runtime, but browser/login/upload behavior still requires manual validation. |

## Shared Runtime Results

| env_id | Status | Apps recorded | Key packages / lock | Result |
| --- | --- | --- | --- | --- |
| `py313-win_amd64-runtime-37c71daf` | created / reused | `zt_calibook_py_20260516`, `zt_xcgate_20260516` | empty lock hash `e3b0c442...` | Problematic. It was reused for XCgate without Playwright, and the failed Calibook import still remained in registry. |
| `py313-win_amd64-flet0283-fletdesktop0283-03c58f59` | created | `zt_agendasnap_20260516` | `flet==0.28.3`, `flet-desktop==0.28.3`, audio/scipy stack | Runtime check passed and runner launch used this environment. Approval failed due registered payload. |
| `py313-win_amd64-playwright1550-27ead7db` | created | `zt_xcgate_srcroot_20260516` | `playwright==1.55.0`, `PyYAML==6.0.2` | Runtime import check passed. Startup smoke remained warning because Playwright flows can require login/external sites. |

## Key Findings

1. `main.py` 指定だけで完了した代表ケースはなかった。
2. 共有ランタイム作成は機能しているが、依存情報が誤ると空 runtime が作られ、その後の registration / approval gate で検出しきれないケースがある。
3. Calibook のような import-derived dependency は候補として検出されても、requirements に反映されず startup で落ちる。
4. ExcelBatchReplace では nested `requirements.txt` の妥当性確認が弱く、pip requirements ではないファイルをそのまま採用した。
5. RealtimeTranslator では UTF-8 requirements を pip が CP932 として読んで失敗した。App Studio 側で requirements / lock を UTF-8 safe に扱う必要がある。
6. AgendaSnap は runtime startup smoke と実 runner 起動が通ったが、最終登録 payload に `__pycache__` が混入して approval 不可になった。inventory 段階と final_app / registered_app 段階の禁止 payload 判定がずれている。
7. XCgateAutoUpload は source root 未指定だと `src` だけが対象になり、親ディレクトリの requirements を拾えない。結果として Playwright なし runtime でも approval allowed になった。
8. 明示 source root を指定した XCgate は Playwright runtime を作成できたが、`run.entry` は `src/src/main.py` になり、ユーザーが画面で判断するには分かりにくい。
9. `scripts/verify_release.ps1` は exit code 0 だったが、AgendaSnap の approval-blocking payload と XCgate auto source root の missing dependency は検出しなかった。

## Evidence

代表証跡:

- `C:\Users\kuroron\Documents\RD\20250608_RealtimeTranslator\RealtimeTranslator_Clean2\ToolHub_AppStudio_Output\zt_rt_clean2_20260516\shared_runtime_report.md`
- `C:\Users\kuroron\Documents\RD\20250916_Calibook\py\ToolHub_AppStudio_Output\zt_calibook_py_20260516\runtime_check_result.json`
- `C:\Users\kuroron\Documents\RD\20251123_ExcelBatchReplace\ToolHub_AppStudio_Output\zt_excelbatch_20260516\shared_runtime_report.md`
- `C:\Users\kuroron\Documents\RD\20260201_AgendaSnap\ToolHub_AppStudio_Output\zt_agendasnap_20260516\execution_test_result.json`
- `C:\Users\kuroron\Documents\RD\20251103_XCgateAutoUpload\xcgate_flows\src\ToolHub_AppStudio_Output\zt_xcgate_20260516\execution_test_result.json`
- `C:\Users\kuroron\Documents\RD\20251103_XCgateAutoUpload\xcgate_flows\src\ToolHub_AppStudio_Output\zt_xcgate_srcroot_20260516\execution_test_result.json`
- `runtime/envs/toolhub_env_registry.json`

Runner launch evidence:

- `python runner\toolhub_runner\main.py --project-root . --app-id zt_agendasnap_20260516`
- Result: runner returned ok and used `runtime\envs\py313-win_amd64-flet0283-fletdesktop0283-03c58f59\Scripts\python.exe`.
- Log: `data\logs\zt_agendasnap_20260516\run_20260516_171918.json`

Safe import checks:

- `runtime\envs\py313-win_amd64-runtime-37c71daf\Scripts\python.exe -c "import playwright"` failed with `ModuleNotFoundError`.
- `runtime\envs\py313-win_amd64-playwright1550-27ead7db\Scripts\python.exe -c "import playwright, yaml"` passed.
- `runtime\envs\py313-win_amd64-flet0283-fletdesktop0283-03c58f59\Scripts\python.exe -c "import flet, flet_desktop, numpy"` passed.

## Commands Run

Core validation:

```powershell
python main.py --check
```

```powershell
python tools\app_studio\main.py import --entry <candidate-main.py> --app-id <zt_app_id> --name <name> --build-mode shared-env --apply
```

Representative runner check:

```powershell
python runner\toolhub_runner\main.py --project-root . --app-id zt_agendasnap_20260516
```

Release verification:

```powershell
.\scripts\verify_release.ps1
```

`verify_release.ps1` returned exit code 0, but it should not be treated as proof that App Studio registration was approval-safe or dependency-complete.

## Required Fix Areas

| Priority | Area | Required change |
| --- | --- | --- |
| P0 | dependency source selection | Do not pick arbitrary nested `requirements.txt` unless it is clearly associated with the selected source root; validate that it is pip-parseable before shared runtime creation. |
| P0 | requirements encoding | Write generated requirements / lock inputs in a form pip can read reliably on Windows, or force UTF-8-safe processing where possible. |
| P0 | approval safety | Re-run forbidden payload checks against `final_app` and registered `apps/<app_id>` contents, not only early inventory. |
| P0 | shared runtime registry | Do not record failed imports as runtime consumers, or roll back registry updates when Apply fails before registration. |
| P0 | dependency completeness | Treat import-derived third-party modules as unresolved dependencies unless they are installed, ignored, or explicitly classified as optional. |
| P1 | source root UX | When entry is under `src`, detect a parent source root with requirements/config and present it as a clear recommendation before Apply. |
| P1 | release verify | Extend release verification to catch approval-blocking registered payload and shared-env dependency completeness for enabled or newly imported apps. |
| P1 | Playwright checks | Keep external/browser execution manual, but verify package presence and app entry importability before allowing approval. |

## Current Workspace Artifacts

The validation intentionally created test registration artifacts:

- `apps/zt_agendasnap_20260516/`
- `apps/zt_xcgate_20260516/`
- `apps/zt_xcgate_srcroot_20260516/`
- `data/app_studio/build_profiles/zt_*_20260516.json`
- `runtime/envs/`
- `release/app_manifest.json` changes for the test apps

These artifacts should remain until the next investigation step is decided, because they are useful evidence. If a clean baseline is needed, remove them through the app deletion flow or an explicit cleanup plan rather than deleting shared runtime folders directly.
