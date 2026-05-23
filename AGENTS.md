# ToolHub Codex Working Rules

このファイルは Codex の最初の読み込み量を抑え、ToolHub の現行設計から外れた変更を防ぐための最小ルールです。

## 1. First Read

通常は次だけ読む。

1. `AGENTS.md`
2. `docs/00_AI_CONTEXT.md`
3. ユーザーが指定したファイル
4. 依頼に直接関係するファイル

`README.md` と `docs/README.md` は、起動方法、配布、文書位置を確認したい場合だけ読む。`docs/archive/`、`release/`、`runtime/`、`data/`、`logs/`、`apps/*/src/assets/payload/` は、明確な理由がない限り読まない。

## 2. Project Boundary

ToolHub は複数の Python アプリを 1 つのデスクトップ UI から探して起動する業務用アプリランチャー。

- `apps/<app_id>/app.yaml`: アプリ定義。
- `runner/`: Python App Runner。アプリ起動処理を集約する。
- `launcher/`: Tauri + React の UI / desktop shell。
- `launcher/src-tauri/`: Rust backend。
- `tools/app_studio/`: App Studio CLI / 登録補助。
- `scripts/`: build / package / verify / diagnostics。
- `docs/`: 現行仕様と運用説明。
- `runtime/`, `release/`: 配布 artifact 領域。原則として不用意に変更しない。

ランチャー本体に個別アプリ固有の処理を混ぜない。特定アプリ専用の起動分岐を Rust backend に追加しない。アプリ固有情報は `app.yaml` と runner 経由で扱う。

## 3. Current App Contract

現行の通常 App Studio 登録は `shared-env` が標準。

- `run.runner: python_shared_env`
- `run.entry: src/<entry>.py`
- `run.env_id: <env_id>`
- `runtime.distribution_mode: shared_env`
- `runtime.required_runtime: python-shared-env:<env_id>`
- `runtime.requirements_lock: requirements.lock`

既存 `app.yaml` 互換性を壊さない。必須項目を増やす場合は、既存 app と App Pack / release verification への影響を確認する。

## 4. Change Scope

依頼に関係する範囲で変更してよいもの:

- `launcher/`
- `launcher/src-tauri/`
- `runner/`
- `tools/app_studio/`
- `apps/`
- `scripts/`
- `docs/`
- `config.default/`
- `installer/`
- `updater/`
- `README.md`

明確な理由なしに変更しないもの:

- `release/`
- `runtime/`
- `data/`
- `logs/`
- `backups/`
- `node_modules/`
- `target/`
- `dist/`
- `.git/`
- `__pycache__/`
- `.pytest_cache/`
- 生成物、実行ログ、ユーザーデータ

依存関係を追加・変更していない場合、`launcher/package-lock.json` と `launcher/src-tauri/Cargo.lock` は変更しない。

## 5. Stop Conditions

以下に当たる場合は実装せず、理由、選択肢、推奨案、ユーザー判断点を返す。

- `app.yaml` 仕様や `runner/` 公開 I/F を破壊する必要がある。
- 保存データ形式や既存ユーザーデータを変更・削除する必要がある。
- `release/manifest.json` / `release/app_manifest.json` の互換性を壊す。
- runtime 同梱方針、署名、配布信頼性に関わる重大判断が必要。
- 大規模リファクタが必要。
- ユーザー依頼と既存設計が明確に矛盾する。

## 6. Self Review

実装前:

- 目的、主対象、呼び出し元、参照元を確認する。
- runner / Rust backend / app.yaml / App Pack / docs / check script への影響を確認する。
- 変更範囲が広すぎないか、狭すぎないか確認する。

実装後:

- 依頼範囲外の変更が混ざっていないか確認する。
- 既存仕様、import、型、UI 文言、検証スクリプトに破綻がないか確認する。
- docs 更新や ignore 更新が必要なら実施する。

## 7. Validation

ユーザー指定があればそれを優先する。指定がない場合は変更範囲に応じて最小検証を選ぶ。

```powershell
python main.py --check
```

```powershell
.\scripts\check_all.ps1
```

launcher / React 変更時:

```powershell
cd launcher
npm run build
```

release / package 変更時:

```powershell
.\scripts\package_app_pack.ps1
.\scripts\verify_release.ps1
```

runtime 実体が必要な検証は、`-AllowMissingRuntime` / `-RequireRuntime` の意味を確認してから実行する。

## 8. Final Report

作業完了時は、成功したことと未確認のことを分けて報告する。

```md
## Summary
- ...

## Changed Files
- `path/to/file`

## What Changed
- ...

## Pre-Implementation Self Review
- 確認した観点:
- 追加で確認したファイル:
- 見落とし防止のために確認したこと:

## Post-Implementation Self Review
- 依頼範囲外の変更:
- 既存仕様への影響:
- docs 更新要否:
- 未確認リスク:

## Validation
実行したコマンド:

```powershell
...
```

結果:
- Pass / Fail / Not run

## Notes
- ...
```
