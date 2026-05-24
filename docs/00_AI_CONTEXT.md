# ToolHub AI Context

Codex は通常、このファイルだけで現在の前提を把握する。詳細が必要な場合だけ個別 docs や実装を読む。

## 現行到達点

- ToolHub は Tauri + React のランチャーと Python runner で構成する。
- 個別アプリの情報は `apps/<app_id>/app.yaml` に置く。
- アプリ起動は `runner/` に集約し、launcher / Rust backend に個別アプリ専用分岐を入れない。
- App Studio の通常新規登録は `shared-env` 標準。
- 配布は installer 型が基本。runtime 実体、App Pack、installer は release artifact として扱う。
- 現行 release manifest は ToolHub `0.1.6` / `ToolHub_Setup_0.1.6.exe`。AgendaSnap は一般公開対象から外している。GitHub Release Latest の remote manifest / installer hash 検証と VM install / launch / bundled runtime 確認は済み。証明書署名済み artifact は未作成。
- 有効アプリは docs ではなく `release/app_manifest.json` と `apps/<app_id>/app.yaml` で確認する。

## Repository Map

| Path | Role | Codex default |
| --- | --- | --- |
| `apps/` | 登録済みアプリ。各 app は `app.yaml` を入口にする。 | 対象 app だけ読む。 |
| `runner/` | Python App Runner。runner I/F と起動結果を扱う。 | 起動契約に触る時だけ読む。 |
| `launcher/` | React UI と Tauri desktop shell。 | UI / Tauri 変更時だけ読む。 |
| `launcher/src-tauri/` | Rust backend。manifest、setup、commands、runner 呼び出し。 | backend 変更時だけ読む。 |
| `tools/app_studio/` | App Studio CLI / 登録補助。 | App Studio 変更時だけ読む。 |
| `scripts/` | build / package / verify / diagnostics。 | 検証や配布契約に触る時だけ読む。 |
| `docs/` | 現行仕様と運用説明。 | 目的に合う docs だけ読む。 |
| `config.default/` | 初回 user config のテンプレート。 | 設定仕様変更時だけ読む。 |
| `runtime/` | 同梱 runtime 実体と shared env。 | artifact 扱い。通常読まない。 |
| `release/` | manifest、App Pack、installer artifact。 | manifest / release 変更時だけ読む。 |
| `data/`, `config/`, `backups/` | 実行時状態、ローカル設定、退避先。 | ユーザーデータ扱い。通常読まない。 |

## shared-env app の基本形

```yaml
run:
  runner: python_shared_env
  entry: src/main.py
  mode: gui
  env_id: <env_id>
  # Optional only for apps that require console interaction:
  # show_terminal: true

runtime:
  distribution_mode: shared_env
  required_runtime: python-shared-env:<env_id>
  requirements_lock: requirements.lock
```

## 触る前に注意する場所

- `runtime/` と `release/` は配布 artifact 領域。明示依頼がない限り編集しない。
- `data/`, `logs/`, `backups/`, `config/` は実行時・ユーザー状態を含み得る。通常は編集しない。
- `docs/archive/` は現在仕様ではない。過去経緯を追う必要がある場合だけ読む。
- `apps/*/src/assets/payload/` は同梱生成物の混入候補。通常のコード探索対象にしない。
- `apps/pdf_workbench/src/assets/payload/` は現行 PDF Workbench launcher が `pdf-workbench.exe` を探すため、未参照 artifact として削除しない。

## 文書の使い分け

- `README.md`: 起動と検証の短い入口。
- `docs/README.md`: 詳細 docs の案内。
- `docs/01_architecture.md`: 責務分担。
- `docs/13_app_studio.md`: App Studio 現行仕様。
- `docs/05_build_and_release.md`, `docs/06_acceptance_checklist.md`: 配布と検収。

## 標準検証

一般変更:

```powershell
python main.py --check
```

広めの変更:

```powershell
.\scripts\check_all.ps1
```

App Pack / release manifest に影響する変更:

```powershell
.\scripts\package_app_pack.ps1
.\scripts\verify_release.ps1
```
