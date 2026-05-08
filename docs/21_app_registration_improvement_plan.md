# App Registration Improvement Plan

作成日: 2026-05-08

## 目的

ToolHub の App Studio / アプリ登録プロセスについて、現時点で見えている失敗要因、待機時間の原因、検証漏れ、アイコン生成の fallback 化を整理し、次ステップで実装する改善リストとして使える形にする。

この文書は調査結果と改善バックログであり、実装済みの項目は「実施状況」に記録する。

## 現在の登録フローの要約

通常の App Studio 登録は、管理者が Python スクリプトを用意したあと、ToolHub 側が以下を実行する前提になっている。

1. Python entry point と周辺ファイルを解析する。
2. secret scan / file inventory / import analysis を行う。
3. metadata / README / icon 候補を作る。
4. `build_env` を作成し、必要パッケージをインストールする。
5. `requirements.lock` を生成する。
6. PyInstaller の frozen folder を作る。
7. `apps/<app_id>/` に登録する。
8. App Pack zip を作る。
9. `release/app_manifest.json` に disabled 状態で登録する。
10. approve 後に enabled にする。

通常の App 登録では、管理者が runtime archive を作る必要はない。runtime archive は ToolHub 本体の配布用共通 runtime であり、個別 App Pack とは別物である。

## 最重要の結論

現在の問題は、主に次の 5 系統に分かれる。

1. 登録成功判定が甘く、壊れた App Pack / 壊れた `apps/<app_id>` を成功扱いできてしまう。
2. App Studio が対象外ファイルまで広く含め、secret scan と PyInstaller の両方を重くしている。
3. Apply 時に毎回 `build_env` 作成、pip install、PyInstaller clean build を行うため、再登録や再試行が遅い。
4. アイコン生成は AI 設定不足と secret scan の AI submission block により、実質 fallback へ流れやすい。
5. 失敗理由の分類と UI への表示が弱く、管理者が次に何を直せばよいか分かりにくい。

## 実施状況

### 2026-05-08 Phase 0

壊れた登録を成功扱いしないための検証強化を開始し、以下を実装した。

- `scripts/package_app_pack.ps1` で `app.yaml` の `run.entry` と `display.icon` を app directory 内の相対パスとして検証する。
- `scripts/package_app_pack.ps1` で local file 欠落時に zip 作成前に fail する。
- `scripts/package_app_pack.ps1` で zip 作成後、`app.yaml`、`pack_manifest.json`、`README.md`、`requirements.txt`、`display.icon`、`run.entry` が App Pack 内に含まれることを検証する。
- `scripts/verify_release.ps1` で local `run.entry` / `display.icon` と App Pack 内 `run.entry` / `display.icon` を検証する。
- App Studio 本体の `registrar.package_app_pack()` でも同じく `run.entry` / `display.icon` 欠落を App Pack 作成時に fail する。
- App Studio approval の targeted verification で、App Pack 内に `run.entry` が含まれることを確認する。
- App Studio unit test に、`run.entry` 欠落時の packaging failure と zip 内 `run.entry` 検証を追加した。

この変更により、現在の checkout に残っている frozen-folder app の exe 欠落は `verify_release.ps1` で fail として検出される。これは想定どおりであり、次に対象アプリを再 build して `apps/<app_id>/bin/...exe` と App Pack を復元する必要がある。

実行確認:

- PowerShell parser で `scripts/package_app_pack.ps1` と `scripts/verify_release.ps1` の構文を確認済み。
- `python -m py_compile tools/app_studio/app_studio/registrar.py tools/app_studio/app_studio/approval.py` は成功。
- `python -m unittest discover -s tools/app_studio/tests` は成功。
- `scripts/package_app_pack.ps1 -AppId addnum_pdf -NoManifestUpdate` は、`addnum_pdf run.entry file is missing` で想定どおり fail。
- `scripts/verify_release.ps1` は、`addnum_pdf`、`app_20260201_agendasnap`、`officetopdf_toc`、`run_xcgate_upload` の local `run.entry` 欠落と App Pack 内 `run.entry` 欠落を想定どおり NG として検出。

