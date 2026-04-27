# GUI Build方式・AI提案・結果表示補足

App Studio GUI の Build mode には hover の `title` と選択中説明、Entryに応じた推奨表示があります。

- `auto`: 通常はこれを選びます。Entryの種類から App Studio が自動判定します。.exe なら `existing-exe`、軽量Pythonなら `app-env`、複雑Pythonなら `frozen-folder` を提案します。
- `app-env`: Pythonソースを ToolHub 同梱Pythonと `runtime/app_envs/<app_id>` で起動します。単一スクリプトや中規模Pythonツール向けです。
- `frozen-folder`: 複雑なPythonアプリを PyInstaller `--onedir` 相当の展開済みフォルダで配布します。GUI、音声、外部依存、複数ファイル構成向けです。
- `existing-exe`: すでに `.exe` があるアプリを登録します。exeと同じフォルダのDLL、設定ファイル、補助ファイルも `bin` 配下へコピーする想定です。

Entryが `.exe` の場合、GUIは `existing-exe` を推奨します。Entryが `main.py` / `app.py` の場合は `auto` を推奨し、固有名の単一 `.py` では `app-env` を推奨します。不明なEntryでは `auto` で Suggest し、判定結果を確認してください。

GUIでは、Suggest が生成した `proposed_app.yaml` と `icon_work/` をAI/fallback提案として読み込めます。表示対象は、表示名、short_description、detail.description、categories、search keywords、examples、use_cases、inputs、outputs、notes、icon prompt、更新時の release notes 草案、`icon_candidate_1.png`、`icon_final.png`、`icon_candidate_1.url.txt`、`icon_fallback.svg`、互換用の `icon_final.svg` です。AI提案は自動確定せず、採用ボタンで表示名やicon promptなど編集可能な入力欄へ反映します。APIキー未設定、AI無効、OpenAI packageなし、API失敗時も CLI 側の deterministic fallback で動きます。high secret 検出時はAI送信しません。

AI提案パネルはCLIへ渡すAI環境の診断も表示します。表示対象は AI enabled、API key source、Text model、Image model、CLI env ready です。APIキー本文は表示しません。`metadata_ai_report` と `icon_work/ai_generation_report.md` から、metadata/image それぞれの `status`、`model`、`parse_status`、`content_type`、`saved_candidate`、`fallback_reason` も確認できます。

GUIでは CLI process の `exit_code` / `process_ok` と、`execution_test_result.json` の `overall_status` / `approval_allowed` を分けて表示します。`existing-exe` や `frozen-folder` では runner dry execution がスキップされ、`overall_status: warn` になることがあります。`approval_allowed: true` で、他のチェックが pass の場合は致命的失敗ではありません。GUIはこの状態を `warn / approval OK` と表示し、AllowWarnings で承認できるようにします。App Packが見つからない場合は App Pack 欄だけ `not found` と表示します。Apply後はGUIが `app_studio_read_result` を再実行し、生成済みJSONの内容を表示へ反映します。

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
- Entry 参照ボタン: Windows ではファイル選択ダイアログから `.py` / `.exe` / 任意ファイルを選択できます。非対応環境では手入力で続行します。
- App ID
- 表示名
- BuildMode: `auto`, `app-env`, `frozen-folder`, `existing-exe`
- Icon Prompt
- `requirements.lock` 生成
- app_env 作成/再作成
- frozen-folder build
- runtime 検証

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
- BuildMode
- `runtime/python/python.exe` の有無
- App Studio 実行に使う Python の種類: `runtime`, `python`, `py`, `missing`

`runtime/python/python.exe` が未配置でも、開発環境 Python fallback が見つかる場合は警告として扱います。Python が見つからない場合は Suggest / Apply を実行できませんが、通常ランチャー機能には影響しません。

承認モード:

- `AllowWarnings`: `fail` がなければ承認可能です。
- `StrictApproval`: `pass` のみ承認可能です。`warn` がある場合は承認できません。

結果サマリーでは `selected_build_mode`、`exit_code`、最後に実行した action、次に必要な操作も表示します。

GUI実行ログ:

```text
%LOCALAPPDATA%\ToolHub\data\logs\admin\app_studio_gui.log
```

ログには action、exit code、app_id、build_mode、output_dir を記録します。APIキー、パスワード、secret値は記録しません。stdout/stderr 表示前にも `sk-` 形式のキーらしい文字列をマスクします。

GUI未対応またはMVPに留めている機能:

