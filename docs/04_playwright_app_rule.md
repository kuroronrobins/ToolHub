# Web Automation App Rule

Web自動化アプリも利用者画面では通常の業務アプリとして扱います。

## User-Facing Rule

利用者向け画面には以下の内部技術名を表示しません。

- Playwright
- Chromium
- ブラウザ実行環境
- playwright install
- Python仮想環境
- technical runner

初回ログインなど利用者操作が必要な場合は、以下のように自然な案内を表示します。

> 初回設定が必要です。表示される画面でログインを完了してください。次回以降はそのまま使用できます。

## Internal Rule

内部的には `app.yaml` の以下で判定します。

```yaml
run:
  runner: playwright_python
```

特殊処理は `runner/toolhub_runner/playwright_runner.py` に集約します。

## Data Locations

- アプリ別プロファイル: `data/browser_profiles/<app_id>/`
- 実行ログ: `data/logs/<app_id>/`
- 詳細エラー: `data/logs/<app_id>/run_*.log`

## Error Handling

利用者向けには一般的なメッセージを返します。

> アプリの起動に失敗しました。時間をおいて再実行するか、管理者に連絡してください。

詳細ログにはモジュール不足、起動コマンド、標準エラーなどの技術情報を残します。

