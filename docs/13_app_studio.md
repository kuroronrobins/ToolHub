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

