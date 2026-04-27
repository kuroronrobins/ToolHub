# App Studio exe化運用方針

ToolHub App Studio では、すべての Python アプリを無条件にワンクリック exe 化するのではなく、登録方式を分けて安全に運用する。

## 標準の登録方式

- 軽量 Python アプリ: `app-env`
- 複数モジュール、GUI、Playwright、多数ファイルを含む Python アプリ: `frozen-folder`
- 既存 exe アプリ: `existing-exe`

`frozen-folder` は PyInstaller の `--onedir` 相当を標準とする。`--onefile` は標準採用しない。

## Build Profile

`frozen-folder` ではアプリごとに Build Profile を持つ。

主な項目:

- `paths`: import 解決用の追加パス
- `hidden_imports`: PyInstaller が自動検出できない import
- `add_data`: exe フォルダへ同梱する設定、flow、assets など
- `add_binaries`: DLL や外部バイナリ
- `collect_all`: Playwright など package 全体の収集が必要なもの
- `runtime_cwd`: 起動時の作業ディレクトリ方針
- `environment`: 実行時に必要な環境変数名と値
- `manual_checks`: GUI 操作、ログイン、ファイル選択など人間確認が必要な項目

App Studio は自動検出した Build Profile を `build_profile.json` に出力し、GUI から手動追加した内容を CLI へ渡せる。保存済み Profile は次回登録時に再利用される。

## 管理されたビルド環境

exe 化は通常のグローバル Python に直接依存させない。`frozen-folder` では次の順に管理対象の Python を使う。

1. `runtime/app_envs/<app_id>/Scripts/python.exe`
2. `runtime/python/python.exe`

管理対象の実行環境が無い場合、App Studio は `app_env` を作成し、PyInstaller をその環境に導入してから frozen-folder build を行う。`--skip-app-env-build` を指定した場合は自動作成せず、管理対象 Python が無ければ fail とする。

## 成果物ゲート

`frozen-folder` の Apply 後は、少なくとも次を機械確認する。

- `final_app/bin/<app_id>/<app_id>.exe` または `apps/<app_id>/bin/<app_id>/<app_id>.exe` が存在する
- `app.yaml` が exe 起動を指す
- Build Profile の `add_data` に指定されたファイルが exe フォルダへ入っている
- `requirements.lock`、runtime、Playwright/browser 依存、secret scan の状態が記録されている
- `execution_test_result.json` が pass/warn/fail を明確に示す

確認結果は次のファイルに出力する。

- `build_profile.json`
- `build_profile_report.md`
- `exe_readiness.json`
- `exe_readiness_report.md`
- `execution_test_result.json`

## 承認ゲート

- `pass`: 自動確認を通過。承認可能。
- `warn`: 開発機では進められるが、正式配布前に人間確認が必要。
- `fail`: 承認不可。原因を修正して再実行する。

`AllowWarnings` は軽微な警告を人間が確認したうえで承認する運用向け。`StrictApproval` は警告を含めて問題ゼロの場合だけ承認する運用向け。

## Playwright / 手動操作系アプリ

XCgate のような Playwright や手動操作を含むアプリでは、次を別ゲートとして扱う。

- exe 生成成功
- exe の短時間起動確認
- browser / driver / flow / config / assets の同梱確認
- ログイン、ファイル選択、業務操作などの手動確認

exe 生成成功だけを業務利用可能とは扱わない。`manual_checks` に必要な確認項目を残し、承認時に人間が確認する。

## 失敗時の扱い

PyInstaller 不足、hidden import 不足、data file 不足、runtime/browser 不足、high secret 検出は成功扱いにしない。App Studio は report と GUI に原因と次の操作を表示し、必要に応じて fallback または fail/warn として扱う。

