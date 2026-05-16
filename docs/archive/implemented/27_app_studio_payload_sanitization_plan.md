# App Studio Payload Sanitization and Gate Policy Plan

Created: 2026-05-11
Updated: 2026-05-11

Implementation result:

- Implemented shared payload policy in `tools/app_studio/app_studio/payload_policy.py`.
- Implemented sanitized staging for PyInstaller directory `add_data`.
- Updated runtime distribution checks to ignore generated artifacts for required-data expectations while still failing if generated artifacts remain packaged.
- Added rollback handling for App Studio registration copy / App Pack failures.
- Verified `legacy_flet_system_20260510` registration with `distribution_check: pass`; approval was reapplied and `apps/legacy_flet_system_20260510/app.yaml` exists.

## Status

未実装。

この文書は、App Studio の frozen-folder 登録で `__pycache__` / `.pyc` などの生成物が配布物に混入し、`distribution_check` が fail になる問題を修正するための方針です。

次工程では、この文書に従って実装を開始します。

## Current Problem

`legacy_flet_system_20260510` の再登録で、PyInstaller build と frozen smoke execution は成功したが、配布物検証で fail になった。

直接原因:

```text
forbidden payload files: fail
Forbidden files were packaged:
bin/legacy_flet_system_20260510/pdf_app/services/__pycache__
bin/legacy_flet_system_20260510/pdf_app/services/__pycache__/*.pyc
```

発生経路:

```json
{
  "source": "pdf_app/services",
  "destination": "pdf_app/services"
}
```

App Studio が `pdf_app/services` を directory `add_data` として PyInstaller に渡したため、ソースツリー内に残っていた `__pycache__` と `.pyc` まで同梱された。

この種のファイルは、人間がアプリごとに除外設定する対象ではない。Python / build の生成物であり、ToolHub 側が機械的に除外すべきである。

## Design Principles

1. 人間に生成物除外を求めない。
2. App Studio が配布物を自動で正規化する。
3. build 側と check 側で同じ payload policy を使う。
4. fail は本当に配布・起動・安全性を壊すものだけに限定する。
5. warn は利用者が確認すべき残リスクに限定する。
6. 登録処理は不整合を残さない。

## Payload Policy

### Always Exclude

以下は source に存在しても自動除外する。

```text
__pycache__/
*.pyc
*.pyo
*.pyd.tmp
.pytest_cache/
.mypy_cache/
.ruff_cache/
.cache/
ToolHub_AppStudio_Output/
build/
dist/
be/
bt/
.venv/
venv/
env/
*.spec
```

注意:

- `.pyd` 本体は Python 拡張として必要な場合があるため、原則除外しない。
- `*.spec` は App Studio が PyInstaller コマンドを管理するため、通常は同梱不要。
- `node_modules/` など巨大 dependency は、既存の inventory policy と衝突しないよう別途扱う。

### Fail

以下は登録を止める。

```text
exe missing
app.yaml missing
run.entry missing
required_files missing
secret / token / credential packaged
frozen exe immediate crash
App Pack required entry missing
App Pack sha256 mismatch
manifest parse error
```

### Warn

以下は登録を止めない。

```text
GUI の完全操作は未確認
Playwright のログイン状態は手動確認が必要
browser / file picker / keep-open flow は自動完了確認できない
配布物サイズが大きいが動作には影響しない
生成物を自動除外した
```

### Auto Fix / Auto Normalize

以下は fail でも warn でもなく、処理ログに記録して自動補正する。

```text
__pycache__ removed
*.pyc removed
cache directory skipped
App Studio output directory skipped
build_env / build temp skipped
```

## Implementation Plan

### 1. 共通 payload policy を追加する

候補:

```text
tools/app_studio/app_studio/payload_policy.py
```

責務:

- 除外対象 path 判定
- 除外対象 file suffix 判定
- 配布物に残ってはいけない forbidden payload 判定
- レポート用の除外理由を返す

想定 API:

```python
def should_exclude_payload_path(relative: Path) -> tuple[bool, str]:
    ...

def is_forbidden_packaged_payload(relative: Path) -> tuple[bool, str]:
    ...
```

### 2. add_data directory を sanitized staging 経由にする

対象候補:

```text
tools/app_studio/app_studio/build_profile.py
tools/app_studio/app_studio/frozen_folder_builder.py
```

方針:

- `add_data` に directory が含まれる場合、source directory をそのまま PyInstaller に渡さない。
- `output_dir/bt/sanitized_data/<stable_name>/` に必要ファイルだけをコピーする。
- `__pycache__`, `.pyc`, cache, build output は staging に入れない。
- PyInstaller には sanitized directory を渡す。

理由:

