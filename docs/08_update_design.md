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
  - `config.default/launcher.yaml` の `updates.source_url` / `updates.manifest_url` / `updates.url` が未設定の場合は「更新元未設定」と表示する
  - 利用者向け通知と詳細ダイアログ、管理者画面の「更新確認MVP」で状態を表示する

未実装:

- manifestのダウンロード
- 配布元URLから取得した remote manifest との比較
- 更新ファイルのダウンロード、展開、原子的置き換え
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

現在の非破壊MVPは 1 と、ローカルmanifestに対する 3/4 の準備表示までです。2、5以降、および remote manifest の取得・署名検証は未実装です。

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

管理者向け詳細では以下のような差分を表示できる設計にします。

- ToolHub Core: `0.1.0` -> `0.2.0`
- Runner: `0.1.0` -> `0.1.1`
- アプリ: `1.0.0` -> `1.1.0`
- Web自動化用ランタイム更新あり

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

