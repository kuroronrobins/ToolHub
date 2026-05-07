# App Lifecycle Management

App Studio の Delete タブは、完全削除ではなく安全なライフサイクル管理MVPです。管理者セッション中だけ利用でき、`release/app_manifest.json` と `apps/<app_id>/` の状態を診断し、非表示、再表示、バックアップ付き削除、復元を行います。

## State

| State | 条件 | 通常の扱い |
| --- | --- | --- |
| `active` | manifest entry があり、`enabled=true` かつ `apps/<app_id>/app.yaml` がある | 通常表示・更新確認対象 |
| `disabled_with_source` | manifest entry があり、`enabled=false` かつ source がある | 非表示または未承認。再表示可能 |
| `disabled_stale` | manifest entry があり、`enabled=false` かつ source がない | 過去履歴・退避済み相当。通常検証では warn |
| `enabled_missing_source` | manifest entry があり、`enabled=true` かつ source がない | 危険状態。通常検証でも fail |
| `source_missing_from_manifest` | source はあるが manifest entry がない | 診断対象。MVPでは登録自動生成しない |
| `invalid_manifest` | `app.yaml` などの読み込みに失敗 | 診断対象 |

この分類は `scripts/diagnose_app_manifest.ps1`、release 検証、管理者GUIで同じ意味になるように揃えています。

## Operations

- 非表示: `release/app_manifest.json` の対象 entry を `enabled=false` にします。source がなくても実行できます。
- 再表示: `apps/<app_id>/app.yaml` が存在する場合だけ `enabled=true` にします。manifest entry がない source からの新規 entry 作成はしません。
- バックアップ付き削除: `apps/<app_id>/` を `backups/app_lifecycle/<timestamp>/<app_id>/app/` にバックアップしてから、active location から退避し、manifest entry は `enabled=false` にします。
- 復元: lifecycle backup の `app/` を `apps/<app_id>/` へコピーします。復元直後は必ず `enabled=false` のままで、管理者が別途「再表示」を実行します。

非表示、再表示、バックアップ付き削除、復元はいずれも `release/app_manifest.json` を完全削除しません。操作前後の manifest snapshot と metadata は `backups/app_lifecycle/<timestamp>/<app_id>/` に保存します。

## Safety

- バックアップ付き削除は、確認入力 `DELETE <app_id>` が一致する場合だけ実行します。
- 復元は、確認入力 `RESTORE <app_id>` が一致する場合だけ実行します。
- バックアップ作成が成功するまで `apps/<app_id>/` は退避しません。
- 復元時に `apps/<app_id>/` が既に存在する場合は上書きしません。
- 管理者操作ログには操作種別、app_id、backup path などを残します。secret 値は記録しません。
- App Pack zip は削除しません。

## Not Implemented

以下は今回のMVPでは未実装です。

- `release/app_manifest.json` から entry を完全削除する操作
- `release/app_packs/*.zip` の削除
- lifecycle backup の削除
- release 履歴の削除
- ユーザーデータの削除
- manifest entry がない source の自動登録
- backup からの上書き復元

完全削除は、配布履歴、App Pack、更新確認、監査ログ、復元可否に影響するため、別途公開I/Fと運用ルールを決めてから実装します。

## Strict Verification

通常検証では `disabled_stale` を warn に留めます。これは、非表示、削除準備、バックアップ退避済みの履歴を保持できるようにするためです。

Strict 検証や正式配布前の検証では、`disabled_stale` と `source_missing_from_manifest` は整理対象として fail にできます。`enabled_missing_source` は通常検証でも fail です。