- `--add-data directory;destination` は directory 全体を同梱しやすく、生成物混入を制御しにくい。
- 個別 file に展開すると Windows の command length に当たりやすい。
- sanitized staging が最も安定する。

### 3. runtime check を同じ policy に合わせる

対象候補:

```text
tools/app_studio/app_studio/runtime_checker.py
```

方針:

- `forbidden_payload_check` は残す。
- ただし build 側で除外できる生成物は、生成時に除外する。
- check 側は「残っていたら sanitizer の漏れ」として fail にする。
- `required add-data files` の期待値生成では、自動除外対象を required 扱いしない。

これにより、ユーザーは `__pycache__` を手で消す必要がなくなる。

### 4. registration transaction を整理する

対象候補:

```text
tools/app_studio/app_studio/registrar.py
tools/app_studio/main.py
launcher/src-tauri/src/app_studio_management.rs
launcher/src-tauri/src/app_studio_result_reader.rs
```

方針:

- apply が fail した場合、既存の `apps/<app_id>/app.yaml` を壊さない。
- `release/app_manifest.json enabled=true` だが `apps/<app_id>/app.yaml missing` の状態を残さない。
- 既に不整合がある場合は、UI に「登録失敗」ではなく「登録状態が不整合」と出す。
- approval 済みでも app yaml がなければ catalog visible にしないのは現状通り。ただし復旧手順を明示する。

### 5. UI message を改善する

対象候補:

```text
launcher/src/components/admin/*
launcher/src-tauri/src/app_studio_result_reader.rs
```

方針:

- `distribution_check fail` のときは、最初に fail check 名を出す。
- `__pycache__` / `.pyc` は通常ユーザー修正対象ではなく「App Studio が除外すべき生成物」と説明する。
- `app_yaml_missing` は「manifest と app source の不整合」と説明し、再 apply または復旧が必要と示す。

## Test Policy

テストは闇雲に増やさない。fail 条件を増やすのではなく、自動補正で吸収できるものは吸収する。

### Required Unit Tests

最小限、以下だけ追加または更新する。

1. payload policy が `__pycache__` と `.pyc` を exclude する。
2. directory add_data が sanitized staging になり、`.pyc` を含まない。
3. `required add-data files` が除外済み生成物を required 扱いしない。
4. final_app に `.pyc` が残った場合は fail する。
5. apply fail 時に既存 manifest / app directory の不整合を残さない。

### Required Integration Tests

最小限、以下だけ確認する。

1. `legacy_flet_system_20260510` 型の directory add_data で `distribution_check` が pass する。
2. `frozen smoke execution` が pass する。
3. 登録コピー後に `apps/<app_id>/app.yaml` が存在する。
4. `release/app_manifest.json` の enabled と catalog visibility が一致する。

### Not Required

以下は自動テストで完全保証しない。

```text
GUI 操作の完全成功
PDF 編集など業務機能の完全シナリオ
Playwright ログイン済み状態
外部サービス接続
ユーザー資格情報入力
```

これらは App Studio の登録可否とは別の業務受入確認で扱う。

## Acceptance Criteria

修正完了条件:

1. ソースに `__pycache__` / `.pyc` が存在しても、final_app に混入しない。
2. `distribution_check` は生成物混入で fail しない。
3. `frozen smoke execution` が即時クラッシュを検出できる。
4. fail 時に `manifest enabled=true` かつ `app_yaml_missing` の不整合を新規に作らない。
5. UI が fail の原因を 1 つ以上具体名で示す。
6. 登録済みアプリの app.yaml 互換性を壊さない。

## Recommended Validation Commands

実装後の最小検証:

```powershell
python -m unittest tools.app_studio.tests.test_builders
python -m unittest runner.tests.test_detached_runner
python main.py --check
```

必要に応じて実アプリで確認:

```powershell
python tools\app_studio\main.py import --entry "C:\Users\kuroron\Documents\RD\20260215_PDFApplication\archive\legacy_flet_system_20260510\app.py" --build-mode frozen-folder --app-id legacy_flet_system_20260510 --name "Legacy Flet System 20260510" --apply
```

重い検証:

```powershell
cd launcher
npm run tauri build
```

`npm run tauri build` は時間がかかるため、Rust / Tauri resource / installer 変更時だけ実行する。

## Notes for Next Process

- まず `payload_policy.py` を追加し、build / check 双方から使う。
- 次に directory add_data の sanitized staging を実装する。
- その後に `legacy_flet_system_20260510` を再 apply して、`app_yaml_missing` を解消する。
- テスト追加は上記の最小セットに限定する。
- fail gate を増やす場合は、必ず「ユーザーが何を直せばよいか」をレポートに出す。
