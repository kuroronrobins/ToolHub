# GitHub Release Updater Implementation Plan

## 目的

管理者が自分の環境で ToolHub 本体、内蔵アプリ、設定、表示、依存 runtime を更新したあと、その状態を GitHub Releases 上の最新版として公開できるようにする。

利用者側では、ToolHub 起動時に GitHub Releases 上の remote manifest を確認し、自分の ToolHub が古い場合は、複雑な操作なしで最新版へ更新できるようにする。

この文書は、実装途中に方針がぶれないようにするための実装基準である。既存の `docs/22_beta_installer_updater_plan.md` と `docs/24_beta_installer_updater_execution_handoff.md` を上書きするものではなく、GitHub Releases を実運用配布元にするための追加方針として扱う。

## 確認済みの現状

2026-05-23 時点の確認では、利用者側 updater の Beta MVP 実装は大部分が存在する。

- `check_updates_remote` は remote manifest を取得し、現在 version と比較できる。
- `download_update_installer` は installer を `%LOCALAPPDATA%\ToolHub\update_cache\` に保存し、manifest の sha256 と照合できる。
- `launch_verified_update_installer` は sha256 検証済み installer だけを起動できる。
- installer 起動時は `update_cache` 外、`.exe` / `.msi` 以外、`ToolHub_Setup` を含まない file name を拒否する。
- `http://` update source は拒否し、Beta 本番は `https://` 前提になっている。
- 起動時の通常画面は `checkUpdatesRemote()` を呼び、`update_available` の場合だけ更新候補を表示する。
- 管理者画面には更新確認、installer 取得、検証済み installer 起動の入口がある。
- `scripts/report_release_readiness.ps1` では `beta_ready_blockers: 0` まで到達している。

2026-05-23 の実装で、GitHub Releases を使う基本導線として次を追加した。

- `config.default/launcher.yaml` に本番用 `updates.manifest_url` を設定。
- `scripts/publish_github_release.ps1` で build、verify、tag、GitHub Release 作成 / upload、remote verify を実行できる。
- `scripts/verify_github_release_assets.ps1` で remote manifest、installer URL、sha256、size を検証できる。
- `scripts/check_github_release_endpoint.ps1` で GitHub Release の存在、必須 asset、latest manifest URL を read-only で分類できる。
- App Studio の `公開準備` タブで preflight、publish dry-run、release build / verify、remote verify、実 publish を実行できる。
- 通常利用者画面で、起動時の更新バナー、更新ファイル取得、sha256 検証済み installer 起動を実行できる。
- 前回 updater 結果と次回起動時の version 確認状態を管理者画面で確認できる。
- `scripts/test_github_release_verification.ps1` と `scripts/check_all.ps1` で、local manifest fixture、local installer sha256 match / mismatch、version mismatch、`http://` 拒否、publish dry-run を継続検証できる。
- Rust updater safety tests で、`http://` / unsupported scheme 拒否、local fixture copy、manifest 相対 installer URL 解決、`update_cache` 境界、installer file name 制限、更新後 version 確認 annotation を継続検証できる。

一方で、GitHub Releases を使う実運用には次が残っている。

- 実 endpoint / 実 installer での remote check、download、sha256 match / mismatch、verified launch gating は未完了。
- clean Windows VM または clean Windows user profile での install / update / uninstall / user data 保持は未検証。
- code signing と manifest signing は正式版向け future/formal 項目として残っている。

2026-05-24 の read-only 実 endpoint 確認では、`scripts/check_github_release_endpoint.ps1 -Json` により、`https://github.com/kuroronrobins/ToolHub/releases/latest/download/manifest.json` は `404 Not Found`、`gh release view v0.1.0 --repo kuroronrobins/ToolHub` は `release not found` と分類された。更新機能の実 endpoint 検証は GitHub Release 作成後に再実施する。

## 基本方針

Beta / 初期実装では、最新版インストーラー再配布型アップデートを採用する。

```text
管理者PC
  -> App Studio / 手動編集で ToolHub と apps を更新
  -> release build
  -> manifest / sha256 / size を確定
  -> GitHub Release に installer と manifest を公開

利用者PC
  -> ToolHub 起動
  -> remote manifest を確認
  -> 古い場合だけ更新案内
  -> installer を update_cache へ download
  -> sha256 検証
  -> 利用者操作で ToolHub_Setup.exe を起動
  -> installer が install dir を置き換える
  -> user data は保持
```

