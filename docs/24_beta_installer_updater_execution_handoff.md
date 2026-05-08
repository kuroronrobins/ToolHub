# Beta Installer / Updater Execution Handoff

この文書は、次の Codex 実装ターンで ToolHub の Beta Installer / Updater を途中で見失わず進めるための実行司令書である。

実装者は、ユーザーが席を外していても、停止条件に当たらない限り途中確認せず、実装、セルフレビュー、検証、報告まで進める。

## ゴール

ローカルで実装可能な Beta MVP を完了させる。

Beta MVP の中心方針は、`docs/22_beta_installer_updater_plan.md` の推奨どおり「最新版インストーラー再配布型アップデート」である。

完了時に満たすべき状態:

- `scripts/report_release_readiness.ps1 -Json` の `beta_ready.blockers` から、実装で解消可能な blocker が消えている。
- installer / runtime / remote manifest / download / sha256 / result log の docs と report が矛盾していない。
- 実機や外部配布 endpoint が必要な項目は `manual_checks` として残り、未検証であることが明記されている。
- `release/manifest.json` / `release/app_manifest.json` の既存 schema 互換を壊していない。
- `app.yaml` 仕様と runner I/F を壊していない。
- user data を削除、移動、初期化していない。

## 最初に読む順番

1. `AGENTS.md`
2. `docs/24_beta_installer_updater_execution_handoff.md`
3. `docs/22_beta_installer_updater_plan.md`
4. `docs/06_acceptance_checklist.md`
5. `docs/20_release_readiness_cleanup.md`
6. `scripts/report_release_readiness.ps1`
7. 実装対象に応じて、`launcher/src-tauri/src/commands.rs`, `launcher/src/components/admin/UpdateManagementShell.tsx`, `launcher/src/components/UpdateSummaryDialog.tsx`, `launcher/src/lib/api.ts`, `launcher/src/lib/updateTypes.ts`, `config.default/launcher.yaml`

## 作業開始時の必須 preflight

```powershell
python main.py --check
```

```powershell
.\scripts\report_release_readiness.ps1
.\scripts\report_release_readiness.ps1 -Json
```

`beta_ready.blockers` を実装 backlog として扱う。作業中に blocker を 1 つ解消するたび、report の期待結果を更新または確認する。

## 自律実行ルール

- ユーザー確認待ちで止まらない。合理的な既定値を選び、選んだ理由を final report に書く。
- ただし停止条件に当たる場合は実装せず止める。
- 外部 endpoint、署名 policy、承認済み runtime archive の実体など、人間判断や社内資産が必要なものは捏造しない。
- 実機 install / uninstall / clean PC 確認は、実行できなければ `manual_check` として残す。
- artifact 生成が必要な Phase に入るまでは、`release/`, `runtime/`, App Pack zip, installer binary を作らない。
- manifest schema を壊す変更はしない。拡張が必要なら optional field のみにする。
- app 固有処理を launcher にハードコードしない。

## 停止条件

以下に当たる場合は、実装を止め、理由、選択肢、推奨案、ユーザー判断事項を報告する。

- `release/manifest.json` または `release/app_manifest.json` の互換性を壊す必要がある。
- 既存 `app.yaml` 仕様を壊す必要がある。
- runner 公開 I/F を壊す必要がある。
- 保存済み user data の形式変更、削除、migration が必要。
- runtime 同梱方針を大きく変える必要がある。
- installer 署名、社内配布 policy、remote manifest 配布先の確定など、実装前に人間判断が必要。
- 大規模リファクタが必要。
- updater 本体が install dir を直接上書きする必要が出た。

## 実装順

### Step 1: report を実装 backlog として確定

目的:

- `beta_ready.blockers` が実装進捗の入口になるようにする。

やること:

- 現在の `beta_ready.blockers`, `manual_checks`, `future_formal_only` を確認する。
- report の分類が実装後の状態を表現できない場合だけ、read-only の範囲で `scripts/report_release_readiness.ps1` を拡張する。

完了条件:

- JSON で機械可読に分類できる。
- report は artifact を生成しない。

### Step 2: Phase 1 installer / runtime readiness

目的:

- installer payload と runtime 同梱の Beta Ready 判定を実装可能な範囲で固める。

やること:

- `verify_release.ps1` / `report_release_readiness.ps1` が required payload を検査できるか確認する。
- `runtime/python/python.exe` と Web runtime が local artifact として存在しても、installer 同梱検証済みとは扱わない。
- 実機 install / uninstall / `%LOCALAPPDATA%` 配置 / user data 保持 / sample app 起動は `manual_check` として残す。
- runtime archive の承認や取得が必要なら、捏造せず manual/external blocker として扱う。

