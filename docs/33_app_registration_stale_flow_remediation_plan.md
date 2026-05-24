# App Registration Stale Flow Remediation Plan

## Purpose

ToolHub のアプリ登録後、単体で動く Python アプリが ToolHub 上でも同じ状態で起動できるようにする。

今回の AgendaSnap では、子プロセス起動問題は解消したが、起動後も ToolHub が「起動処理を実行しています」のままになった。原因は、登録元の `apps/<app_id>/app.yaml` は `mode: gui` に更新済みなのに、実際に起動している release 実行 root 側の `app.yaml` が古い `mode: cli` のままだったこと。

この文書では、現状のアプリ登録フローに残る古い箇所をシステム全体から拾い、効率的に直す方針を定義する。

## Confirmed Failure

確認済みの状態:

- 登録元:
  - `apps/app_20260201_agendasnap/app.yaml`
  - `run.runner: exe`
  - `run.entry: bin/app_20260201_agendasnap/app_20260201_agendasnap.exe`
  - `run.mode: gui`
- 実際に起動していた release root:
  - `launcher/src-tauri/target/release/apps/app_20260201_agendasnap/app.yaml`
  - `run.runner: exe`
  - `run.entry: bin/app_20260201_agendasnap/app_20260201_agendasnap.exe`
  - `run.mode: cli`
- 実行中 runner:
  - `launcher/src-tauri/target/release/runtime/python/python.exe`
  - `launcher/src-tauri/target/release/runner/toolhub_runner/main.py`
  - `--project-root launcher/src-tauri/target/release`
  - `--app-id app_20260201_agendasnap`

結果:

- `runner: exe` かつ `mode: cli` のため、runner は AgendaSnap exe の終了を待つ。
- Tauri 側の `launch_app` は runner の終了を同期的に待つ。
- AgendaSnap 画面は開くが、ToolHub は起動完了 result を受け取れず、起動ダイアログが閉じない。
- AgendaSnap を閉じると、その時点で初めて result JSON が作られる。

## Core Policy

1. `apps/<app_id>/app.yaml` を source of truth とする。
2. `launcher/src-tauri/target/release/` は生成物であり、恒久修正先にしない。
3. 開発中 bootstrap は release artifact を探さず、開発 source root から起動する。
4. アプリ登録 Apply 後は、登録先 root、実行 root、App Pack、release manifest の一致を検証する。
5. GUI 起動は runner が短時間で detached success を返すことを前提にする。
6. たとえ manifest が誤っていても、ToolHub UI が無期限に固まらない防御を入れる。
7. 個別アプリ専用分岐は入れない。AgendaSnap で見つかった問題は一般化して扱う。

## Root Scope Clarification

この問題では root を混同しないことが重要。

| Root type | Meaning | Should be writable by App Studio? | Stale risk | Policy |
| --- | --- | --- | --- | --- |
| Dev source root | `C:\Users\kuroron\Documents\RD\20260426_Toolhub` のような作業 repo。 | Yes | Low | 開発中の canonical source root。App Studio 登録、docs、tests はここを基準にする。 |
| Dev build artifact root | `launcher/src-tauri/target/release` や `launcher/src-tauri/target/debug`。 | No, except as build output | High | 生成物。開発中に直接 source of truth として使わない。 |
| Installed resource root | `%LOCALAPPDATA%\Programs\ToolHub\...` 配下、または Tauri の `resources` / `_up_/_up_` resource root。 | Yes, if installed current-user and App Studio is supported there | Medium | 実ユーザー環境ではこの root が active source of truth になる。dev repo との一致を常に要求しない。 |
| User data root | `%LOCALAPPDATA%\ToolHub`。 | Yes | N/A | logs、config、browser profiles、app state 用。app source ではない。 |

したがって、修正は「常に dev repo を読ませる」ではない。

- 開発 bootstrap は local release artifact を起動せず、dev source root を起点にする。
- インストール済み shortcut から起動する場合は、installed resource root を正とする。
- `target/release` を active root として採用してよいのは、release artifact の検証中だけ。その場合も source root との差分を report に出す。

## Old Flow Inventory

