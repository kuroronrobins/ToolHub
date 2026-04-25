# Windows Build Environment

ToolHubの実インストーラー生成にはWindows上のTauri/Rust build環境が必要です。

## Required Tools

- Python 3.10以降
- Node.js LTS
- npm
- Rust
- cargo
- rustc
- Visual Studio Build Tools
- Desktop development with C++
- MSVC v143以降
- Windows SDK

Tauri CLIは `launcher/package.json` のnpm依存から `npm run tauri` で使います。global `tauri` commandは必須ではありません。

確認:

```powershell
.\scripts\check_all.ps1
```

`check_all.ps1` は現時点で以下を確認します。

- node / npm / cargo / rustc
- Visual Studio C++ toolchainの検出状況
- Tauri icon `launcher/src-tauri/icons/icon.ico` とICO header
- `tauri.conf.json` の `bundle.icon` と `bundle.resources` の主要パス
- release manifest JSON
- Python runner tests
- frontend typecheck / Vitest / Vite build
- Rust `cargo check`

## Visual Studio Build Tools

`cargo check` や `npm run tauri build` が `link.exe` 不在で失敗する場合、MSVC linkerが現在のシェルPATH上にありません。Visual Studio C++ workloadが導入済みでも、通常のPowerShellではPATHに出ず、Developer PowerShell for VSでは通る場合があります。

導入するもの:

- Visual Studio Build Tools
- Desktop development with C++
- MSVC v143以降
- Windows SDK

導入後も通常のPowerShellで見つからない場合は、Developer PowerShell for VSで実行します。

## Frontend Dependencies

配布再現性のため、`launcher/package-lock.json` を管理対象にします。

```powershell
cd launcher
npm ci
```

`npm ci` はlock fileに従って依存を復元します。lock fileがない場合はrelease buildの再現性が落ちます。

## Rust Dependencies

ToolHubは配布アプリケーションなので、`launcher/src-tauri/Cargo.lock` を管理対象にします。Rust library crateとは異なり、release buildの依存解決を固定することを優先します。

## Build Command

通常:

```powershell
.\scripts\build_release.ps1
```

Tauri bundleがまだ作れない環境で、App Pack、runtime雛形、staging、manifest検証だけ進める場合:

```powershell
.\scripts\build_release.ps1 -SkipBuild -AllowMissingBundle
```

runtime実体まで必須にする場合:

```powershell
.\scripts\build_release.ps1 -RequireRuntime
```
