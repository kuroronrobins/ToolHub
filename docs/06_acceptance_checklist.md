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

今回の配布・runtime・検証強化で実行したコマンド:

- `python main.py --help`: OK
- `python main.py --check`: OK
- `python -m unittest discover -s runner/tests`: 12 tests OK
- `python -m py_compile main.py`: OK
- `python -m json.tool release/manifest.json`: OK
- `python -m json.tool release/app_manifest.json`: OK
- `scripts/package_app_pack.ps1`: OK。3つのサンプルApp Pack zipを生成し、`release/app_manifest.json` にsha256を反映
- `scripts/prepare_runtime.ps1 -AllowMissingRuntime`: OK。runtime雛形とapp_env skeletonを作成。Python runtime実体とWeb自動化用ランタイム実体はWARN
- `scripts/package_installer.ps1 -AllowMissingBundle`: OK。`release/staging/installer_payload/` を作成。Tauri bundle未生成のためinstaller sha256/sizeは空
- `scripts/verify_release.ps1`: OK。App Pack sha256、zip内部の `app.yaml` / `pack_manifest.json`、staging manifestを確認
- `scripts/build_release.ps1 -SkipBuild -AllowMissingBundle`: OK。App Pack、runtime雛形、staging、release検証まで通過
- `scripts/check_all.ps1`: OK。環境不足とfrontend build制約はWARNとして分類
- `npm run typecheck` 相当: OK。`scripts/frontend_check.ps1` 経由で `tsc --noEmit` が通過
- `cargo fmt --check`: 既存Rustファイルのformat差分がありNG。今回追加の `setup.rs` は指摘箇所を修正済み
- `git diff --check`: OK。CRLF変換警告のみ

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
- `main.py` 静的境界確認
- Python runner単体テスト
- TypeScript型チェック

環境不足または環境制約で実行できなかったチェック:

- `npm test`: `esbuild` の `spawn EPERM` によりWARN。対策は `docs/12_troubleshooting.md` に記載
- `npm run build`: 同じ `spawn EPERM` によりWARN。`tsc --noEmit` はOK
- `cargo check`: MSVC linker `link.exe` 不在で失敗。Visual Studio Build Tools / C++ workload / Windows SDKが必要
- `npm run tauri build`: frontend buildの `spawn EPERM` とMSVC linker不足があるため未完了
- 実際の `ToolHub_Setup.exe` 生成: Tauri bundle成果物がないため未確認
- 実インストール / アンインストール検証: installer未生成のため未実施
- コード署名: 未実装

未完了項目:

- Python runtime実体同梱
- app_env実体生成
- Web自動化用ランタイム実体同梱
- 自動更新本体
- コード署名
- 実インストーラー生成
- 実インストール / アンインストール検証

次に人間が確認すべき項目:

- Visual Studio Build Toolsを導入したWindows環境で `cargo check` を実行する
- OneDriveやセキュリティソフトの影響がないローカルパスで `npm test` / `npm run build` を再実行する
- `npm run tauri build` で `release/dist_installer/ToolHub_Setup_0.1.0.exe` が生成されることを確認する
- インストール先が `%LOCALAPPDATA%\Programs\ToolHub\` になることを確認する
- 初回起動時にユーザーデータが `%LOCALAPPDATA%\ToolHub\` に作成され、既存設定を上書きしないことを実機で確認する
- runtime実体を配置し、`verify_release.ps1 -RequireRuntime -Strict` を通す
