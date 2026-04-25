# Runtime Packaging

ToolHubは、利用者がPython、Node.js、Rust、各アプリの依存関係、Web自動化用ランタイムを手動導入しなくても動作することを目標にします。

## Runtime Layout

```text
runtime/
├─ python/
├─ app_envs/
│  ├─ sample_gui_app/
│  ├─ sample_cli_app/
│  └─ sample_playwright_app/
└─ web_automation_runtime/
```

`runtime/` はrelease時に配置する成果物です。巨大なPython runtime、app_env、Web自動化用ランタイム本体はGit管理に含めません。GitにはREADME、`.gitkeep`、スクリプト、manifest、docsだけを置きます。

## Prepare Runtime Script

雛形作成:

```powershell
.\scripts\prepare_runtime.ps1 -AllowMissingRuntime
```

このコマンドは以下を作成します。

- `runtime/README.md`
- `runtime/python/`
- `runtime/app_envs/`
- `runtime/app_envs/<app_id>/`
- `runtime/web_automation_runtime/`

ローカルruntime archiveを展開する場合:

```powershell
.\scripts\prepare_runtime.ps1 -SourceArchive .\vendor\runtime\python.zip -SourceSha256 <sha256>
```

デフォルトでは外部サイトから自動ダウンロードしません。社内で承認済みのruntime archiveを `vendor/runtime/` または `tools/runtime_sources/` に置き、sha256を確認して展開します。

## Python Runtime

正式配布では利用者にPythonインストールを要求しません。第一候補は `runtime/python/` にPython embedded runtimeを固定配置する方式です。

現行のRust backendはまだ同梱runtimeを使っておらず、PATH上の `python` / `py` を探してPython runnerを起動します。これは開発・検証用の暫定実装です。正式配布前に `runtime/python/python.exe` を優先する実装へ切り替え、利用者にPython導入を要求しない状態にする必要があります。

検証対象:

- `runtime/python/python.exe`
- 標準ライブラリ
- runner実行に必要な最小依存
- アプリenv作成に必要なpipまたは同等の導入手順

現段階ではPython runtime実体は未同梱です。`prepare_runtime.ps1 -AllowMissingRuntime` ではWARN扱いにし、`verify_release.ps1 -RequireRuntime` ではNG扱いにします。

## App Dependency Modes

ToolHubでは2方式を許容します。

方式A: app_env方式

```text
runtime/app_envs/<app_id>/
```

アプリごとのPython環境を固定配置します。当面の正式方針です。`requirements.lock` を使って依存関係を固定し、release時にapp_envを作成します。

方式B: exe方式

PyInstaller等で内蔵アプリを個別exe化し、`run.runner: exe` として扱います。重いアプリ、外部ベンダー提供アプリ、ライセンスや依存関係の都合でPython envを分けたいアプリに使います。

## Future app.yaml Fields

既存の必須仕様は維持します。将来、配布情報を以下のように追加できます。

```yaml
runtime:
  required_runtime: python-embedded-toolhub-001
  app_env: sample_csv_merger
  requirements_lock: requirements.lock

distribution:
  mode: app_env
  package: app_packs/sample_csv_merger-1.0.0.zip
```

初回実装ではランチャーUIには表示しません。管理者向けdocs、manifest、検収で使う情報として扱います。

## App Manifest Relation

`release/app_manifest.json` は各App Packのruntime要求を持ちます。

```json
{
  "required_runtime": "web-runtime-001"
}
```

軽量Pythonアプリは `required_runtime: null` を許容します。Web操作アプリはWeb自動化用ランタイムのIDを宣言します。

## Web Automation Runtime

利用者向け表現は「Web自動化用ランタイム」に統一します。利用者向けUIに内部技術名、ブラウザ製品名、手動インストール手順を表示しません。

管理者向けには、Web操作アプリが内部で専用runnerとブラウザ実行環境を必要とすることを説明してよいです。実体は `runtime/web_automation_runtime/` に配置し、ToolHub Coreや軽量App Packとは別のHeavy Runtime更新単位として扱います。

現段階ではWeb自動化用ランタイム実体は未同梱です。`prepare_runtime.ps1 -AllowMissingRuntime` ではWARN扱いにし、`verify_release.ps1 -RequireRuntime` ではNG扱いにします。

`sample_playwright_app` は検証安定性のため `headless=True` でローカルHTMLを操作します。正常時もブラウザウィンドウは表示されません。

## Heavy Runtime Update

Heavy Runtimeは更新サイズが大きく、更新頻度もCoreやApp Packと異なります。

方針:

- `release/manifest.json` でruntime IDとversionを管理する。
- App Packは `required_runtime` で必要runtimeを宣言する。
- sha256検証後に一時フォルダへ展開する。
- 更新前にバックアップを作る。
- User Dataは更新対象にしない。
- 失敗時は更新前状態へロールバックする。

## Git Policy

Gitに含める:

- `runtime/README.md`
- `runtime/**/.gitkeep`
- runtime準備スクリプト
- runtime設計docs
- manifest雛形

Gitに含めない:

- `runtime/python/*`
- `runtime/app_envs/*` の実体
- `runtime/web_automation_runtime/*` の実体
- `vendor/runtime/`
- `tools/runtime_sources/`

この方針は `.gitignore` に反映します。