ToolHub 稼働中に updater が install dir を直接上書きしない。更新の実適用は、検証済み `ToolHub_Setup_<version>.exe` を利用者が起動し、installer に任せる。

## GitHub Releases の公開単位

GitHub Release には、最低限次を登録する。

| Asset | 必須 | 目的 |
| --- | --- | --- |
| `ToolHub_Setup_<version>.exe` | 必須 | 利用者が実行する最新版 installer。 |
| `manifest.json` | 必須 | ToolHub version、installer file / url、sha256、size の remote source of truth。 |
| `app_manifest.json` | 推奨 | 配布対象 app index の確認と将来拡張用。 |
| `checksums.sha256.txt` | 推奨 | 管理者と診断用の照合情報。 |
| release notes | 推奨 | 利用者に更新理由を示す。 |

remote manifest は既存 `release/manifest.json` の `schema_version: 1` 互換を維持する。必須 field を増やさない。GitHub Releases 向けに必要な情報は optional field として追加する。

推奨する optional field:

```json
{
  "toolhub": {
    "installer": {
      "file": "ToolHub_Setup_0.2.0.exe",
      "url": "https://github.com/<owner>/<repo>/releases/download/v0.2.0/ToolHub_Setup_0.2.0.exe",
      "sha256": "<sha256>",
      "size": 123456789
    }
  },
  "release_notes_url": "https://github.com/<owner>/<repo>/releases/tag/v0.2.0"
}
```

`toolhub.installer.url` がある場合はそれを優先する。ない場合は、remote manifest URL を基準に `toolhub.installer.file` を相対解決する既存方針を維持する。

## 配布 URL 方針

GitHub Release が public で利用者端末から認証なしに取得できる場合、default config には次のような URL を設定する。

```yaml
updates:
  channel: stable
  manifest_url: https://github.com/<owner>/<repo>/releases/latest/download/manifest.json
  manifest: release/manifest.json
  app_manifest: release/app_manifest.json
```

private repository の GitHub Release は、利用者端末から認証なしに取得できない可能性が高い。その場合は、GitHub Releases を管理者用の成果物保管場所にし、利用者向け remote manifest は GitHub Pages、社内 HTTPS server、または認証不要の配布 endpoint に置く。

Beta 本番 endpoint は `https://` を必須にする。`file://` と相対パスは local test 専用として扱い、update result に local test source として記録する。

## 管理者 publish フロー

管理者は自分の環境でアプリ追加、削除、更新、ToolHub 修正を行える。公開時は、その時点の checkout を release build し、GitHub Release に公開する。

初期実装では、UI に GitHub token を保存しない。まず PowerShell script で publish を確実にし、App Studio の `公開準備` タブはその preflight / 実行入口 / 結果表示として実装する。

実装入口:

```text
scripts/publish_github_release.ps1
scripts/verify_github_release_assets.ps1
```

`publish_github_release.ps1` の責務:

1. release version を決定する。
2. `launcher/package.json`、`launcher/src-tauri/Cargo.toml`、`launcher/src-tauri/tauri.conf.json`、`release/manifest.json` の version 整合を確認する。
3. `scripts/build_release.ps1 -RequireRuntime` または指定された release build command を実行する。
4. `scripts/verify_release.ps1 -RequireInstaller -RequireAppPacks -RequireRuntime -Strict` を実行する。
5. `release/dist_installer/ToolHub_Setup_<version>.exe` の sha256 / size と `release/manifest.json` を照合する。
6. `release/github_release_targets/v<version>/` を作成し、GitHub Release に upload する対象だけを集約する。
7. `release_target_manifest.json` に upload asset、source path、sha256、size、tag の対象 commit を記録し、管理者が公開対象フォルダを確認できるようにする。
8. `verify_release_target_folder.ps1` で target folder の `checksums.sha256.txt`、`release_target_manifest.json`、installer `sha256` / `size` を検証する。
9. Git tag `v<version>` を対象 commit に作成する。既存 local tag が別 commit を指す場合は停止する。
10. GitHub Release を作成または更新する。
11. installer、`manifest.json`、`app_manifest.json`、`checksums.sha256.txt` を upload する。
12. `https://github.com/<owner>/<repo>/releases/latest/download/manifest.json` から取得できることを確認する。

`gh` が使える場合は `gh release` を使う。`gh auth` が壊れているが Git credential は有効な場合があるため、必要なら GitHub Releases API fallback を用意する。

