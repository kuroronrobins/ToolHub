# App Registration Zero-Stress Validation Protocol

作成日: 2026-05-16

## 目的

`C:\Users\kuroron\Documents\RD` 配下に保存されている各種 Python アプリの `main.py` を対象に、現在の ToolHub が「アプリ登録画面でメインファイルを指定するだけで、登録、共有ランタイム作成または再利用、承認、起動確認まで進められる状態」にあるかを検証する。

この検証では、単に登録が成功するかだけでなく、管理者が迷わず進められるか、共有ランタイムが app ごとではなく依存バージョン単位で適切に自動登録されるか、登録後にランチャーから実際に起動できるかを確認する。

## 現行仕様の前提

2026-05-16 時点の実装上、通常新規登録は `shared-env` 固定である。

- GUI の初期値は `buildMode: shared-env`、`generateLock: true`、`buildFrozenFolder: false`、`verifyRuntime: true`。
- 通常新規登録では `.exe` は受け付けず、Python ソースを entry とする。
- App Studio CLI は通常登録時に `shared-env` へ正規化し、`runtime/envs/<env_id>/` を作成または再利用する。
- 生成 `app.yaml` は `run.runner: python_shared_env`、`run.entry: src/<entry_relative>`、`run.env_id: <env_id>`、`runtime.distribution_mode: shared_env`、`runtime.required_runtime: python-shared-env:<env_id>`、`runtime.requirements_lock: requirements.lock` を持つ。
- runner は `runtime/envs/<env_id>/Scripts/python.exe` を使い、`VIRTUAL_ENV` と `PATH` をその共有環境へ向けて起動する。
- Playwright 系は自動 startup smoke が warning 扱いで skip される場合があり、ログイン、ブラウザ、外部サイト操作は手動確認対象である。

古い docs には frozen-folder 標準の記述が残っているため、本検証では docs 記述ではなく、生成された `app.yaml`、`import_plan.json`、`shared_runtime_report.md`、`runtime_check_result.json`、runner 起動結果を最終判定の根拠にする。

## 用語

`ゼロストレス登録` は、次を満たす状態と定義する。

- 管理者が登録画面で `main.py` を選び、必要なら表示名と App ID を確認するだけで進められる。
- `requirements.txt`、`requirements.lock`、`app.yaml`、runtime env、App Pack を手で作らない。
- Python、pip package、Playwright browser、app_env、PyInstaller を管理者が個別に手作業で準備しない。
- 失敗時は、画面または report から次に直すことが分かる。
- 登録後、ホーム更新で表示され、ランチャーから起動できる。

判定ランク:

| ランク | 意味 | ゼロストレス判定 |
| --- | --- | --- |
| S | `main.py` 指定のみで Preflight、Suggest、Apply、Approve、起動確認まで完了 | 合格 |
| A | `main.py` 指定に加え、source root の指定または表示名/App ID 修正のみで完了 | 実用上合格 |
| B | `.toolhubignore` 追加、依存 pin、認証 state 除外など、軽微なソース側調整が必要 | 要改善 |
| C | App Studio 側の修正、runner/runtime 修正、依存解決方針変更、アプリコード修正が必要 | 不合格 |
| N/A | venv、生成物、site-packages、過去 output、失敗版など登録対象外 | 評価対象外 |

全体として「現在の ToolHub はゼロストレス」と言える条件は、代表本番候補がすべて S または A で、共有ランタイムの自動作成または再利用が確認でき、登録後起動に C 判定がないこととする。

## 安全方針

検証は、可能なら production checkout ではなく一時コピーまたは検証用 branch で実施する。

