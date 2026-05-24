# Installer Distribution

ToolHubはインストーラー型配布を正式方針にします。

早期ベータでの installer 完成条件、実インストール検証、updater 連携は [22_beta_installer_updater_plan.md](22_beta_installer_updater_plan.md) を基準にします。

## Current Status

- 現行 release manifest は ToolHub `0.1.5` / `ToolHub_Setup_0.1.5.exe` を指します。
- Tauri標準のNSIS bundle生成、`release/dist_installer/` への収集、`release/manifest.json` の installer `sha256` / `size` 更新、`verify_release.ps1 -RequireInstaller` は確認済みです。
- 2026-05-24 時点で、GitHub Release Latest の `manifest.json` と `ToolHub_Setup_0.1.5.exe` は remote download 後の size / sha256 一致を確認済みです。
- VM 環境で、per-user install、first launch、app card 表示、登録済み検証アプリ起動、同梱 Python / Web runtime 利用を確認済みです。最新 pass 結果ファイルが repo に取り込まれていない場合は、`docs/06_acceptance_checklist.md` の記録と混同せず扱います。
- コード署名 pipeline はありますが、証明書署名済み artifact は未作成です。

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
│  ├─ envs/
│  ├─ app_envs/        # legacy compatibility only
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