| Area | Current old behavior | Impact | Fix policy | Priority |
| --- | --- | --- | --- | --- |
| Bootstrap `main.py` | `python main.py` は dev source の launcher を起動し、既存 release artifact は探さない。 | 開発中の起動で古い release root を読まない。 | 旧互換オプションを持たせず、`python main.py` と環境チェックだけを維持する。 | Done |
| Rust `manifest::project_root()` | `TOOLHUB_ROOT` の次に current executable directory を優先する。local release artifact は `target/release` を root として採用できる。 | 直接 release artifact を起動すると、`target/release/apps`、`target/release/runner`、`target/release/tools` が古いままでも正規 root と扱われる。 | root 決定結果をログと UI 診断に表示する。dev bootstrap では release artifact を起動しない。 | P0 |
| `target/release/apps` | build 時点の app copy が残り、source `apps/` と別管理になる。 | `mode: cli` など古い `app.yaml` が実行される。 | 直接修正ではなく、stale check で検出する。release build 時に current source から再生成する。dev 起動では読ませない。 | P0 |
| `target/release/runner` | build 時点の Python runner が残る。 | runner 修正が source にはあるのに release 実行では反映されない。 | source root 実行を優先する。release verification に runner freshness check を追加する。 | P0 |
| `target/release/tools/app_studio` | build 時点の App Studio が残る。 | 登録 UI から実行した Apply が古い登録ロジックを使う可能性がある。 | active root の tools version を診断に出す。source root と divergence がある場合は登録前に警告または block する。 | P0 |
| Tauri bundle resources | `tauri.conf.json` は `../../apps`、`../../runner`、`../../runtime`、`../../tools/app_studio` を build 時点で resource に含める。 | 正しい設計だが、local build artifact は build した瞬間の snapshot なので、開発中の修正とズレる。 | installed resource root は正規 root として扱う。一方、dev `target/release` は snapshot として freshness check 対象にする。 | P0 |
| App Studio Apply | `apply_registration()` は `context.repo_root/apps` と `context.repo_root/release/app_manifest.json` を更新する。active ToolHub が別 root を読んでいる場合の検出がない。 | ユーザーが登録したと思っても、起動中 ToolHub が別 root の古い app を使う。 | Apply 前後に active root と context root を記録し、異なる場合は明示する。local dev では source root に統一する。 | P0 |
| App Studio active root | App Studio UI は `manifest::project_root()` で得た active root の `tools/app_studio/main.py` を実行する。 | active root 自体が stale `target/release` の場合、context root と active root が一致しても古い App Studio が使われ、単純な root mismatch 検出では見逃す。 | context root だけでなく canonical source root / root type / tool hash を report する。dev build artifact root で Apply する場合は warning/block 対象にする。 | P0 |
| App Pack | Apply 後に App Pack は作るが、local release artifact root への同期保証ではない。 | App Pack が最新でも、現在起動中の release root は古いままになり得る。 | App Pack は配布用 artifact と位置づけ、現在起動中 root の freshness とは別に検査する。 | P1 |
| Rust `launch_runner()` | `Command::new(...).output()` で runner 完了まで同期待ちする。 | runner が blocking になると Tauri command が戻らず、UI が固まる。 | 非同期実行または bounded timeout にする。起動中 result が返らない場合でも UI を復帰できるようにする。 | P0 |
| `ExeRunner` | `run.mode == "cli"` なら exe を `run_blocking()`、それ以外なら `start_detached()`。 | `mode` が古いだけで GUI exe を終了まで待つ。 | manifest 生成と freshness check で `mode` 誤りを潰す。runner 側は mode 契約を維持しつつ、diagnostic を強化する。 | P0 |
| Launch modal | `launchApp()` の Promise が返るまで running のまま。running 中は close button も出ない。 | backend が返らないとユーザーが復帰できない。 | running timeout、キャンセル表示、診断リンク、close fallback を追加する。 | P1 |
| Launcher result logs | runner が戻るまで result JSON ができない。stuck 中に原因が見えにくい。 | 「何を読んでいるか」が UI から分からない。 | launch 開始時点で root、app_yaml、runner、entry、mode、result path を backend log に出す。必要なら pending marker を作る。 | P1 |
| Normal registration docs/code | Normal UI は shared-env を強制するが、CLI と古い docs には frozen-folder 経路が残る。 | どれが現行標準か判断しづらい。 | shared-env を標準として明記し、frozen-folder は legacy/admin-only とラベル付けする。削除はしない。 | P1 |
| Release verification | `verify_release.ps1` は release artifact を見るが、source root と local release root の app/runner/tools divergence を直接検出しない。 | build 済み artifact の古さが起動時まで残る。 | `diagnose_active_root_staleness.ps1` または verify extension で source root と active root を比較する。 | P1 |
| Diagnostics | 既存診断は app manifest、App Studio import、release readiness に分かれている。active root mismatch 専用の分類がない。 | 今回のような「正しい root と古い root」の切り分けに時間がかかる。 | `active_root_mismatch`、`release_root_stale_app_yaml`、`release_root_stale_runner`、`launcher_blocking_wait` を分類に追加する。 | P1 |