- 検証用 App ID は `zt_<project>_<yyyymmdd>_<seq>` のように prefix を付ける。
- 既存 app_id へ上書き登録しない。
- `release/`、`runtime/`、`apps/` は検証で更新されるため、検証前後の `git status --short` を必ず記録する。
- 共有ランタイムは複数 app から参照されうるため、Delete tab で app を削除しても `runtime/envs/<env_id>` を不用意に削除しない。
- `.auth/`、cookie、storage state、token、`.env`、logs、screenshots、tmp、venv、生成物を登録対象に含めない。
- 外部サービス、社内サイト、実メール送信、ファイルアップロードなどを伴う app は、実処理を行わない smoke モードまたは手動確認に切り分ける。

## Phase 0: 環境確認

目的: App Studio と共有ランタイム作成に必要な前提を確認する。

実行コマンド:

```powershell
git status --short
python main.py --check
Test-Path .\tools\app_studio\main.py
Test-Path .\runtime\python\python.exe
Test-Path .\runtime\envs
```

可能なら追加で実行する。

```powershell
.\scripts\verify_runtime.ps1 -RequireRuntime
```

確認項目:

- App Studio CLI が存在する。
- `runtime/python/python.exe` がある場合、共有 runtime 作成の base Python として優先される。
- `runtime/python/python.exe` がない場合、どの fallback Python が使われるかを report に記録できる。
- 既存の `runtime/envs/toolhub_env_registry.json` がある場合、既存 env と app 参照を記録する。
- 検証前 dirty file がある場合、今回の検証由来かどうかを区別する。

Pass 条件:

- App Studio preflight が CLI 欠落で止まらない。
- 共有ランタイム作成に使える Python が検出される。

## Phase 1: RD 配下 main.py の棚卸し

目的: RD 配下の `main.py` から、実際に登録評価すべきアプリ候補と除外対象を分ける。

探索コマンド例:

```powershell
$root = "C:\Users\kuroron\Documents\RD"
Get-ChildItem -Path $root -Recurse -Filter main.py -File -ErrorAction SilentlyContinue |
  Where-Object {
    $_.FullName -notmatch '\\(venv|\.venv|env|site-packages|__pycache__|ToolHub_AppStudio_Output|build|dist|target|release|runtime|node_modules|\.git|\.gitup|backups)\\'
  } |
  Select-Object FullName, Length, LastWriteTime |
  Sort-Object FullName
```

除外ルール:

- `venv`, `.venv`, `env`, `site-packages` 配下の `main.py` は対象外。
- `ToolHub_AppStudio_Output`, `build`, `dist`, `target`, `release`, `runtime`, `.gitup`, `backups` 配下は対象外。
- ToolHub 自身の `main.py`、runner、旧同梱検証アプリ、過去 staging output は対象外。
- `失敗` と名前にある過去試行版は、必要がある場合だけ regression ケースに回す。
- SecurityFixWork や clone repo 内の重複は、元プロジェクトが残っている場合は原則重複扱いにする。

一次代表候補:

| グループ | 代表候補 | ねらい |
| --- | --- | --- |
| RealtimeTranslator | `C:\Users\kuroron\Documents\RD\20250608_RealtimeTranslator\RealtimeTranslator_Clean2\main.py` または最新安定版 | 音声/VAD/GUI 依存、重め依存の登録性 |
| Calibook | `C:\Users\kuroron\Documents\RD\20250916_Calibook\py\main.py` | entry が nested source root にある場合の扱い |
| XCgateAutoUpload | `C:\Users\kuroron\Documents\RD\20251103_XCgateAutoUpload\xcgate_flows\src\main.py` | Playwright、認証 state 除外、manual check |
| ExcelBatchReplace | `C:\Users\kuroron\Documents\RD\20251123_ExcelBatchReplace\main.py` または `app\main.py` | Excel/ファイル処理、source root 推定 |
| AgendaSnap | `C:\Users\kuroron\Documents\RD\20260201_AgendaSnap\main.py` | 既存 App Studio output と重複しない再登録 |
| PDFApplication | 実ソースが残っている場合のみ対象化 | Flet/PDF 大型 GUI、既知バージョン維持 |

各候補について記録する。

