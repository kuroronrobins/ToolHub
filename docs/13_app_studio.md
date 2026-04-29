# GUI Build方式・AI提案・結果表示補足

通常新規登録 GUI は BuildMode を選ばせません。Python ソースから配布用 frozen-folder exe を作成して登録する固定フローです。

旧来の `auto` / `app-env` / `existing-exe` / Python 直接実行は、既存 manifest 互換や古いログを読むための概念として残っていますが、通常新規登録 GUI の選択肢ではありません。Entry が `.exe` の場合は、既存 exe 登録ではなく Python ソースを選び直す必要があります。

GUIでは、Suggest が生成した `proposed_app.yaml` と `icon_work/` をAI/fallback提案として読み込めます。表示対象は、表示名、short_description、detail.description、categories、search keywords、examples、use_cases、inputs、outputs、notes、icon prompt、更新時の release notes 草案、`icon_candidate_1.png`、`icon_final.png`、`icon_candidate_1.url.txt`、`icon_fallback.svg`、互換用の `icon_final.svg` です。AI提案は自動確定せず、採用ボタンで表示名やicon promptなど編集可能な入力欄へ反映します。APIキー未設定、AI無効、OpenAI packageなし、API失敗時も CLI 側の deterministic fallback で動きます。secret scan でAI送信対象にリスクがある場合はAI送信しません。

AI提案パネルはCLIへ渡すAI環境の診断も表示します。表示対象は AI enabled、API key source、Text model、Image model、CLI env ready です。APIキー本文は表示しません。`metadata_ai_report` と `icon_work/ai_generation_report.md` から、metadata/image それぞれの `status`、`model`、`parse_status`、`content_type`、`saved_candidate`、`fallback_reason` も確認できます。

GUIでは CLI process の `exit_code` / `process_ok` と、`execution_test_result.json` の `overall_status` / `approval_allowed` を分けて表示します。通常新規登録の frozen-folder では runner dry execution や Playwright ログイン未確認により `overall_status: warn` になることがあります。警告は `approval_blocking_warning`、`non_blocking_warning`、`info` に分類され、`approval_allowed: true` かつ `approval_blocking_warnings_count: 0` の場合は、デフォルトの慎重モードでも承認できます。App Packが見つからない場合は App Pack 欄だけ `not found` と表示します。Apply後はGUIが `app_studio_read_result` を再実行し、生成済みJSONの内容を表示へ反映します。

## AI提案メタデータとmetadata_override

Metadata editor は、現在の編集値と AI/fallback 提案値を項目ごとに並べて表示します。`Adopt` はその項目だけを編集値へコピーし、`Revert` は採用直前の値へ戻します。`Adopt all proposals` は表示中の提案項目だけをまとめて採用します。AI提案は読み込み・生成だけでは確定しません。

GUIで編集できる metadata は `short_description`、`description`、`categories`、`keywords`、`examples`、`use_cases`、`inputs`、`outputs`、`notes` です。更新GUIでは `release_notes` と `change_summary` も同じ editor で扱います。配列項目はMVPとして改行またはカンマ区切りの textarea です。

