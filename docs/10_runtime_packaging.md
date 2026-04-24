# Runtime Packaging

ToolHubは、利用者が環境構築しなくても動作することを目標にします。

## Runtime Layout

```text
runtime/
├─ python/
├─ app_envs/
│  ├─ sample_gui_app/
│  ├─ sample_cli_app/
│  └─ sample_playwright_app/
└─ web_automation_runtime/
```

## Python Runtime

将来的にはPython embedded runtime、またはPython runnerのexe化を検討します。

候補:

- Python embedded distribution
- runnerをexe化
- appごとに固定envを生成

正式配布では利用者にPythonインストールを要求しません。

## App Environments

`runtime/app_envs/<app_id>/` にアプリごとの依存関係を固定できます。

初回改修ではenv生成までは未実装です。App Packとmanifestに互換性情報を持たせ、後からenv生成を追加できる構造にします。

## Web Automation Runtime

利用者向けには「Web自動化用ランタイム」と呼びます。

内部的にはWeb操作アプリに必要な重い依存を `runtime/web_automation_runtime/` に分離します。これにより、ToolHub Coreや軽量アプリの更新と、重いruntime更新を分けられます。

## Heavy Runtime Update

Heavy Runtimeは更新サイズが大きく、更新頻度もCoreやApp Packと異なります。

方針:

- manifestでruntime IDとversionを管理する。
- App Packは `required_runtime` で必要runtimeを宣言する。
- sha256検証後に一時フォルダへ展開する。
- 更新前にバックアップを作る。
- User Dataは更新対象にしない。

