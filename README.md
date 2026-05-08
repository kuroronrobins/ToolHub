# ToolHub

ToolHubは、複数のPythonアプリケーションを1つのデスクトップ画面から探して起動するための業務用アプリランチャーです。

各アプリは `apps/<app_id>/app.yaml` を持つプラグインとして配置します。ランチャー本体には個別アプリ固有の処理を書かず、起動処理は `runner/` のPython App Runnerに集約します。

## 開発時の起動方法

開発者は、プロジェクト直下で以下を実行します。

```powershell
python main.py
```

Windowsで `py` ランチャーを使う場合は以下でも起動できます。

```powershell
py main.py
```

`main.py` は開発用ブートストラップです。配布済み環境の利用者は `main.py` を実行しません。

## 配布時の起動方法

利用者には原則として `ToolHub_Setup.exe` 1個を配布します。

利用者は `ToolHub_Setup.exe` を実行してインストールします。インストール後は、デスクトップショートカットまたはスタートメニューの `ToolHub` から起動します。

利用者は以下を手動でインストールする必要がない方針です。

- Python
- pip package
- Node.js / npm
- Rust / cargo
- Tauri CLI（通常は `launcher/package.json` のnpm依存から `npm run tauri` で使います。global installは必須ではありません）
- Web自動化用ランタイム
- 各Pythonアプリのライブラリ

現段階では、完全なPython同梱runtimeとWeb自動化用ランタイムの同梱は設計・スクリプト雛形までです。正式配布前に `runtime/` の実体作成、インストーラー生成、署名、実機検証が必要です。

現行実装の到達点:

- 新しいPCで `python main.py --dev` によるランチャー起動、アプリカード表示、GUI/CLI/Web操作サンプルの起動は確認済みです。
- `scripts/build_release.ps1 -SkipInstall` によりTauri標準NSIS/MSI bundle生成、`release/dist_installer/ToolHub_Setup_0.1.0.exe` への収集、`release/manifest.json` のinstaller `sha256` / `size` 更新は確認済みです。
- 実インストール検証、コード署名、installerへのruntime同梱検証は未完了です。runtime実体はローカルrelease artifactとして扱い、Gitには含めません。

## 開発モードで起動

```powershell
python main.py --dev
```

ビルド済み実行ファイルがあっても、強制的にTauri開発モードで起動します。

## 環境チェック

```powershell
python main.py --check
```

フォルダ構成、`launcher/package.json`、Node.js/npm、Rust/cargoなど、起動に必要な環境を確認します。

## その他の起動オプション

```powershell
python main.py --release
```

ビルド済みのToolHub実行ファイルのみを探して起動します。見つからない場合は開発モードへフォールバックしません。

```powershell
python main.py --help
```

使い方を表示します。

## 開発環境

主な前提は以下です。

- Python 3.10以降
- Node.js / npm
- Rust / cargo
- Tauri CLI
- Visual Studio Build Tools
- Desktop development with C++
- MSVC v143以降
- Windows SDK

開発時のPythonは仮想環境ではなく実環境で実行する前提です。runnerは標準ライブラリ中心で動作し、YAML読み込みはPyYAMLがある場合に使用します。PyYAMLがない環境でも、サンプルのような基本的な `app.yaml` は簡易パーサーで読み込めます。

WindowsでTauri/Rustのrelease buildを行う場合は、Rust本体だけでなくMSVC linkerの `link.exe` とC++ compilerの `cl.exe` が必要です。見つからない場合はVisual Studio Build ToolsにC++ workloadとWindows SDKを追加してください。
通常のPowerShellではPATHに出ていなくても、Developer PowerShell for VSでは見つかる場合があります。

フロントエンド依存関係は `launcher/` で管理します。

```powershell
cd launcher
npm ci
```

ToolHubは配布アプリケーションなので、再現性のために以下のlock fileを管理対象にします。

- `launcher/package-lock.json`
- `launcher/src-tauri/Cargo.lock`

`package-lock.json` は `npm ci` で同じ依存バージョンを復元するために使います。`Cargo.lock` はTauri/Rust側の依存解決を固定するために使います。

## サンプルアプリ

`apps/` には初回検証用のサンプルを3つ用意しています。

- `sample_gui_app`: Python標準のTkinterを使うGUIサンプル
- `sample_cli_app`: JSON Linesイベントを標準出力に出すCLIサンプル
- `sample_playwright_app`: Web自動化アプリ想定のサンプル

`sample_playwright_app` は `headless=True` でローカルHTMLを操作するため、正常時もブラウザウィンドウは表示されません。