| 項目 | 記録内容 |
| --- | --- |
| candidate_id | `rt_clean2`, `calibook_py` など |
| entry_path | 絶対パス |
| suggested_source_root | 空欄で試すか、明示 source root が必要か |
| existing requirements | `requirements.txt`, `requirements.lock`, `pyproject.toml` の有無 |
| known app type | GUI / CLI / Playwright / Flet / audio / file batch |
| sensitive risk | `.auth`, `.env`, logs, storage state, credentials の有無 |
| duplicate status | canonical / duplicate / generated / old failed |

Pass 条件:

- 評価対象外の `main.py` を誤って本登録しない。
- 本番候補を最低 5 系統選ぶ。

## Phase 2: 静的事前確認

目的: App Studio を走らせる前に、登録阻害要因を見落とさない。

各候補で確認する。

```powershell
Test-Path "<entry_path>"
Get-ChildItem "<source_root>" -Force
Get-ChildItem "<source_root>" -Force -Include requirements.txt,requirements.lock,pyproject.toml,.toolhubignore
```

確認項目:

- entry が source root 配下にある。
- source root が広すぎない。`C:\Users\kuroron\Documents\RD` 全体や drive root は不可。
- `.auth/`, `.env`, token, cookie, storage state がある場合は、初回はそのまま Preflight/Suggest で block されるか確認し、必要なら `.toolhubignore` を別ケースとして扱う。
- `requirements.txt` に broad range がある場合、既存 `.venv` または `requirements.lock` から既知動作バージョンが拾われるかを重点確認する。
- Flet app は `flet` と `flet-desktop` のバージョンが揃うかを重点確認する。

Pass 条件:

- source root 混入リスクと secret risk を事前に分類できている。
- source root 未指定でよい候補と明示指定が必要な候補が分かれている。

## Phase 3: GUI 登録プロトコル

目的: 実際のアプリ登録画面で、管理者操作だけで登録できるかを確認する。

各候補で次を実施する。

1. ToolHub を起動し、管理者画面から App Studio 新規登録を開く。
2. `Entry` に対象 `main.py` を指定する。
3. まず `ソース範囲` は空欄で試す。entry 親フォルダでは不足する構成だけ、2 回目に明示 source root を指定する。
4. 自動提案された App ID と表示名を確認する。検証用 App ID に置き換える。
5. `事前確認を実行` を押す。
6. `登録内容を作成` を押す。
7. AI 提案、metadata、icon は必須条件にしない。API 候補がない場合は default icon 使用として記録する。
8. `テスト登録して配布物検証` を押す。
9. 結果パネルで `登録方式`、`runtime検証`、`実行テスト`、`App Pack`、`承認ゲート診断` を確認する。
10. 承認可能な場合、まず `配布リスクがある警告は承認しない` で承認する。manual check のみで strict 不可の場合は `警告ありでも承認可能` を使い、理由を記録する。
11. ホームを更新し、アプリカードが表示されることを確認する。
12. ランチャーから起動し、初期画面表示または CLI 完了を確認する。

GUI 証跡として記録する。

- Preflight 結果。
- 操作ごとの所要時間。
- 画面に出た user-facing message。
- `selectedBuildMode`。
- `runtimeStatus`。
- `executionStatus`。
- `approvalAllowed`。
- `enabled`。
- `catalogVisible`。
- 起動結果と log path。

Pass 条件:

- `Entry` 指定から `Apply` まで、管理者が CLI を手で実行しない。
- `Apply` 後に `apps/<app_id>/app.yaml` と App Pack が生成される。
- `release/app_manifest.json` は Apply 後 `enabled=false`、Approve 後 `enabled=true` になる。
- ホーム更新後に表示される。

## Phase 4: 共有ランタイム検証

目的: 共有ランタイムが自動作成または再利用され、runner がその環境で起動していることを確認する。

Apply 後、対象 app について以下を確認する。

