# App Manifest Spec

各アプリは `apps/<app_id>/app.yaml` を必ず持ちます。

## Example

```yaml
id: sample_csv_merger
name: CSV結合ツール

display:
  icon: icon.svg
  short_description: 複数のCSVを1つにまとめます。
  categories:
    - CSV
    - ファイル処理

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
```

## Required Fields

- `id`
- `name`
- `display.icon`
- `display.short_description`
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

メイン画面に以下は表示しません。

- バージョン
- 実行方式
- Python環境
- Web自動化の内部技術名
- 依存関係
- 実行パス
- ログ保存先

