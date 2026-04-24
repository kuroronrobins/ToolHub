# Architecture

ToolHubは以下の層で構成します。

## Layers

| Layer | Path | Responsibility |
| --- | --- | --- |
| Bootstrap | `main.py` | プロジェクト入口、環境確認、ビルド済み実行ファイルまたは開発モード起動 |
| Launcher UI | `launcher/src` | 検索、カテゴリ、カード表示、説明モーダル、起動状態表示 |
| Tauri Backend | `launcher/src-tauri` | `apps/` のスキャン、manifest読込、runner呼び出し |
| Python App Runner | `runner/toolhub_runner` | runner種別選択、起動、イベント解釈、ログ保存、利用者向けエラー変換 |
| App Plugins | `apps/<app_id>` | 各アプリ本体、`app.yaml`、README、アイコン |
| Runtime Data | `data/` | ログ、ブラウザプロファイル、検索インデックス |

## Data Flow

1. `main.py` が起動方法を判断する。
2. Tauri backend が `apps/*/app.yaml` を読み込む。
3. React UI は表示用情報だけを受け取りカードを描画する。
4. 利用者が起動すると、Tauri backend が `runner/toolhub_runner/main.py` を呼び出す。
5. runnerが対象アプリを起動し、標準出力をイベントとして解釈する。
6. 実行ログは `data/logs/<app_id>/` に保存する。

## Responsibility Rules

- `main.py` に個別アプリ固有処理を書かない。
- Reactのメイン画面に `run.runner`、実行パス、依存関係、ログパスを表示しない。
- Tauri backendにサンプルアプリ名などの個別分岐を書かない。
- runner種別ごとの起動差分はPython runner層に閉じる。

## Search Extension Note

初回実装の検索はキーワードベースです。将来AI検索を追加する場合は、以下をベクトル化対象にできます。

- `search.keywords`
- `search.examples`
- `detail.description`
- 各アプリの `README.md`

検索インデックスの保存先は `data/search_index/` を想定します。

## Update Extension Note

初回実装では自動更新を行いません。将来は `release/manifest.json` を起点に、ランチャー本体と各アプリのバージョン確認、差分取得、署名またはハッシュ検証を追加できます。

