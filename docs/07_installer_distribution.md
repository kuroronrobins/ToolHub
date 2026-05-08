# Installer Distribution

ToolHubはインストーラー型配布を正式方針にします。

早期ベータでの installer 完成条件、実インストール検証、updater 連携は [22_beta_installer_updater_plan.md](22_beta_installer_updater_plan.md) を基準にします。

## Current Status

- Tauri標準のNSIS/MSI bundle生成は確認済みです。
- 正式配布名 `release/dist_installer/ToolHub_Setup_0.1.0.exe` への収集、`release/manifest.json` のinstaller `sha256` / `size` 更新、`verify_release.ps1 -RequireInstaller` は確認済みです。
- 実インストール検証、コード署名は未完了です。
- runtime実体やWeb自動化用ランタイム実体はローカルrelease artifactとして存在する場合がありますが、installerへの正式同梱検証は未完了です。

## User Flow

1. 利用者は `ToolHub_Setup.exe` を受け取る。
2. `ToolHub_Setup.exe` を実行する。
3. デスクトップまたはスタートメニューの `ToolHub` から起動する。

利用者はPython、Node.js、Rust、Tauri CLI、Web自動化用ランタイム、各Pythonライブラリを手動導入しません。

## Per-User Install

第一候補:

```text
%LOCALAPPDATA%\Programs\ToolHub\
```

想定構成:

```text
%LOCALAPPDATA%\Programs\ToolHub\
├─ ToolHub.exe
├─ launcher/
├─ runner/
├─ apps/
├─ runtime/
│  ├─ python/
│  ├─ app_envs/
│  └─ web_automation_runtime/
├─ config.default/
├─ release/
├─ updater/
└─ uninstall/
```

## User Data

保存先:

```text
%LOCALAPPDATA%\ToolHub\
```

想定構成:

```text
%LOCALAPPDATA%\ToolHub\
├─ config/
├─ data/
│  ├─ logs/
│  ├─ browser_profiles/
│  ├─ search_index/
│  └─ app_state/
├─ backups/
└─ update_cache/
```

更新や再インストールでこの領域を消してはいけません。

Tauriランチャー経由では、起動時初期化とrunner呼び出しの両方でこのユーザーデータ先を使います。runner直接実行時は開発・テスト用フォールバックとしてリポジトリ直下の `data/` を使います。

## Staging Output

ビルド・パッケージング作業では以下を使います。

- `release/staging/`: 配布物作成用の一時ステージング
- `release/dist_installer/`: インストーラー成果物
- `release/app_packs/`: App Pack zip

これらは配布作業の成果物または一時ファイルです。ユーザーデータとは分離します。

## Future Installer Options

初期方針はTauri標準bundleです。将来、以下へ移行できます。

- NSIS詳細カスタマイズ
- MSI/WiX
- Inno Setup
- 社内配布基盤

移行しても、配布物名は `ToolHub_Setup.exe` 系、インストール先とユーザーデータ先の分離方針は維持します。