publish script は destructive な履歴 rewrite をしない。既存 tag / release がある場合は、上書きしてよいかを明示 option で制御する。

dry-run:

```powershell
.\scripts\publish_github_release.ps1 -DryRun -SkipBuild -SkipVerify -SkipTag -SkipRemoteVerify -AllowDirty
```

公開対象フォルダだけを作成して確認する場合:

```powershell
.\scripts\publish_github_release.ps1 -PrepareTargetOnly -SkipBuild -SkipVerify -SkipTag -SkipRemoteVerify -AllowDirty
```

実 publish の標準形:

```powershell
.\scripts\publish_github_release.ps1
```

GitHub Release の tag は既定で現在の `HEAD` を指す。別 commit / branch へ紐づける場合は `-TargetCommitish <commit-or-branch>` を使う。`-AllowDirty` は検証途中の Beta に限って許容し、正式 publish では build / verify 対象の変更を commit してから実行する。

公開済み remote manifest の確認:

```powershell
.\scripts\verify_github_release_assets.ps1 `
  -ManifestUrl https://github.com/kuroronrobins/ToolHub/releases/latest/download/manifest.json `
  -ExpectedVersion <version>
```

GitHub Release と必須 asset まで含めた read-only endpoint 確認:

```powershell
.\scripts\check_github_release_endpoint.ps1 -Json
```

remote installer まで download して sha256 を実証する場合:

```powershell
.\scripts\verify_github_release_assets.ps1 `
  -ManifestUrl https://github.com/kuroronrobins/ToolHub/releases/latest/download/manifest.json `
  -ExpectedVersion <version> `
  -DownloadInstaller
```

## App Studio 公開準備 UI

`launcher/src/components/admin/AppStudioShell.tsx` の `公開準備` タブを、次の段階で実装する。

### Phase A: Read-only preflight

- 現在 version を表示する。
- `release/manifest.json` の installer file / sha256 / size を表示する。
- `report_release_readiness.ps1 -Json` の `beta_ready` summary を表示する。
- GitHub remote、current branch、dirty files、tag 候補を表示する。
- publish に必要な未完了項目を blocker / manual check / future formal に分けて表示する。

### Phase B: Local release build launcher

- 管理者操作で release build script を実行する。
- 実行 log は管理者 log に記録する。
- build / verify の pass / fail を UI に返す。
- 生成 artifact の path、sha256、size を表示する。

App Studio の `公開準備` タブから `publish_github_release.ps1` の dry-run を実行できるようにする。dry-run は `-DryRun -SkipBuild -SkipVerify -SkipTag -SkipRemoteVerify -AllowDirty` 固定とし、Git tag 作成、Release 作成、asset upload、manifest 書き換えは行わない。

同じタブから `publish_github_release.ps1 -PrepareTargetOnly -SkipBuild -SkipVerify -SkipTag -SkipRemoteVerify -AllowDirty` を実行できるようにする。これにより `release/github_release_targets/v<version>/` に、実 upload 対象の installer、`manifest.json`、`app_manifest.json`、`checksums.sha256.txt` と、確認用 `release_target_manifest.json` が作成される。管理者はこのフォルダを見て、GitHub Release に載せるファイルと tag 対象 commit を publish 前に確認する。この target folder は生成物として `.gitkeep` 以外 Git 管理しない。

target folder 作成直後には `verify_release_target_folder.ps1` を自動実行する。ここで upload 対象 asset の存在、`checksums.sha256.txt`、`release_target_manifest.json`、installer `sha256` / `size` を検証し、失敗時は Git tag / GitHub Release 操作へ進まない。

Beta / Pre-release 検証では `latest/download/manifest.json` ではなく、`releases/download/<tag>/manifest.json` を remote verify 対象にする。GitHub の latest は prerelease を指さない可能性があるため、Beta では tag 固定 URL で remote manifest / installer sha256 を検証し、promote 後に stable `latest` を確認する。

同じタブから `build_release.ps1 -RequireRuntime` と `verify_release.ps1 -RequireInstaller -RequireAppPacks -RequireRuntime -Strict` を連続実行できるようにする。build / verify は release artifact を更新し得るため、実行結果と stdout / stderr を管理者向けに表示する。

### Phase C: GitHub Release publish

- 管理者操作で `scripts/publish_github_release.ps1` を実行する。
- Release URL、asset URL、manifest URL を表示する。
- publish 後に remote manifest を再取得して、現在 version より新しいこと、installer URL が解決できること、sha256 が存在することを確認する。

