# Troubleshooting

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
