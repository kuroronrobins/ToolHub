# Add New App

## Template Script

```powershell
.\scripts\create_app_template.ps1 -AppId my_app -Name "業務ツール"
```

作成後、`apps/my_app/app.yaml` の説明、カテゴリ、起動方式を編集します。

## Manual Steps

1. `apps/<app_id>/` を作成する。
2. `app.yaml` を追加する。
3. `main.py` またはexeを配置する。
4. `requirements.txt`、`README.md`、`icon.svg` を追加する。
5. `python main.py --check` で構成を確認する。
6. ToolHubを起動し、カード表示と起動結果を確認する。

## Runner Selection

| App Type | `run.runner` | `run.mode` |
| --- | --- | --- |
| Python GUI | `python` | `gui` |
| CLI | `cli` | `cli` |
| exe | `exe` | `gui` or `background` |
| Web自動化 | `playwright_python` | `background` |

## Notes

- ランチャー本体にアプリ固有の分岐を追加しない。
- 表示名、説明、検索語は `app.yaml` に書く。
- 技術的な注意や依存関係は `admin` またはアプリREADMEに書く。