実 publish の前後確認として、App Studio の `公開準備` タブから `verify_github_release_assets.ps1 -Json` を実行できるようにする。既定では installer 本体を download せず、remote manifest の取得、schema、version、installer URL、sha256、size の確認に留める。結果は check 単位で表示し、必要時だけ checkbox で `-DownloadInstaller` 相当の installer download / sha256 実証を有効にする。

実 publish は App Studio の `公開準備` タブからも実行できるようにする。ただし誤操作防止のため、backend でも `confirmPublish` が true でない限り拒否する。dirty tree 許可、既存 Release 上書き、manifest の installer URL 書き込み、Draft / Pre-release、publish 後 installer download verify はすべて明示 checkbox とする。通常の publish は `build_release.ps1 -RequireRuntime`、`verify_release.ps1 -RequireInstaller -RequireAppPacks -RequireRuntime -Strict`、tag 作成、GitHub Release 作成 / upload、remote verify を script の標準順で実行する。

preflight の dirty tree 表示は、release / publish 境界、runtime / data / config、source / docs、other に分類する。特に `release/`、`runtime/`、`data/` が dirty な場合は、`-AllowDirty` を使う前に意図した変更かを確認する。

この UI は通常利用者には出さない。管理者認証済み画面でのみ実行できるようにする。

## 通常利用者向け更新 UI

通常利用者には、技術詳細を見せず、短く自然に更新したくなる構造にする。

表示方針:

- 更新なし: 通常画面では静かにする。
- 更新確認失敗: 通常画面では過度に警告しない。必要なら管理者画面へ残す。
- 更新あり: topbar の更新状態を目立つ tone にし、クリックで更新 dialog を開く。
- 更新あり: 起動後に通常画面へ更新バナーを表示し、「更新する」と「あとで」を出す。
- 更新 dialog には「更新を取得」「更新を開始」だけを出す。
- manifest URL、sha256、cache path などは通常 dialog の管理者向け details に閉じる。

バナーの「あとで」は同一セッション内の同一 current -> target version だけを抑制する。更新は必須にしないが、次回起動や別 version では再度自然に案内する。

ユーザー操作:

1. `更新を取得`
2. download と sha256 検証
3. `更新を開始`
4. `ToolHub_Setup.exe` 起動
5. ToolHub を閉じる案内

installer 起動前には、既存作業を保存し、ToolHub を閉じる必要があることを短く伝える。

## 更新後確認

installer 起動後、次回 ToolHub 起動時に前回 update result と現在 version を比較する。

記録する状態:

- download / launch の実行結果は既存の `status` に記録する。
- installer 起動時には `targetVersion` と、その時点の `currentVersion` を記録する。
- 次回起動時には `observedCurrentVersion` を付与し、`postUpdateStatus` として `version_confirmed` / `version_pending` / `not_launched` を返す。
- `sha256_mismatch`、`launch_failed`、unsafe path rejection などは既存の失敗 `status` と `failureReason` で追跡する。

記録先は既存方針どおり `%LOCALAPPDATA%\ToolHub\data\logs\updater\latest_update_result.json` を使う。token、cookie、credential、個人情報、query string 付き URL は記録しない。

管理者画面には、前回更新結果、対象 version、現在 version、失敗理由、再試行可否を表示する。

## 実装対象

主な変更候補:

| 領域 | 変更内容 |
| --- | --- |
| `config.default/launcher.yaml` | 本番 `updates.manifest_url` の設定。endpoint 未決定なら placeholder は入れず、docs / readiness 上で manual check に残す。 |
| `scripts/` | GitHub Release publish script、checksum 作成、remote manifest preflight。 |
| `launcher/src-tauri/src/commands.rs` | 更新後確認、result log 補強、必要なら publish preflight command。既存 update commands は壊さない。 |
| `launcher/src/lib/updateTypes.ts` | 通常利用者向け download / launch / post-update state の型追加。 |
| `launcher/src/components/UpdateSummaryDialog.tsx` | 通常利用者向けの更新取得 / 更新開始 UI。 |
| `launcher/src/components/admin/UpdateManagementShell.tsx` | 前回更新結果、remote endpoint 検証、failure diagnosis の表示強化。 |
| `launcher/src/components/admin/AppStudioShell.tsx` | `公開準備` タブの実装。 |
| `docs/` | GitHub Release 配布、publish 操作、検証手順の更新。 |

## 触らないもの

初期実装では次をしない。

