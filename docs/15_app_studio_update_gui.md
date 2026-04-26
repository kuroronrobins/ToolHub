# App Studio 既存アプリ更新GUI MVP

## 目的

管理者画面の App Studio から、既存アプリ更新のMVPを実行できるようにします。これは publish や配布済みランチャーへの更新配信ではなく、既存 `app_id` を選び、CLI版 App Studio の import/apply/approve フローを再実行するための管理者向け入口です。

通常ランチャー画面には更新機能を出しません。React側の表示制御だけでなく、Rust/Tauri command 側で管理者セッションを必須にします。

## できること

- `apps/<app_id>/app.yaml` と `release/app_manifest.json` から登録済みアプリ一覧を取得する。
- App ID、表示名、現在version、enabled状態、runner、現在entryを表示する。
- 更新用Entryを手入力または参照ボタンで指定する。
- Version Bumpを `patch`、`minor`、`major`、`manual` から選ぶ。
- BuildModeと `GenerateLock`、`CreateAppEnv`、`RebuildAppEnv`、`BuildFrozenFolder`、`VerifyRuntime` を指定する。
- 更新用Preflightを実行する。
- `Suggest update`、`Apply update`、`Approve update` を実行する。
- current version / new version、execution、runtime、App Pack、enabled、次に必要な操作を表示する。

## Version Bump

簡易SemVer `x.y.z` を対象にします。

- `patch`: `1.2.3 -> 1.2.4`
- `minor`: `1.2.3 -> 1.3.0`
- `major`: `1.2.3 -> 2.0.0`
- `manual`: 入力値をそのまま使う

SemVerでないversionはpanicせずwarningにし、manual入力を促します。同一versionはwarning、古いversionはerrorです。

## 更新処理

更新MVPは専用publish処理ではなく、既存CLIの次の形を使います。

```text
tools/app_studio/main.py import --app-id <app_id> --version <new_version> --apply
```

既存 `apps/<app_id>/` と `release/app_manifest.json` のバックアップ、`enabled=false` 仮登録、App Pack生成、承認後の `enabled=true` はCLI版の方針を維持します。

## ログ

GUI更新操作は次へ記録します。

```text
%LOCALAPPDATA%\ToolHub\data\logs\admin\app_studio_gui.log
```

記録するイベント:

- `update_suggest started` / `update_suggest finished`
- `update_apply started` / `update_apply finished`
- `update_approve started` / `update_approve finished`

ログには `app_id`、`current_version`、`new_version`、`build_mode`、`approval_mode`、`exit_code`、`output_dir` を残します。APIキー、管理者パスワード、stdout/stderr全文、secret値は記録しません。

## 未実装

- 完全な差分ビューア
- 削除/アンインストールGUI
- publish GUI
- 配布済みランチャーへの自動更新配信
- manifest署名
- GitHub Releases / GitHub Pages 連携