## 調査で確認した根拠

### 1. release 検証が壊れた登録を見逃す

現状の `scripts/verify_release.ps1` は App Pack zip の存在、hash、`app.yaml`、`pack_manifest.json` の有無を中心に確認している。一方で、`app.yaml` の `run.entry` が実際に存在するか、zip 内に含まれているかは確認していない。

現時点の `apps/*/app.yaml` では、次のように `run.entry` が存在しないアプリがある。

| app_id | run.entry | local file exists |
| --- | --- | --- |
| `addnum_pdf` | `bin/addnum_pdf/addnum_pdf.exe` | false |
| `app_20260201_agendasnap` | `bin/app_20260201_agendasnap/app_20260201_agendasnap.exe` | false |
| `officetopdf_toc` | `bin/officetopdf_toc/officetopdf_toc.exe` | false |
| `run_xcgate_upload` | `bin/run_xcgate_upload/run_xcgate_upload.exe` | false |

さらに、現時点の `release/app_packs/*.zip` には `.exe` が含まれていない App Pack がある。それでも `scripts/verify_release.ps1` は成功する。

原因:

- `verify_release.ps1` が `run.entry` を parse していない。
- `package_app_pack.ps1` が zip 作成前に `run.entry` の存在を必須検証していない。
- `apps/*/bin/` は `.gitignore` 対象のため、生成済み exe がない状態でも repo 上では見逃しやすい。

影響:

- 登録済み・release 検証済みのように見えても、実際にはアプリ起動に失敗する。
- アプリ登録失敗の再現性が悪くなり、利用者環境で初めて壊れていることに気づく。

### 2. 待機時間の大部分が secret scan / build_env / PyInstaller に集中している

`data/logs/app_studio/security_checker_timing_report.json` の最新 suggest では、合計約 141.7 秒のうち secret scan が約 129.9 秒を占めていた。

過去の apply 実行ログでは、合計約 448 秒のうち `build_env_creation` が約 336 秒、`pyinstaller_build` が約 82 秒を占めていた。

原因:

- source root が広く、対象外の clone repo、work directory、結果出力、生成物まで scan 対象になっている。
- `build_env` が毎回 rebuild され、pip install の再利用がない。
- PyInstaller が `--clean` で毎回 build cache を捨てている。
- Apply が Suggest 相当の解析、metadata、icon、export も再実行している。
- timing estimate が app_id 単位の直近総時間だけを使い、action、source hash、profile、cache 状態を区別していない。

影響:

- 小さな修正や再試行でも数分単位で待つ。
- Suggest と Apply の見積もりがずれる。
- 管理者が「止まっている」と感じやすい。

### 3. source root が広すぎると PyInstaller が関係ない依存まで拾う

`security_checker_frozen_folder_build_report.md` では、PyInstaller command に unrelated repo 配下の多数の Python file / data file が含まれていた。例として、ToolHub 自体、別プロジェクト、clone repo、作業ディレクトリ配下のファイルが `--add-data` や hidden import 候補に混ざっていた。

その結果、`hook-webrtcvad.py` が要求する `__PyInstaller_hooks_0_webrtcvad` import に失敗し、PyInstaller build が止まっている。

原因:

- entry point の親や周辺ディレクトリを source として扱う際の除外ルールが不足している。
- `work/`, `results/`, clone repo, generated output, unrelated project directory を明確に除外できていない。
- hidden import 推定が広すぎ、対象アプリの import graph ではなく、同一 source tree 内のファイルを過剰に拾っている。
- PyInstaller hook / hooks-contrib の組み合わせが動的で、既知安定版に固定されていない。

影響:

- build が遅くなる。
- アプリ本体と関係ない依存の hook failure で登録が失敗する。
- secret scan の対象も増え、AI submission block につながる。

### 4. アイコン生成が fallback へ流れる原因は複数ある

`icon_work/ai_generation_report.md` では、AI icon prompt generation と image generation が skip され、fallback 候補のみが作られていた。