```powershell
$appId = "<app_id>"
Get-Content ".\apps\$appId\app.yaml"
Get-ChildItem ".\runtime\envs"
Get-Content ".\runtime\envs\toolhub_env_registry.json" -Raw
Get-Content ".\apps\$appId\requirements.lock" -Raw
```

確認項目:

- `apps/<app_id>/app.yaml`:
  - `run.runner: python_shared_env`
  - `run.entry: src/...py`
  - `run.env_id` が空でない
  - `runtime.distribution_mode: shared_env`
  - `runtime.required_runtime: python-shared-env:<env_id>`
  - `runtime.requirements_lock: requirements.lock`
  - `runtime.shared_env.env_id` が `run.env_id` と一致
- `runtime/envs/<env_id>/`:
  - `Scripts/python.exe` が存在する
  - `requirements.lock` が存在する
  - `toolhub_env_manifest.json` が存在する
  - `requirements_lock_sha256` が app 側 lock と整合する
- `runtime/envs/toolhub_env_registry.json`:
  - 対象 app_id が env の `apps` に入る
  - 2 個目以降の同じ lock の app では既存 env の `apps` へ追加される
- `shared_runtime_report.md`:
  - `created` か `reused` が分かる
  - `known_good_python` と `known_good_source` が記録される
  - `base_python` が妥当
- `requirements.lock`:
  - App 実行依存だけが入り、PyInstaller など build-only package が混入しない
  - broad requirement が既知動作 version に pin される
  - Flet app は `flet` と `flet-desktop` の version が揃う

再利用テスト:

1. 依存 lock が同じになる小さい app を 2 個登録する。
2. 2 個目の `shared_runtime` phase が `reused` になることを確認する。
3. `env_id` が同一で、registry の `apps` に 2 app が並ぶことを確認する。

ランナー起動確認:

```powershell
python runner/toolhub_runner/main.py --project-root . --app-id <app_id>
```

GUI app は detached 起動になる場合があるため、結果 log と画面表示を合わせて確認する。CLI app は exit code と stdout/stderr を確認する。

Pass 条件:

- 管理者が runtime env を手で作らなくても `runtime/envs/<env_id>` が作成される。
- 同じ依存 lock は再利用される。
- runner が PATH Python ではなく `runtime/envs/<env_id>/Scripts/python.exe` を使う。
- 共有 runtime がない、env_id が空、registry 未登録、app.yaml と runtime が不整合、のいずれも起きない。

## Phase 5: 代表ケース別テストマトリクス

| ケース | 対象 | 期待結果 |
| --- | --- | --- |
| 標準 CLI | 依存なし、または標準ライブラリ中心 | S 判定、env 作成、CLI exit 0 |
| ファイル処理 | Excel/PDF/CSV 系 | source root と assets が適切に含まれ、起動確認できる |
| nested entry | `py/main.py`, `src/main.py` | entry のみで不足する場合は source root 指定で A 判定 |
| Flet GUI | PDFApplication 等 | 既知 Flet version が lock に反映され、起動直後 TypeError が出ない |
| Playwright | XCgateAutoUpload | `.auth` を同梱せず、startup smoke は manual warning、browser/login は手動確認 |
| 音声/VAD | RealtimeTranslator | native/audio 依存の lock と起動時 stderr を確認 |
| 既存 lock | `requirements.lock` あり | 既存 lock が優先され、env_id が lock に基づく |
| broad requirements | `flet>=...` 等 | 既知動作 version があれば pin、なければ fresh resolve として明示 |
| secret 混入 | `.env`, `.auth`, storage state | Apply block または明示除外が必要。無言同梱しない |
| runtime 再利用 | 同一 lock の 2 app | 2 app 目で `reused`、registry apps 追記 |

## Phase 6: 失敗分類

失敗時は、以下の分類で記録する。

