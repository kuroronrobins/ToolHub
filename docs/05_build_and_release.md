# Build and Release

## App Studio 由来アプリの配布検証

App Studio の通常新規登録で追加された Python アプリは、`shared-env` 方式で登録します。`requirements.lock` を生成し、`runtime/envs/<env_id>/` の共有ランタイムを作成または再利用し、`app.yaml` は `run.runner: python_shared_env` と `run.entry: src/<entry_relative>.py` を指します。

App Pack には `apps/<app_id>/` 配下の登録済み app source、`app.yaml`、`README.md`、`requirements.txt`、`requirements.lock`、`icon.png`、必要な app assets を含めます。`.auth/`、logs、screenshots、tmp/temp、仮想環境、build/dist、node_modules、認証状態、個人データらしいファイルは含めません。大容量ファイルや Playwright を含む場合は警告または manual check として扱います。

既存 exe 登録と PyInstaller frozen-folder は通常新規登録フローでは扱いません。既存の `run.runner: exe` app は互換対象として残しますが、新規登録の標準ではありません。legacy frozen-folder / exe の扱いは [16_app_studio_exe_build_operations.md](16_app_studio_exe_build_operations.md) を参照してください。

ToolHubの正式配布方式はインストーラー型配布です。

早期ベータ展開に向けた installer / updater の完成条件と実装順は [22_beta_installer_updater_plan.md](22_beta_installer_updater_plan.md) にまとめます。

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
7. 必要に応じて installer 署名
8. release検証

Tauri bundleをまだ生成できない環境でも、App Pack、runtime雛形、staging、manifest検証を進める場合:

```powershell
.\scripts\build_release.ps1 -SkipBuild -AllowMissingBundle
```

runtime実体まで必須にする場合:

```powershell
.\scripts\build_release.ps1 -RequireRuntime
```

正式配布で `ToolHub_Setup_<version>.exe` に Authenticode 署名を付ける場合:

```powershell
.\scripts\build_release.ps1 `
  -RequireRuntime `
  -SignInstaller `
  -RequireInstallerSignature `
  -CodeSignCertificateThumbprint <thumbprint>
```

`-SignInstaller` は installer を `release/dist_installer/` へ収集した直後、sha256 / size を `release/manifest.json` に書く前に署名します。これにより manifest、GitHub Release target、updater の sha256 検証は署名後の配布物を対象にします。

## GitHub Release Publish Flow

GitHub Releases を更新配布元にする場合は、まず release artifact を生成・検証し、その後 GitHub Release へ `manifest.json`、`app_manifest.json`、installer、`checksums.sha256.txt` を登録します。

公開前の読み取り確認:

```powershell
.\scripts\publish_github_release.ps1 -DryRun -SkipBuild -SkipVerify -SkipTag -SkipRemoteVerify -AllowDirty
```

公開対象フォルダだけを作成して目視確認する場合:

```powershell
.\scripts\publish_github_release.ps1 -PrepareTargetOnly -SkipBuild -SkipVerify -SkipTag -SkipRemoteVerify -AllowDirty
```

このコマンドは `release/github_release_targets/v<version>/` に、GitHub Release へ upload する installer、`manifest.json`、`app_manifest.json`、`checksums.sha256.txt` だけを集約します。同じフォルダの `release_target_manifest.json` には source path、target path、sha256、size、tag の対象 commit が記録されます。実 publish でもこのフォルダを作り直し、そこにある upload 対象を `gh release` へ渡します。この target folder は生成物なので `.gitkeep` 以外は Git 管理しません。

target folder の検証:

```powershell
.\scripts\verify_release_target_folder.ps1 -TargetDir .\release\github_release_targets\v<version> -Version <version>
```

この検証は `publish_github_release.ps1` が target folder を作成した直後にも自動実行します。`checksums.sha256.txt`、`release_target_manifest.json`、installer の `sha256` / `size` が揃わない場合は publish 前に停止します。

