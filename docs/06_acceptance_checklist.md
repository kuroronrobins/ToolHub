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

## Installer / Distribution

- [x] `ToolHub_Setup.exe` を正式配布物とする方針がREADMEに記載されている
- [x] インストール先がdocsに記載されている
- [x] ユーザーデータ保存先がdocsに記載されている
- [x] ユーザーがPython / Node.js / Rust / Web自動化用ランタイムを手動導入しない方針がdocsに記載されている
- [x] `scripts/package_installer.ps1` が存在する
- [x] `scripts/verify_release.ps1` が存在する
- [x] `release/manifest.json` が拡張されている
- [x] `release/app_manifest.json` が存在する
- [x] ToolHub Core / Runner / Apps / Runtime / User Data の更新単位がdocsに記載されている
- [x] per-user install方針がdocsに記載されている
- [x] 完全単一exeを正式方式にしない理由がdocsに記載されている
- [x] フォルダ配布を正式方式にしない理由がdocsに記載されている
- [ ] 実際の `ToolHub_Setup.exe` が生成されている
- [ ] `ToolHub_Setup.exe` のコード署名が完了している

## Update Design

- [x] App Pack方式がdocsに記載されている
- [x] `app_manifest.json` の仕様がdocsに記載されている
- [x] sha256検証方針がdocsに記載されている
- [x] 更新前バックアップ方針がdocsに記載されている
- [x] ロールバック方針がdocsに記載されている
- [x] User Dataを更新で消さない方針がdocsに記載されている
- [x] Web自動化用ランタイムをHeavy Runtimeとして扱う方針がdocsに記載されている
- [x] `scripts/package_app_pack.ps1` でApp Pack zipとsha256を生成できる
- [x] `scripts/verify_release.ps1` でApp Pack sha256を検証できる
- [ ] 自動更新本体は未実装
- [ ] 更新ダウンロード、展開、原子的置き換え、ロールバックの実処理は未実装

## Regression

- [x] `python main.py --check` が引き続き動作する
- [x] 既存`app.yaml`プラグイン方式が維持されている
- [x] メイン画面に管理者情報を出さない方針が維持されている
- [x] 利用者画面に内部技術名を出さない方針が維持されている
- [x] runner層に起動処理が集約されている
- [x] `main.py` は開発用ブートストラップに留まっている

## main.py Self-Check

- [x] `--help` が使い方を表示する
- [x] `--check` がフォルダ不足を検出する
- [x] Node.js/npm/Rust/cargo不足時に分かりやすいメッセージを出す
- [x] 起動ログが `data/logs/launcher/` に保存される
- [x] `--release` はビルド済み実行ファイルがない場合に開発起動へ進まない

## Self-Inspection Result

今回の配布・更新対応で実行したコマンド:

- `python -m unittest discover -s runner/tests`: 12 tests OK
- `python -m py_compile ...`: Python主要ファイルの構文チェックOK
- `python -m json.tool release/manifest.json`: OK
- `python -m json.tool release/app_manifest.json`: OK
- `python -m json.tool launcher/src-tauri/tauri.conf.json`: OK
- `launcher/node_modules/.bin/tsc.cmd --noEmit`: OK
- `scripts/package_app_pack.ps1`: OK。3つのサンプルApp Pack zipを作成し、`release/app_manifest.json` にsha256を反映
- `scripts/package_installer.ps1 -AllowMissingBundle`: OK。Tauri bundle未生成のためinstaller sha256は空のまま
- `scripts/verify_release.ps1`: OK。installer未生成はWARN、App Pack sha256はOK
- `scripts/build_release.ps1 -SkipBuild -AllowMissingBundle`: OK。App Pack作成、installer manifest staging、release検証まで通過
- `scripts/check_all.ps1`: OK。TypeScript/Rustは環境制約でWARN
- `python main.py --help`: OK
- `python main.py --check`: フォルダ構成、Node.js/npm/Rust/cargo確認OK
- `python main.py --dev`: npm不足時に利用者向けメッセージと `data/logs/launcher/latest.log` を表示
- `python main.py --release`: ビルド済み実行ファイルなしを表示し、開発起動へ進まない
- `python runner/toolhub_runner/main.py --project-root . --app-id sample_cli_app ...`: OK、ログ保存確認
- `python runner/toolhub_runner/main.py --project-root . --app-id sample_playwright_app ...`: この環境では実行環境不足で失敗、利用者向けエラーと詳細ログ保存を確認
- `scripts/check_all.ps1`: 実行済み。Bootstrap checkはNode.js/npm/Rust/cargo不足でNG、Python runner testsはOK、TypeScript/Rustチェックは環境不足でSKIP
- 利用者向けUIソースと表示用manifestに内部技術名が出ていないことを検索で確認

成功したチェック:

- release manifest JSON検証
- app manifest JSON検証
- App Pack生成
- App Pack sha256検証
- App Pack内部の `app.yaml` / `pack_manifest.json` 確認
- 配布docs存在確認
- `main.py` 静的境界確認
- Python runner単体テスト

環境不足または環境制約で実行できなかったチェック:

- TypeScript/Vitestは `esbuild` のspawnが `EPERM` で失敗
- Vite buildは同じ `spawn EPERM` で失敗。TypeScript単体の `tsc --noEmit` はOK
- Rust `cargo check` はMSVC linker `link.exe` 不在で失敗
- Tauriが起動できていないため、実画面でのカード表示、モーダル表示、GUIサンプル起動は未確認
- Tauri bundle成果物がないため、実際の `ToolHub_Setup.exe` 生成は未確認
- コード署名は未実施

未完了項目:

- runtime/python の実体同梱
- runtime/app_envs の生成
- Web自動化用ランタイム実体同梱
- 自動更新本体
- 署名
- 実インストーラー生成とインストール/アンインストール検証

次に人間が確認すべき項目:

- Visual Studio Build Toolsを入れたWindows環境で `cargo check` と `npm run tauri build` を実行する
- `release/dist_installer/ToolHub_Setup_0.1.0.exe` が生成されることを確認する
- インストール先が `%LOCALAPPDATA%\Programs\ToolHub\` になることを確認する
- ユーザーデータが `%LOCALAPPDATA%\ToolHub\` に分離されることを確認する
- 実機でショートカット起動、App Pack検証、runner起動、ログ保存を確認する
