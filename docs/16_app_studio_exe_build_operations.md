# Legacy Frozen-Folder / Exe Operations

この文書は、既存互換として残している `frozen-folder` / `exe` 経路の運用注意をまとめます。

通常新規登録の標準は `shared-env` です。現在の App Studio GUI で新しい Python app を登録する場合は、Python source を entry にし、`run.runner: python_shared_env` と `runtime/envs/<env_id>/` を使います。詳細は [13_app_studio.md](13_app_studio.md) を参照してください。

## この文書の対象

対象:

- 既存の `run.runner: exe` app。
- 過去に PyInstaller `--onedir` で登録された app。
- App Pack や release 検証で古い frozen-folder app を読む場合。
- 管理者が互換目的で frozen-folder を明示的に調査する場合。

対象外:

- 通常新規登録 GUI の標準フロー。
- `shared-env` app の通常実行。
- 利用者 PC に app ごとの private venv を要求する設計。

## Legacy frozen-folder の形

典型的な manifest は次の形です。

```yaml
run:
  runner: exe
  entry: bin/<app_id>/<app_id>.exe
  mode: gui

runtime:
  distribution_mode: frozen_folder
  requirements_lock: requirements.lock
```

`frozen-folder` は PyInstaller の `--onedir` 相当の folder output です。ToolHub では `--onefile` を標準採用しません。起動が遅くなりやすく、ログ調査と同梱ファイル確認が難しくなるためです。

## Build Profile

legacy frozen-folder app では、アプリごとに build profile を持つ場合があります。

主な項目:

- `paths`: import 解決用の追加 path。
- `hidden_imports`: PyInstaller が自動検出できない import。
- `add_data`: exe フォルダへ同梱する設定、flow、assets。
- `add_binaries`: DLL や外部バイナリ。
- `collect_all`: Playwright など package 全体の収集が必要なもの。
- `runtime_cwd`: 起動時の working directory 方針。
- `environment`: 実行時に必要な環境変数。
- `manual_checks`: GUI 操作、ログイン、ファイル選択など人間確認が必要な項目。

古い profile を修正する場合でも、`.auth/`、storage state、cookie、token、credential、logs、screenshots、tmp、venv、生成物を同梱対象にしないでください。

## 検証ゲート

legacy frozen-folder app を維持または再確認する場合は、少なくとも次を確認します。

- `apps/<app_id>/bin/<app_id>/<app_id>.exe` が存在する。
- `app.yaml` の `run.entry` が app directory 内の相対 path を指す。
- `display.icon` が app directory 内に存在する。
- `requirements.lock` が必要な app では、App Pack 内にも同じ path で入っている。
- build profile の `add_data` / `required_files` が実際の frozen-folder 内に存在する。
- `build_env`、`.auth/`、logs、screenshots、tmp、credential 類が App Pack に混入していない。
- `execution_test_result.json` が pass / warn / fail を明確に示す。

Playwright、ブラウザログイン、社内サイト操作、ファイル選択、メール送信、アップロードは自動確認だけで業務利用可能とは扱いません。manual check として残します。

## shared-env へ戻す場合

既存 frozen-folder app を現行標準へ戻す場合は、exe ではなく Python source を entry として App Studio から再登録します。

再登録後の期待値:

- `run.runner: python_shared_env`
- `run.entry: src/<entry_relative>.py`
- `run.env_id: <env_id>`
- `runtime.distribution_mode: shared_env`
- `runtime.required_runtime: python-shared-env:<env_id>`
- `runtime.requirements_lock: requirements.lock`

古い frozen-folder output は、削除計画または app 管理 UI の対象として扱い、直接削除しないでください。共有 runtime や user data を巻き込まないことが重要です。

## 関連文書

- [13_app_studio.md](13_app_studio.md): 現行 App Studio 登録フロー。
- [09_app_pack_spec.md](09_app_pack_spec.md): App Pack の必要 entry と検証。
- [17_app_management_model.md](17_app_management_model.md): app 管理と削除対象分類。
- [18_app_delete_execution_plan.md](18_app_delete_execution_plan.md): 削除実行計画。
