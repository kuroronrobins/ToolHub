# Troubleshooting

## icons/icon.ico not found

症状:

- `npm run tauri build` が `icons/icon.ico not found` で失敗する。
- Windows Resource file生成時にTauri buildが停止する。

原因:

- `launcher/src-tauri/icons/icon.ico` はTauriのWindowsビルドに必要なアイコン資産である。
- このファイルがGitにコミットされていないと、別PCのfresh cloneで同じ失敗が起きる。

対応:

- `launcher/src-tauri/icons/icon.ico` が存在することを確認する。
- 必要な場合は `python make_icon.py` で最小アイコン資産を再生成する。
- 生成した `launcher/src-tauri/icons/icon.ico` をリポジトリにコミットする。

確認:

```powershell
.\scripts\check_all.ps1
```

## bundle.icon or bundle.resources missing

症状:

- `check_all.ps1` が `Tauri bundle icon missing` または `Tauri bundle resource missing` を出す。
- `npm run tauri build` は進むが、bundle成果物に必要ファイルが入らない可能性がある。

対応:

- `launcher/src-tauri/tauri.conf.json` の `bundle.icon` に `icons/icon.ico` と `icons/icon.png` があることを確認する。
- `bundle.resources` の相対パスが `launcher/src-tauri/` から見て存在することを確認する。
- `launcher/src-tauri/gen/` はTauri CLIが生成するschema類であり、Git管理対象にしない。

## link.exe not found

症状:

- `cargo check` が失敗する。
- `npm run tauri build` がWindows linker不足で失敗する。

対応:

- Visual Studio Build Toolsをインストールする。
- Desktop development with C++ workloadを追加する。
- MSVC v143以降を追加する。
- Windows SDKを追加する。
- Developer PowerShell for VSで再実行する。

確認:

```powershell
where.exe link
where.exe cl
.\scripts\check_all.ps1
```

## esbuild spawn EPERM

症状:

- `npm test` が `spawn EPERM` で失敗する。
- `npm run build` またはVite buildが `spawn EPERM` で失敗する。

対応:

- ターミナルを管理者権限で試す。
- セキュリティソフトのブロックや隔離を確認する。
- `launcher/node_modules` を削除して `npm ci` をやり直す。
- OneDriveやネットワーク同期フォルダ外で試す。
- `npm cache clean --force` を実行する。
- PCを再起動する。
- Node.js LTSを使う。

TypeScript単体チェックは以下で継続できます。

```powershell
cd launcher
npm run typecheck
```

または:

```powershell
.\scripts\frontend_check.ps1 -SkipTests -SkipBuild
```

## PowerShell Script Execution Policy

症状:

- `.\scripts\*.ps1` の実行がポリシーで止まる。

対応:

- 社内ポリシーを確認する。
- 必要な場合のみ、一時的に以下のように実行する。

```powershell
pwsh -ExecutionPolicy Bypass -File .\scripts\check_all.ps1
```

## OneDrive or Network Drive Issues

OneDriveやネットワーク同期配下では、Node.jsの実行ファイル、esbuild、Rust build成果物がセキュリティソフトや同期処理と競合することがあります。

切り分け:

- ローカルの短いパスへcloneして再実行する。
- `launcher/node_modules` を作り直す。
- セキュリティソフトのログを確認する。

## Runtime Missing

症状:

- `verify_release.ps1 -RequireRuntime` が失敗する。

対応:

- `runtime/python/python.exe` を含む承認済みruntime archiveを用意する。
- `scripts/prepare_runtime.ps1 -SourceArchive <path> -SourceSha256 <sha256>` で展開する。
- Web自動化用ランタイム本体を `runtime/web_automation_runtime/` に配置する。

雛形だけ確認する場合:

```powershell
.\scripts\prepare_runtime.ps1 -AllowMissingRuntime
.\scripts\verify_release.ps1
```

## Python command was not found

症状:

- ランチャーからアプリ起動時にPython runnerを呼べず、起動失敗になる。

原因:

- 現行のRust backendは暫定的にPATH上の `python` / `py` を探します。
- 正式配布では `runtime/python/python.exe` などの同梱runtimeへ切り替える予定ですが、現時点では未実装です。

対応:

- 開発環境ではPython 3.10以降をPATHから実行できる状態にする。
- 正式配布前の残作業として、Rust runnerのPython探索を同梱runtime優先へ変更する。

## Logs are not under project data

症状:

- Tauriランチャー経由で起動したログが `data/logs/` に見つからない。

原因:

- 現行実装では、Tauriランチャー経由のログとbrowser profileは `%LOCALAPPDATA%\ToolHub\data\` 配下へ保存します。
- `data/logs/` はrunner直接実行時の開発・テスト用フォールバックです。

確認:

```powershell
Get-ChildItem "$env:LOCALAPPDATA\ToolHub\data\logs" -Recurse
```

## ToolHub_Setup.exe not generated

症状:

- `release/dist_installer/ToolHub_Setup_0.1.0.exe` が存在しない。
- `verify_release.ps1 -RequireInstaller` が失敗する。

切り分け:

- `npm run tauri build` はTauri標準bundleを `launcher/src-tauri/target/release/bundle/` に生成します。
- `scripts/package_installer.ps1` がTauri標準bundleを `release/dist_installer/ToolHub_Setup_<version>.exe` または `.msi` へ収集し、`release/manifest.json` の `sha256` / `size` を更新します。

対応:

```powershell
cd launcher
npm run tauri build
cd ..
.\scripts\package_installer.ps1
.\scripts\verify_release.ps1 -RequireInstaller
```
