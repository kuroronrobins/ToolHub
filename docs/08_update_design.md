# Update Design

ToolHubは将来、ToolHub本体と内蔵アプリを安全に更新できる構造にします。

早期ベータでは、まず最新版インストーラー再配布型アップデートを優先します。Beta MVP の範囲と段階計画は [22_beta_installer_updater_plan.md](22_beta_installer_updater_plan.md) を参照してください。

## Implementation Status

2026-05-23 時点で実装済み:

- `release/manifest.json` と `release/app_manifest.json` の雛形
- App Pack zip生成とsha256記録
- App Pack sha256検証
- runtime雛形作成
- 更新対象とUser Dataを分離する設計docs
- GitHub Releases 向け更新確認 / installer 起動MVP
  - 起動後に `check_updates_remote` Tauri command を呼ぶ
  - 更新設定は `%LOCALAPPDATA%\ToolHub\config\launcher.yaml` のユーザー設定を優先する
  - 既存ユーザー設定に `updates.manifest_url` / `updates.source_url` / `updates.url` がない場合は、互換維持のため `config.default/launcher.yaml` の更新元URLへフォールバックする
  - `updates.source_url` / `updates.manifest_url` / `updates.url` が未設定の場合は `source_not_configured` として扱う
  - remote manifest を取得し、現在の ToolHub version と比較する
  - app単位の更新候補は `release/app_manifest.json` の `enabled=true` かつ `apps/<app_id>/app.yaml` がある active app を主対象にする
  - `enabled=false` の disabled / stale entry は通常ユーザー向け更新候補に出さず、管理者向け診断・整理対象として扱う
  - 通常ユーザー向け通知は `update_available` の場合だけ表示する
  - 通常画面には「更新する」「あとで」の更新バナーを出し、同一セッション内の同一 current -> target version だけ dismiss できる
  - `download_update_installer` は installer を `%LOCALAPPDATA%\ToolHub\update_cache\` に保存し、manifest の sha256 / size と照合する
  - GitHub Releases からの取得は Windows PowerShell 経由で行い、TLS 1.2 を明示して GitHub の HTTPS endpoint に接続する
  - `launch_verified_update_installer` は検証済み installer だけを起動する
  - installer 起動時は `update_cache` 外、`.exe` / `.msi` 以外、`ToolHub_Setup` を含まない file name を拒否する
  - `http://` update source は拒否し、Beta 本番は `https://` を前提にする
  - download / launch / check の結果を `%LOCALAPPDATA%\ToolHub\data\logs\updater\latest_update_result.json` に記録する
  - 次回起動時に `targetVersion` と現在 version を比較し、`version_confirmed` / `version_pending` / `not_launched` を管理者画面へ表示する
- GitHub Release 公開導線
  - `scripts/publish_github_release.ps1` で build、verify、tag、Release 作成 / upload、remote verify を実行できる
  - publish 前に `release/github_release_targets/v<version>/` へ upload 対象 asset を集約し、管理者が公開対象フォルダを確認できる
  - `scripts/verify_release_target_folder.ps1` で target folder の checksum / manifest / installer hash を検証できる
  - Beta / Pre-release では `latest` ではなく `releases/download/<tag>/manifest.json` を remote verify 対象にできる
  - `scripts/verify_github_release_assets.ps1` で remote manifest、installer URL、sha256、size を検証できる
  - App Studio の `公開準備` タブから preflight、dry-run、publish target作成、release build / verify、remote verify、実 publish を実行できる

未実装:

- installer 内での更新適用後確認を clean VM で完了すること
- 更新ファイルの展開と原子的置き換えを ToolHub 自身が行うこと
- 更新対象ファイルの削除
- 更新前バックアップとロールバックの実処理
- manifestやinstallerの署名検証

この文書は現時点では将来設計を含みます。現在動くのは remote manifest 確認、installer download、sha256 検証、検証済み installer 起動までです。ToolHub 自身が install dir を直接上書きする展開、置換、削除、バックアップ、ロールバック、署名検証が動作することを意味しません。

## Update Units

| Unit | Examples | User Data |
| --- | --- | --- |
| ToolHub Core | Tauri / React / Rust, `ToolHub.exe`, UI | No |
| Runner | `runner/`,ログ処理,エラー処理,共通起動処理 | No |
| Built-in Apps | `apps/<app_id>/`, `app.yaml`, app code | No |
| Heavy Runtime | Python runtime, app envs, Web自動化用ランタイム | No |
| User Data | config, logs, browser_profiles, app_state | Yes |

User Dataは更新対象ではありません。更新処理で削除しないでください。

## Manifest Files

- `release/manifest.json`: ToolHub Core、Runner、Runtime、installerの情報
- `release/app_manifest.json`: App Pack一覧、sha256、互換性条件

## Safe Update Flow

1. 起動後、バックグラウンドで更新確認
2. latest manifestを取得
3. 現在バージョンと比較
4. 更新内容を利用者向けに要約表示
5. 利用者が承認
6. ダウンロード
7. sha256検証
8. 検証済み `ToolHub_Setup_<version>.exe` を起動
9. installer が install dir を更新
10. 次回起動時に現在 version を確認
11. 署名検証
12. 一時フォルダへ展開
13. `app.yaml` / manifest互換性確認
14. 更新前バックアップ作成
15. 原子的に置き換え
16. 起動確認
17. 失敗時ロールバック

現在の Beta MVP は 1-10 の whole-installer update flow を対象にします。11以降の署名、ToolHub内での展開、原子的置き換え、バックアップ、ロールバックは正式版向けの将来拡張です。

## Locations

バックアップ:

```text
%LOCALAPPDATA%\ToolHub\backups\
```

更新キャッシュ:

```text
%LOCALAPPDATA%\ToolHub\update_cache\
```

インストール先を直接上書きせず、必ず一時展開と検証を経由します。

## User-Facing Update UI

利用者向け表示例:

```text
ToolHubを更新できます。
内蔵アプリの改善や不具合修正が含まれます。
```

現在の Beta MVP では、通常ユーザーには更新候補がある場合だけ更新バナーを表示します。「あとで」で同一セッション中だけ閉じられますが、topbar の更新状態は残り、クリックすると更新 dialog を開けます。更新元未設定や更新候補なしは、通常ユーザーには毎回通知しません。

管理者画面では以下を確認できます。

- ToolHub Core: `0.1.0` -> `0.2.0`
- Runner: `0.1.0` -> `0.1.1`
- アプリ: `1.0.0` -> `1.1.0`
- Web自動化用ランタイム更新あり
- 参照した設定ファイル: user / default / missing
- ローカル `release/manifest.json` / `release/app_manifest.json` の参照path
- 未実装 / 将来操作: ToolHub内での展開、置換、バックアップ、ロールバック、署名検証
- 前回 update result: download / launch の状態、対象 version、現在 version、次回起動時の確認結果

利用者向けUIには内部技術名を表示しません。

## Rollback

更新前に対象単位ごとのバックアップを作ります。更新後の起動確認に失敗した場合は、バックアップから復元します。

ロールバック対象:

- ToolHub Core
- Runner
- Built-in Apps
- Heavy Runtime

ロールバック対象外:

- User Data
- ログ
- browser_profiles

