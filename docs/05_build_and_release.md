# Build and Release

## App Studio 由来アプリの配布検証

App Studio の通常新規登録で追加された Python アプリは、通常ユーザー向け配布として frozen-folder / exe で登録します。`requirements.lock` 生成、PyInstaller `--onedir` build、frozen-folder 配布物検証は常に実行され、`.py` を `run.entry` とする登録は通常フローでは行いません。

App Pack には `apps/<app_id>/bin/<app_id>/<app_id>.exe` と、その frozen-folder に必要な同梱ファイルだけを含めます。`build_env`、`.auth/`、logs、screenshots、tmp/temp、仮想環境、build/dist、node_modules、認証状態、個人データらしいファイルは含めません。配布物サイズと add-data 合計サイズは App Studio の検証レポートで確認します。大容量ファイルや Playwright を含む場合は警告または manual check として扱います。

既存 exe 登録は通常新規登録フローでは扱いません。環境依存 exe や不完全な exe を誤って App Pack に含めるリスクを避けるため、通常フローは ToolHub が Python ソースから生成した exe のみを登録対象にします。

ToolHubの正式配布方式はインストーラー型配布です。

開発者はリポジトリ直下で `python main.py` を使います。利用者には `ToolHub_Setup.exe` を配布し、インストール後はデスクトップショートカットまたはスタートメニューの `ToolHub` から起動してもらいます。

## Distribution Policy

インストーラー型を正式方針にする理由:

- 利用者にPython、Node.js、Rust、Web自動化用ランタイムの導入を要求しない。
- ToolHub本体、runner、内蔵アプリ、runtimeを固定配置できる。
- 更新時に置き換える対象と、消してはいけないユーザーデータを分離できる。
- ショートカット、アンインストール、将来の署名や社内配布ポリシーに対応しやすい。

完全単一exeを正式方式にしない理由:

- 起動のたびに大量ファイルを一時展開すると起動速度が落ちる。
- Python環境やWeb自動化用ランタイムのような重い依存を毎回展開する設計になりやすい。
- 差分更新、sha256検証、ロールバックの単位が粗くなる。

フォルダ配布を正式方式にしない理由:

- 利用者が内部フォルダを移動・削除して壊すリスクが高い。
- ショートカット、アンインストール、更新権限、配置先の標準化が弱い。
- 社内配布時に配布物の正当性を保証しにくい。

## Install Locations

per-user installを第一候補にします。

```text
%LOCALAPPDATA%\Programs\ToolHub\
```

ユーザーデータ先:

```text
%LOCALAPPDATA%\ToolHub\
```

インストール先にはToolHub本体と更新対象を置きます。ユーザーデータ先には設定、ログ、browser profiles、search_index、app_state、update_cache、backupsを置きます。

更新時に消してはいけないもの:

- ユーザー設定
- ログ
- browser_profiles
- search_index
- app_state
- 必要なupdate_cache
- ユーザーが追加した外部アプリ情報

Tauri/Rust側の起動時初期化で、ユーザーデータ先の基本フォルダを作成します。`config.default/launcher.yaml` が見つかり、かつユーザー設定が未作成の場合だけ初期設定をコピーします。既存設定は上書きしません。

