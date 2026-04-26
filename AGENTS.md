# ToolHub Codex Working Rules

このファイルは、Codex が ToolHub リポジトリを修正する際の作業規約です。  
目的は、AI の精度を落とさず、無駄な探索・不要な大規模変更・手戻りを減らすことです。

---

## 1. Project Overview

ToolHub は、複数の Python アプリケーションを 1 つのデスクトップ画面から探して起動するための業務用アプリランチャーです。

重要な設計方針:

- 各アプリは `apps/<app_id>/app.yaml` を持つプラグインとして配置する。
- ランチャー本体に、個別アプリ固有の処理を混ぜない。
- アプリ起動処理は `runner/` の Python App Runner に集約する。
- `launcher/` は Tauri + React による UI / desktop shell を担当する。
- `launcher/src-tauri/` は Rust backend を担当する。
- `scripts/` は build / package / verify / check などの開発・配布補助を担当する。
- `docs/` は設計、配布、検収、トラブルシュートの説明を担当する。
- `runtime/` と `release/` は配布・実行環境に関わるため、不用意に変更しない。

---

## 2. Default Working Principle

Codex は、ユーザーから実装依頼を受けた場合、原則として 1 回の作業内で以下を完了してください。

1. 依頼内容を読む。
2. この `AGENTS.md` を確認する。
3. 関連する最小限のファイルを確認する。
4. 実装前セルフレビューを行い、影響範囲の見落としがないか確認する。
5. 必要な場合のみ、探索範囲を段階的に広げる。
6. 実装する。
7. 実装後に差分セルフレビューを行う。
8. 指定された検証コマンド、または妥当な最小検証を実行する。
9. 変更内容、検証結果、未確認事項を報告する。

重要:

- レビューのためだけに途中でユーザーへ確認を求めない。
- 通常は、実装前レビュー、実装、実装後レビュー、検証まで 1 回で完了する。
- ただし、破壊的変更や重大な仕様判断が必要な場合は、実装せず停止して提案のみ返す。

---

## 3. Exploration Policy

探索を禁止しない。  
ただし、無関係な全体探索は避ける。

### 3.1 最初に確認するもの

原則として、最初に以下を確認する。

- `AGENTS.md`
- `README.md`
- `docs/00_AI_CONTEXT.md` が存在する場合はそれ
- ユーザーが指定したファイル
- 依頼内容に直接関係するファイル

### 3.2 必要に応じて確認してよいもの

以下に該当する場合は、必要最小限の追加探索を行ってよい。

- 呼び出し元・参照元が不明な場合
- 型定義や interface に影響する場合
- React component 間の props / state / event flow に影響する場合
- CSS / layout / UI 文言に影響する場合
- Tauri command / Rust backend に影響する場合
- Python runner の公開 I/F に影響する場合
- `apps/<app_id>/app.yaml` の仕様に影響する場合
- build / check / package / verify script に影響する場合
- docs の既存説明と矛盾する可能性がある場合
- release / runtime の設計前提に影響する可能性がある場合

### 3.3 探索時の注意

- 読むことと変更することを分ける。
- `docs/`, `scripts/`, `runner/`, `release/`, `runtime/` は、仕様確認のために読んでよい。
- ただし、変更は依頼内容と明確に関係する場合だけに限定する。
- 大きなフォルダや生成物を無目的に探索しない。

---

## 4. Change Policy

### 4.1 原則として変更してよいもの

依頼内容に関係する範囲で、以下は変更してよい。

- `launcher/`
- `launcher/src-tauri/`
- `runner/`
- `apps/`
- `scripts/`
- `docs/`
- `config.default/`
- `installer/`
- `updater/`
- `README.md`

ただし、変更は依頼目的に対して必要最小限にする。

### 4.2 原則として変更しないもの

以下は、明確な理由がない限り変更しない。

- `release/`
- `runtime/`
- `node_modules/`
- `target/`
- `dist/`
- `logs/`
- `data/`
- `.git/`
- `__pycache__/`
- `.pytest_cache/`
- 生成物
- ユーザーデータ
- 実行ログ
- 一時ファイル

### 4.3 lock file の扱い

以下の lock file は、依存関係を追加・変更した場合のみ更新する。

- `launcher/package-lock.json`
- `launcher/src-tauri/Cargo.lock`

依存関係を追加していないのに lock file だけを変更しない。

---

## 5. Architecture Rules

### 5.1 ランチャーと個別アプリの責務分離

禁止:

- 個別アプリ固有の処理を `launcher/` に直接埋め込む。
- 特定アプリ専用の起動ロジックを Rust backend にハードコードする。
- `apps/<app_id>/app.yaml` を無視した個別分岐を追加する。

守ること:

- 個別アプリ情報は `apps/<app_id>/app.yaml` を中心に扱う。
- 起動処理は `runner/` 側に集約する。
- UI は app metadata / runner result / logs を表示する役割に留める。

### 5.2 app.yaml 互換性

- 既存の `app.yaml` 仕様を破壊しない。
- 既存アプリが読み込めなくなる変更をしない。
- 仕様拡張が必要な場合は、後方互換を優先する。
- 必須項目を増やす場合は、既存 app への影響を確認する。

