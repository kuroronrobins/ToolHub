# Update Design

ToolHubは将来、ToolHub本体と内蔵アプリを安全に更新できる構造にします。

## Implementation Status

現時点で実装済み:

- `release/manifest.json` と `release/app_manifest.json` の雛形
- App Pack zip生成とsha256記録
- App Pack sha256検証
- runtime雛形作成
- 更新対象とUser Dataを分離する設計docs
- 非破壊の更新確認MVP
  - 起動後に読み取り専用の `check_updates_mvp` Tauri command を呼ぶ
  - `release/manifest.json` / `release/app_manifest.json` をローカル読み込みする
  - 現在の ToolHub version とローカルmanifest versionを比較する
  - app単位の更新候補は `release/app_manifest.json` の `enabled=true` かつ `apps/<app_id>/app.yaml` がある active app を主対象にする
  - `enabled=false` の disabled / stale entry は通常ユーザー向け更新候補に出さず、管理者向け診断・整理対象として扱う
  - 更新設定は `%LOCALAPPDATA%\ToolHub\config\launcher.yaml` のユーザー設定を優先し、存在しない場合だけ `config.default/launcher.yaml` にフォールバックする
  - `updates.source_url` / `updates.manifest_url` / `updates.url` が未設定の場合は `source_not_configured` として扱う
  - 通常ユーザー向け通知は `update_available` の場合だけ表示する
  - `source_not_configured` / `no_update` / `update_available` の全ステータス、参照した設定ファイル、manifest path、未実装操作は管理者画面の「更新確認MVP」で確認する

未実装:

- remote manifestの取得
- manifestのダウンロード
- 配布元URLから取得した remote manifest との比較
- 更新ファイルのダウンロード、展開、原子的置き換え
- 更新対象ファイルの削除
- 更新前バックアップとロールバックの実処理
- manifestやinstallerの署名検証

この文書は現時点では将来設計を含みます。現在動くのはローカルmanifestを読む非破壊MVPまでであり、自動更新本体、ダウンロード、展開、置換、削除、バックアップ、ロールバック、署名検証が動作することを意味しません。

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
8. 署名検証
9. 一時フォルダへ展開
10. `app.yaml` / manifest互換性確認
11. 更新前バックアップ作成
12. 原子的に置き換え
13. 起動確認
14. 失敗時ロールバック

現在の非破壊MVPは 1 と、ローカルmanifestに対する 3/4 の準備表示までです。通常ユーザー画面では `update_available` の場合だけ通知し、`source_not_configured` と `no_update` は管理者画面で確認する状態です。2、5以降、および remote manifest の取得・署名検証は未実装です。

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

現在の非破壊MVPでは、通常ユーザーには更新候補がある場合だけ「確認のみで、適用は管理者機能」であることを通知します。更新元未設定や更新候補なしは、通常ユーザーには毎回通知しません。

管理者画面では以下を確認できます。

- ToolHub Core: `0.1.0` -> `0.2.0`
- Runner: `0.1.0` -> `0.1.1`
- アプリ: `1.0.0` -> `1.1.0`
- Web自動化用ランタイム更新あり
- 参照した設定ファイル: user / default / missing
- ローカル `release/manifest.json` / `release/app_manifest.json` の参照path
- 未実装操作: ダウンロード、展開、置換、バックアップ、ロールバック、署名検証

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

