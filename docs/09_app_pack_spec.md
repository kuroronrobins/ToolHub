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
├─ pack_manifest.json
├─ requirements.lock
├─ README.md
├─ icon.svg
└─ src/
```

`scripts/package_app_pack.ps1` はアプリフォルダ全体をコピーしてzip化し、`pack_manifest.json` を追加します。

パッケージ時に必須として確認するファイル:

- `app.yaml`
- `README.md`
- `requirements.txt`
- `icon.svg`

`main.py` はサンプルとPython系runnerの標準entryです。`app.yaml` の `run.entry` が `main.py` を指す場合は実行時に必要です。`requirements.lock` と `src/` はアプリに必要な場合だけ含めます。

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

## App Manifest Entry State

`release/app_manifest.json` の entry は、`enabled` と `apps/<app_id>/app.yaml` の有無で次の状態に分けます。

| State | Meaning | Normal verification | Strict / formal release |
| --- | --- | --- | --- |
| `enabled=true` and source exists | 通常表示・更新対象の active app | `app.yaml`、`version`、`package`、`required_core`、`required_runner` を必須確認 | 必須確認。App Packやruntime未整備も fail 対象 |
| `enabled=true` and source missing | 表示・更新対象なのに実体がない危険な不整合 | fail | fail |
| `enabled=false` and source exists | 未承認、非表示、または一時停止中の app | metadata と App Pack target を確認。App Pack 未生成は warn | fail 可能 |
| `enabled=false` and source missing | stale / removed / hidden history | warn。通常検証では履歴として残せる | fail。正式配布前に復元、維持理由の確認、または将来の完全削除フローで整理 |
| source exists but manifest missing | `apps/` にあるが配布manifestにない app | warn | fail |

通常検証で disabled stale entry を fail にしない理由は、App Studio の仮登録、非表示、削除準備、過去の検証履歴を保持できるようにするためです。ただし `enabled=true` の missing source は通常ランチャー表示や更新確認に影響するため、常に fail です。

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

manifest上の対象アプリ:

```powershell
.\scripts\package_app_pack.ps1
```

引数なしの場合は `release/app_manifest.json` の entry を対象にします。`enabled=false` かつ `apps/<app_id>/app.yaml` がない stale entry は skip し、`enabled=true` で source missing の entry は fail します。`-AppId` で明示指定した app に source がない場合も fail します。

App Studio のライフサイクル管理でバックアップ付き削除を行った app は、manifest entry を残したまま `enabled=false` かつ source missing の `disabled_stale` になります。この状態は通常の全体 App Pack 生成対象から除外されます。App Pack zip はライフサイクル操作では削除しません。正式配布前や Strict 検証では、復元するか、stale として維持する理由を確認するか、将来の完全削除フローで整理します。

単一アプリ:

```powershell
.\scripts\package_app_pack.ps1 -AppId sample_cli_app
```

## Verification

```powershell
.\scripts\verify_release.ps1
```

manifestとapp sourceの診断:

```powershell
.\scripts\diagnose_app_manifest.ps1
.\scripts\diagnose_app_manifest.ps1 -Strict
```

検証内容:

- zipの存在
- sha256一致
- zip内部に `<app_id>/app.yaml` がある
- zip内部に `<app_id>/pack_manifest.json` がある
- manifestに互換性条件がある
- active / disabled / stale / missing source の分類