現行実装では、Tauriランチャー経由のRust backendとPython runnerは `%LOCALAPPDATA%\ToolHub\` をユーザーデータrootとして使います。runnerを `python runner/toolhub_runner/main.py --project-root . --app-id ...` で直接実行する場合は、開発・テスト用フォールバックとしてリポジトリ直下の `data/` を使います。

## Windows Build Environment

実インストーラー生成には以下が必要です。

- Python 3.10以降
- Node.js LTS
- npm
- Rust / cargo / rustc
- Visual Studio Build Tools
- Desktop development with C++
- MSVC v143以降
- Windows SDK
- Tauri CLI（通常は `launcher/package.json` のnpm依存から `npm run tauri` で使う。global installは必須ではない）

確認:

```powershell
.\scripts\check_all.ps1
```

厳格に扱う場合:

```powershell
.\scripts\check_all.ps1 -Strict
```

`link.exe` や `cl.exe` が見つからない場合、Tauri/RustのWindows buildは失敗します。Visual Studio Build Toolsを導入し、C++ workload、MSVC、Windows SDKを追加してください。通常のPowerShellではPATHが通らない場合があるため、Developer PowerShell for VSでの実行も確認します。

## Lock Files

ToolHubは配布アプリケーションなので、lock fileを管理対象にします。

- `launcher/package-lock.json`
- `launcher/src-tauri/Cargo.lock`

`package-lock.json` は `npm ci` による再現可能なfrontend依存復元に使います。`Cargo.lock` はTauri/Rust側の依存解決を固定するために使います。Rust library crateではなく配布アプリケーションなので、`Cargo.lock` もコミット対象です。

## Release Build Flow

正式な入口:

```powershell
.\scripts\build_release.ps1
```

内部の流れ:

1. build環境の事前確認
2. App Pack生成
3. runtime準備
4. `npm ci` または `npm install`
5. `npm run tauri build`
6. installer成果物収集とstaging作成
7. release検証

Tauri bundleをまだ生成できない環境でも、App Pack、runtime雛形、staging、manifest検証を進める場合:

```powershell
.\scripts\build_release.ps1 -SkipBuild -AllowMissingBundle
```

runtime実体まで必須にする場合:

```powershell
.\scripts\build_release.ps1 -RequireRuntime
```

## Individual Commands

App Pack作成:

```powershell
.\scripts\package_app_pack.ps1
```

runtime雛形準備:

```powershell
.\scripts\prepare_runtime.ps1 -AllowMissingRuntime
```

ローカルruntime archiveを展開する場合:

```powershell
.\scripts\prepare_runtime.ps1 -SourceArchive .\vendor\runtime\python.zip -SourceSha256 <sha256>
```

インストーラー成果物収集とstaging:

```powershell
.\scripts\package_installer.ps1
```

Tauri bundleがまだない状態でstagingだけ作る場合:

```powershell
.\scripts\package_installer.ps1 -AllowMissingBundle
```

release検証:

```powershell
.\scripts\verify_release.ps1
```

厳格検証:

```powershell
.\scripts\verify_release.ps1 -RequireInstaller -RequireAppPacks -RequireRuntime -Strict
```

## Installer Artifact Rules

Tauri bundleでNSISまたはMSIを生成します。`scripts/package_installer.ps1` は `launcher/src-tauri/target/release/bundle/` から成果物を収集し、`release/dist_installer/` に配置します。

現状では `scripts/build_release.ps1 -SkipInstall` により、Tauri標準NSIS/MSI bundle生成、正式配布名 `release/dist_installer/ToolHub_Setup_0.1.0.exe` への収集、installer `sha256` / `size` の確定まで確認済みです。実インストール検証、コード署名、runtime実体同梱は未完了として扱います。

優先順位:

1. `.exe` がある場合はNSIS installerとして `ToolHub_Setup_<version>.exe` にする。
2. `.msi` しかない場合は `ToolHub_Setup_<version>.msi` にする。
3. 両方ない場合、`-AllowMissingBundle` 指定時だけstaging作成とmanifest検証を続ける。

`release/manifest.json` の `toolhub.installer.file`、`type`、`sha256`、`size` は `package_installer.ps1` が更新します。
Release JSON と App Pack metadata JSON は PowerShell 5.1 / 7 の差異を避けるため、`scripts/utf8_no_bom.ps1` の helper で UTF-8 no BOM として書き出します。`scripts/check_all.ps1` は `release/manifest.json` と `release/app_manifest.json` の BOM 有無を直接検査し、helper test は App Pack 内 `pack_manifest.json` と同じ JSON 書き込み経路が BOM を付けないことを検査します。

## Staging and Tauri Resources

Tauri `bundle.resources` は、Tauri bundleへ同梱する最低限のruntime resourceを指定します。`release/staging/installer_payload/` は、インストーラーに入れるべき固定配置ファイルを検証しやすくするための作業領域です。

TauriのWindows buildには `launcher/src-tauri/icons/icon.ico` が必要です。`tauri.conf.json` の `bundle.icon` には `icons/icon.ico` と `icons/icon.png` を指定します。必要な場合は `python make_icon.py` で最小アイコン資産を再生成できます。

stagingに含める対象:

- `runner/`
- `apps/`
- `runtime/`
- `config.default/`
- `release/manifest.json`
- `release/app_manifest.json`
- `updater/`
- `installer/`
- `README.md`

stagingから除外する対象:

- `.git`
- `node_modules`
- `target/debug`
- 実行ログ
- browser_profiles
- update_cache
- 一時ファイル
- `__pycache__`
- `.pytest_cache`

巨大runtimeを完全単一exeに詰め込み、毎回一時展開する方式は正式方式にしません。インストール先へ固定配置して起動速度と更新単位を保ちます。

## Runtime Bundling

runtime方針は [docs/10_runtime_packaging.md](10_runtime_packaging.md) にまとめます。現段階では `prepare_runtime.ps1` が以下を作成します。

- `runtime/README.md`
- `runtime/python/`
- `runtime/app_envs/<app_id>/`
- `runtime/web_automation_runtime/`

Python runtime本体、app_env実体、Web自動化用ランタイム本体は未同梱です。正式配布前にローカルruntime archiveを準備し、sha256検証付きで展開する必要があります。

Rust backendのrunner起動は、現時点ではPATH上の `python` / `py` を探してPython runnerを呼びます。正式配布前に `runtime/python/python.exe` などの同梱runtimeを優先する実装へ切り替える必要があります。

## App Pack

内蔵アプリは将来アプリ単位で更新できるよう、App Pack zipとして扱います。

```text
release/app_packs/<app_id>-<version>.zip
```

App Packの仕様は [docs/09_app_pack_spec.md](09_app_pack_spec.md) に記載します。

## Troubleshooting

`link.exe not found`:

- Visual Studio Build Toolsをインストールする。
- Desktop development with C++ workloadを追加する。
- MSVC v143以降とWindows SDKを追加する。
- Developer PowerShell for VSで再実行する。

`esbuild spawn EPERM`:

- 管理者権限のターミナルで試す。
- セキュリティソフトのブロックや隔離を確認する。
- `launcher/node_modules` を削除して `npm ci` をやり直す。
- OneDriveやネットワーク同期フォルダ外で試す。
- `npm cache clean --force` を実行する。
- PC再起動後にNode.js LTSで再実行する。

PowerShell script execution policy:

- 社内ポリシーに従い、必要に応じて実行ポリシーを確認する。
- 直接 `pwsh -ExecutionPolicy Bypass -File .\scripts\check_all.ps1` のように一時的に実行する運用を検討する。

## Signing and Hash Verification

初回改修ではコード署名は未実装です。正式配布では以下を追加します。

- `ToolHub_Setup.exe` のコード署名
- `release/manifest.json` と `release/app_manifest.json` の署名または信頼済み配布経路
- 各配布物のsha256検証
- CI上のrelease生成と検証
