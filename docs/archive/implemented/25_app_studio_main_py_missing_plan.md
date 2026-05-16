# App Studio main.py Missing Investigation Plan

Created: 2026-05-10

## Implementation Status

2026-05-10 に修正を実装し、以下を反映した。

- Tauri `bundle.resources` へ App Studio CLI の実行最小セットを追加する。
- Rust backend に App Studio CLI availability check を追加し、preflight / diagnostics / 実行時エラーを同じ判定へ揃える。
- App Studio GUI の事前確認と AI 診断に CLI の有無を表示する。
- `scripts/package_installer.ps1` と `scripts/verify_release.ps1` に App Studio CLI resource の staging / 検証を追加する。
- NSIS installer を再生成し、`release/dist_installer/ToolHub_Setup_0.1.0.exe` と `release/manifest.json` を更新した。

## Purpose

App Studio の新規登録で AI 提案を作成しようとした際に、GUI が
`tools/app_studio/main.py が見つかりません。` と表示し、AI 生成まで進めない問題の原因と改善方針をまとめる。

この文書は調査結果と実装方針を記録するためのもの。初回作成時点では修正未着手だったが、上記ステータスのとおり修正を開始した。

## Observed Symptom

- 管理者画面 > App Studio > 新規登録 > AI 提案で失敗する。
- 画面には `登録内容の作成に失敗しました。` と表示される。
- 詳細には `tools/app_studio/main.py が見つかりません。` と表示される。
- AI/API キー設定や画像モデル設定の問題ではなく、App Studio CLI 起動前のローカルファイル解決で止まっている。

## Investigation Summary

### Source tree state

- 開発チェックアウトには `tools/app_studio/main.py` が存在する。
- `tools/app_studio/main.py` は App Studio の CLI エントリであり、以下を担当している。
  - `import --suggest`
  - `import --apply`
  - `approve`
  - `image-test`
  - `icon-regenerate`

### Rust backend call path

Tauri/Rust 側の App Studio コマンドは、`manifest::project_root()` で取得した root から固定的に次を参照している。

```text
<root>/tools/app_studio/main.py
```

主な参照箇所:

- `launcher/src-tauri/src/app_studio_commands.rs`
  - `run_image_generation_test_for_model`
  - `run_icon_regenerate_action`
  - `run_import_action`
  - `run_approve_action`

特に新規登録の AI 提案は `run_import_action()` で次の存在確認に失敗すると、CLI を起動せずに即エラーを返す。

```text
root/tools/app_studio/main.py
```

このため、AI metadata/icon generation の処理には到達しない。

### Runtime resource state

ビルド済み Tauri resource root の例として、以下を確認した。

```text
launcher/src-tauri/target/release/_up_/_up_/
launcher/src-tauri/target/debug/_up_/_up_/
```

これらには次が含まれている。

- `apps/`
- `config.default/`
- `release/`
- `runner/`
- `runtime/`
- `updater/`
- `README.md`

一方で、`tools/` が含まれていない。

### Tauri bundle configuration

`launcher/src-tauri/tauri.conf.json` の `bundle.resources` には、現在以下が含まれている。

- `../../runner`
- `../../apps`
- `../../runtime`
- `../../config.default`
- `../../release/manifest.json`
- `../../release/app_manifest.json`
- `../../updater`
- `../../README.md`

`../../tools/app_studio` は含まれていない。

### Verification gap

`scripts/verify_release.ps1` は repository root の `runner`, `apps`, `runtime`, `config.default`, `updater`, `installer`, `release/*` などを確認しているが、App Studio CLI の配布同梱を検査していない。

そのため、開発ツリーでは `tools/app_studio/main.py` が存在して App Studio が動いていても、Tauri bundle / installer resource に `tools/app_studio` が欠けた状態を検出できない。

## Root Cause

根本原因は、App Studio CLI が Tauri resource として同梱されていないこと。

Rust backend は実行時 root から `tools/app_studio/main.py` を必須ファイルとして探す設計だが、Tauri bundle の resource 定義に `tools/app_studio` が含まれていない。そのため、installer / bundled executable から起動した環境では root 解決自体は成功しても、App Studio CLI だけが見つからず、新規登録の AI 提案が開始できない。

これは AI API 設定不備ではない。AI 生成が失敗しているように見えるが、実際には AI 生成処理の前段にある App Studio CLI 起動ファイル解決で失敗している。

## Contributing Factors

- `manifest::project_root()` の root 判定は `apps/` と `runner/` を中心に成立するため、`tools/app_studio/main.py` がなくても ToolHub root として採用される。
- App Studio CLI path の組み立てが複数箇所に重複している。
- App Studio preflight / diagnostics が `tools/app_studio/main.py` の有無を事前表示していない。
- release verification が bundled resource 内の App Studio CLI 欠落を検出していない。
- `run_import_action()` は script check で即 return するため、今回の失敗は `app_studio_gui.log` に started / finished として残りにくい。

## Improvement Policy

### 1. Bundle App Studio CLI as a Tauri resource

`launcher/src-tauri/tauri.conf.json` の `bundle.resources` に App Studio CLI の実行に必要な最小セットを追加する。

候補:

```json
"../../tools/app_studio/main.py": "tools/app_studio/main.py",
"../../tools/app_studio/app_studio": "tools/app_studio/app_studio",
"../../tools/app_studio/assets": "tools/app_studio/assets"
```

`tests/`, `__pycache__/`, fixtures まで installer に含めないため、`../../tools` 全体ではなく App Studio 実行に必要な範囲だけを同梱する方針を優先する。

### 2. Centralize App Studio CLI path resolution

Rust 側に `resolve_app_studio_script(root)` のような helper を追加し、以下を一箇所に集約する。

- 期待パスの組み立て
- 存在確認
- user-facing message
- developer-facing diagnostic detail

重複している `root.join("tools").join("app_studio").join("main.py")` を置き換える。

対象:

- image-test
- icon-regenerate
- suggest/apply
- approve

### 3. Keep general root resolution broad, but make App Studio requirements explicit

`manifest::project_root()` 全体に `tools/app_studio/main.py` を必須化するのは避ける。

理由:

- ホーム画面のアプリ一覧や通常起動は `apps/` と `runner/` があれば成立する。
- App Studio だけの欠落で ToolHub 全体を起動不能にする必要はない。

代わりに、App Studio 系 command の preflight / diagnostics で `tools/app_studio/main.py` を必須条件として扱う。

### 4. Add preflight and diagnostics visibility

`app_studio_preflight` と `app_studio_ai_diagnostics` に、App Studio CLI の状態を追加する。

追加候補:

- `appStudioCliPath`
- `appStudioCliExists`
- `appStudioRepoRoot`
- `appStudioCliMessage`

GUI では、AI/API キー設定とは別に「App Studio CLI がこのインストールに含まれていない」ことを表示する。

### 5. Improve error message and logging

現在の表示は `tools/app_studio/main.py が見つかりません。` で止まるため、利用者には原因が分かりにくい。

改善案:

- 利用者向け:
  - `App Studio の実行ファイルがこの ToolHub に含まれていません。ToolHub を再ビルドまたは再インストールしてください。`
- 開発者向けログ:
  - resolved root
  - expected cli path
  - Tauri resource root candidate
  - whether `apps/`, `runner/`, `tools/` exist

script check で return する前にも `app_studio_gui.log` に diagnostic event を残す。

### 6. Add release verification for bundled resources

`scripts/verify_release.ps1` または release readiness report に、少なくとも次を追加する。

- repository root の `tools/app_studio/main.py` が存在すること
- `launcher/src-tauri/tauri.conf.json` の `bundle.resources` が App Studio CLI を含むこと
- Tauri build 済みの場合、resource output に `tools/app_studio/main.py` が存在すること

Tauri build 済み output がない場合は warning にし、`npm run tauri build` 後は fail できる形にする。

### 7. Add focused tests

追加候補:

- Rust unit test:
  - App Studio CLI がある root では helper が成功する。
  - App Studio CLI がない root では分かりやすい error を返す。
  - preflight result に CLI missing が反映される。
- PowerShell verification:
  - `tauri.conf.json` の `bundle.resources` に App Studio CLI resource が含まれる。
- Optional integration check:
  - Tauri build 後の resource root に `tools/app_studio/main.py` が存在する。

## Proposed Implementation Order

1. `tauri.conf.json` に App Studio CLI の最小 resource mapping を追加する。
2. Rust 側に App Studio CLI path resolver を追加する。
3. `run_import_action`, `run_icon_regenerate_action`, `run_image_generation_test_for_model`, `run_approve_action` を resolver 経由にする。
4. preflight / AI diagnostics に CLI availability を追加する。
5. GUI の App Studio preflight / result 表示に CLI missing を出す。
6. `verify_release.ps1` に bundle resource 検査を追加する。
7. unit test / release verification を追加する。

## Validation Plan For Next Implementation

次回修正時は、変更範囲に応じて以下を実行する。

```powershell
cd launcher
npm run build
```

Rust/Tauri resource と command 層を変更するため、可能なら以下も実行する。

```powershell
cd launcher
npm run tauri build
```

Tauri build 後に以下を確認する。

```powershell
Test-Path .\src-tauri\target\release\_up_\_up_\tools\app_studio\main.py
```

release verification も更新する場合は以下を実行する。

```powershell
.\scripts\verify_release.ps1
```

## Risks And Notes

- `tools/app_studio/tests` や fixtures を installer に含めると配布サイズと不要情報が増えるため、最小 resource mapping を優先する。
- App Studio CLI は Python module imports と assets を使うため、`main.py` だけを同梱しても不十分。`app_studio/` package と `assets/` も必要。
- App Studio CLI の依存 Python package は runtime Python / build_env 側の問題として別途検証が必要。ただし今回のエラーは dependency import 前に発生している。
- root resolution 全体を厳しくしすぎると、App Studio 欠落だけで通常ランチャー機能まで壊す可能性がある。
- この修正は `app.yaml` 仕様や runner public I/F を破壊しない方針で進める。

## Decision For Next Work

推奨方針は、`tools/app_studio` の実行最小セットを Tauri bundle resource に追加し、App Studio command 専用の CLI availability check と release verification を追加すること。

これにより、開発環境と installer / bundled environment の差分をなくし、同じ欠落が次回リリースで再発しないようにする。
