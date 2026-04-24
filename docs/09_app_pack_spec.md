# App Pack Spec

App Packは内蔵アプリをアプリ単位で配布・更新するためのzipです。

## File Name

```text
release/app_packs/<app_id>-<version>.zip
```

## Zip Layout

```text
<app_id>/
├─ app.yaml
├─ main.py
├─ requirements.txt
├─ requirements.lock
├─ README.md
├─ icon.svg
└─ src/
```

`requirements.lock` と `src/` はアプリに必要な場合に含めます。

## Required Metadata

`release/app_manifest.json` には以下を持たせます。

- `version`
- `package`
- `sha256`
- `required_core`
- `required_runner`
- `required_runtime`
- `enabled`

`sha256` は `scripts/package_app_pack.ps1` 実行後に自動記入します。空の場合は未生成または未検証状態です。

## Compatibility

互換性条件:

- `required_core`
- `required_runner`
- `required_runtime`

例:

```json
{
  "version": "1.0.0",
  "package": "app_packs/sample_cli_app-1.0.0.zip",
  "sha256": "...",
  "required_core": ">=0.1.0",
  "required_runner": ">=0.1.0",
  "required_runtime": null,
  "enabled": true
}
```

## Packaging Command

全サンプルアプリ:

```powershell
.\scripts\package_app_pack.ps1
```

単一アプリ:

```powershell
.\scripts\package_app_pack.ps1 -AppId sample_cli_app
```

## Verification

```powershell
.\scripts\verify_release.ps1
```

検証内容:

- zipの存在
- sha256一致
- zip内部に `<app_id>/app.yaml` がある
- manifestに互換性条件がある

