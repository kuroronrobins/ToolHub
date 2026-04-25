# Acceptance Checklist

このチェックリストは初回実装の自己検収結果を記録する場所です。

## Real-Machine Verification

新しいPCで確認済み:

- [x] `python main.py --dev` でToolHubランチャーが起動する
- [x] ランチャーにアプリカードが表示される
- [x] GUIサンプルアプリがウィンドウを開く
- [x] CLIサンプルアプリがrunner経由で `ok: true` を返し、ログを保存する
- [x] Web操作サンプルアプリがrunner経由で `ok: true` を返し、ログを保存する
- [x] Web操作サンプルは `headless=True` のため、ブラウザウィンドウが表示されない挙動を正常として確認済み

## Functional

- [x] プロジェクト直下で `python main.py` を実行するとToolHub起動を試行できる
- [x] `python main.py --dev` で開発モード起動を試行できる
- [x] `python main.py --release` でビルド済み実行ファイルのみ起動を試行できる
- [x] `python main.py --check` で環境確認ができる
- [x] ランチャーが起動できる
- [x] `apps/` 配下の `app.yaml` を自動検出できる構造がある
- [x] アプリカードが表示される
- [x] カードにアイコン、名称、短い説明、カテゴリを表示する実装がある
- [x] メイン画面に管理者向け情報が表示されない実装である
- [x] カテゴリで絞り込める実装がある
- [x] 検索で絞り込める実装がある
- [x] 説明を見るを押すと詳細が表示される実装がある
- [x] GUIサンプルアプリを起動できる
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

## Release Build Flow

- [x] `build_release.ps1` が正式なリリース入口として整理されている
- [x] `build_release.ps1 -SkipBuild -AllowMissingBundle` が通る
- [x] `package_app_pack.ps1` がApp Packを生成できる
- [x] `prepare_runtime.ps1` がruntime雛形を作成できる
- [x] `package_installer.ps1` がstagingを作成できる
- [x] `package_installer.ps1` がbundle成果物を `release/dist_installer/` へ収集できる構造になっている
- [x] `verify_release.ps1` がmanifest / app pack / staging / runtimeを検証できる
- [x] `release/manifest.json` がinstaller file/type/sha256/sizeを保持する
- [x] `release/app_manifest.json` がApp Pack package/sha256/runtime要求を保持する
- [x] `npm run tauri build` でTauri標準のNSIS/MSI成果物を生成できた
- [ ] 実際のTauri bundle成果物から `ToolHub_Setup_0.1.0.exe` を生成できた

## Environment

- [x] `check_all.ps1` がnode/npm/cargo/rustc/link.exe/cl.exeを確認する
- [x] Visual Studio Build Tools不足時の案内がある
- [x] `esbuild spawn EPERM` のトラブルシューティングがdocsにある
- [x] `package-lock.json` / `Cargo.lock` の管理方針がdocsにある
- [x] `launcher/package-lock.json` が存在する
- [x] `launcher/src-tauri/Cargo.lock` が存在する
- [ ] この環境で `link.exe` / `cl.exe` がPATH上にある

## Runtime

- [x] `runtime/README.md` がある
- [x] `runtime/app_envs/` が作成される
- [x] `runtime/web_automation_runtime/` が作成される
- [x] runtimeをGitに含めない方針がdocsと `.gitignore` にある
- [x] runtime同梱が未完了の場合、未完了としてdocsに明記されている
- [ ] `runtime/python/python.exe` の実体が同梱されている
- [ ] `runtime/app_envs/<app_id>/` の実体が生成されている
- [ ] Web自動化用ランタイム実体が同梱されている

## Self-Inspection Result

今回の安定化作業で実行したコマンド:

- `python main.py --check`: OK
- `python -m unittest discover -s runner/tests`: 14 tests OK
- `python runner/toolhub_runner/main.py --project-root . --app-id sample_cli_app`: OK。runner側の初期statusと、アプリ側の実処理eventのみ出力
- `python runner/toolhub_runner/main.py --project-root . --app-id sample_playwright_app`: sandbox内ではWinError 5、sandbox外再実行でOK。runner側の初期statusと、アプリ側の実処理eventのみ出力
- `scripts/check_all.ps1`: OK。`icon.ico`、`bundle.icon`、`bundle.resources` の存在確認を含む
- `npm run tauri build`: sandbox内ではVite/esbuildの `spawn EPERM`、sandbox外再実行でOK

成功したチェック:

- release manifest JSON検証
- app manifest JSON検証
- lock file存在確認
- App Pack生成
- App Pack sha256検証
- App Pack内部の `app.yaml` / `pack_manifest.json` 確認
- runtime雛形作成
- installer staging作成
- staging manifest作成
- Tauri bundle targetがNSIS/MSIを含むことの確認
- Tauri Windows icon `launcher/src-tauri/icons/icon.ico` の存在とICO header確認
- Tauri `bundle.icon` と `bundle.resources` の主要パス存在確認
- Tauri標準NSIS/MSI bundle生成
- `main.py` 静的境界確認
- Python runner単体テスト
- TypeScript型チェック
- CLI / Web操作サンプルの重複初期status削除確認

環境不足または環境制約で実行できなかったチェック:

- `scripts/check_all.ps1` 内のVitest/Vite build: sandbox内では `esbuild` の `spawn EPERM` によりWARN。sandbox外の `npm run tauri build` ではVite build通過
- 実際の `ToolHub_Setup.exe` 生成: Tauri標準bundleは生成済みだが、正式配布名での `release/dist_installer/` 収集は未確認
- 実インストール / アンインストール検証: 正式配布installer未生成のため未実施
- コード署名: 未実装

未完了項目:

- Python runtime実体同梱
- app_env実体生成
- Web自動化用ランタイム実体同梱
- 自動更新本体
- コード署名
- 正式配布名の実インストーラー生成
- 実インストール / アンインストール検証

次に人間が確認すべき項目:

- OneDriveやセキュリティソフトの影響がないローカルパスで `npm test` / `npm run build` を再実行する
- release packaging flowで `release/dist_installer/ToolHub_Setup_0.1.0.exe` が生成されることを確認する
- インストール先が `%LOCALAPPDATA%\Programs\ToolHub\` になることを確認する
- 初回起動時にユーザーデータが `%LOCALAPPDATA%\ToolHub\` に作成され、既存設定を上書きしないことを実機で確認する
- runtime実体を配置し、`verify_release.ps1 -RequireRuntime -Strict` を通す
