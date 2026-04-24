# Update Design

ToolHubは将来、ToolHub本体と内蔵アプリを安全に更新できる構造にします。

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
8. 一時フォルダへ展開
9. `app.yaml` / manifest互換性確認
10. 更新前バックアップ作成
11. 原子的に置き換え
12. 起動確認
13. 失敗時ロールバック

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