| 分類 | 例 | 判定 |
| --- | --- | --- |
| source selection | source root が狭すぎる、広すぎる、entry が外 | A または B |
| source contamination | venv、生成物、別 repo、logs が混入 | B |
| secret block | `.auth`, token, `.env`, storage state | B。案内が不明なら C |
| dependency lock | broad range が最新へ上がり既存 app と不整合 | C |
| shared runtime create | venv 作成失敗、pip install 失敗、base Python 不正 | C |
| shared runtime reuse | 同一 lock なのに env が再利用されない | C |
| runtime check | env python なし、entry なし、fatal startup stderr | C |
| approval gate | app-specific fail、App Pack 欠落、stale result | C |
| catalog visibility | enabled なのにホームに出ない | C |
| runner launch | ランチャーから起動不可、PATH Python を使う | C |
| UX | 画面上の理由が分からず report を深掘りしないと進めない | B または C |

## Phase 7: 合否判定

各候補の最終判定表:

| candidate_id | entry | source root | 操作量 | Preflight | Suggest | Apply | Approve | Launch | runtime | 判定 | 主因 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
|  |  | blank / explicit | S/A/B/C | pass/fail | pass/fail | pass/fail | pass/fail | pass/fail/manual | created/reused/fail |  |  |

共有ランタイム判定表:

| env_id | created/reused | apps | python | lock sha256 | key packages | known_good_source | 判定 |
| --- | --- | --- | --- | --- | --- | --- | --- |
|  |  |  |  |  |  |  |  |

ゼロストレス総合判定:

- 合格: 代表本番候補がすべて S/A。共有ランタイムは自動作成または再利用。ランチャー起動確認済み。C 判定なし。
- 条件付き合格: B があるが、画面案内と `.toolhubignore` などの軽微操作で解決でき、C がない。
- 不合格: 1 件以上 C があり、特に共有ランタイム、dependency lock、runner 起動、catalog visibility のいずれかに C がある。

## 最終報告フォーマット

```md
## Summary

- RD 配下 main.py 候補数:
- 評価対象数:
- S/A/B/C/N/A:
- 総合判定:

## Environment

- ToolHub commit:
- 検証 checkout:
- runtime/python/python.exe:
- 既存 runtime/envs:
- 検証前 git status:

## Candidate Results

| candidate | result | reason | runtime | launch |
| --- | --- | --- | --- | --- |

## Shared Runtime Results

| env_id | created/reused | apps | lock | notes |
| --- | --- | --- | --- | --- |

## Zero-Stress Findings

- main.py 指定のみで完了したもの:
- source root 指定だけ必要だったもの:
- .toolhubignore や依存調整が必要だったもの:
- ToolHub 実装修正が必要だったもの:

## Evidence

- `ToolHub_AppStudio_Output/<app_id>/import_plan.json`
- `ToolHub_AppStudio_Output/<app_id>/shared_runtime_report.md`
- `ToolHub_AppStudio_Output/<app_id>/runtime_check_result.json`
- `ToolHub_AppStudio_Output/<app_id>/execution_test_result.json`
- `apps/<app_id>/app.yaml`
- `runtime/envs/<env_id>/toolhub_env_manifest.json`
- `runtime/envs/toolhub_env_registry.json`
- runner log path

## Risks / Open Items

- Playwright 手動確認:
- 外部サービス依存:
- 認証 state:
- runtime cleanup:
- docs と実装の差分:
```

## 最小検証セット

時間が限られる場合は、まず次の 4 件で実施する。

1. 依存なしまたは軽量 CLI app: shared runtime 作成の基本確認。
2. Calibook: nested source root と source root 指定要否の確認。
3. ExcelBatchReplace または AgendaSnap: 実務ファイル処理 app の登録確認。
4. XCgateAutoUpload: Playwright、`.auth` 除外、manual warning の確認。

この 4 件で S/A が揃い、共有 runtime 作成と再利用が確認できた後に、RealtimeTranslator、PDFApplication、その他重い GUI app へ広げる。