検証:

```powershell
.\scripts\verify_runtime.ps1 -RequireRuntime
.\scripts\report_release_readiness.ps1 -Json
```

重い build は、次の実装依頼で明示的に Phase 1 artifact 生成まで進める場合のみ行う。

### Step 3: Phase 2 remote manifest fetch

目的:

- ローカル manifest MVP と remote manifest fetch を分離し、remote manifest を取得して version 比較できるようにする。

既定方針:

- 既存 `check_updates_mvp` を壊さず、新しい command または互換拡張で remote check を追加する。
- `updates.manifest_url` を優先し、なければ `updates.source_url` / `updates.url` を互換として扱う。
- remote manifest URL が未設定なら通常利用者へ通知しない。管理者画面と report では `source_not_configured` として表示する。
- network error、invalid JSON、schema mismatch、timeout は install dir / user data を変更しない。

変更候補:

- `launcher/src-tauri/src/commands.rs`
- `launcher/src/lib/api.ts`
- `launcher/src/lib/updateTypes.ts`
- `launcher/src/components/admin/UpdateManagementShell.tsx`
- `launcher/src/components/UpdateSummaryDialog.tsx`
- `launcher/src/components/UpdateNotice.tsx`
- `config.default/launcher.yaml`
- tests がある場合は該当 tests

検証:

```powershell
cd launcher
npm run build
```

Rust 変更時:

```powershell
cd launcher
cargo check
```

### Step 4: Phase 3 installer download / sha256 verify / user launch

目的:

- remote manifest の installer 情報から installer を `update_cache` へ download し、sha256 OK の場合だけ user action で起動できるようにする。

既定方針:

- installer URL は、`toolhub.installer.url` があれば優先する。
- `url` がない場合は、remote manifest URL を基準に `toolhub.installer.file` を相対解決する。
- `toolhub.installer.sha256` は Beta でも必須。
- download 先は `%LOCALAPPDATA%\ToolHub\update_cache\`。
- sha256 mismatch の場合、installer を起動しない。
- ToolHub 自身の install dir を updater が直接置き換えない。
- installer 起動は user confirmation 後のみ。

検証:

- mock remote manifest + small dummy payload で success / sha256 mismatch / 404 / timeout を確認する。
- installer 実体起動が危険または未生成の場合、launch path までは mock で検証し、実 installer 起動は manual_check として残す。

### Step 5: Phase 4 update result log / diagnostics

目的:

- ベータ運用中に update failure を診断できる状態にする。

既定方針:

- update result は `%LOCALAPPDATA%\ToolHub\` 配下に保存する。
- token、cookie、credential、個人情報を log に残さない。
- 管理者 UI で前回結果、失敗理由、cache path、manifest URL、sha256 result を確認できるようにする。
- 通常利用者には短い日本語説明だけを出す。

検証:

- success / failure / cancel / mismatch の結果が記録されること。
- report が updater result log 実装済みを分類できること。

## 推奨検証セット

最低限:

```powershell
python main.py --check
.\scripts\report_release_readiness.ps1
.\scripts\report_release_readiness.ps1 -Json
```

frontend / Tauri command を触った場合:

```powershell
cd launcher
npm run build
cargo check
```

release/readiness script を触った場合:

```powershell
$json = .\scripts\report_release_readiness.ps1 -Json | ConvertFrom-Json
$json.beta_ready
```

runtime / installer readiness を触った場合:

```powershell
.\scripts\verify_runtime.ps1 -RequireRuntime
.\scripts\verify_release.ps1
```

重い installer build:

```powershell
cd launcher
npm run tauri build
```

重い build は必要な Phase に入った場合だけ実行する。失敗が sandbox / 権限 / toolchain 由来なら、AGENTS.md の escalation ルールに従って再実行する。

## final report に必ず書くこと

- どの `beta_ready.blockers` を解消したか。
- 残った blocker / manual_check / future_formal_only。
- 実行した検証コマンドと結果。
- 生成していない artifact、未実施の実機確認。
- user data、release manifest、app manifest、runtime、App Pack zip を変更したかどうか。

## 次の実装依頼で使う一文

次のターンでは、以下の指示で開始する。

```text
docs/24_beta_installer_updater_execution_handoff.md に従って、Beta Installer / Updater の実装を Phase 1 から開始し、停止条件に当たらない限り Phase 4 まで自律的に進めてください。各 Phase で report の beta_ready blocker を減らし、検証まで実施してください。
```