確認された要因:

- AI が有効化されていない。
- API key が検出されていない。
- secret scan が AI submission を block している。
- 実際の image generation status が `skipped` / model `not_configured` になっている。
- fallback candidate count は 3、API candidate count は 0。

`secret_scan_report.json` では、`blocks_apply=false` である一方、`affects_ai_submission=true` の finding が多数あり、AI 送信だけが止まる状態になっていた。

原因:

- `OPENAI_API_KEY` または Credential Manager 側の API key 設定がない。
- `TOOLHUB_APP_STUDIO_AI_ENABLED` が有効化されていない。
- App Studio が「実際に AI へ送る payload」ではなく、含まれる package 全体の secret scan 結果で AI 送信を止めている。
- source root が広いため、無関係なファイル内の medium finding が AI block に影響している。
- image model / organization verification / quota / rate limit / unsupported parameter の診断が登録フロー前に十分表示されていない。

影響:

- アイコン生成は毎回 fallback になりやすい。
- 管理者には「AI が失敗した」ように見えるが、実際は AI 未設定、secret block、model 問題のどれかを区別しづらい。
- fallback が正常動作なのか、設定不備なのか判断できない。

### 5. 失敗診断と進捗表示が弱い

CLI は progress line を出しているが、Rust backend 側は subprocess の出力を最後にまとめて受け取る実装になっている箇所があり、長時間 phase の live progress 表示に弱い。

また、PyInstaller の failure は report file には残るが、利用者に対しては「何を直せばよいか」の分類が不足している。

原因:

- stdout / stderr を streaming parse して phase update に変換する backend 処理が不足している。
- PyInstaller failure classifier がない。
- secret scan / AI skip / model error / missing key / broad source root の診断が UI 上で分離されていない。
- Apply failure 後に「最短で直すための次アクション」を提示する仕組みがない。

影響:

- 長い待機中に状況が分からない。
- 再試行しても同じ原因で失敗しやすい。
- 管理者が build profile や source root の修正にたどり着きにくい。

## 改善バックログ

