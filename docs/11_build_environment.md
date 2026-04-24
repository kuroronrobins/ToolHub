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

確認:

```powershell
.\scripts\check_all.ps1
```

## Visual Studio Build Tools

`cargo check` や `npm run tauri build` が `link.exe` 不在で失敗する場合、MSVC linkerがPATH上にありません。

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