### 5.3 runner I/F

- `runner/` の公開 I/F を不用意に変えない。
- Rust backend から Python runner を呼ぶ契約を壊さない。
- stdout / stderr / JSON Lines / log path / exit code の扱いを変更する場合は、呼び出し元を確認する。
- 変更が必要な場合は、互換性または移行処理を用意する。

### 5.4 UI / UX

- 利用者向け画面では、不要に内部技術名を露出しない。
- 日本語 UI 文言は自然で、業務利用者に分かりやすい表現にする。
- エラーは、利用者向けの短い説明と、開発者向けの詳細ログに分ける。
- 既存の画面密度、操作導線、ステップ構造を不用意に崩さない。

### 5.5 配布・runtime

- 正式配布方針はインストーラー型配布を基本とする。
- `ToolHub_Setup.exe`、App Pack、runtime、manifest の責務を混同しない。
- `runtime/` の実体同梱が未完了である前提を壊さない。
- `release/manifest.json` や `release/app_manifest.json` の仕様変更は慎重に扱う。

---

## 6. Self Review Requirements

Codex は実装前と実装後に、内部で必ずセルフレビューを行う。

### 6.1 実装前セルフレビュー

実装前に以下を確認する。

- 依頼目的は何か。
- 主対象ファイルはどこか。
- 呼び出し元・参照元はどこか。
- 型定義や interface に影響しないか。
- CSS / layout に影響しないか。
- runner / Rust backend / app.yaml 仕様に影響しないか。
- docs や check script と矛盾しないか。
- 変更範囲が狭すぎて、必要な関連修正を見落としていないか。
- 逆に、変更範囲が広すぎて不要な修正をしようとしていないか。

### 6.2 実装後セルフレビュー

実装後に以下を確認する。

- 依頼範囲外の変更が混ざっていないか。
- 既存仕様を壊していないか。
- 不要な大規模リファクタが入っていないか。
- 型、import、未使用変数、lint 的な問題がないか。
- UI 文言に不自然な日本語がないか。
- エラー処理が不足していないか。
- 既存の検証コマンドに耐えられるか。
- docs 更新が必要なのに漏れていないか。
- 生成物やログを誤って変更していないか。

---

## 7. Stop Conditions

通常は途中確認せず、実装・レビュー・検証まで完了する。

ただし、以下に該当する場合は、実装せず停止し、提案のみ返す。

- 既存の `app.yaml` 仕様を破壊する必要がある。
- `runner/` の公開 I/F を破壊する必要がある。
- 保存データ形式を変更する必要がある。
- 既存データを削除する可能性がある。
- `release/manifest.json` または `release/app_manifest.json` の互換性を壊す。
- runtime 同梱方針を大きく変更する必要がある。
- 大規模リファクタが必要。
- ユーザー依頼と既存設計が明確に矛盾する。
- セキュリティ・署名・配布信頼性に関わる重大判断が必要。
- 実装すると後戻りが難しい変更になる。

停止する場合も、単に止まるのではなく、以下を返す。

- なぜ停止したか。
- どの選択肢があるか。
- 推奨案はどれか。
- 次にユーザーが判断すべきことは何か。

---

## 8. Validation Policy

ユーザーが検証コマンドを指定した場合は、それを優先する。

指定がない場合は、変更内容に応じて最小限の検証を選ぶ。

### 8.1 一般チェック

```powershell
python main.py --check
```

```powershell
.\scripts\check_all.ps1
```

### 8.2 launcher / React 変更

```powershell
cd launcher
npm run build
```

### 8.3 Tauri / Rust 変更

必要に応じて以下を検討する。

```powershell
cd launcher
npm run tauri build
```

ただし、重い release build は毎回実行しなくてよい。  
ユーザーが指定した場合、または Rust backend / Tauri 設定変更時に実行を検討する。

### 8.4 release / package 変更

```powershell
.\scripts\build_release.ps1 -SkipBuild -AllowMissingBundle
```

```powershell
.\scripts\verify_release.ps1
```

### 8.5 runtime 変更

runtime 実体が未同梱の場合があるため、`-AllowMissingRuntime` や `-RequireRuntime` の意味を確認して実行する。

---

## 9. Documentation Policy

docs 更新は、以下の場合のみ行う。

- ユーザーが docs 更新を依頼した場合
- 実装により既存 docs と明確に差異が出る場合
- 新しい操作方法、仕様、検証手順が追加された場合
- 既存の README / docs が誤解を招く状態になる場合

docs 更新時の注意:

- 実装されていないことを、実装済みのように書かない。
- 未完了事項は未完了として明記する。
- 実装済み、設計のみ、雛形のみ、未検証を区別する。
- ToolHub の現状到達点を過大評価しない。

---

## 10. Output Format

作業完了時は、以下の形式で報告する。

```md
## Summary

- ...

## Changed Files

- `path/to/file`
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
- Not run の場合は理由

## Notes

- ...
```

報告では、成功したことと未確認のことを分けて書く。  
検証していないことを「確認済み」と書かない。