| ID | 優先度 | 領域 | 課題 | 原因 | 改善案 | 検証観点 |
| --- | --- | --- | --- | --- | --- | --- |
| AR-001 | P0 | 登録検証 | `run.entry` が存在しない App Pack を成功扱いできる | package / verify が `run.entry` を見ていない | `package_app_pack.ps1` と `verify_release.ps1` で app.yaml を parse し、local / zip 内の `run.entry` 存在を必須チェックする | 既存の exe 欠落 App Pack が fail になる |
| AR-002 | P0 | 登録検証 | approve 前後の release 検証が壊れたアプリを見逃す | App Pack 構造検証が浅い | App Pack 内の `app.yaml`, `pack_manifest.json`, `README`, icon, `run.entry`, forbidden files を検証する | `scripts/verify_release.ps1` が欠落 payload を検出する |
| AR-003 | P0 | source scope | unrelated repo / generated files が登録対象に混ざる | source root と除外ルールが不足 | App Studio に source root の明示指定、preview、除外ルール、`.toolhubignore` 相当を追加する | `work/`, `results/`, clone repo が inventory / secret scan / PyInstaller に入らない |
| AR-004 | P0 | failure prevention | PyInstaller が関係ない hook failure で落ちる | hidden import / add-data 推定が広すぎる | import graph 起点を entry point に限定し、build profile の exclude / hidden-import override を UI で扱う | `webrtcvad` のような無関係 hook が入らない |
| AR-005 | P0 | icon AI | AI icon が毎回 fallback になる | AI disabled / missing key / secret block が区別されない | 登録前に AI 診断を実行し、AI disabled、missing key、secret block、model error を別々に表示する | fallback 理由が UI と report で一致する |
| AR-006 | P1 | secret scan | AI 送信だけ過剰に block される | package 全体の finding で AI submission を止めている | 実際に AI へ送る prompt payload だけを別途 scan し、package finding とは分ける | package 内 warning があっても AI payload が安全なら icon AI が動く |
| AR-007 | P1 | performance | Apply が毎回 `build_env` を作り直す | env cache がない | requirements hash + Python version + build profile hash で `build_env` を再利用する | 2 回目 Apply の env 作成が skip される |
| AR-008 | P1 | performance | pip install が毎回遅い | wheel / pip cache 活用が明示されていない | App Studio 専用 wheel cache を使い、offline / cached install を優先する | 同一 dependencies の install 時間が短縮される |
| AR-009 | P1 | performance | PyInstaller が毎回 clean build される | `--clean` 固定で cache を捨てる | 通常再試行では incremental build、問題時だけ clean build にする | clean なし再試行の build 時間が短縮される |
| AR-010 | P1 | performance | Suggest 後の Apply が同じ解析をやり直す | Suggest artifact を Apply が再利用しない | metadata / README / icon / inventory / secret scan を source hash 付きで保存し、Apply で再利用する | Suggest 済みアプリの Apply 前半 phase が skip される |
| AR-011 | P1 | progress UX | 長時間 phase が止まって見える | subprocess output の streaming が弱い | Rust backend で App Studio CLI stdout を streaming parse し、phase progress を UI に反映する | build_env / PyInstaller 中に UI が更新される |
| AR-012 | P1 | timing | 見積もりが action と実測に合わない | app_id 単位の前回総時間だけを使う | action、source hash、profile、cache hit 状態ごとに timing history を分ける | Suggest と Apply の見積もりが混ざらない |
| AR-013 | P1 | PyInstaller | hooks-contrib / PyInstaller の新しさで壊れる | version range が広い | 既知安定版を lock し、更新は検証後に行う | 同じ app が日によって hook failure しにくくなる |
| AR-014 | P1 | Python runtime | 開発機の Python version に依存する | build Python が固定されていない | App Studio build 用 Python version を決め、診断に表示する | 未対応 Python で build する前に警告が出る |
| AR-015 | P1 | failure UX | PyInstaller error が利用者に難しすぎる | failure classifier がない | common failure を分類し、source scope、missing package、hook failure、binary dependency などの対処を出す | failure report に分類と推奨アクションが出る |
| AR-016 | P2 | build profile | 管理者が profile 調整しづらい | profile editor / dry-run が弱い | hidden imports / excludes / data files の preview と編集 UI を追加する | profile 変更前後の PyInstaller command 差分が見える |
| AR-017 | P2 | icon UX | fallback が失敗に見える | fallback と AI skip の意味が表示されない | fallback は正常代替、AI skip は設定/scan理由として分けて表示する | 管理者が fallback 採用か AI 設定修正か選べる |
| AR-018 | P2 | approval | approve が全体 release verify に依存し遅い | target app だけの軽量検証がない | approve 前は対象 app / target App Pack の検証を優先し、全体 verify は別コマンドに分ける | approve の待ち時間が短縮される |
| AR-019 | P2 | smoke test | App Pack が起動可能か検証していない | entry file 存在以上の実行検証がない | optional smoke command / CLI check / launch dry-run を app.yaml に追加できるようにする | 登録後に最低限の起動確認ができる |
| AR-020 | P2 | reports | 調査に必要な情報が複数 report に分散 | summary index がない | App Studio run summary に phase time、skip reason、failure reason、重要 report path を集約する | 1 つの summary から原因調査を開始できる |
| AR-021 | P2 | App Pack spec | `requirements.lock` の扱いが仕様と実装で曖昧 | spec では source of truth に含まれるが sample app には存在せず、package / verify は必須にしていない | runner / build_mode 別に `requirements.lock` を必須・任意・警告のどれにするか決め、package / verify / docs を揃える | sample app と frozen-folder app の両方で意図した結果になる |
| AR-022 | P2 | validator consistency | PowerShell と Python で app.yaml path 検証が重複している | packaging / release verify / App Studio registrar が別々に YAML scalar と相対パスを処理している | 共通 validator 化、または同じ fixture を使う golden test を追加して挙動差を防ぐ | `run.entry` / `display.icon` の edge case が各経路で同じ結果になる |

