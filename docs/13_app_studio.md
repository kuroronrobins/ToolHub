# App Studio

この文書は、現在の ToolHub App Studio の通常新規登録フローを説明します。

## 現行方針

2026-05-17 時点の通常新規登録は `shared-env` 固定です。

確認済みの実装上の根拠:

- `tools/app_studio/app_studio/models.py` の `NORMAL_REGISTRATION_BUILD_MODE` は `shared-env`。
- `scripts/import_app.ps1` は legacy BuildMode を受けても `shared-env` に正規化する。
- 新規登録 GUI は `buildMode: shared-env` を初期値にし、通常登録では frozen-folder build を要求しない。
- runner は `python_shared_env` をサポートし、配布同梱の `runtime/python/python.exe` から `runtime/envs/<env_id>/Lib/site-packages` を bootstrap して app を起動する。

通常新規登録で作る `app.yaml` の要点:

```yaml
run:
  runner: python_shared_env
  entry: src/<entry_relative>.py
  mode: gui | cli | background
  env_id: <env_id>
  show_terminal: true  # CLI操作が必要なアプリだけ任意指定

runtime:
  distribution_mode: shared_env
  required_runtime: python-shared-env:<env_id>
  requirements_lock: requirements.lock
```

`run.runner: exe`、PyInstaller `frozen-folder`、`python_app_env`、既存 exe 登録は、既存 app 互換または管理者向け legacy 経路です。通常新規登録の標準ではありません。

## 通常新規登録フロー

管理者画面の App Studio で Python entry を選び、必要に応じて App ID、表示名、説明、アイコン prompt、起動時のターミナル表示を調整します。アイコンは通常フローでは AI 画像候補を作りますが、管理者が PNG を指定した場合は AI 画像生成の代わりにその PNG を採用します。`.exe` は通常新規登録の入力として扱いません。

処理の流れ:

1. Python entry と source root を確認する。
2. source inventory、secret scan、依存解析、metadata 提案、icon 提案を実行する。GUI では事前確認の成功後に AI 提案を自動実行する。
3. `requirements.lock` を生成または更新する。
4. lock 内容から共有 runtime env を作成または再利用する。
5. `apps/<app_id>/src/` に source を登録する。
6. `apps/<app_id>/app.yaml` を生成する。
7. `release/app_manifest.json` に `enabled=false` で仮登録する。
8. runtime check、execution check、App Pack 作成結果を表示する。
9. 管理者が結果を確認し、承認可能な場合だけ `Approve` で `enabled=true` にする。

通常登録では、利用者 PC に app ごとの private venv や PyInstaller output を要求しません。依存は `runtime/envs/<env_id>/` に共有 runtime として置き、同じ lock set の app で再利用します。

## Source Root と除外

App Studio は entry file の親フォルダ、または GUI / CLI で指定された source root を app source として扱います。entry が source root 配下にない場合や、drive root のように広すぎる範囲は拒否します。

source root 直下の `.toolhubignore` は、最小限の gitignore 風 glob として読み込みます。次のような生成物、認証 state、別プロジェクト領域は通常登録に含めません。

- `.git`, `.venv`, `venv`, `node_modules`
- `build`, `dist`, `release`, `runtime`, `target`
- `ToolHub_AppStudio_Output`, `logs`, `screenshots`, `tmp`, `temp`
- `.auth`, cookie, storage state, token, password, API key, credential 類

`.auth/` や storage state を `.toolhubignore` で除外した場合は、App 側で初回ログイン、手動ログイン、再認証、またはユーザー管理領域への runtime state 保存を用意してください。

## AI 提案とアイコン

AI 提案は自動作成しますが、自動確定はしません。GUI の採用操作で、表示名、説明、補助分類、対象カテゴリ、特徴タグ、検索語、icon prompt などの編集値へ反映します。

カテゴリは自由生成ではなく、ToolHub の taxonomy へ正規化します。

- 利用者向けカテゴリは対象カテゴリの先頭を使います。COMPASS上で3DX文書を取得するアプリは `COMPASS`, `3DX` の順にし、COMPASSの棚にまとまるようにします。
- 補助分類は `文書・PDF`, `Excel・表計算`, `帳票・会計`, `Web・ブラウザ`, `開発・管理`, `その他` などから1つを選びます。対象カテゴリがない場合のフォールバックです。
- 対象カテゴリは自動化・連携の対象です。自動化アプリでは `XCgate`, `COMPASS`, `3DX` などの対象を必ず含めます。
- 特徴タグは `一括処理`, `ダウンロード`, `登録`, `置換`, `ID取得`, `ブラウザ操作` などの細かい特徴に使います。
- 既存候補にない新しい対象や用途だけを新カテゴリ候補として扱い、即時公開せず管理者レビュー対象にします。

