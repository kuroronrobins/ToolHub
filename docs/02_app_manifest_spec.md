# App Manifest Spec

各アプリは `apps/<app_id>/app.yaml` を必ず持ちます。

## Example

```yaml
id: sample_csv_merger
name: CSV結合ツール

display:
  icon: icon.svg
  short_description: 複数のCSVを1つにまとめます。
  primary_category: Excel・表計算
  target_categories:
    - Excel
  tags:
    - 一括処理
  categories:
    - Excel
    - Excel・表計算
    - 一括処理

detail:
  description: >
    複数のCSVファイルを指定順に結合し、文字コードやヘッダー有無を指定して
    1つのCSVとして出力するアプリです。
  use_cases:
    - 複数CSVを1つにまとめたい
  inputs:
    - CSVファイル
  outputs:
    - 結合済みCSVファイル
  notes:
    - 出力文字コードは利用先システムに合わせて選択してください。

search:
  keywords:
    - CSV
    - 結合
  examples:
    - CSVをまとめたい

run:
  runner: python
  entry: main.py
  mode: gui

admin:
  version: 1.0.0
  owner: admin
  requirements: requirements.txt
  log_dir: logs

# Optional future distribution metadata.
# The current launcher UI does not display these fields.
runtime:
  required_runtime: python-embedded-toolhub-001
  app_env: sample_csv_merger
  requirements_lock: requirements.lock

distribution:
  mode: app_env
  package: app_packs/sample_csv_merger-1.0.0.zip
```

## Required Fields

- `id`
- `name`
- `display.icon`
- `display.short_description`
- `display.primary_category`
- `display.categories`
- `detail.description`
- `run.runner`
- `run.entry`
- `run.mode`

## Runner Values

| Value | Purpose |
| --- | --- |
| `python` | GUIまたは通常のPythonアプリ |
| `cli` | 標準出力中心のCLIアプリ |
| `exe` | 既にexe化済みの外部アプリ |
| `playwright_python` | Web自動化を行うPythonアプリ |

## Mode Values

- `gui`
- `cli`
- `background`

## UI Visibility

メイン画面は `display` の内容だけを表示します。`detail` は説明モーダル、`admin` は管理者向け折りたたみ領域で使います。

## Category Taxonomy

`display.categories` は過去互換用の表示配列です。新規登録やApp StudioのAI提案では、次の3軸を優先して設定します。利用者向けの左サイドバーとカードのカテゴリは、`display.target_categories` の先頭を優先して使います。対象カテゴリがないアプリだけ `display.primary_category` をフォールバック表示します。

- `display.primary_category`: 補助分類です。必須で、1つだけ指定します。例: `文書・PDF`, `Excel・表計算`, `帳票・会計`, `Web・ブラウザ`, `開発・管理`, `その他`
- `display.target_categories`: 自動化・連携の対象です。自動化アプリでは必須です。先頭の値が利用者向けカテゴリになります。例: `XCgate`, `COMPASS`, `3DX`, `Excel`, `PDF`
- `display.tags`: 細かい特徴です。例: `一括処理`, `ダウンロード`, `登録`, `置換`, `ID取得`, `ブラウザ操作`

`業務支援`, `業務効率化`, `業務ツール`, `自動化` のような汎用語は利用者向けカテゴリとして増やしません。COMPASS上で3DX文書を取得するようなアプリは `target_categories: [COMPASS, 3DX]` の順にし、同じCOMPASS操作としてまとまるようにします。既存候補にない新しい対象システムや用途を追加する場合は、App Studioで新カテゴリ候補としてレビューし、承認後にtaxonomyへ追加します。

`runtime` と `distribution` は将来の配布・更新管理用の任意フィールドです。初回実装では必須ではなく、利用者向けUIには表示しません。依存関係や実行方式の情報は管理者向けdocs、manifest、検収で扱います。

メイン画面に以下は表示しません。

- バージョン
- 実行方式
- Python環境
- Web自動化の内部技術名
- 依存関係
- 実行パス
- ログ保存先