## Efficient Remediation Plan

### Phase 0: Immediate Recovery

目的: 現在の AgendaSnap が起動完了になる状態に戻す。

対応:

1. 起動中の stale runner を止める。
2. local release artifact への同期を開発中 bootstrap の前提にしない。必要な確認は release verification で扱う。
3. ただし `target/release` 直接修正は恒久対応にしない。
4. 再起動後、runner command が `mode: gui` を読んで `start_detached()` になり、2 秒程度で result JSON が作られることを確認する。

完了条件:

- 起動ダイアログが AgendaSnap の画面表示後に閉じる。
- `runner finished app_id=app_20260201_agendasnap` が短時間で出る。
- `result_*.json` に success event が入る。

### Phase 1: Root Selection Fix

目的: 開発 repo から起動した ToolHub が古い `target/release` root を誤って source of truth にしないようにする。

対応候補:

1. `python main.py` の既定を dev 起動に寄せ、検証用 bootstrap から release artifact は起動しない。
2. `manifest::project_root()` の採用 root を `tauri_backend.log` と System Info に表示する。
3. root が `launcher/src-tauri/target/release` の場合、dev repo では stale warning を出す。
4. root type を `dev_source`、`dev_build_artifact`、`installed_resource`、`user_data` に分類して診断へ出す。

推奨:

- まず 1 と 2 を実装する。
- `main.py` を検証用 bootstrap に限定し、release artifact 起動を廃止する。
- 4 は staleness 判定の前提なので、Phase 2 の前に入れる。

検証:

```powershell
python main.py
```

期待:

- 起動した dev launcher の backend log に `project_root=<repo root>` が出る。
- アプリ一覧と起動は source root の `apps/` を読む。

### Phase 2: Active Root Staleness Detection

目的: source root と active root のズレを登録前後に自動検出する。

追加する診断:

- `scripts/diagnose_active_root_staleness.ps1`
- または `scripts/diagnose_app_studio_import.ps1` の分類追加

比較対象:

- canonical source root:
  - `TOOLHUB_ROOT` が設定されている場合はそれ。
  - dev repo 内 bootstrap から起動している場合は repo root。
  - installed shortcut から起動している場合は installed resource root itself。
- `apps/<app_id>/app.yaml`
- `apps/<app_id>/requirements.lock`
- `apps/<app_id>/bin/` または `apps/<app_id>/src/`
- `release/app_manifest.json`
- `runner/toolhub_runner/*.py`
- `tools/app_studio/main.py`
- `tools/app_studio/app_studio/*.py`

分類:

- `root_type_dev_source`
- `root_type_dev_build_artifact`
- `root_type_installed_resource`
- `active_root_matches_source_root`
- `active_root_differs_from_source_root`
- `active_root_is_stale_build_artifact`
- `release_root_stale_app_yaml`
- `release_root_stale_runner`
- `release_root_stale_app_studio`
- `app_manifest_differs_between_roots`
- `app_pack_current_but_active_root_stale`

完了条件:

- 今回の状態を `release_root_stale_app_yaml` として検出できる。
- `mode: gui` vs `mode: cli` の差分を report に出せる。
- active root と context root が同じでも、その root が dev `target/release` なら stale build artifact として検出できる。

### Phase 3: Launch Flow Hardening

目的: manifest や app 側に問題が残っても ToolHub UI が無期限に固まらないようにする。

対応:

1. `launcher/src-tauri/src/runner.rs` の `Command.output()` を bounded wait にする。
2. runner が一定時間で戻らない場合は、backend が timeout result を返す。
3. timeout result には以下を含める。
   - active project root
   - app yaml path
   - runner
   - entry
   - mode
   - result JSON path
   - pid
4. GUI 想定の場合は、timeout を error ではなく diagnostic warning にするか、runner 側で detached success を返すよう優先修正する。
5. Frontend の launch modal は一定時間後に「診断を開く」「閉じる」を出す。

注意:

- CLI アプリは長時間実行が正しい場合があるため、単純に全 CLI を数秒で timeout fail にしない。
- ただし UI thread を固めないことは必須。

