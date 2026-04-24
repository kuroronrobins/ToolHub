# Acceptance Checklist

このチェックリストは初回実装の自己検収結果を記録する場所です。

## Functional

- [x] プロジェクト直下で `python main.py` を実行するとToolHub起動を試行できる
- [x] `python main.py --dev` で開発モード起動を試行できる
- [x] `python main.py --release` でビルド済み実行ファイルのみ起動を試行できる
- [x] `python main.py --check` で環境確認ができる
- [ ] ランチャーが起動できる
- [x] `apps/` 配下の `app.yaml` を自動検出できる構造がある
- [ ] アプリカードが表示される
- [x] カードにアイコン、名称、短い説明、カテゴリを表示する実装がある
- [x] メイン画面に管理者向け情報が表示されない実装である
- [x] カテゴリで絞り込める実装がある
- [x] 検索で絞り込める実装がある
- [x] 説明を見るを押すと詳細が表示される実装がある
- [ ] GUIサンプルアプリを起動できる
- [x] CLIサンプルアプリを起動できる
- [x] Web自動化サンプルアプリを他アプリと同様のrunner経由で起動できる
- [x] エラー時に利用者向けメッセージが出る
- [x] 詳細ログが保存される

## UI

- [x] 利用者画面に内部技術名が出ていない実装である
- [x] メイン画面がシンプルである実装である
- [x] アイコン、名称、説明、カテゴリだけでアプリ概要が分かる実装である
- [x] 空状態がある
- [x] 検索結果なし状態がある
- [x] 起動中状態がある
- [x] エラー状態がある

## Maintainability

- [x] 新規アプリは `apps/` にフォルダ追加するだけで登録できる
- [x] `app.yaml` 仕様がdocsに記載されている
- [x] サンプルアプリをコピーして新規アプリを作れる
- [x] ランチャー本体に個別アプリ固有処理がない
- [x] `main.py` に個別アプリ固有処理がない
- [x] `main.py` にUIロジックがない
- [x] Web自動化用の特殊処理が各アプリに散らばっていない
- [x] runner層に起動処理が集約されている

## Distribution

- [x] `main.py` がある
- [x] `scripts/dev_start.ps1` がある
- [x] `scripts/check_all.ps1` がある
- [x] `scripts/build_release.ps1` がある
- [x] `scripts/create_app_template.ps1` がある
- [x] READMEだけで開発開始の流れが分かる
- [x] `docs/` に設計資料がある
- [x] `release/manifest.json` の雛形がある

## main.py Self-Check

- [x] `--help` が使い方を表示する
- [x] `--check` がフォルダ不足を検出する
- [x] Node.js/npm/Rust/cargo不足時に分かりやすいメッセージを出す
- [x] 起動ログが `data/logs/launcher/` に保存される
- [x] `--release` はビルド済み実行ファイルがない場合に開発起動へ進まない

## Self-Inspection Result

実行済みチェック:

- `python -m unittest discover -s runner/tests`: 12 tests OK
- `python -m py_compile ...`: Python主要ファイルの構文チェックOK
- `python main.py --help`: OK
- `python main.py --check`: フォルダ構成OK、Node.js/npm/Rust/cargo不足をNG表示
- `python main.py --dev`: npm不足時に利用者向けメッセージと `data/logs/launcher/latest.log` を表示
- `python main.py --release`: ビルド済み実行ファイルなしを表示し、開発起動へ進まない
- `python runner/toolhub_runner/main.py --project-root . --app-id sample_cli_app ...`: OK、ログ保存確認
- `python runner/toolhub_runner/main.py --project-root . --app-id sample_playwright_app ...`: この環境では実行環境不足で失敗、利用者向けエラーと詳細ログ保存を確認
- `scripts/check_all.ps1`: 実行済み。Bootstrap checkはNode.js/npm/Rust/cargo不足でNG、Python runner testsはOK、TypeScript/Rustチェックは環境不足でSKIP
- 利用者向けUIソースと表示用manifestに内部技術名が出ていないことを検索で確認

未完了または環境依存:

- Node.js/npmがないため、React/Vitest/TypeScript buildは未実行
- Rust/cargoがないため、Tauri/Rustの `cargo check` とTauri起動は未実行
- Tauriが起動できていないため、実画面でのカード表示、モーダル表示、GUIサンプル起動は未確認
- リリースビルドは未実行

メモ:

- 初回テストで作成された `data/test_tmp` は環境ACLの都合で削除できない一時フォルダが残ったため、`.ignore` と `.gitignore` で検索・管理対象から除外しています。