source package に手動確認レベルの secret scan 警告がある場合でも、実際に AI へ送る metadata prompt / icon prompt payload を個別に再スキャンし、安全な payload だけを送信します。payload 自体に token、password、API key などの可能性がある場合は AI 送信を止めます。

OpenAI API キーは管理者画面の AI/API キー管理で扱います。キー本文は設定 JSON、`app.yaml`、App Pack、ログへ保存しません。Windows では Credential Manager を使います。

アイコンは PNG を標準成果物にします。

- 採用済み PNG がある場合は `icon.png` に反映する。
- 管理者が PNG を指定した場合は `uploaded_png` として扱い、AI 画像生成をスキップして `icon.png` に反映する。
- AI 画像 API が失敗した場合でも local fallback candidate は作らない。
- 採用済み PNG がない場合は ToolHub 共通 default icon を `icon.png` に使う。
- 古い saved proposal の fallback candidate は読み取り互換だけ維持する。

CLI で通常登録する場合は、`--icon-png <path-to-icon.png>` または `scripts/import_app.ps1 -IconPng <path-to-icon.png>` で指定 PNG を採用できます。ターミナル操作が必要なアプリは `--show-terminal` または `scripts/import_app.ps1 -ShowTerminal` を指定します。`--icon-png` と `--icon-override` は同時に指定しません。

画像生成テストで `organization_verification_required` が出る場合は、OpenAI Platform 側の組織認証が必要です。認証が完了するまでは、メタデータ編集や手動入力は継続できますが、AI 画像候補は増えません。

## 結果と承認

Apply 後は仮登録です。`release/app_manifest.json` の対象 entry は `enabled=false` から始まります。

主な出力:

- `import_plan.json`
- `requirements.lock`
- `shared_runtime_report.md`
- `runtime_check_result.json`
- `execution_test_result.json`
- `metadata_ai_report.md`
- `icon_work/candidate_manifest.json`
- `apps/<app_id>/app.yaml`
- App Pack zip と `release/app_manifest.json` entry

承認の基本:

- `fail`: 承認不可。原因を修正して再実行する。
- `approval_blocking_warning`: 慎重モードでは承認不可。
- `non_blocking_warning` / `info`: 管理者確認後に承認可能。

Playwright、ブラウザログイン、社内サイト操作、ファイル選択、メール送信、アップロードなどは自動検証済みとは扱いません。manual check として残し、人間確認後に承認します。

## 既存アプリ更新

既存アプリ更新 GUI は MVP です。登録済み app_id の選択、version bump、更新 entry 指定、Suggest update、Apply update、Approve update までを対象にします。

詳細は [15_app_studio_update_gui.md](15_app_studio_update_gui.md) を参照してください。

## Legacy / 互換経路

次の方式は削除しませんが、通常新規登録の標準ではありません。

- `run.runner: exe`
- PyInstaller `frozen-folder`
- `python_app_env`
- 既存 exe 登録
- Python 直接実行 manifest

これらは既存 app、古い manifest、または管理者が明示的に扱う互換経路として残します。現在の通常登録へ戻す場合は、Python source を entry にして `shared-env` として再登録してください。

Legacy frozen-folder / exe の運用上の注意は [16_app_studio_exe_build_operations.md](16_app_studio_exe_build_operations.md) を参照してください。

## 関連文書

- [09_app_pack_spec.md](09_app_pack_spec.md): App Pack と `release/app_manifest.json` の仕様。
- [10_runtime_packaging.md](10_runtime_packaging.md): runtime layout と shared env の扱い。
- [14_admin_and_ai_settings.md](14_admin_and_ai_settings.md): 管理者画面、AI/API キー、画像生成テスト。
- [17_app_management_model.md](17_app_management_model.md): app 管理と削除モデル。
- [29_app_registration_zero_stress_validation_protocol.md](29_app_registration_zero_stress_validation_protocol.md): App Studio 登録の検証 protocol。