完了条件:

- 誤った `mode: cli` の GUI exe を起動しても ToolHub が応答なしにならない。
- ユーザーが閉じる、ログを見る、再試行する操作を選べる。

### Phase 4: Registration Apply Finalization

目的: App Studio Apply が完了した時点で、実際に起動される状態まで検証する。

対応:

1. Apply の output に `registration_root_report.json` を追加する。
2. report に以下を記録する。
   - context repo root
   - active ToolHub root
   - root type
   - canonical source root
   - App Studio CLI path
   - App Studio CLI hash or mtime
   - app yaml path
   - generated run runner
   - generated run entry
   - generated run mode
   - App Pack path
   - release manifest entry
3. context root と active root が異なる場合は、UI に明示する。
4. context root と active root が同じでも、root type が `dev_build_artifact` なら UI に明示する。
5. active root が generated release root で、source root と差分がある場合は approval-blocking warning にする。
6. `run.mode`、`runner`、`entry` の最終値を execution report に必ず出す。

完了条件:

- Apply 後に「登録されたが現在の ToolHub では古い root を読んでいる」状態を検出できる。
- ユーザーは再起動、release rebuild、dev root 起動のどれが必要か分かる。

### Phase 5: Release Build and Verification

目的: release artifact を作る時に古い apps/runner/tools が混ざらないようにする。

対応:

1. release build 前に stale `target/release/apps`、`target/release/runner`、`target/release/tools` を検査する。
2. Tauri build が source root の最新内容を resource に含めることを確認する。
3. `verify_release.ps1` に local release root consistency check を追加する。
4. App Pack と `apps/<app_id>` の一致は existing App Pack contract check を使う。
5. `target/release/_up_/_up_` など legacy fallback root も検査対象に入れる。
6. installed path `%LOCALAPPDATA%\Programs\ToolHub` と Tauri `resources` root は、VM / sandbox install test で別途確認する。

完了条件:

- `launcher/src-tauri/target/release/apps/<app_id>/app.yaml` が source root より古い場合に検出される。
- release artifact 検証では、読み込む root と app yaml が明示される。
- installed shortcut では installed resource root を正として扱い、dev repo との差分だけで誤って failure にしない。

### Phase 6: Documentation Cleanup

目的: 現行標準と legacy 経路を混同しない。

2026-05-17 の文書整理で、完了済みの調査・handoff・古い frozen-folder 前提の長文計画は `docs/archive/` へ移動し、`docs/13_app_studio.md`、`docs/16_app_studio_exe_build_operations.md`、`docs/05_build_and_release.md`、`docs/09_app_pack_spec.md` は shared-env 標準と legacy frozen-folder を分けて書き直した。

対応:

1. `docs/31_app_registration_app_authoring_guidelines.md` はアプリ作者向けとして維持する。
2. `docs/32_toolhub_agendasnap_launch_parity_fix_plan.md` は AgendaSnap 発見事項として維持する。
3. 本文書を ToolHub 側 stale flow 修正の親方針にする。
4. 古い frozen-folder 標準の説明がある docs は historical/legacy と明示する。
5. README の起動説明で `python main.py` が開発中 launcher を起動することを明記する。

## Implementation Order

推奨順:

1. P0 root selection fix
2. P0 launch flow hardening
3. P0 active root staleness detection
4. P0 App Studio Apply finalization report
5. P1 release verification extension
6. P1 frontend timeout and diagnostics
7. P1 docs cleanup

この順にする理由:

- まず「正しい root を読む」状態にしないと、登録フローを直しても画面に反映されない。
- 次に「固まらない」防御を入れれば、次の不具合調査が止まらない。
- その後に登録 Apply、release verification、docs を整えると、修正が重複しない。

## Tests to Add

### Rust Tests

- `manifest::project_root()`:
  - `TOOLHUB_ROOT` が current exe dir より優先される。
  - `target/release` と source root が両方 root に見える場合の採用 root が期待通り。
- `launch_runner()`:
  - runner が戻らない場合も bounded result を返す。
  - timeout result に root、app yaml、mode が含まれる。

### Python Runner Tests

- `ExeRunner`:
  - `runner: exe` + `mode: gui` は `start_detached()`
  - `runner: exe` + `mode: cli` は `run_blocking()`
  - result log に runner、entry、mode が残る。

### App Studio Tests

