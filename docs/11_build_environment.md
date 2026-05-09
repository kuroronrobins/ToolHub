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

## Codex / non-Developer PowerShell からの実行

Codex の実行 shell や通常の PowerShell では、Visual Studio Build Tools が入っていても `cl.exe` / `link.exe` が PATH に出ない場合があります。まず現在の shell を診断します。

```powershell
.\scripts\diagnose_build_shell.ps1
```

JSON で確認する場合:

```powershell
.\scripts\diagnose_build_shell.ps1 -Json
```

`VsDevCmd.bat` が見つかる環境では、次の wrapper で Visual Studio Developer environment を読み込んだ同一 cmd session 内で build command を実行できます。

```powershell
.\scripts\run_in_vs_dev_shell.ps1 -Command "where.exe cl && where.exe link"
```

```powershell
.\scripts\run_in_vs_dev_shell.ps1 -Command "cargo check --manifest-path .\launcher\src-tauri\Cargo.toml"
```

```powershell
.\scripts\run_in_vs_dev_shell.ps1 -Command "powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_release.ps1 -RequireRuntime"
```

この wrapper は `VsDevCmd.bat` による PATH / INCLUDE / LIB などの build environment 読み込みだけを行います。Windows Application Control で `rustc.exe` / `cargo.exe` がブロックされる場合、repo 側の script では解消しません。その場合は以下のいずれかを人間判断で選びます。

- `rustc.exe` / `cargo.exe` の allowlist 追加。
- Rust toolchain を組織の trusted path に入れ直す。
- Developer PowerShell for VS 2022 上で手動実行する。
- 別の release build machine を使う。

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
