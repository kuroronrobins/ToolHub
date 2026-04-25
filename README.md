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
- 実インストール検証、コード署名、runtime実体同梱は未完了です。

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
- `icon.svg`

ToolHubを再起動すると、`app.yaml` から自動検出されます。

## 検収方法

可能な範囲のチェックは以下で実行します。

```powershell
.\scripts\check_all.ps1
```

配布物検証は以下を使います。

```powershell
.\scripts\package_app_pack.ps1
.\scripts\prepare_runtime.ps1 -AllowMissingRuntime
.\scripts\package_installer.ps1
.\scripts\verify_release.ps1
```

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
- [docs/11_build_environment.md](docs/11_build_environment.md)
- [docs/12_troubleshooting.md](docs/12_troubleshooting.md)

## 既知の制約

- 初回実装では、TauriからReactへのリアルタイムイベントストリーミングは将来拡張の構造に留め、起動結果とログパスを返します。
- Web操作サンプルは外部サイト依存を避けるため、安全なローカルHTMLデモを優先します。実行環境が未準備の場合は利用者向けエラーと詳細ログを確認できます。
- 自動更新機能は未実装です。`release/manifest.json`、`release/app_manifest.json`、App Packスクリプト、更新設計docsを用意しています。
- Rust backendのrunner起動は現時点ではPATH上の `python` / `py` を探します。正式配布前に `runtime/python/python.exe` などの同梱runtimeへ切り替える必要があります。
- `ToolHub_Setup.exe` の署名、完全なruntime同梱、実機インストール検証は今後の作業です。
- 現段階の `scripts/prepare_runtime.ps1 -AllowMissingRuntime` はruntimeフォルダとapp_env雛形を作りますが、Python runtime本体とWeb自動化用ランタイム本体は同梱しません。
- Tauri iconは `launcher/src-tauri/icons/icon.ico` / `icon.png` をGit管理します。必要な場合は `python make_icon.py` で再生成できます。