- 既存アプリ更新GUI MVPの詳細は `docs/15_app_studio_update_gui.md` を参照してください。
- 既存アプリ更新はMVPです。登録済みapp_idの選択、version bump、更新Entry指定、Suggest update / Apply update / Approve update までを対象にします。
- 完全な差分ビューア
- 削除/アンインストールの本実装
- publish の本実装
- 配布済みランチャーへの自動更新配信
- manifest署名

## 対応する登録方式

- `app-env`: 標準方式。`runtime/app_envs/<app_id>/Scripts/python.exe` を優先し、なければ `runtime/python/python.exe` を使います。
- `frozen-folder`: 複雑な Python アプリ向け。PyInstaller `--onedir` 相当のフォルダ配布を想定します。
- `existing-exe`: 既存 exe と周辺ファイルを `bin/` に置く方式です。

`auto` を指定した場合、単純な Python スクリプトは `app-env`、多数のモジュール、assets/config、音声、外部 DLL、複雑な依存がある場合は `frozen-folder`、Entry が exe の場合は `existing-exe` を選びます。

## app-env方式

`app-env` は ToolHub 標準の Python アプリ登録方式です。利用者 PC の PATH 上の Python には依存せず、ToolHub インストール時に `%LOCALAPPDATA%\Programs\ToolHub\` 配下へ展開済みの runtime を使う前提です。

生成される `app.yaml` は `run.runner: python_app_env` を使います。

## frozen-folder方式

`frozen-folder` は PyInstaller `--onedir` 相当を前提にした方式です。通常は plan 生成だけでも利用できますが、`-BuildFrozenFolder` を指定すると PyInstaller `--onedir` の実ビルドを行います。

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

最低限、次を検出します。

- `.env`
- `*.key`
- `*.pem`
- `token`
- `secret`
- `password`
- `api_key`
- `OPENAI_API_KEY`
- `credentials`
- `client_secret`
- `*.log`
- 録音ファイル `*.wav`, `*.mp3`, `*.m4a`
- 大容量ファイル

`DryRun` と `Suggest` ではレポートのみ生成します。`Apply` では high 検出がある場合、既定で中止します。

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

frozen-folder 方式:

```powershell
.\scripts\import_app.ps1 -Entry "C:\path\to\main.py" -AppId "agendasnap" -Name "AgendaSnap" -BuildMode "frozen-folder" -Apply
```

アイコン修正プロンプト:

```powershell
.\scripts\import_app.ps1 -Entry "C:\path\to\main.py" -AppId "agendasnap" -Name "AgendaSnap" -IconPrompt "マイクとメモ帳を組み合わせ、ToolHub既存アイコンに合うシンプルな線画にする" -Suggest
```

## app_env実体作成

`app-env` 方式では、開発時に `runtime/app_envs/<app_id>/` を作成できます。利用者PCでは、この作成済み app_env が ToolHub インストール先へ展開される前提であり、利用者に Python や pip の導入を要求しません。

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
- app_env Python がある場合は `pip freeze` を使います。
- それ以外は `requirements.txt` の正規化結果を lock として保存します。
- `-SkipLock` では lock 生成をスキップします。

レポートは `lock_generation_report.md` と `data/logs/app_studio/<app_id>_lock_generation_report.md` に保存されます。`pip freeze` は過剰依存が混ざる可能性があるため、人間レビューを前提にします。

## frozen-folder実ビルド

複雑な Python アプリは `frozen-folder` 方式で PyInstaller `--onedir` 相当のフォルダビルドを行えます。

```powershell
.\scripts\import_app.ps1 -Entry "C:\work\AgendaSnap\agendasnap\app.py" -AppId "agendasnap" -Name "AgendaSnap" -BuildMode "frozen-folder" -Apply -BuildFrozenFolder
```

- `-BuildFrozenFolder`: PyInstaller `--onedir` でビルドします。
- `-RebuildFrozenFolder`: 既存出力を再作成します。
- `-SkipFrozenBuild`: ビルドをスキップし、plan のみ残します。

`--onefile` は標準では使いません。App Studio の frozen build は `bin/<app_id>/<app_id>.exe` を `run.entry` として扱います。PyInstaller が見つからない場合は失敗し、`frozen_folder_build_report.md` に理由を残します。

PyInstaller probe や build が obsolete `pathlib` backport の影響で失敗した場合、レポートに原因候補と対処案を出します。App Studio はユーザー環境を壊さないため、自動で `pip uninstall pathlib` は実行しません。

## runtime検証

正式配布前には、開発環境 Python ではなく ToolHub 同梱 runtime で確認してください。

```powershell
.\scripts\import_app.ps1 -Entry "C:\work\tool\main.py" -AppId "my_tool" -Apply -VerifyRuntime
```

`-VerifyRuntime` は次を確認し、`runtime_check_report.md` と `runtime_check_result.json` を元フォルダ側および `data/logs/app_studio/` に保存します。

- `runtime/python/python.exe` の存在
- `runtime/python/python.exe --version`
- `runtime/python/python.exe -m pip --version`
- `runtime/app_envs/<app_id>/Scripts/python.exe` の存在
- app_env Python の `--version`
- app_env Python の `-m pip --version`

開発中に `runtime/python/python.exe` が未配置でも通常フローは壊しません。ただし正式配布前は `runtime/python/python.exe` を配置し、app_env を再作成してから次を通すことを推奨します。

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

`fail` がある場合は承認不可です。`warn` は通常承認では許容できますが、`StrictApproval` では承認不可です。

## 承認モード

```powershell
.\scripts\approve_imported_app.ps1 -AppId "agendasnap" -StrictApproval
```

- 既定: `fail` がなければ承認できます。
- `-AllowWarnings`: warn まで承認可能です。
- `-StrictApproval`: `pass` のみ承認可能です。

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
- high severity の秘密情報が検出された場合はAI送信しません。
- Entry全文は送らず、ファイル名、README抜粋、既存カテゴリなどの限定情報だけを使います。
- metadata提案は Responses API `responses.create` を使い、JSON parseに失敗した場合はfallbackします。
- 画像生成は Images API `images.generate` を使います。`response_format` は渡しません。
- 標準アイコンは `icon.png` です。`app.yaml` は `display.icon: icon.png` と `display.icon_fallback: icon.svg` を出力します。
- 最終 `icon.svg` はfallback/互換用として保存し、既存SVGアイコンの表示互換性を保ちます。
- 画像APIが b64 PNG を返した場合は `icon_work/icon_candidate_1.png` に保存します。
- 画像APIが URL を返した場合は、ダウンロードせず `icon_work/icon_candidate_1.url.txt` に保存します。
- PNG/URL は人間レビュー用候補であり、PNG候補は人間がGUIで採用した場合だけ `icon.png` に反映します。

## 実運用推奨コマンド

軽量アプリ:

```powershell
.\scripts\import_app.ps1 -Entry "C:\work\tool\main.py" -AppId "my_tool" -Name "My Tool" -BuildMode "app-env" -Apply -GenerateLock -CreateAppEnv
```

複雑アプリ:

```powershell
.\scripts\import_app.ps1 -Entry "C:\work\AgendaSnap\agendasnap\app.py" -AppId "agendasnap" -Name "AgendaSnap" -BuildMode "frozen-folder" -Apply -BuildFrozenFolder
```

厳格承認:

```powershell
.\scripts\approve_imported_app.ps1 -AppId "agendasnap" -StrictApproval
```

## 実アプリ適用前チェックリスト

app-env方式:

- `requirements.txt` を確認する。
- `-GenerateLock` で `requirements.lock` を生成する。
- `-CreateAppEnv` で `runtime/app_envs/<app_id>/` を作成する。
- `-VerifyRuntime` を実行し、runtime/app_env の状態を確認する。
- `execution_test_result.json` が `pass` または許容できる `warn` であることを確認する。
- `runtime/python/python.exe` 配置後に app_env を再作成する。
- `.\scripts\approve_imported_app.ps1 -AppId "<app_id>" -StrictApproval` を実行する。

frozen-folder方式:

- PyInstaller が使える環境であることを確認する。
- obsolete `pathlib` backport が入っていないことを確認する。
- `-BuildFrozenFolder` で `bin/<app_id>/<app_id>.exe` が生成されることを確認する。
- `execution_test_result.json` の `frozen-folder executable` が `pass` であることを確認する。
- `--onefile` を使っていないことを確認する。
- 起動速度を実機で確認する。
- `.\scripts\approve_imported_app.ps1 -AppId "<app_id>" -StrictApproval` を実行する。

AI利用時:

- `TOOLHUB_APP_STUDIO_AI_ENABLED=true` を明示する。
- `OPENAI_API_KEY` が設定されていることを確認する。
- high secret がある場合はAI送信されないことを確認する。
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
PyInstaller logs, or manifest registration gaps.

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
