# ToolHub

ToolHub は、複数の Python アプリケーションを 1 つのデスクトップ画面から探して起動するための業務用アプリランチャーです。

個別アプリの情報は `apps/<app_id>/app.yaml` に置きます。ランチャー本体には個別アプリ固有の処理を書かず、起動処理は `runner/` の Python App Runner に集約します。

## 最初に読む文書

- Codex / AI 作業の入口: [AGENTS.md](AGENTS.md), [docs/00_AI_CONTEXT.md](docs/00_AI_CONTEXT.md)
- 文書一覧: [docs/README.md](docs/README.md)
- 全体設計: [docs/01_architecture.md](docs/01_architecture.md)
- App Studio: [docs/13_app_studio.md](docs/13_app_studio.md)
- 配布と検収: [docs/05_build_and_release.md](docs/05_build_and_release.md), [docs/06_acceptance_checklist.md](docs/06_acceptance_checklist.md)

古い調査記録や handoff は通常の作業開始時には読みません。必要な場合は Git 履歴または `docs/archive/README.md` を確認してください。

## 開発時の起動

プロジェクト直下で実行します。

```powershell
python main.py
```

Windows の `py` ランチャーでも実行できます。

```powershell
py main.py
```

Tauri 開発モードを強制する場合:

```powershell
python main.py --dev
```

ビルド済み実行ファイルだけを探す場合:

```powershell
python main.py --release
```

## 環境チェック

```powershell
python main.py --check
```

より広い検証:

```powershell
.\scripts\check_all.ps1
```

App Pack / release manifest に影響する変更:

```powershell
.\scripts\package_app_pack.ps1
.\scripts\verify_release.ps1
```

## 開発環境

主な前提:

- Python 3.10 以降
- Node.js / npm
- Rust / cargo
- Visual Studio Build Tools
- Desktop development with C++
- MSVC v143 以降
- Windows SDK

フロントエンド依存関係は `launcher/` で管理します。

```powershell
cd launcher
npm ci
```

配布アプリケーションとして再現性を保つため、次の lock file は管理対象です。

- `launcher/package-lock.json`
- `launcher/src-tauri/Cargo.lock`

依存関係を追加・変更していない場合、lock file だけを更新しないでください。

## アプリ追加

通常の新規登録は、管理者画面の App Studio から行います。現行標準は `shared-env` です。

`shared-env` app の基本:

- `run.runner: python_shared_env`
- `run.entry: src/<entry>.py`
- `runtime.distribution_mode: shared_env`
- `runtime.required_runtime: python-shared-env:<env_id>`
- `runtime.requirements_lock: requirements.lock`

詳細は [docs/13_app_studio.md](docs/13_app_studio.md) と [docs/31_app_registration_app_authoring_guidelines.md](docs/31_app_registration_app_authoring_guidelines.md) を参照してください。

手動テンプレートを作る場合:

```powershell
.\scripts\create_app_template.ps1 -AppId my_app -Name "業務ツール"
```

## 配布方針

利用者には原則として `ToolHub_Setup.exe` 1 個を配布します。利用者が Python、Node.js、Rust、pip package、Web 自動化用 runtime を手動導入しない方針です。

runtime 実体、App Pack、installer は release artifact として扱います。Git 管理物とローカル配布 artifact を混同しないでください。

## ディレクトリ概要

| Path | 役割 |
| --- | --- |
| `apps/` | 登録済みアプリ |
| `runner/` | Python App Runner |
| `launcher/` | Tauri + React UI |
| `launcher/src-tauri/` | Rust backend |
| `tools/app_studio/` | App Studio CLI / 登録補助 |
| `scripts/` | build / package / verify / diagnostics |
| `docs/` | 現行仕様と運用説明 |
| `config.default/` | 初期設定テンプレート |
| `runtime/`, `release/` | 配布 artifact 領域 |
| `data/`, `logs/`, `config/` | 実行時・ユーザー状態 |

生成物、実行ログ、ユーザー設定は原則として Git 管理しません。
