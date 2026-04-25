# ToolHub App Studio

## 目的

ToolHub App Studio は、開発者が既存アプリのメインファイルを指定するだけで、ToolHub が検出できる `apps/<app_id>/app.yaml` 形式へ変換するための開発者向け CLI です。

ランチャー本体には App Studio 専用 UI や個別アプリ固有処理を入れません。解析、提案、仮登録、承認は `tools/app_studio` と `scripts/import_app.ps1` で扱います。

## 対応する登録方式

- `app-env`: 標準方式。`runtime/app_envs/<app_id>/Scripts/python.exe` を優先し、なければ `runtime/python/python.exe` を使います。
- `frozen-folder`: 複雑な Python アプリ向け。PyInstaller `--onedir` 相当のフォルダ配布を想定します。
- `existing-exe`: 既存 exe と周辺ファイルを `bin/` に置く方式です。

`auto` を指定した場合、単純な Python スクリプトは `app-env`、多数のモジュール、assets/config、音声、外部 DLL、複雑な依存がある場合は `frozen-folder`、Entry が exe の場合は `existing-exe` を選びます。

## app-env方式

`app-env` は ToolHub 標準の Python アプリ登録方式です。利用者 PC の PATH 上の Python には依存せず、ToolHub インストール時に `%LOCALAPPDATA%\Programs\ToolHub\` 配下へ展開済みの runtime を使う前提です。

生成される `app.yaml` は `run.runner: python_app_env` を使います。

## frozen-folder方式

`frozen-folder` は PyInstaller `--onedir` 相当を前提にした方式です。MVP では実際の PyInstaller 実行は行わず、`build_plan.md` と配置雛形を生成します。

`--onefile` は標準にしません。起動が遅くなりやすく、利用者体験とログ調査の面で ToolHub の標準配布方式に合わないためです。

## アイコン修正プロンプト

`-IconPrompt` を指定すると、`icon_work/icon_prompt_revision.md` に修正指示を保存し、ローカルの deterministic SVG 生成で `icon_candidate_1.svg` と `icon_final.svg` を更新します。

OpenAI API 実呼び出しは MVP では必須ではありません。将来差し替えるため、`ai_metadata_suggester.py` と `icon_generator.py` はインターフェースを分けています。モデル名は `TOOLHUB_APP_STUDIO_TEXT_MODEL` と `TOOLHUB_APP_STUDIO_IMAGE_MODEL` から読みます。

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

```powershell
$env:TOOLHUB_APP_STUDIO_AI_ENABLED="true"
$env:TOOLHUB_APP_STUDIO_TEXT_MODEL="<configurable-model>"
$env:TOOLHUB_APP_STUDIO_IMAGE_MODEL="<configurable-model>"
$env:OPENAI_API_KEY="..."
```

安全方針:

- `TOOLHUB_APP_STUDIO_AI_ENABLED` が `true` / `1` の場合だけAPI呼び出しを試みます。
- APIキーやモデル名が未設定ならfallbackします。
- `openai` Python package がない場合もfallbackします。
- high severity の秘密情報が検出された場合はAI送信しません。
- Entry全文は送らず、ファイル名、README抜粋、既存カテゴリなどの限定情報だけを使います。
- 最終 `icon.svg` は常にローカル生成SVGを保存し、ToolHubのSVG表示互換性を保ちます。

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