利用者向け画面では、アプリの実行方式や内部技術名は表示しません。

## 新しいアプリの追加

以下の補助スクリプトでテンプレートを作成できます。

```powershell
.\scripts\create_app_template.ps1 -AppId my_app -Name "業務ツール"
```

手動で追加する場合は、`apps/<app_id>/` に以下を配置します。

- `app.yaml`
- `main.py`
- `requirements.txt`
- `README.md`
- `icon.png`
- `icon.svg`（fallback / 互換用）

ToolHubを再起動すると、`app.yaml` から自動検出されます。

## 管理者向けアプリ管理

管理者画面の App Studio では、新規登録、既存アプリ更新MVPに加えて、Delete タブでアプリ管理MVPを利用できます。

- 非表示: `release/app_manifest.json` の対象 entry を `enabled=false` にします。
- 再表示: `apps/<app_id>/app.yaml` が存在する場合だけ `enabled=true` に戻します。
- 削除計画: `apps/<app_id>/`、App Pack、staging、runtime app_env、App Studio backup などの将来削除対象と、外部参照・ユーザーデータ・共有runtimeの除外対象を表示します。
- 完全削除: 管理者セッション中の Delete タブで削除計画を表示し、安全条件を満たす場合だけ repo 内の対象アプリ由来管理対象を削除します。

完全削除は外部ソース、外部 output mirror、ユーザーデータ、logs、browser profiles、app_state、共有runtime、曖昧なstaging候補を削除しません。PowerShell production `-Apply` は未実装のままです。管理モデルは [docs/17_app_management_model.md](docs/17_app_management_model.md)、実装計画は [docs/18_app_delete_execution_plan.md](docs/18_app_delete_execution_plan.md)、executor設計は [docs/19_full_delete_executor_design.md](docs/19_full_delete_executor_design.md) を参照してください。

## 検収方法

可能な範囲のチェックは以下で実行します。

```powershell
.\scripts\check_all.ps1
```

`check_all.ps1` の通常検証では、`release/app_manifest.json` の `enabled=true` かつ `apps/<app_id>/app.yaml` がない entry は fail です。`enabled=false` かつ source missing の古い entry は stale / hidden history として warn に留めます。Strict検証や正式配布前の整理では fail 対象です。

app manifest の状態だけを確認する場合:

```powershell
.\scripts\diagnose_app_manifest.ps1
.\scripts\diagnose_app_manifest.ps1 -Strict
```

Release readiness cleanup candidates and non-delete packaging/build work:

```powershell
.\scripts\report_release_readiness.ps1
.\scripts\report_release_readiness.ps1 -Json
```

This report is read-only. It separates disabled stale delete candidates from App Pack rebuild work, shared runtime
packaging, installer/release build work, intentional warnings, and local build environment blockers.

`release/app_manifest.json` を `apps/` から再生成する計画や、完全削除前の削除予定を確認する場合:

```powershell
.\scripts\rebuild_app_manifest.ps1 -DryRun
.\scripts\plan_app_delete.ps1 -AppId addnum_pdf -DryRun
.\scripts\execute_app_delete.ps1 -AppId addnum_pdf -DryRun
```

削除計画は dry-run のみです。App Pack は manifest の package path と
`release/app_packs/<app_id>-*.zip`、staging は `<app_id>` または
`<app_id>-<version>` と明確に判定できる path segment だけを削除候補にします。
部分一致だけの staging 候補は除外対象として表示されます。`execute_app_delete.ps1` の production `-Apply` は未実装として拒否します。production完全削除は管理者画面のTauri command経由で実行します。

```powershell
.\scripts\test_app_delete_plan.ps1
.\scripts\test_app_delete_plan_parity.ps1
.\scripts\rehearse_app_delete.ps1
.\scripts\test_app_delete_executor_design.ps1
.\scripts\test_app_full_delete_e2e.ps1
```

`test_app_delete_plan_parity.ps1` は PowerShell版とTauri/Rust helper版の削除計画を同じ一時fixtureで比較します。
`rehearse_app_delete.ps1` は一時appを作って削除計画だけを検証し、manifestや一時生成物を元に戻します。
`test_app_full_delete_e2e.ps1` はTemp配下のfixtureだけで `-Apply -AllowTemporaryAppApply` を実行します。production rootや実在appへのApplyは拒否されます。

配布物検証は以下を使います。

```powershell
.\scripts\package_app_pack.ps1
.\scripts\prepare_runtime.ps1 -AllowMissingRuntime
.\scripts\package_installer.ps1
.\scripts\verify_release.ps1
```