編集値がある場合、GUI は `%LOCALAPPDATA%\ToolHub\data\app_studio\metadata_overrides\` に一時JSONを書き、CLIへ `--metadata-override <path>` を渡します。空欄や空配列は上書きしません。JSONには APIキーや secret を入れず、ログには値本文ではなく `metadata_override_keys` だけを記録します。不正JSONは CLI エラーとして扱い、型不一致や secret らしい値は警告として無視します。

metadata_override は CLI の metadata 生成後に merge され、`proposed_app.yaml`、`final_app/app.yaml`、Apply 後の `apps/<app_id>/app.yaml` に反映されます。反映先は `display.short_description`、`detail.description`、`display.categories`、`search.keywords`、`search.examples`、`detail.use_cases`、`detail.inputs`、`detail.outputs`、`detail.notes`、`release.release_notes`、`release.change_summary` です。結果パネルには metadata_override の使用有無と反映キーを表示します。

Icon候補はPNGを主表示にします。GUIで `candidate_png` または `final_png` を採用すると、管理者認証済みの Tauri command が `%LOCALAPPDATA%\ToolHub\data\app_studio\icon_overrides\` に一時JSONを書き、CLIへ `--icon-override <path>` を渡します。採用前のPNG候補はレビュー用だけで、Apply時に自動確定しません。fallback SVGを選ぶ場合はPNG overrideを渡さず、CLIの deterministic fallback PNG と互換用SVGを使います。

# ToolHub App Studio

## 通常新規登録フローの固定ポリシー

App Studio の通常新規登録フローは、通常ユーザー向け配布専用です。入力は Python ソースを基本とし、既存 exe 登録、Python 直接実行、利用者向け app_env 実行方式は通常 GUI から選択できません。

通常フローは、Python ソース入力 → 解析 → 内部 `build_env` 作成 → 依存インストール → `requirements.lock` 生成/更新 → PyInstaller frozen-folder build → frozen-folder 配布物検証 → `app.yaml` 生成/仮登録、の一本道です。`requirements.lock` 生成、frozen-folder build、配布物検証は常に ON です。

`app.yaml` の `run.entry` は `bin/<app_id>/<app_id>.exe` を指し、通常ユーザー向け配布で `.py` を実行入口にしません。`--onefile` は標準にせず、ToolHub の標準は PyInstaller `--onedir --clean --contents-directory .` の folder-based frozen output です。

`build_env` は exe 作成のためだけに使う内部作業環境です。`runtime/app_envs/<app_id>` には作らず、App Studio 出力ディレクトリ配下に作成します。利用者 PC に要求せず、`final_app`、App Pack、release、runtime には含めません。

非 Python 資産は拡張子だけで一律に除外しません。メイン Python ファイルとローカル import 先を再帰的に解析し、`open(...)`、`Path(...)`、`Path(__file__).parent / ...`、`os.path.join(...)`、`read_text()`、`read_bytes()`、`pandas.read_csv(...)`、`pandas.read_excel(...)`、設定ファイル読み込みなどの固定パス参照から JSON / CSV / XLSX / YAML / TOML / INI / flow / txt / md を add-data 候補にします。`config`、`config.default`、`assets`、`templates`、`static`、`icons`、`images`、`flows` などの定番リソースフォルダも候補になります。

`.auth/`、logs、screenshots、tmp/temp、仮想環境、build/dist、node_modules、`.git`、`.env`、pem/key、token/secret/password/api_key/credentials、storage_state/cookie/session らしいファイルは同梱しません。機微情報の可能性がある場合は blocked または manual check とし、`file_inventory.json` / `file_inventory.md` / `build_profile_report.md` / `runtime_check_report.md` で理由を確認できるようにします。動的パス参照は無理に全フォルダを同梱せず manual check とします。

配布物検証では、exe の存在、`run.entry` が exe を指すこと、build_profile の add-data が frozen-folder 内に存在すること、禁止ファイルが混入していないこと、`build_env` が混入していないこと、frozen-folder と add-data のサイズを確認します。Playwright を含むアプリでは `--collect-all playwright` を自動反映しますが、ブラウザバイナリ、ログイン、社内サイト操作、認証済み storage state は自動検証済みとは扱わず manual check とします。

## 目的

ToolHub App Studio は、開発者が既存アプリのメインファイルを指定するだけで、ToolHub が検出できる `apps/<app_id>/app.yaml` 形式へ変換するための開発者向け CLI です。

ランチャー本体には App Studio 専用 UI や個別アプリ固有処理を入れません。解析、提案、仮登録、承認は `tools/app_studio` と `scripts/import_app.ps1` で扱います。

GUI 版 App Studio は管理者画面から開く方針です。通常ランチャー画面に App Studio や APIキー管理を直接出さず、初回管理者パスワード設定または管理者ログイン後の管理者ダッシュボードからのみ遷移します。

OpenAI APIキーは管理者画面の AI/APIキー管理で扱います。キー本体は設定JSON、`app.yaml`、App Pack、ログには保存せず、Windows では Credential Manager を使います。APIキー未設定時も App Studio は deterministic fallback で動作します。

## GUI新規登録フロー

管理者画面の App Studio から、新規アプリ登録の GUI フローを実行できます。GUI は既存の CLI 版 `tools/app_studio/main.py` を呼び出し、CLI の生成物と登録仕様をそのまま使います。

GUI で入力できる項目:

- Entry ファイルパス
- Entry 参照ボタン: Windows ではファイル選択ダイアログから Python ソースを選択します。`.exe` は通常新規登録の入力として扱いません。
- App ID
- 表示名
- Icon Prompt

GUI で固定表示される実行予定:

- `requirements.lock` 生成/更新
- 内部 `build_env` 作成と依存インストール
- PyInstaller `--onedir --clean --contents-directory .` による frozen-folder build
- frozen-folder 配布物検証

app_env 作成/再作成、BuildMode 選択、既存 exe 登録、Python 直接実行は通常新規登録 GUI から選べません。

GUI で実行できる操作:

- `Suggest`: 元フォルダ側の `ToolHub_AppStudio_Output/<app_id>/` に提案生成
- `Apply`: `apps/<app_id>/` へ仮登録し、`release/app_manifest.json` へ `enabled=false` で登録
- `Approve`: 実行確認結果を確認し、承認可能な場合に `enabled=true` へ変更

Apply 後は `execution_test_result.json`、`runtime_check_result.json`、App Pack、`enabled` 状態を GUI に表示します。`fail` がある場合は承認できません。GUIでは `AllowWarnings` と `StrictApproval` を選択できます。

AppId / Name 自動提案:

- `main.py`, `app.py`, `__main__.py`, `launcher.py`, `run.py` のような汎用Entry名では親フォルダ名から提案します。
- それ以外はファイル名の stem から提案します。
- AppId は英小文字、数字、`_`、`-` に正規化し、空になった場合は `app` を使います。
- Name は `snake_case` / `kebab-case` を空白区切りの表示名へ変換します。

Preflight表示:

- Entry の存在
- AppId 形式
- Entry が Python ソースであること
- App Studio 実行に使う開発環境 Python の有無

通常新規登録の配布物検証は `runtime/python/python.exe` や `runtime/app_envs/<app_id>` の有無を承認ブロック理由にしません。exe 作成には出力ディレクトリ配下の内部 `build_env` を使います。Python が見つからない場合は Suggest / Apply を実行できませんが、通常ランチャー機能には影響しません。

承認モード:

- 既定は「配布リスクがある警告は承認しない」です。
- `StrictApproval`: `fail` と `approval_blocking_warning` は承認不可です。`non_blocking_warning` や `info` だけなら承認できます。
- `AllowWarnings`: 配布リスクのない警告を許容します。ただし exe欠落、required_files欠落、secret混入、`BUILD_REQUIRED.txt` 残存などの `fail` は承認できません。

Apply 中は `TOOLHUB_PROGRESS {...}` 行を stdout に出力し、`timing_report.json` / `timing_report.md` に工程別時間を記録します。GUI は実行中に現在工程、経過時間、目安時間、残り目安を表示します。目安は同じ app_id の過去実績または一般的な初回ビルド目安であり、環境や依存関係により変動します。

結果サマリーでは `selected_build_mode`、`exit_code`、最後に実行した action、次に必要な操作も表示します。

GUI実行ログ:

```text
%LOCALAPPDATA%\ToolHub\data\logs\admin\app_studio_gui.log
```

ログには action、exit code、app_id、固定 build mode、output_dir、CLI path、argv を記録します。APIキー、パスワード、secret値は記録しません。stdout/stderr 表示前にも `sk-` 形式のキーらしい文字列をマスクします。

GUI未対応またはMVPに留めている機能:

- 既存アプリ更新GUI MVPの詳細は `docs/15_app_studio_update_gui.md` を参照してください。
- 既存アプリ更新はMVPです。登録済みapp_idの選択、version bump、更新Entry指定、Suggest update / Apply update / Approve update までを対象にします。
- 完全な差分ビューア
- 削除/アンインストールの本実装
- publish の本実装
- 配布済みランチャーへの自動更新配信
- manifest署名

## 通常フローと legacy 方式

通常新規登録 GUI は `frozen-folder` 固定です。`app.yaml` は `run.runner: exe` と `run.entry: bin/<app_id>/<app_id>.exe` を使います。

`app-env`、`existing-exe`、Python 直接実行、旧 `auto` 判定は legacy / 既存互換の説明です。既存登録済み app や古い manifest を読むために内部型が残る場合がありますが、通常新規登録 GUI では露出しません。

## app-env方式 legacy

`app-env` は既存 app / 互換用の方式です。通常新規登録 GUI では利用者向け実行方式として使いません。

生成される `app.yaml` は `run.runner: python_app_env` を使います。

## frozen-folder方式

`frozen-folder` は通常新規登録の固定方式です。PyInstaller `--onedir --clean --contents-directory .` で実ビルドを行います。

PyInstaller が未導入、またはビルド環境に問題がある場合は、Apply を成功扱いにせず `frozen_folder_build_report.md` に理由と対処案を残します。実ビルド成果物は `bin/<app_id>/<app_id>.exe` を `run.entry` として扱います。

`--onefile` は標準にしません。起動が遅くなりやすく、利用者体験とログ調査の面で ToolHub の標準配布方式に合わないためです。

AgendaSnap 級の複雑アプリ、音声/GUI/外部DLL/重い依存を含むアプリでは、`frozen-folder` 方式を第一候補にします。

## アイコン修正プロンプト

`-IconPrompt` を指定すると、`icon_work/icon_prompt_revision.md` に修正指示を保存します。App Studio の標準アイコン成果物はPNGです。AI画像生成APIが b64 PNG を返した場合は `icon_work/icon_candidate_1.png` に保存し、GUIで人間が採用したPNGだけを `icon_work/icon_final.png`、`final_app/icon.png`、Apply後の `apps/<app_id>/icon.png` に反映します。

APIキー未設定、AI無効、OpenAI packageなし、API失敗、high secret検出時はAI送信せず deterministic fallback PNG を生成します。fallback/互換用SVGは `icon_work/icon_fallback.svg` と `final_app/icon.svg` に残します。モデル名はコードに固定せず、GUIでは管理者画面の Image model 設定、CLIでは `TOOLHUB_APP_STUDIO_IMAGE_MODEL` から読みます。既定候補は `gpt-image-2` ですが、設定で変更できます。

## 実行確認と人間承認

`-Apply` は仮登録のみ行い、`release/app_manifest.json` の `enabled` は必ず `false` で開始します。

Apply 後に App Studio は `execution_test_report.md` を生成します。人間が内容を確認した後、次のコマンドで承認します。

```powershell
.\scripts\approve_imported_app.ps1 -AppId "agendasnap"
```

承認時に `enabled=true` へ変更し、App Pack を再生成し、可能な範囲で `scripts/verify_release.ps1` を実行します。

## 元フォルダ側へ成果物を保存する仕様

Entry が `C:\work\MyApp\main.py` の場合、成果物は次へ保存されます。

```text
C:\work\MyApp\ToolHub_AppStudio_Output\<app_id>\
```

主な中身:

- `import_plan.json`
- `file_inventory.md`
- `file_inventory.json`
- `dependency_report.json`
- `secret_scan_report.md`
- `timing_report.json` / `timing_report.md`
- `build_plan.md`
- `proposed_app.yaml`
- `proposed_README.md`
- `proposed_requirements.txt`
- `icon_work/`
- `final_app/`
- `app_pack/`
- `execution_test_report.md`
- `approval_record.md`

## 上書き仕様

`ToolHub_AppStudio_Output/<app_id>/` が既に存在する場合は削除して作り直します。削除前に、削除対象が Entry の親フォルダ配下であることを検証します。

Apply 時に同じ `app_id` が既に存在する場合は、`backups/app_studio/YYYYMMDD_HHMMSS/<app_id>/` へ既存 `apps/<app_id>/` と `release/app_manifest.json` をバックアップしてから上書きします。

## 秘密情報検査

secret scan は無効化しません。ただし、`high` という単純な severity だけで Apply を止めず、配布物に入るか、AI送信対象になるか、file inventory で安全に除外されているかを分けて判定します。

原則として Apply を止めるもの:

- `included_files` または build_profile の add-data に入る実値らしい API key / token / password / secret
- `.env`、`*.pem`、`*.key`
- `storage_state`、cookie、session、credentials、client_secret などの認証状態ファイル
- `file_inventory.json` で `blocked` のもの
- 人間確認なしでは配布物混入リスクを否定できない high finding

原則として Apply の即時停止ではなく warning / manual check にするもの:

- README や docs の `OPENAI_API_KEY` という環境変数名だけの説明
- `api_key: "<your key>"`、`token: "dummy"`、`password: "example"` のような明確な placeholder
- Pythonコード内の `api_key`、`token`、`credentials` などの変数名だけで、実値が含まれないもの
- logs、sessions、screenshots、tmp/temp など、file inventory で配布対象外と判定されたもの

AI送信停止と Apply 停止は別判定です。README に `OPENAI_API_KEY` が書かれている場合などは、AI metadata/icon 提案を fallback にしても、配布物に秘密情報が混入しないなら Apply は進められます。

`secret_scan_report.md` には Summary、Blocking Findings、Warnings / Manual Checks、Excluded from Package、False Positive Candidates を出力します。各 finding には `path`、`severity`、`kind`、`inventory_status`、`included_in_package`、`affects_ai_submission`、`blocks_apply`、`block_reason`、`recommended_action` が記録されます。GUI で secret scan により停止した場合は blocking 件数、warning 件数、manual check 件数、レポートパス、上位 blocking finding を表示します。

## 使い方

解析のみ:

```powershell
.\scripts\import_app.ps1 -Entry "C:\path\to\main.py" -DryRun
```

提案生成:

```powershell
.\scripts\import_app.ps1 -Entry "C:\path\to\main.py" -Suggest
```

仮登録:

```powershell
.\scripts\import_app.ps1 -Entry "C:\path\to\main.py" -Apply
```

app_id と名称を指定:

```powershell
.\scripts\import_app.ps1 -Entry "C:\path\to\main.py" -AppId "agendasnap" -Name "AgendaSnap" -Apply
```

通常新規登録:

```powershell
.\scripts\import_app.ps1 -Entry "C:\path\to\main.py" -AppId "agendasnap" -Name "AgendaSnap" -Apply
```

アイコン修正プロンプト:

```powershell
.\scripts\import_app.ps1 -Entry "C:\path\to\main.py" -AppId "agendasnap" -Name "AgendaSnap" -IconPrompt "マイクとメモ帳を組み合わせ、ToolHub既存アイコンに合うシンプルな線画にする" -Suggest
```

## app_env実体作成 legacy

`app-env` 作成は通常新規登録 GUI の機能ではありません。以下は legacy / 既存互換フローの説明です。

```powershell
.\scripts\import_app.ps1 -Entry "C:\work\tool\main.py" -AppId "my_tool" -Name "My Tool" -BuildMode "app-env" -Apply -GenerateLock -CreateAppEnv
```

- `-CreateAppEnv`: `runtime/app_envs/<app_id>/` を作成します。
- `-RebuildAppEnv`: 既存 app_env を `backups/app_studio/...` へ退避して再作成します。
- `-SkipAppEnvBuild`: app_env 作成を明示的にスキップします。

`runtime/python/python.exe` があればそれを使います。ない場合は開発環境 Python を使い、`app_env_build_report.md` に明記します。

## requirements.lock生成

`-GenerateLock` を指定すると、`requirements.lock` を生成またはコピーします。

- 既存 `requirements.lock` がある場合はコピーを優先します。
- 通常新規登録では内部 `build_env` の `pip freeze` を使います。
- それ以外は `requirements.txt` の正規化結果を lock として保存します。
- 通常新規登録では lock 生成をスキップしません。

レポートは `lock_generation_report.md` と `data/logs/app_studio/<app_id>_lock_generation_report.md` に保存されます。`pip freeze` は過剰依存が混ざる可能性があるため、人間レビューを前提にします。

## frozen-folder実ビルド

通常新規登録では、Python アプリを常に `frozen-folder` 方式で PyInstaller `--onedir` 相当のフォルダビルドにします。

```powershell
.\scripts\import_app.ps1 -Entry "C:\work\AgendaSnap\agendasnap\app.py" -AppId "agendasnap" -Name "AgendaSnap" -Apply
```

- frozen-folder build は常に実行します。
- `-RebuildFrozenFolder` は互換用に残る場合がありますが、通常 Apply は毎回ビルドします。
- `-SkipFrozenBuild` は通常新規登録では使えません。

`--onefile` は標準では使いません。App Studio の frozen build は `bin/<app_id>/<app_id>.exe` を `run.entry` として扱います。PyInstaller が見つからない場合は失敗し、`frozen_folder_build_report.md` に理由を残します。

PyInstaller probe や build が obsolete `pathlib` backport の影響で失敗した場合、レポートに原因候補と対処案を出します。App Studio はユーザー環境を壊さないため、自動で `pip uninstall pathlib` は実行しません。

## frozen-folder配布物検証

通常新規登録では、旧 runtime/app_env 検証ではなく frozen-folder 配布物検証を実行します。

```powershell
.\scripts\import_app.ps1 -Entry "C:\work\tool\main.py" -AppId "my_tool" -Apply -VerifyRuntime
```

`-VerifyRuntime` は互換名として残っていますが、通常新規登録では次を確認し、`runtime_check_report.md` と `runtime_check_result.json` を元フォルダ側および `data/logs/app_studio/` に保存します。

- `final_app/bin/<app_id>/<app_id>.exe` の存在
- `app.yaml` の `run.entry` が exe を指すこと
- build_profile の add-data / required_files が frozen-folder 内に存在すること
- `BUILD_REQUIRED.txt` が残っていないこと
- `.auth`、logs、screenshots、tmp、credentials、token、secret、storage_state、`build_env` が配布物に混入していないこと
- frozen-folder と add-data のサイズ

開発中に `runtime/python/python.exe` や `runtime/app_envs/<app_id>` が未配置でも通常フローは壊しません。

```powershell
.\scripts\verify_release.ps1 -RequireRuntime -Strict
```

## 実行確認JSON

Apply 後、Markdown に加えて machine-readable な結果を生成します。

```text
execution_test_result.json
data/logs/app_studio/<app_id>_execution_test_result.json
```

形式:

```json
{
  "app_id": "agendasnap",
  "generated_at": "...",
  "overall_status": "pass",
  "approval_allowed": true,
  "checks": [
    { "name": "app.yaml parse", "status": "pass", "detail": "..." }
  ]
}
```

`fail` がある場合は承認不可です。`warn` は承認可否の観点で分類されます。`approval_blocking_warning` は配布品質や安全性に影響する未解決リスクとして承認不可です。`non_blocking_warning` は AI fallback、Playwright ログイン未確認、外部サービス実操作未確認などの参考警告で、配布物自体が成立している場合はデフォルトの慎重モードでも承認できます。

## 承認モード

```powershell
.\scripts\approve_imported_app.ps1 -AppId "agendasnap" -StrictApproval
```

- 既定: GUI は「配布リスクがある警告は承認しない」です。
- `-AllowWarnings`: 配布リスクのない警告を許容します。
- `-StrictApproval`: `fail` と `approval_blocking_warning` を拒否します。`non_blocking_warning` / `info` だけなら承認できます。

`execution_test_result.json` には `approval_blocking_warnings_count`、`non_blocking_warnings_count`、`info_count`、`unresolved_distribution_risks_count`、`approval_blocking_reasons`、`non_blocking_warning_summaries` が記録されます。required_files や add-data が配布物検証で pass した場合、ビルド前の「packaged data を確認する」注意書きだけで承認不可にはしません。

承認時は `execution_test_result.json`、`apps/<app_id>/app.yaml`、`release/app_manifest.json`、App Pack 生成、可能な範囲の `verify_release.ps1` を確認します。失敗した場合は `enabled=true` にせず、途中で変更した場合も元に戻します。

## OpenAI API連携

AI 連携は明示的に有効化した場合だけ試行します。未設定時や失敗時は deterministic fallback を使います。

GUI では管理者画面の AI/APIキー管理から AI ON/OFF、Text model、Image model、OpenAI APIキーを管理します。CLI では従来通り環境変数を利用できます。

```powershell
$env:TOOLHUB_APP_STUDIO_AI_ENABLED="true"
$env:TOOLHUB_APP_STUDIO_TEXT_MODEL="<configurable-model>"
$env:TOOLHUB_APP_STUDIO_IMAGE_MODEL="<configurable-model>"
$env:OPENAI_API_KEY="..."
```

安全方針:

- `TOOLHUB_APP_STUDIO_AI_ENABLED` が `true` / `1` の場合だけAPI呼び出しを試みます。
- Tauri GUIから起動するCLIには、管理者画面のAI設定を優先して `TOOLHUB_APP_STUDIO_AI_ENABLED`、`TOOLHUB_APP_STUDIO_TEXT_MODEL`、`TOOLHUB_APP_STUDIO_IMAGE_MODEL` を渡します。
- APIキーはAI有効かつキー存在時だけ子プロセスへ `OPENAI_API_KEY` として渡します。Credential Managerが優先で、無ければ環境変数を使います。
- APIキーやモデル名が未設定ならfallbackします。
- `openai` Python package がない場合もfallbackします。
- secret scan で AI送信対象に秘密情報リスクがある場合はAI送信せず fallback します。Apply 停止とは別判定です。
- Entry全文は送らず、ファイル名、README抜粋、既存カテゴリなどの限定情報だけを使います。
- metadata提案は Responses API `responses.create` を使い、JSON parseに失敗した場合はfallbackします。
- 画像生成は Images API `images.generate` を使います。`response_format` は渡しません。
- 標準アイコンは `icon.png` です。`app.yaml` は `display.icon: icon.png` と `display.icon_fallback: icon.svg` を出力します。
- 最終 `icon.svg` はfallback/互換用として保存し、既存SVGアイコンの表示互換性を保ちます。
- 画像APIが b64 PNG を返した場合は `icon_work/icon_candidate_1.png` に保存します。
- 画像APIが URL を返した場合は、ダウンロードせず `icon_work/icon_candidate_1.url.txt` に保存します。
- PNG/URL は人間レビュー用候補であり、PNG候補は人間がGUIで採用した場合だけ `icon.png` に反映します。

## 実運用推奨コマンド

通常新規登録:

```powershell
.\scripts\import_app.ps1 -Entry "C:\work\tool\main.py" -AppId "my_tool" -Name "My Tool" -Apply
```

Playwright や複数ファイルを含むアプリも同じ通常フロー:

```powershell
.\scripts\import_app.ps1 -Entry "C:\work\XCgate_AutoUpload\run_xcgate_upload.py" -AppId "run_xcgate_upload" -Name "Run XCgate Upload" -Apply
```

厳格承認:

```powershell
.\scripts\approve_imported_app.ps1 -AppId "agendasnap" -StrictApproval
```

## 実アプリ適用前チェックリスト

通常新規登録:

- `requirements.txt` または `pyproject.toml`、必要な nested requirements を確認する。
- `requirements.lock` が生成/更新されることを確認する。
- `build_env` が App Studio 出力ディレクトリ配下に作成され、`runtime/app_envs/<app_id>` が PyInstaller に使われていないことを確認する。
- PyInstaller / pyinstaller-hooks-contrib が `build_env` に導入されることを確認する。
- obsolete `pathlib` backport が入っていないことを確認する。
- `final_app/bin/<app_id>/<app_id>.exe` と `apps/<app_id>/bin/<app_id>/<app_id>.exe` が生成されることを確認する。
- `BUILD_REQUIRED.txt` が残っていないことを確認する。
- build_profile の add-data / required_files が frozen-folder 内に存在することを確認する。
- `execution_test_result.json` の `frozen-folder executable` が `pass` であることを確認する。
- `execution_test_result.json` が今回の Apply で更新され、`approval_allowed` が配布物検証結果に基づいていることを確認する。
- `--onefile` を使っていないことを確認する。
- Playwright のブラウザ操作、ログイン、社内サイト操作は manual check として実機で確認する。
- `.\scripts\approve_imported_app.ps1 -AppId "<app_id>" -StrictApproval` を実行する。

AI利用時:

- `TOOLHUB_APP_STUDIO_AI_ENABLED=true` を明示する。
- `OPENAI_API_KEY` が設定されていることを確認する。
- AI送信対象の secret finding がある場合はAI送信されず fallback になることを確認する。
- 生成アイコン候補PNG/URLは人間レビュー用であり、採用したPNGだけが `icon.png` に反映されることを確認する。
- 既存 `display.icon: icon.svg` のアプリが引き続き表示できることを確認する。

## App Studio Import Diagnostic Script

When App Studio approval shows only `Execution test result does not allow approval.`,
use the read-only diagnostic script to separate the direct approval gate from the
root cause in Apply/build artifacts.

```powershell
.\scripts\diagnose_app_studio_import.ps1 -AppId <app_id>
```

Useful options:

- `-Entry <main.py>`: also checks `ToolHub_AppStudio_Output/<app_id>` under the entry parent.
- `-OutputDir <path>`: explicitly points to an App Studio output mirror.
- `-NoWrite`: prints the report without saving `data/logs/app_studio/<app_id>_diagnostic_report.md`.
- `-AsJson`: prints a JSON summary.
- `-VerboseFiles`: includes detailed file evidence.

The script does not run Apply, Approve, PyInstaller, or any app. It only reads
logs, `apps/<app_id>`, output mirror files, and `release/app_manifest.json`, then
classifies likely causes such as stale `execution_test_result.json`, frozen build
failure, registration copy not reached, missing add-data files, old app_env-based
PyInstaller logs, secret scan Apply blocks, possible secret scan overblocking,
AI-only secret scan fallback, or manifest registration gaps.

## App Studio normal registration policy

This section is authoritative for the current normal new-registration GUI.

The normal App Studio registration flow is distribution-only for ordinary users:

```text
Python source -> analyze -> build_env -> install dependencies -> requirements.lock
-> PyInstaller frozen-folder build -> distribution check -> app.yaml/register
```

The normal GUI does not let users choose BuildMode, app_env execution, Python direct execution, or existing-exe registration. Those names may still appear in legacy code paths, old logs, or compatibility documentation for existing apps, but they are not user-facing choices in the normal new-registration GUI.

Normal registration always generates or refreshes `requirements.lock`, always builds a PyInstaller frozen folder, and always runs a frozen-folder distribution/execution check before approval. `app.yaml` must point `run.entry` at the generated executable, usually `bin/<app_id>/<app_id>.exe`; it must not point at a `.py` file for normal distribution.

The build environment is internal. App Studio may create `build_env` under the output workspace to run PyInstaller and build tools, but this is separate from `runtime/app_envs/<app_id>`, is not a user runtime, and must not be copied into `final_app`, App Packs, `release`, or `runtime`.

PyInstaller uses folder output (`--onedir --clean --contents-directory .`) as the ToolHub standard. The verifier accepts older PyInstaller 6 `_internal` add-data placement as a compatibility warning when files are present there, but a current build using `--contents-directory .` is expected to place required add-data beside the executable. If an old failed `execution_test_result.json` is older than `app.yaml`, `build_profile.json`, or the generated exe, approval reports a stale execution result instead of hiding the reason behind a generic approval failure.

Legacy/compatibility notes:

- `app-env`, `existing-exe`, and Python direct execution are compatibility concepts for existing manifests, historical CLI paths, or old registered apps.
- The normal new-registration GUI intentionally does not expose existing-exe registration because ToolHub cannot verify that a user-provided exe is portable and complete.
- Any other section that lists BuildMode choices should be read as legacy background unless it explicitly says it applies to the current normal GUI.