Beta / Pre-release を実 endpoint で検証する場合は、`latest` ではなく tag 固定の manifest URL を使います。GitHub の `latest` は prerelease を指さない場合があるためです。

```powershell
.\scripts\publish_github_release.ps1 `
  -Prerelease `
  -Tag v<version>-beta.1 `
  -AllowDirty `
  -SkipBuild `
  -SkipVerify
```

この場合、publish 後の remote verify は既定で次の tag 固定 URL を検証します。

```text
https://github.com/kuroronrobins/ToolHub/releases/download/v<version>-beta.1/manifest.json
```

実 publish の標準形:

```powershell
.\scripts\publish_github_release.ps1
```

この標準形は、`build_release.ps1 -RequireRuntime`、`verify_release.ps1 -RequireInstaller -RequireAppPacks -RequireRuntime -Strict`、tag 作成、GitHub Release 作成 / asset upload、remote manifest verify を順番に実行します。

署名なし配布の推奨形:

```powershell
.\scripts\publish_github_release.ps1 `
  -UpdateManifestInstallerUrl `
  -DownloadInstallerForRemoteVerify
```

署名なしを標準にする場合も、公開前の strict verify、`release/manifest.json` の installer `sha256` / `size`、公開対象フォルダの `checksums.sha256.txt`、公開後の installer download verify は必須扱いにします。正式 publish では `-AllowDirty` と `-AllowExistingRelease` を既定では使わず、新しい version / tag に clean worktree から公開します。

GitHub Release に署名済み installer だけを公開する場合:

```powershell
.\scripts\publish_github_release.ps1 `
  -SignInstaller `
  -RequireInstallerSignature `
  -CodeSignCertificateThumbprint <thumbprint>
```

`-SignInstaller` を付けた publish は build / package 中に署名し、upload target 作成前にも `Get-AuthenticodeSignature` が `Valid` であることを確認します。`-SkipBuild` と同時には使いません。既存 artifact を使う場合は、先に `package_installer.ps1 -SignInstaller` を実行し、その後 `publish_github_release.ps1 -SkipBuild -RequireInstallerSignature` を使います。

tag の対象 commit は既定で現在の `HEAD` です。別 commit / branch に紐づける場合は `-TargetCommitish <commit-or-branch>` を指定します。dirty worktree で `-AllowDirty` を使う場合、生成 asset は未コミット変更を含み得ますが、GitHub tag の source snapshot は `target_commitish` の commit だけを指します。正式 publish では、原則として build / verify 対象の変更を commit してから実行します。

既存 Release へ再アップロードする場合、dirty tree で意図的に実行する場合、または manifest に installer URL を書き込む場合は明示 option を使います。

```powershell
.\scripts\publish_github_release.ps1 -AllowDirty -AllowExistingRelease -UpdateManifestInstallerUrl
```

remote manifest だけを検証する場合:

```powershell
.\scripts\verify_github_release_assets.ps1 `
  -ManifestUrl https://github.com/kuroronrobins/ToolHub/releases/latest/download/manifest.json `
  -ExpectedVersion <version>
```

GitHub Release 自体、必須 asset、latest manifest URL をまとめて read-only 確認する場合:

```powershell
.\scripts\check_github_release_endpoint.ps1 -Json
```

installer 本体の download と sha256 照合まで確認する場合:

```powershell
.\scripts\verify_github_release_assets.ps1 `
  -ManifestUrl https://github.com/kuroronrobins/ToolHub/releases/latest/download/manifest.json `
  -ExpectedVersion <version> `
  -DownloadInstaller
```

App Studio の `公開準備` タブからも、preflight、publish dry-run、publish target作成、release build / verify、remote verify、実 publish を実行できます。実 publish は管理者認証に加え、UI と backend の両方で明示確認を要求します。

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

インストーラー成果物収集と署名:

```powershell
.\scripts\package_installer.ps1 `
  -SignInstaller `
  -CodeSignCertificateThumbprint <thumbprint>
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

署名を release gate として要求する場合:

```powershell
.\scripts\verify_release.ps1 `
  -RequireInstaller `
  -RequireInstallerSignature `
  -RequireAppPacks `
  -RequireRuntime `
  -Strict
```

## Installer Artifact Rules

Tauri bundleでNSISまたはMSIを生成します。`scripts/package_installer.ps1` は `launcher/src-tauri/target/release/bundle/` から成果物を収集し、`release/dist_installer/` に配置します。

現状では `scripts/build_release.ps1 -SkipInstall` により、Tauri標準NSIS/MSI bundle生成、正式配布名 `release/dist_installer/ToolHub_Setup_0.1.0.exe` への収集、installer `sha256` / `size` の確定まで確認済みです。実インストール検証、証明書を使った実署名、runtime実体同梱は未完了として扱います。

優先順位:

1. `.exe` がある場合はNSIS installerとして `ToolHub_Setup_<version>.exe` にする。
2. `.msi` しかない場合は `ToolHub_Setup_<version>.msi` にする。
3. 両方ない場合、`-AllowMissingBundle` 指定時だけstaging作成とmanifest検証を続ける。

`release/manifest.json` の `toolhub.installer.file`、`type`、`sha256`、`size` は `package_installer.ps1` が更新します。
Release JSON と App Pack metadata JSON は PowerShell 5.1 / 7 の差異を避けるため、`scripts/utf8_no_bom.ps1` の helper で UTF-8 no BOM として書き出します。`scripts/check_all.ps1` は `release/manifest.json` と `release/app_manifest.json` の BOM 有無を直接検査し、helper test は App Pack 内 `pack_manifest.json` と同じ JSON 書き込み経路が BOM を付けないことを検査します。

`-SignInstaller` を指定した場合、`package_installer.ps1` は `scripts/sign_installer.ps1` を呼び出します。証明書は repo に置かず、`-CodeSignCertificateThumbprint` / `-CodeSignCertificateSubject` / `-SignToolExtraArgs`、または `TOOLHUB_CODESIGN_CERT_THUMBPRINT` などの環境変数から渡します。

個人として ToolHub を配布する場合は、個人向け `Standard Code Signing` / `Individual Code Signing` 証明書を使います。組織名や法人名で発行者を表示したい場合だけ OV 証明書を使います。ToolHub の署名スクリプトは証明書種別には依存せず、Windows 証明書ストア、USB token / HSM / cloud HSM、または `signtool.exe` の追加引数で利用できる Authenticode 対応証明書を前提にします。

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
- `tools/app_studio/main.py`
- `tools/app_studio/app_studio/`
- `tools/app_studio/assets/`
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

Python runtime本体、app_env実体、Web自動化用ランタイム本体はGit管理対象には含めません。ローカルrelease artifactとして存在する場合でも、正式配布前に承認済みruntime archiveからsha256検証付きで再現し、installer同梱環境で検証する必要があります。

Rust backendのrunner起動は、`runtime/python/python.exe` があれば優先し、ない場合だけPATH上の `python` / `py` を探します。正式配布前に、installer同梱runtimeでこの経路が使われることを実機で確認する必要があります。

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

正式配布では、GitHub Release へ upload する前に installer 署名と署名後 hash の一致を release gate にします。

- `scripts/sign_installer.ps1` による `ToolHub_Setup.exe` の Authenticode 署名
- `verify_release.ps1 -RequireInstallerSignature` による署名検証
- `release/manifest.json` と `release/app_manifest.json` の署名または信頼済み配布経路
- 各配布物のsha256検証
- CI上のrelease生成と検証

署名後に installer を変更すると Authenticode 署名が壊れるため、署名は installer 収集後、manifest の sha256 / size 記録前に行います。`checksums.sha256.txt` と `release_target_manifest.json` は署名後のファイルから作成します。