`package_app_pack.ps1` regenerates App Packs from `apps/*/app.yaml`, preserves each manifest entry's `enabled` state,
and updates `release/app_manifest.json` `package` / `sha256` to match the generated zip. The zip files under
`release/app_packs/` are local release artifacts and are ignored by Git except for `.gitkeep`.

Runtime binaries are also local release artifacts and are not tracked by Git. Use approved local archives and explicit
SHA256 values:

```powershell
.\scripts\prepare_runtime.ps1 -PythonArchive <python.zip> -PythonSha256 <sha256>
.\scripts\prepare_runtime.ps1 -WebRuntimeArchive <web-runtime.zip> -WebRuntimeSha256 <sha256>
.\scripts\verify_runtime.ps1
```

Without approved archives, `.\scripts\prepare_runtime.ps1 -AllowMissingRuntime` keeps placeholder folders and reports
warnings only. After local runtime archives are expanded, `.\scripts\verify_runtime.ps1 -RequireRuntime` must pass on the
release build machine.

Tauri bundleが未生成の環境でも、App Pack、runtime雛形、staging、manifest検証まで進める場合は以下を使います。

```powershell
.\scripts\build_release.ps1 -SkipBuild -AllowMissingBundle
```

詳細な検収項目は [docs/06_acceptance_checklist.md](docs/06_acceptance_checklist.md) を参照してください。

## 現行のデータ保存先

Tauriランチャー経由では、起動時に `%LOCALAPPDATA%\ToolHub\` 配下へ以下を作成し、Rust backendとPython runnerに同じユーザーデータrootを渡します。

- `config/`
- `data/logs/`
- `data/browser_profiles/`
- `data/search_index/`
- `data/app_state/`
- `backups/`
- `update_cache/`

`python runner/toolhub_runner/main.py --project-root . --app-id ...` のようにrunnerを直接実行した場合は、開発・テスト用のフォールバックとしてリポジトリ直下の `data/` を使います。

## 配布・更新設計

- 正式配布方式: インストーラー型配布
- 配布ファイル: `ToolHub_Setup.exe`
- 推奨インストール先: `%LOCALAPPDATA%\Programs\ToolHub\`
- 推奨ユーザーデータ先: `%LOCALAPPDATA%\ToolHub\`
- App Pack: `release/app_packs/<app_id>-<version>.zip`
- 更新対象: ToolHub Core、Runner、Built-in Apps、Heavy Runtime
- 更新対象外: User Data、ログ、browser profiles、app_state

詳細は以下を参照してください。

- [docs/05_build_and_release.md](docs/05_build_and_release.md)
- [docs/07_installer_distribution.md](docs/07_installer_distribution.md)
- [docs/08_update_design.md](docs/08_update_design.md)
- [docs/09_app_pack_spec.md](docs/09_app_pack_spec.md)
- [docs/10_runtime_packaging.md](docs/10_runtime_packaging.md)
- [docs/22_beta_installer_updater_plan.md](docs/22_beta_installer_updater_plan.md)
- [docs/11_build_environment.md](docs/11_build_environment.md)
- [docs/12_troubleshooting.md](docs/12_troubleshooting.md)

## 既知の制約

- 初回実装では、TauriからReactへのリアルタイムイベントストリーミングは将来拡張の構造に留め、起動結果とログパスを返します。
- Web操作サンプルは外部サイト依存を避けるため、安全なローカルHTMLデモを優先します。実行環境が未準備の場合は利用者向けエラーと詳細ログを確認できます。
- 自動更新は非破壊MVPまでです。起動後にローカルmanifestを読み、通常ユーザーには更新候補がある場合だけ通知します。更新元未設定、更新候補なし、参照した設定ファイルやmanifest pathは管理者画面で確認できますが、manifestダウンロード、更新ファイルの取得、展開、置換、バックアップ、ロールバック、署名検証は未実装です。
- Rust backendのrunner起動は `runtime/python/python.exe` があれば優先し、無い場合はPATH上の `python` / `py` を探します。正式配布前に同梱runtimeの実体作成と検証が必要です。
- `ToolHub_Setup.exe` の署名、完全なruntime同梱、実機インストール検証は今後の作業です。
- `scripts/prepare_runtime.ps1 -AllowMissingRuntime` はruntimeフォルダだけを維持するwarning用です。正式配布前は承認済みarchiveをSHA256付きで展開し、`scripts/verify_runtime.ps1 -RequireRuntime` を通してください。
- Tauri iconは `launcher/src-tauri/icons/icon.ico` / `icon.png` をGit管理します。必要な場合は `python make_icon.py` で再生成できます。