- Apply 後に `registration_root_report.json` が作られる。
- context root と active root が違う場合に approval-blocking warning が出る。
- context root と active root が同じでも root type が `dev_build_artifact` の場合に warning/block できる。
- App Studio CLI hash / mtime が report に残る。
- AgendaSnap 型 source は `mode: gui` を生成する。
- stale active root の `mode: cli` を検出する。

### Frontend Tests

- launch modal running timeout 後に close/diagnostics action が表示される。
- success result が返った場合は従来通り閉じられる。
- error result が返った場合はログ path を見せられる。

### Script Tests

- `diagnose_active_root_staleness.ps1`:
  - source `mode: gui`、release `mode: cli` を stale と判定する。
  - runner file hash mismatch を stale と判定する。
  - active root と source root が同じなら pass。
  - active root と context root が同じ stale `target/release` でも `active_root_is_stale_build_artifact` を出す。
  - installed resource root は dev repo と違っても、それだけでは fail にしない。

## Triple Check Protocol

方針確定後、実装前と実装後に以下を必ず行う。

### Check 1: Static Root and Artifact Check

目的: 古い root、古い app.yaml、古い runner が残っていないか確認する。

確認項目:

- `TOOLHUB_ROOT`
- Tauri backend が採用した project root
- root type
- canonical source root
- source root の `apps/<app_id>/app.yaml`
- active root の `apps/<app_id>/app.yaml`
- `release/app_manifest.json`
- `launcher/src-tauri/target/release/apps`
- `launcher/src-tauri/target/release/runner`
- `launcher/src-tauri/target/release/tools/app_studio`
- `launcher/src-tauri/target/release/_up_/_up_`
- `%LOCALAPPDATA%\Programs\ToolHub`
- `%LOCALAPPDATA%\ToolHub`

合格条件:

- active root が意図通り。
- active root の app yaml が source root と一致、または差分が明示的に説明されている。
- `mode`、`runner`、`entry` の差分が report に出る。
- installed resource root は installed environment の正規 root として分類され、dev build artifact root と混同されない。

### Check 2: Runtime Launch Check

目的: 実際の起動で UI が固まらないか確認する。

対象:

- AgendaSnap
- sample GUI app
- sample CLI app
- shared-env app
- legacy frozen-folder app

確認項目:

- 起動ボタン押下後、ToolHub が応答なしにならない。
- GUI アプリは短時間で success result を返す。
- CLI アプリは完了まで待つ場合でも UI が操作不能にならない。
- result JSON が作られる。
- backend log に root、app yaml、mode が出る。

合格条件:

- AgendaSnap の画面が開いた後、起動ダイアログが残り続けない。
- 誤った `mode: cli` を意図的に作っても、timeout/diagnostic に落ちる。

### Check 3: Registration and Release Check

目的: 登録、承認、配布準備のどこにも古い状態が混ざらないか確認する。

確認項目:

- App Studio Suggest
- App Studio Apply
- runtime check
- execution check
- approval gate
- App Pack generation
- `release/app_manifest.json`
- `scripts/verify_release.ps1`
- `scripts/report_release_readiness.ps1`

合格条件:

- Apply 直後に実行 root との整合性 report が出る。
- App Pack が最新でも active root が古い場合、それを別問題として検出できる。
- release verification が target/release stale を見逃さない。

## Non Goals

- `app.yaml` schema を破壊しない。
- runner public I/F を破壊しない。
- `target/release` を手作業同期先として恒久運用しない。
- AgendaSnap 専用の hard code を ToolHub に入れない。
- shared-env 標準化済みの通常登録を frozen-folder 標準へ戻さない。

## Decision Needed Before Implementation

方針確定時に決めること:

1. `python main.py` は dev source 固定とし、release artifact 起動を bootstrap から外す。
2. local release root が source root と違う場合、登録 Apply を block するか warning にするか。
3. launch timeout の既定秒数。
4. running 中の modal をユーザーが閉じられるようにするか、diagnostic 表示後だけ閉じられるようにするか。
5. installed resource root と dev source root の差分をどこまで warning 表示するか。

推奨:

- 1 はまず `TOOLHUB_ROOT` 注入で対応する。
- 2 は dev build artifact root での App Studio Apply は approval-blocking warning、通常起動では warning 表示にする。
- 3 は runner startup result 用に 10 秒、GUI detached probe は runner 側既存 2 秒を維持する。
- 4 は 10 秒後に診断表示と close を許可する。
- 5 は installed resource root では差分だけで fail にしない。更新確認または release verification の対象に留める。
