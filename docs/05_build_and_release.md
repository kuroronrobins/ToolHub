# Build and Release

ToolHubの正式配布方式はインストーラー型配布です。

開発者はリポジトリ直下で `python main.py` を使います。利用者には `ToolHub_Setup.exe` を配布し、インストール後はデスクトップショートカットまたはスタートメニューの `ToolHub` から起動してもらいます。

## Why Installer

インストーラー型を正式方針にする理由:

- 利用者にPython、Node.js、Rust、Web自動化用ランタイムの導入を要求しない。
- ToolHub本体、runner、内蔵アプリ、runtimeを固定配置できる。
- 更新時に置き換える対象と、消してはいけないユーザーデータを分離できる。
- ショートカット、アンインストール、将来の署名や社内配布ポリシーに対応しやすい。

完全単一exeを正式方式にしない理由:

- 起動のたびに大量ファイルを一時展開すると起動速度が落ちる。
- Web自動化用ランタイムやPython環境のような重い依存を毎回展開する設計になりやすい。
- 差分更新、sha256検証、ロールバックの単位が粗くなる。

フォルダ配布を正式方式にしない理由:

- 利用者が内部フォルダを移動・削除して壊すリスクが高い。
- ショートカット、アンインストール、更新権限、配置先の標準化が弱い。
- 社内配布時に配布物の正当性を保証しにくい。

## Install Locations

per-user installを第一候補にします。

インストール先:

```text
%LOCALAPPDATA%\Programs\ToolHub\
```

ユーザーデータ先:

```text
%LOCALAPPDATA%\ToolHub\
```

インストール先にはToolHub本体と更新対象を置きます。ユーザーデータ先には設定、ログ、browser profiles、app_state、update_cache、backupsを置きます。

更新時に消してはいけないもの:

- ユーザー設定
- ログ
- browser_profiles
- app_state
- 必要なupdate_cache
- ユーザーが追加した外部アプリ情報

## Included in Installer

最終的に `ToolHub_Setup.exe` に含める対象:

- `ToolHub.exe`
- launcher実行に必要な成果物
- `runner/`
- `apps/` 初期セット
- `runtime/`
- `config.default/`
- `release/manifest.json`
- updater設定
- 利用者向け最小説明
- uninstall情報

含めない対象:

- 実行ログ
- ユーザー個別設定
- browser_profiles
- app_state
- 検索インデックス生成済みキャッシュ
- 一時ファイル
- `node_modules`
- `target/debug`
- `.git`
- 開発用テスト出力

## Build Commands

開発起動:

```powershell
python main.py --dev
```

リリースビルド:

```powershell
.\scripts\build_release.ps1
```

App Pack作成:

```powershell
.\scripts\package_app_pack.ps1
```

インストーラー成果物収集:

```powershell
.\scripts\package_installer.ps1
```

リリース検証:

```powershell
.\scripts\verify_release.ps1
```

## ToolHub_Setup.exe

Phase AではTauri標準のWindows bundle、特にNSIS/MSIを優先します。Tauri buildが生成したbundle成果物を `release/dist_installer/` に集約し、NSISのexeが見つかる場合は `ToolHub_Setup_<version>.exe` として扱います。

Phase Bでは、Inno Setupや社内配布基盤へ移行できるように、`scripts/package_installer.ps1` と `installer/` 配下に責務を分離します。

## Runtime Bundling

利用者が環境構築しなくても動作することを目標にします。

将来構成:

```text
runtime/
├─ python/
├─ app_envs/
│  ├─ sample_gui_app/
│  ├─ sample_cli_app/
│  └─ sample_playwright_app/
└─ web_automation_runtime/
```

利用者向けには「Web自動化用ランタイム」と表現します。管理者向けdocsやmanifestでは内部runner名を記載できます。

## App Pack

内蔵アプリは将来アプリ単位で更新できるよう、App Pack zipとして扱います。

```text
release/app_packs/<app_id>-<version>.zip
```

App Packの仕様は [docs/09_app_pack_spec.md](09_app_pack_spec.md) に記載します。

## Update and Rollback

更新は直接上書きしません。

1. manifest取得
2. バージョン比較
3. 利用者承認
4. ダウンロード
5. sha256検証
6. 一時フォルダへ展開
7. 互換性確認
8. 更新前バックアップ作成
9. 原子的置き換え
10. 起動確認
11. 失敗時ロールバック

バックアップ先:

```text
%LOCALAPPDATA%\ToolHub\backups\
```

更新キャッシュ先:

```text
%LOCALAPPDATA%\ToolHub\update_cache\
```

## Signing and Hash Verification

初回改修では署名は未実装です。正式配布では以下を追加します。

- `ToolHub_Setup.exe` のコード署名
- `release/manifest.json` と `release/app_manifest.json` の署名または信頼済み配布経路
- 各配布物のsha256検証
- CI上のrelease生成と検証