## 推奨実装順

### Phase 0: 壊れた登録を成功扱いしない

最初に `run.entry` 検証を強化する。これは待ち時間短縮ではないが、失敗した登録を成功扱いするリスクを止めるため最優先にする。

対象:

- `scripts/package_app_pack.ps1`
- `scripts/verify_release.ps1`
- 必要なら `tools/app_studio/app_studio/approval.py`

実装内容:

- `app.yaml` の `run.entry` を parse する。
- local `apps/<app_id>/<run.entry>` の存在を確認する。
- App Pack zip 内の `<app_id>/<run.entry>` の存在を確認する。
- 欠落時は warning ではなく fail にする。

### Phase 1: source scope を絞る

次に、待機時間と失敗率の両方に効く source scope の改善を行う。

対象:

- `tools/app_studio/app_studio/file_classifier.py`
- `tools/app_studio/app_studio/build_profile.py`
- `tools/app_studio/app_studio/frozen_folder_builder.py`
- App Studio UI / Rust command 層

実装内容:

- source root 明示指定を追加する。
- include / exclude preview を出す。
- `work/`, `results/`, generated output, clone repo, `.git`, virtualenv, cache 類を既定除外に追加する。
- `.toolhubignore` 相当の project-local ignore を検討する。

### Phase 2: 再試行を速くする

source scope を絞ったあと、cache と再利用を入れる。

対象:

- `app_env_builder.py`
- `lock_generator.py`
- `frozen_folder_builder.py`
- `timing.py`
- App Studio output artifact 管理

実装内容:

- `build_env` を requirements hash で再利用する。
- wheel cache を使う。
- Suggest artifact を Apply で再利用する。
- PyInstaller clean build を通常再試行から外す。
- timing history を action / source hash / profile hash 別にする。

### Phase 3: AI icon 生成を診断可能にする

fallback そのものは残しつつ、AI を使う場合に何が必要かを明確にする。

対象:

- `openai_client.py`
- `icon_generator.py`
- `secret_scanner.py`
- App Studio UI

実装内容:

- 登録前 AI diagnostics を必須表示する。
- AI disabled / missing key / secret block / model error を区別する。
- AI payload のみを対象にした secret scan を追加する。
- image model の利用可否を事前に診断する。
- fallback の採用と AI 再試行を UI 上で分ける。

### Phase 4: PyInstaller failure を直しやすくする

失敗時に管理者が修正できる状態にする。

対象:

- `frozen_folder_builder.py`
- build report generator
- build profile UI

実装内容:

- hook failure / missing module / binary dependency / broad source root / hidden import 過剰を分類する。
- report に原因分類と推奨修正を出す。
- known-good PyInstaller / hooks-contrib version を固定する。
- build profile の exclude / hidden import を UI から編集できるようにする。

## 今すぐ直すべきもの

次の改善は、実装リスクに対して効果が大きい。

1. `run.entry` の local / zip 存在検証を追加する。（2026-05-08 Phase 0 で実装済み）
2. `package_app_pack.ps1` で `run.entry` 欠落時に fail する。（2026-05-08 Phase 0 で実装済み）
3. `verify_release.ps1` で App Pack 内 `run.entry` 欠落時に fail する。（2026-05-08 Phase 0 で実装済み）
4. source scope preview と既定除外を強化する。
5. AI icon fallback の理由を UI / report で分離表示する。

## 注意点

- runtime archive の自動生成や同梱方針をこの改善で大きく変える必要はない。
- App Pack と runtime archive の責務は分けたままにする。
- `app.yaml` の既存仕様は破壊しない。
- 既存 app が `run.entry` 欠落で fail するようになるため、検証強化の導入時には現在の欠落 app を修正するか、検証結果を known issue として扱う必要がある。
- `release/` や `runtime/` の実体を直接変更する前に、まず scripts / App Studio 側の検証強化から進める。