- updater が install dir を直接上書きする処理。
- App Pack 単位 remote 更新。
- runtime 単位 remote 更新。
- 完全自動更新。
- user data migration。
- `release/manifest.json` / `release/app_manifest.json` の破壊的 schema 変更。
- `app.yaml` 仕様変更。
- runner 公開 I/F 変更。
- GitHub token の通常 UI 保存。

## 停止条件

以下に当たる場合は実装を止め、判断事項として報告する。

- private GitHub Release のまま利用者端末から認証なし取得が必要になる。
- code signing が社内 policy 上必須で、署名前 Beta 配布が許容されない。
- manifest signing を Beta 前に必須とする判断が出た。
- installer が user data を削除、移動、上書きする可能性がある。
- 保存済み user data の migration が必要になる。
- `release/manifest.json` または `release/app_manifest.json` の schema 互換を壊す必要がある。
- runner I/F または `app.yaml` 互換を壊す必要がある。
- 大規模リファクタが必要になる。

## 検証計画

### Local static / build verification

```powershell
python main.py --check
```

```powershell
.\scripts\report_release_readiness.ps1
.\scripts\report_release_readiness.ps1 -Json
```

launcher / Tauri 変更時:

```powershell
cd launcher
npm run build
```

Rust command 変更時:

```powershell
cd launcher\src-tauri
cargo check
```

release / package 変更時:

```powershell
.\scripts\build_release.ps1 -RequireRuntime
.\scripts\verify_release.ps1 -RequireInstaller -RequireAppPacks -RequireRuntime -Strict
```

### GitHub Release verification

- GitHub Release が作成または更新される。
- `manifest.json`、`app_manifest.json`、`ToolHub_Setup_<version>.exe` が asset として存在する。
- latest manifest URL から `manifest.json` を取得できる。
- remote manifest の `toolhub.version` が release version と一致する。
- installer URL が解決できる。
- remote manifest の sha256 / size が asset と一致する。

### Updater verification

- `no_update`
- `update_available`
- invalid manifest
- 404
- timeout
- `http://` refusal
- sha256 match
- sha256 mismatch
- size mismatch
- path traversal rejection
- `update_cache` 外 installer 起動拒否
- `ToolHub_Setup` 以外の installer 名拒否
- verified installer launch

### Installed environment verification

clean Windows VM または clean Windows user profile で確認する。

- `%LOCALAPPDATA%\Programs\ToolHub\` に install される。
- `%LOCALAPPDATA%\ToolHub\` に user data が分離される。
- 既存 `config/launcher.yaml` を上書きしない。
- Python / Node.js / Rust / Tauri CLI / pip package が利用者 PC に不要。
- app card が表示される。
- 登録済み検証アプリが起動する。
- updater で installer を取得し、sha256 検証後に起動できる。
- update 後に version が上がる。
- uninstall 後も `%LOCALAPPDATA%\ToolHub\` が保持される。

## 完了条件

初期 GitHub Release updater は、次を満たしたら完了とする。

- 管理者がローカル変更を release build し、GitHub Release に publish できる。
- GitHub Release 上の remote manifest が利用者端末から取得できる。
- 起動時に ToolHub が remote manifest を確認し、古い場合だけ更新案内を出す。
- 利用者が通常画面から installer を取得できる。
- sha256 一致時だけ installer 起動が可能。
- 失敗時に既存 install と user data が保持される。
- 管理者画面で update result と失敗理由を確認できる。
- `report_release_readiness.ps1` が残タスクを blocker / warning / manual check / future formal に分類できる。

## 実装優先順

1. GitHub Release の公開形式と `updates.manifest_url` を決定する。
2. `scripts/publish_github_release.ps1` を追加し、CLI で publish flow を成立させる。
3. remote manifest と GitHub asset の preflight / verification script を追加する。
4. 通常利用者向け update dialog に download / verified launch 導線を追加する。
5. update 後 version 確認と前回結果表示を追加する。
6. App Studio `公開準備` タブを read-only preflight から実装する。
7. `公開準備` タブから local build / GitHub publish を実行できるようにする。
8. clean Windows VM で install / update / uninstall を検証する。
9. code signing / manifest signing / App Pack 単位更新 / runtime 単位更新を正式版向けに分離設計する。

2026-05-23 時点では 1-7 と local verification fixture / local installer sha256 match-mismatch / publish dry-run / Rust updater safety tests の継続検証を実装済み。8 は実環境検証待ち、9 は正式版向け future/formal 項目として残す。
