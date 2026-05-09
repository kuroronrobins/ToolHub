# Beta Installer and Updater Plan

## 目的

ToolHub を早期にベータ展開するため、インストーラー化と ToolHub 全体アップデート機能の完成条件を固定する。

この文書は実装開始前の計画書であり、今後の Codex 実装依頼ではこの方針を基準にする。コード実装、manifest schema の破壊的変更、runtime / installer 実体の変更、ユーザーデータ削除はこの文書の対象外とする。

優先する成果は以下である。

- 利用者が `ToolHub_Setup.exe` だけで ToolHub を導入できる。
- 利用者 PC に Python / Node.js / Rust / Tauri CLI / pip package を要求しない。
- 配布後に ToolHub 本体を更新できる。
- `%LOCALAPPDATA%\Programs\ToolHub\` のインストール領域と `%LOCALAPPDATA%\ToolHub\` のユーザーデータ領域を分離する。
- ユーザーデータを壊さず、ベータ運用しながら継続改善できる。

## 背景

ToolHub には App Studio、App Pack、runtime 準備、release manifest、release script、更新確認 MVP が存在する。

一方で、早期ベータ展開に必要な完成条件はまだ分散している。特に以下は区別して扱う必要がある。

- `ToolHub_Setup.exe` を生成できることと、実インストール / アンインストール検証が済んでいること。
- runtime 準備 script があることと、承認済み runtime 実体が release build に同梱され検証済みであること。
- ローカル manifest 確認 MVP と、remote manifest 取得 / installer ダウンロード / 更新適用が動くこと。
- sha256 を manifest に記録できることと、配布後のダウンロードファイルを sha256 検証してから起動できること。

このため、まず Beta MVP の境界を狭く定義し、正式版向けの差分更新、App Pack 単位更新、runtime 単位更新、バックアップ、ロールバック、署名検証は段階的に扱う。

## 現状整理

### 実装済み

| 領域 | 現状 | 根拠 |
| --- | --- | --- |
| per-user user data 初期化 | Tauri 起動時に `%LOCALAPPDATA%\ToolHub\` 配下の `config/`, `data/logs/`, `data/browser_profiles/`, `data/search_index/`, `data/app_state/`, `backups/`, `update_cache/` を作成する。既存 `config/launcher.yaml` は上書きしない。 | `launcher/src-tauri/src/setup.rs` |
| runner への user data 伝搬 | Rust backend が runner 起動時に `TOOLHUB_USER_DATA_ROOT` を渡し、Python runner はその配下へ logs / browser profiles を保存する。 | `launcher/src-tauri/src/runner.rs`, `runner/toolhub_runner/log_manager.py` |
| 同梱 Python の優先探索 | `runtime/python/python.exe` がある場合は Rust backend がそれを優先し、ない場合だけ PATH の `python` / `py` へ fallback する。 | `launcher/src-tauri/src/runner.rs` |
| Tauri bundle resources | `runner/`, `apps/`, `runtime/`, `config.default/`, `release/manifest.json`, `release/app_manifest.json`, `updater/`, `README.md` を bundle resources に含める設定がある。NSIS は `currentUser` install。 | `launcher/src-tauri/tauri.conf.json` |
| App Pack 生成 / 検証 | `release/app_manifest.json` の schema 1、App Pack zip、sha256、`run.entry` / `display.icon` 検証の仕組みがある。 | `docs/09_app_pack_spec.md`, `scripts/package_app_pack.ps1`, `scripts/verify_release.ps1` |

### MVP実装済み

| 領域 | 現状 | Beta での扱い |
| --- | --- | --- |
| 更新確認 MVP / remote check | `check_updates_mvp` はローカル manifest 確認として維持し、`check_updates_remote` が remote manifest を取得して現在 version と比較する。 | Beta では remote check を起動時通知と管理者画面の基準にする。 |
| 通常利用者向け更新通知 | 起動後に更新確認し、`update_available` の場合だけ通知する。`source_not_configured` / `no_update` は通常利用者へ毎回出さない。 | Beta でもこの通知方針を維持する。 |
| 管理者向け更新確認 | 管理者画面で status、current / local / remote manifest version、参照 config、installer URL、sha256、cache path、download / launch result を表示する。 | 実 endpoint と実 artifact での検証は別途必要。 |
| installer packaging script | Tauri bundle から `ToolHub_Setup_<version>.exe` または `.msi` を収集し、installer sha256 / size を `release/manifest.json` に書く。 | 実インストール検証は別途必要。 |

### スクリプトまたは雛形のみ

| 領域 | 現状 | 注意 |
| --- | --- | --- |
| runtime 準備 | `prepare_runtime.ps1` は承認済み local archive を sha256 検証して `runtime/python/` と `runtime/web_automation_runtime/` に展開できる。 | script は runtime を自動ダウンロードしない。archive の承認、保管、release build machine での再現が必要。 |
| runtime 検証 | `verify_runtime.ps1 -RequireRuntime` で `runtime/python/python.exe` と Web runtime 実体を検証できる。 | 現在の checkout に runtime 実体があっても、Git 管理物ではないため正式同梱済みとは扱わない。 |
| release readiness report | `report_release_readiness.ps1` は App Pack / runtime / installer / local build blocker を分類できる。 | read-only report であり、release artifact は作らない。 |
| updater directory | `updater/README.md` は将来統合用の予約領域。 | 更新適用 executor は未実装。 |

### 設計のみ

| 領域 | 現状 |
| --- | --- |
| safe update flow | remote manifest 取得、更新内容表示、ダウンロード、sha256、署名、一時展開、互換性確認、バックアップ、原子的置き換え、起動確認、ロールバックの流れは `docs/08_update_design.md` に設計としてある。 |
| App Pack 単位更新 | App Pack zip / app manifest は将来単位更新を想定しているが、配布後に remote から取得して反映する処理はない。 |
| runtime 単位更新 | Heavy Runtime として分離する方針はあるが、runtime 単位の remote download / swap / rollback はない。 |
| 署名検証 | 正式版での追加項目として記載されているが、現時点では未実装。 |

### MVP実装済み / 未検証

- `check_updates_remote` による remote manifest の取得。
- remote manifest と現在 version の比較。
- `toolhub.installer.url` または `toolhub.installer.file` からの installer URL 解決。
- `download_update_installer` による installer の `update_cache` へのダウンロード。
- ダウンロード済み installer の sha256 検証。
- sha256 検証後の user confirmation と `launch_verified_update_installer` による installer 起動。
- check / download / launch の update result 永続記録。
- `http://` 更新元の拒否、`file://` / 相対パスの local test 扱い、`update_cache` 外 installer 起動拒否、`.exe` / `.msi` かつ `ToolHub_Setup` 名の installer だけを対象にする安全境界。

### 未実装

- 更新後の version 確認。
- バックアップ / ロールバック実処理。
- installer / manifest の署名検証。
- App Pack 単位更新、runtime 単位更新、完全自動更新。

### 未検証

- `ToolHub_Setup.exe` による実インストール。
- アンインストール。
- 新規 PC 相当で Python / Node.js / Rust / Tauri CLI / pip package なしに起動できること。
- `%LOCALAPPDATA%\Programs\ToolHub\` へ配置されること。
- `%LOCALAPPDATA%\ToolHub\` へ user data が分離されること。
- installer 同梱 runtime で sample app が起動すること。
- 再インストール / アップデート時に user data を消さないこと。
- updater が取得した installer の起動後に version が更新されること。

## ベータ版の最小完成条件

Beta Ready は、以下をすべて満たした状態とする。

1. `ToolHub_Setup.exe` だけで per-user install できる。
2. インストール先が `%LOCALAPPDATA%\Programs\ToolHub\` であることを実機で確認している。
3. user data が `%LOCALAPPDATA%\ToolHub\` に作成され、既存 user config を上書きしないことを確認している。
4. Python / Node.js / Rust / Tauri CLI / pip package を利用者 PC に要求しない。
5. release build に `runner/`, `apps/`, `runtime/`, `config.default/`, `release/manifest.json`, `release/app_manifest.json`, `updater/`, `README.md` が含まれる。
6. `runtime/python/python.exe` と Web automation runtime が release build machine で承認済み archive から sha256 検証付きで展開され、`verify_runtime.ps1 -RequireRuntime` が pass する。
7. 初回起動で app card が表示される。
8. 少なくとも `sample_gui_app` と `sample_playwright_app` をインストール済み環境から起動できる。
9. アンインストール後も `%LOCALAPPDATA%\ToolHub\` の user data を削除しない。
10. 起動時または管理者操作で remote manifest を取得できる。
11. remote manifest の version と現在 version を比較できる。
12. 最新 `ToolHub_Setup.exe` を `update_cache` へダウンロードし、manifest の sha256 と一致した場合だけユーザー操作で起動できる。
13. ダウンロード失敗、network timeout、sha256 mismatch、user cancel で既存インストールと user data が保持される。
14. update log / result を `%LOCALAPPDATA%\ToolHub\` 配下に記録できる。

正式版では、これに加えてコード署名、manifest 署名または信頼済み配布経路、バックアップ、ロールバック、App Pack / runtime 単位更新、CI release 連携を要求する。

## 対象外にする機能

Beta MVP では以下を対象外にする。

- 完全自動更新。
- ToolHub Core / runner / apps / runtime の差分更新。
- App Pack 単位の remote 更新適用。
- runtime 単位の remote 更新適用。
- 更新前バックアップとロールバックの実処理。
- publish GUI。
- App Studio の高度化。
- ユーザーデータ migration。
- `release/manifest.json` / `release/app_manifest.json` の破壊的 schema 変更。
- `app.yaml` 仕様の破壊的変更。
- runner 公開 I/F の破壊的変更。

コード署名は Beta MVP では後回しにできる。ただし、社内配布ポリシーやセキュリティ判断で署名が必須と判断された場合、署名なしベータ配布は停止条件とする。署名を後回しにする場合でも、installer ダウンロード後の sha256 検証は必須にする。

## インストーラー化の方針

正式配布方式はインストーラー型配布を維持する。Beta でも `ToolHub_Setup.exe` 1 個を利用者に配布する。

インストール先:

```text
%LOCALAPPDATA%\Programs\ToolHub\
```

user data:

```text
%LOCALAPPDATA%\ToolHub\
```

installer に含める配布単位:

| 単位 | 配置 | Beta での扱い |
| --- | --- | --- |
| ToolHub Core | `ToolHub.exe`, Tauri / React / Rust backend | installer で置き換える。 |
| runner | `runner/` | installer に含める。runner I/F は壊さない。 |
| built-in apps | `apps/` | installer に含める。App Pack 単位更新は将来。 |
| runtime | `runtime/python/`, `runtime/web_automation_runtime/` | Beta Ready では同梱必須。archive の sha256 検証と `verify_runtime.ps1 -RequireRuntime` を必須にする。 |
| default config | `config.default/` | 初回起動時だけ user config に copy。既存 user config は上書きしない。 |
| release manifest | `release/manifest.json`, `release/app_manifest.json` | 現在 version と同梱 payload の index。schema 1 互換を維持する。 |
| updater metadata | `updater/` | Beta Phase 2 / 3 で remote update 実装の置き場として使う。 |

installer 生成と実インストールは別の完了条件にする。

- 生成済み: `scripts/package_installer.ps1` が installer を収集し、`release/manifest.json` の `toolhub.installer.sha256` / `size` を更新する。
- 実インストール検証済み: clean user profile または VM で `ToolHub_Setup.exe` を実行し、配置、起動、sample app、uninstall、user data 保持を確認する。

## アップデート機能の方針

Beta MVP では、最新版 installer 再配布型アップデートを第一候補にする。

基本動作:

1. 起動時または管理者操作で更新確認を実行する。
2. `updates.source_url` / `updates.manifest_url` / `updates.url` のいずれかから remote manifest を取得する。
3. remote manifest の `toolhub.version` または `core.version` と現在 version を比較する。
4. 更新ありの場合、通常利用者には短い通知、管理者には詳細を表示する。
5. ユーザーが承認した場合だけ、最新版 `ToolHub_Setup.exe` を `%LOCALAPPDATA%\ToolHub\update_cache\` へダウンロードする。
6. remote manifest の installer `sha256` と一致することを確認する。
7. sha256 が一致した場合だけ installer 起動ボタンを有効にする。
8. installer 起動前に、ToolHub を閉じる必要があることを案内する。
9. 失敗時は既存インストールと user data を変更しない。

Beta の本番更新経路は `https://` を前提にする。`http://` は更新元として拒否し、`file://` と相対パスは mock manifest / local file による検証専用として扱う。local test source は update result に区別して記録する。

Beta MVP の更新対象:

| 対象 | Beta MVP | 理由 |
| --- | --- | --- |
| ToolHub Core | 更新対象 | installer 再配布で置き換える。 |
| runner | 更新対象 | installer に含めて Core と同時に置き換える。 |
| built-in apps | 更新対象 | installer に含めて Core と同時に置き換える。App Pack 差分更新はしない。 |
| runtime | 原則更新対象 | installer に含めて Core と同時に置き換える。ただし runtime 単体更新はしない。 |
| installer | 更新検知 / download 対象 | remote manifest の installer 情報を使う。 |
| user data | 更新対象外 | 削除、上書き、migration をしない。 |

## 更新方式の比較

| 案 | 内容 | 利点 | 欠点 / リスク | Beta 採用 |
| --- | --- | --- | --- | --- |
| A案: 最新インストーラー再配布型アップデート | remote manifest から最新版 installer を取得し、sha256 検証後にユーザー操作で起動する。 | 既存 installer 方針と合う。Core / runner / apps / runtime を一括更新できる。rollback や差分適用を Beta で実装しなくてよい。user data 境界を守りやすい。 | download / hash / installer 起動 / 再起動後 version 確認は新規実装が必要。installer が user data を消さない検証が必須。 | 採用。Beta MVP の第一候補。 |
| B案: ToolHub Core / runner / apps / runtime の差分更新 | 各 unit を個別に download / 展開 / 置換する。 | 将来の通信量削減と細かい更新に向く。 | 置換中の破損、atomicity、backup、rollback、互換性検査が必要。runtime 更新は重い。 | Beta では不採用。正式版候補。 |
| C案: App Pack 単位更新を先行 | App Pack zip だけを remote 取得して app 単位で更新する。 | App Studio / App Pack の既存設計を活かせる。Core 更新より小さい。 | ToolHub Core や runner の不具合を直せない。App Pack apply / rollback / enabled state / compatibility が必要。 | Beta 初期では不採用。Core 更新成立後に拡張。 |
| D案: 完全自動更新 | silent download / background apply / restart まで自動化する。 | 利用者負担が少ない。 | 署名、権限、失敗時復旧、監査ログ、社内ポリシー判断が必要。破損時の影響が大きい。 | 不採用。正式版後半候補。 |

推奨は A案である。Beta では「安全に最新版 installer を入手し、検証後にユーザー操作で起動する」までを完成させる。ToolHub 稼働中に自分自身を直接置き換える処理は行わない。

## 推奨アーキテクチャ

Beta MVP は以下の構成にする。

```text
ToolHub startup / admin action
  -> read user/default update config
  -> fetch remote release manifest over HTTPS
  -> compare current version
  -> show user notice or admin detail
  -> download ToolHub_Setup.exe to user_data/update_cache
  -> verify sha256 from remote manifest
  -> record update result
  -> user starts installer
  -> installer replaces install_dir
  -> user data remains outside install_dir
```

主要変更対象:

| 領域 | 変更候補 |
| --- | --- |
| Rust backend | `launcher/src-tauri/src/commands.rs` に remote manifest fetch、download、sha256 verify、update result 記録、installer 起動 command を追加する。 |
| React API | `launcher/src/lib/api.ts`, `launcher/src/lib/updateTypes.ts` に remote update 用 type / invoke wrapper を追加する。 |
| 通常 UI | `UpdateNotice`, `UpdateSummaryDialog` に download / verified / launch 状態を追加する。内部技術名は通常利用者には出さない。 |
| 管理者 UI | `UpdateManagementShell` に remote URL、HTTP status、manifest version、installer URL、sha256、cache path、failure reason、unsupported actions を表示する。 |
| scripts | `verify_release.ps1`, `report_release_readiness.ps1` に Beta Ready 向け report 項目を足す。必要なら mock remote manifest 検証 script を追加する。 |
| manifest | schema 1 互換を維持し、必要なら optional field として installer absolute URL や release notes URL を追加する。必須 field は増やさない。 |
| updater | `updater/` を将来の update metadata / helper 置き場として使う。Beta では direct overwrite executor は作らない。 |

remote manifest の installer URL 解決は後方互換を優先する。

- 第一候補: remote manifest の URL を基準に `toolhub.installer.file` を相対解決する。
- optional: `toolhub.installer.url` があればそれを優先する。
- 既存の `file`, `type`, `sha256`, `size` は維持する。
- schema 1 を読める既存実装を壊さない。

## ユーザーデータ保護方針

更新で触ってよい領域:

```text
%LOCALAPPDATA%\Programs\ToolHub\
```

更新で削除、初期化、上書きしてはいけない領域:

```text
%LOCALAPPDATA%\ToolHub\
```

保護対象:

- `config/`
- `data/logs/`
- `data/browser_profiles/`
- `data/search_index/`
- `data/app_state/`
- `backups/`
- `update_cache/` の必要な診断情報
- 管理者設定、AI 設定、将来の user-added app metadata

Beta MVP では user data migration を行わない。保存済み user data 形式の変更が必要になった場合は、実装せず判断待ちにする。

アンインストール検証では、ToolHub 本体が消えても `%LOCALAPPDATA%\ToolHub\` が保持されることを確認する。installer の uninstall option が user data 削除を提示する場合でも、Beta では既定で削除しない。

## manifest / sha256 / 署名の扱い

### manifest

`release/manifest.json`:

- ToolHub Core / runner / runtime / installer の index。
- `schema_version: 1` を維持する。
- `toolhub.installer.file`, `type`, `sha256`, `size` を Beta MVP で使う。
- remote 配布時は manifest URL を基準に installer file を相対解決する。
- optional `toolhub.installer.url` を追加する場合も後方互換とする。

`release/app_manifest.json`:

- App Pack index。
- Beta MVP では installer 一括更新に含まれる reference として扱う。
- App Pack 単位 remote 更新は正式版向け拡張に回す。

### sha256

Beta MVP では sha256 を必須とする。

- installer download 後、remote manifest の sha256 と一致しない場合は installer を起動しない。
- installer 起動直前にも sha256 を再計算し、download 後に差し替えられた file は起動しない。
- 起動対象は canonicalize 後に `%LOCALAPPDATA%\ToolHub\update_cache\` 配下であることを確認し、`..` などによる cache 外脱出を拒否する。
- Beta updater が起動できる installer は `.exe` / `.msi` かつ file name に `ToolHub_Setup` を含むものに限定する。別命名が必要な場合は正式な命名規則として判断してから変更する。
- mismatch は user data に update result として記録する。
- runtime archive 展開時も `prepare_runtime.ps1` の sha256 検証を必須にする。
- App Pack zip は `verify_release.ps1` で sha256 を検証する。

### 署名

コード署名と manifest 署名は正式版向け必須候補である。

Beta では、社内限定配布かつ配布元が管理された HTTPS であることを前提に、署名検証を後回しにできる。ただしこれはセキュリティ判断であり、配布先ポリシーが署名を要求する場合は Beta 配布を止める。

sha256 は改ざん検知の最低条件だが、manifest 自体が改ざんされた場合の真正性は保証しない。正式版では installer code signing、manifest signing、または GitHub Releases / 社内配布基盤など信頼済み経路の採用を検討する。

## runtime同梱方針

Beta Ready では runtime を installer に同梱する。

対象:

- `runtime/python/python.exe`
- Python 標準ライブラリと必要 DLL
- `runtime/web_automation_runtime/` の Web automation runtime
- 必要に応じた runtime manifest / README

方針:

- runtime binaries は Git に含めない。
- release build machine で承認済み local archive を用意する。
- archive は `-PythonSha256` / `-WebRuntimeSha256` で検証してから展開する。
- `prepare_runtime.ps1` は internet download をしない。
- `verify_runtime.ps1 -RequireRuntime` を Beta Ready の必須検証にする。
- App Studio の通常 frozen-folder app は `runtime/app_envs/<app_id>` を実行時 source of truth としない。
- runtime 単位更新は Beta MVP では実装せず、installer 一括更新で置き換える。

現在の checkout に runtime 実体が存在する場合でも、それは local release artifact であり Git 管理済み完成物ではない。Beta 判定では、release build machine 上で archive provenance、sha256、展開、`verify_runtime.ps1 -RequireRuntime`、installer 同梱、インストール後起動を確認する。

## UI / UX 方針

通常利用者向け:

- 更新がある場合だけ通知する。
- 更新元未設定や更新なしを毎回通知しない。
- 内部技術名、manifest path、sha256、runtime などの詳細は初期表示しない。
- 表示文言は「ToolHub を更新できます」「最新版を取得します」など利用者向けにする。
- download、検証、installer 起動はユーザー確認を挟む。
- network failure や hash mismatch は短く説明し、詳細は管理者向けログに残す。

管理者向け:

- config source、remote URL、manifest URL、current / latest version、installer file、sha256、download size、cache path を表示する。
- `source_not_configured`, `no_update`, `update_available`, `network_error`, `hash_mismatch`, `download_failed`, `verified` などの状態を診断できる。
- 未実装操作は未実装として表示する。
- release readiness report と update result を参照できるようにする。

## 管理者向け機能と通常利用者向け機能の分離

| 機能 | 通常利用者 | 管理者 |
| --- | --- | --- |
| 起動時更新確認 | 更新ありの場合だけ通知 | 状態と詳細を確認 |
| remote URL 設定 | 表示しない | 設定 / 診断対象 |
| manifest path / sha256 | 表示しない | 表示する |
| installer download | ユーザー確認後に実行 | 手動実行 / 再試行可能 |
| installer 起動 | sha256 OK 後にユーザー操作 | sha256 OK 後に起動 / cache path 確認 |
| failure detail | 短い説明 | HTTP status、exception、hash、path、log |
| App Pack / runtime 単位更新 | 対象外 | 将来拡張 |

Beta Phase 3 では、まず管理者画面で詳細つきの操作を完成させ、通常利用者向けには同じ backend を使って簡潔な導線を出す。

## 実装フェーズ

### Phase 0: 現状棚卸しとベータ完成条件の固定

目的:

- 既存 installer / runtime / update MVP / manifest / scripts の到達点を整理する。
- 何をもって Beta Ready とするか決める。

変更対象:

- docs
- acceptance checklist
- release readiness report の項目整理

実装内容:

- この文書を基準に、`docs/06_acceptance_checklist.md` へ Beta Ready checklist を追加する。
- `report_release_readiness.ps1` の出力が Beta Ready の blocker / warning を分けられるか確認する。
- 現行 docs の「確認済み」と「未検証」を整理する。

検証条件:

- `python main.py --check`
- `.\scripts\report_release_readiness.ps1`
- Markdown link / 見出し確認

完了条件:

- Beta Ready の必須条件が docs に固定されている。
- 未実装 / 未検証を実装済みのように書いていない。
- 破壊的変更を前提にしていない。

リスク:

- docs 間で runtime 実体の扱いがずれる。
- generated artifact が存在するだけで正式同梱済みと誤認する。

後続作業:

- Phase 1 の installer 実機検証へ進む。

Phase 0 実施状況:

- `docs/06_acceptance_checklist.md` に Beta Ready checklist を追加済み。
- `scripts/report_release_readiness.ps1` に read-only の `beta_ready` JSON section を追加済み。分類は `blockers`, `warnings`, `manual_checks`, `future_formal_only`。
- Phase 0 の report は artifact を生成せず、runtime 展開、installer build、App Pack 生成、user data 変更を行わない。
- Phase 1-A で installer artifact、staging manifest、runtime 検証は完了済み。Phase 1-B の実インストール / アンインストール検証と、Phase 2 の remote endpoint 判断は残っている。

### Phase 1: インストーラー Beta Ready

目的:

- `ToolHub_Setup.exe` だけで導入できることを実機で確認する。

変更対象:

- `scripts/build_release.ps1`
- `scripts/package_installer.ps1`
- `scripts/verify_release.ps1`
- `scripts/verify_runtime.ps1`
- Tauri bundle resources / installer 設定
- docs / acceptance checklist

実装内容:

- release build machine で承認済み runtime archive を展開する。
- `verify_runtime.ps1 -RequireRuntime` を必須化する。
- `build_release.ps1 -RequireRuntime` で installer を生成する。
- installer payload に `runner/`, `apps/`, `runtime/`, `config.default/`, `release/manifest.json`, `release/app_manifest.json` が入ることを確認する。
- 新規 PC 相当の環境で実インストールする。
- `%LOCALAPPDATA%\Programs\ToolHub\` と `%LOCALAPPDATA%\ToolHub\` の分離を確認する。
- 初回起動、sample app 起動、uninstall、user data 保持を確認する。

検証条件:

- `.\scripts\prepare_runtime.ps1 -PythonArchive <python.zip> -PythonSha256 <sha256> -WebRuntimeArchive <web-runtime.zip> -WebRuntimeSha256 <sha256>`
- `.\scripts\verify_runtime.ps1 -RequireRuntime`
- `.\scripts\build_release.ps1 -RequireRuntime`
- `.\scripts\verify_release.ps1 -RequireInstaller -RequireAppPacks -RequireRuntime -Strict`
- clean VM / clean user profile で installer を実行
- Python / Node.js / Rust / Tauri CLI がない環境で起動
- `sample_gui_app` / `sample_playwright_app` 起動
- uninstall 後に `%LOCALAPPDATA%\ToolHub\` が残ることを確認

完了条件:

- 利用者向け導入手順が `ToolHub_Setup.exe` だけで成立する。
- install / uninstall / first launch / sample app / user data separation が実機で確認済み。
- runtime 同梱が release build machine で再現可能。

リスク:

- Tauri NSIS の actual install path が想定と異なる。
- installer が resources を想定どおり配置しない。
- runtime size や Web runtime 依存で installer size が増える。
- security software による installer / runtime block。

後続作業:

- Phase 1-B の clean profile / VM 実機検証を完了し、並行して Phase 2 の remote manifest endpoint 判断へ進む。

Phase 1-A / 1-B 実施状況:

- Phase 1-A: `release/dist_installer/ToolHub_Setup_0.1.0.exe` を生成済み。`release/manifest.json` の installer `sha256` / `size` と一致し、`verify_release.ps1 -RequireInstaller -RequireRuntime` は pass。
- Phase 1-A: `release/staging/installer_payload/staging_manifest.json` を生成済み。payload に `runner/`, `apps/`, `runtime/`, `config.default/`, `release/manifest.json`, `release/app_manifest.json`, `updater/`, `README.md` が含まれる。
- Phase 1-B: 現在 PC で read-only 事前確認を実施。`%LOCALAPPDATA%\Programs\ToolHub\` は存在せず、`%LOCALAPPDATA%\ToolHub\` は既存 user data として存在する。
- Phase 1-B: 現在 PC は clean profile ではなく、既存 user data を壊すリスクを避けるため installer 実行、起動、uninstall、reinstall は未実施。
- Phase 1-B: Windows Sandbox 検証フローを `scripts/beta_sandbox/` に作成済み。host repo は read-only、結果 folder は writeable で mount し、Sandbox 内で preflight / install / launch / uninstall 結果を JSON / Markdown に記録する。
- Phase 1-B: 実 install / launch / sample app / uninstall / user data preservation は Windows Sandbox、clean Windows user profile、または VM の manual check として残す。Sandbox の installer / uninstaller UI と sample app 起動は人間確認を伴うため、検証結果を確認するまで完了済みとはしない。

### Phase 2: remote manifest による更新検知

目的:

- 配布後の ToolHub が remote manifest を取得し、現在 version と比較できるようにする。

変更対象:

- `config.default/launcher.yaml`
- `%LOCALAPPDATA%\ToolHub\config\launcher.yaml`
- `launcher/src-tauri/src/commands.rs`
- `launcher/src/lib/api.ts`
- `launcher/src/lib/updateTypes.ts`
- `launcher/src/components/UpdateNotice.tsx`
- `launcher/src/components/UpdateSummaryDialog.tsx`
- `launcher/src/components/admin/UpdateManagementShell.tsx`

実装内容:

- `updates.manifest_url` または `updates.source_url` の意味を固定する。
- remote manifest fetch command を追加する。
- timeout、HTTP error、invalid JSON、schema mismatch、version parse failure を状態として返す。
- remote manifest の `toolhub.version` / `core.version` と現在 version を比較する。
- 通常利用者には更新ありの場合だけ通知する。
- 管理者画面には remote URL、HTTP status、manifest version、比較結果、failure reason を表示する。
- network failure 時は既存環境を変更しない。

検証条件:

- local mock HTTP server または file server で remote manifest を返す。
- latest > current、latest = current、invalid manifest、404、timeout を確認する。
- 通常 UI が `update_available` のときだけ通知する。
- 管理者 UI が全 status を表示する。

完了条件:

- remote manifest が取得できる。
- 現在 version と remote latest version を比較できる。
- network failure が user data / install dir に影響しない。

リスク:

- config key の意味が既存 `updates.manifest` / `updates.app_manifest` と混同される。
- manifest URL を設定しない環境で通常利用者に不要通知が出る。
- remote manifest の optional field 拡張が後方互換を壊す。

後続作業:

- Phase 3 の installer download / sha256 verify へ進む。

### Phase 3: インストーラー再配布型アップデート

目的:

- 最新 installer を取得し、sha256 検証後にユーザー操作で起動できるようにする。

変更対象:

- Rust backend update command
- React update UI
- user data `update_cache`
- update log / result file
- remote manifest optional installer URL handling

実装内容:

- remote manifest から `ToolHub_Setup.exe` の URL を解決する。
- `%LOCALAPPDATA%\ToolHub\update_cache\` に download する。
- size が manifest と合わない場合は失敗にする。
- sha256 を計算し、manifest と一致しない場合は installer を起動しない。
- verified installer だけ user confirmation 後に起動する。
- installer 起動前に ToolHub を閉じる案内を出す。
- 失敗、cancel、hash mismatch、launch failure を update result に記録する。
- 既存 install dir と user data は updater 側で変更しない。

検証条件:

- 正常 installer download。
- sha256 mismatch。
- download interrupted。
- disk write failure。
- user cancel。
- installer launch 成功。
- installer launch 後に既存 user data が残ること。
- 更新後の ToolHub 起動で version が上がっていること。

完了条件:

- 最新 `ToolHub_Setup.exe` を download できる。
- sha256 OK の場合だけ user が installer を起動できる。
- 失敗時に既存環境と user data が保持される。

リスク:

- Windows が download 済み exe 起動を警告または block する。
- ToolHub 起動中に installer がファイル置換できない。
- unsigned installer の警告が利用者を混乱させる。
- manifest が compromise された場合、sha256 だけでは真正性を保証できない。

後続作業:

- Phase 4 の運用向け診断強化へ進む。

### Phase 4: ベータ運用向け検証強化

目的:

- ベータ運用中に update failure を診断できるようにする。

変更対象:

- update log / result schema
- admin update UI
- release readiness report
- docs / troubleshooting

実装内容:

- update check / download / verify / launch の結果を記録する。
- 前回 update result を管理者画面で見られるようにする。
- 再起動後の version 確認を追加する。
- failed result に retry action と管理者向け detail を含める。
- `report_release_readiness.ps1` に Beta update readiness を追加する。
- troubleshooting に network / hash mismatch / installer launch failure を追加する。

検証条件:

- 前回 successful update が記録される。
- failed update の原因を管理者が確認できる。
- version unchanged / changed を区別できる。
- report script が update readiness を分類できる。

完了条件:

- ベータ配布後の問い合わせに必要な update log が残る。
- release 前に update readiness を機械的に確認できる。

リスク:

- log に個人情報や token を残す。
- update_cache が肥大化する。

後続作業:

- Phase 5 の正式版拡張へ進む。

### Phase 5: 正式版向け拡張

目的:

- Beta MVP で避けた安全性 / 運用性の高い更新方式へ拡張する。

変更対象:

- manifest signing / installer code signing
- backup / rollback executor
- App Pack update executor
- runtime update executor
- CI / GitHub Releases / GitHub Pages / 社内配布基盤
- publish GUI

実装内容:

- installer と manifest の署名検証を追加する。
- 更新前バックアップとロールバックを実装する。
- App Pack 単位更新を実装する。
- runtime 単位更新を実装する。
- 完全自動更新の要否を判断する。
- CI で release artifact、sha256、manifest、signature を生成する。
- GitHub Releases / GitHub Pages または社内配布基盤から remote manifest を配信する。

検証条件:

- signature failure で更新停止。
- backup / rollback e2e。
- App Pack update e2e。
- runtime update e2e。
- CI release dry run。

完了条件:

- unattended または半自動更新を検討できる安全性がある。
- Core / App Pack / runtime の更新単位が分離されている。

リスク:

- 大規模リファクタになる。
- runner I/F や app.yaml 互換性に影響する。
- user data migration が必要になる。

後続作業:

- 正式版 release policy と security review へ進む。

## 各フェーズの完了条件

| Phase | 完了条件 |
| --- | --- |
| Phase 0 | Beta Ready 条件が docs に固定され、未実装 / 未検証が明確になっている。 |
| Phase 1 | `ToolHub_Setup.exe` 実インストール、初回起動、runtime 同梱、sample app、uninstall、user data 保持が実機で確認済み。 |
| Phase 2 | remote manifest fetch、version comparison、通常通知、管理者詳細、network failure handling が動く。 |
| Phase 3 | latest installer download、sha256 verify、user-confirmed launch、failure safe behavior が動く。 |
| Phase 4 | update log、update result、再起動後 version 確認、failure diagnosis、release readiness report 連携がある。 |
| Phase 5 | signature、backup、rollback、App Pack update、runtime update、CI / 配布基盤連携の設計と実装が分離されている。 |

## 検証計画

### docs / local check

```powershell
python main.py --check
```

```powershell
.\scripts\report_release_readiness.ps1
```

### installer / runtime

```powershell
.\scripts\prepare_runtime.ps1 `
  -PythonArchive <python.zip> `
  -PythonSha256 <sha256> `
  -WebRuntimeArchive <web-runtime.zip> `
  -WebRuntimeSha256 <sha256>
```

```powershell
.\scripts\verify_runtime.ps1 -RequireRuntime
```

```powershell
.\scripts\build_release.ps1 -RequireRuntime
```

```powershell
.\scripts\verify_release.ps1 -RequireInstaller -RequireAppPacks -RequireRuntime -Strict
```

### 実機 / VM

- Python / Node.js / Rust / Tauri CLI がない clean Windows 環境を用意する。
- `ToolHub_Setup.exe` を実行する。
- install path が `%LOCALAPPDATA%\Programs\ToolHub\` であることを確認する。
- first launch で `%LOCALAPPDATA%\ToolHub\` が作成されることを確認する。
- `config/launcher.yaml` が初回のみ copy され、既存設定が上書きされないことを確認する。
- app card が表示されることを確認する。
- `sample_gui_app` と `sample_playwright_app` を起動する。
- uninstall 後に `%LOCALAPPDATA%\ToolHub\` が保持されることを確認する。

### update

- mock remote manifest で `no_update` / `update_available` を確認する。
- invalid JSON、404、timeout、TLS failure を確認する。
- installer URL missing、size mismatch、sha256 mismatch を確認する。
- verified installer のみ起動できることを確認する。
- installer 起動後に user data が残ることを確認する。
- 更新後の version が上がっていることを確認する。
- update log / result が `%LOCALAPPDATA%\ToolHub\` 配下に残ることを確認する。

## リスクと停止条件

以下に該当する場合は実装せず、判断待ちとして扱う。

- `release/manifest.json` または `release/app_manifest.json` の互換性を壊す必要がある。
- 既存 `app.yaml` 仕様を壊す必要がある。
- runner の公開 I/F を壊す必要がある。
- 保存済み user data の形式変更が必要。
- user data 削除の可能性がある。
- runtime 同梱方針を大きく変更する必要がある。
- 管理者権限、署名、配布信頼性に関する重大判断が必要。
- Tauri installer の actual install behavior が想定と異なり、installer 方針変更が必要。
- 大規模リファクタが必要。
- 既存 docs と実装の差異が大きく、read-only 確認だけでは判断できない。

主要リスク:

- unsigned installer に対する Windows / security software warning。
- remote manifest が改ざんされた場合の真正性不足。
- installer 実行中に ToolHub が起動したままで置換に失敗する。
- runtime size 増加による download / install 時間増。
- update_cache の肥大化。
- App Pack / runtime の将来単位更新で Core との互換性検査が不足する。

## 将来拡張

- installer code signing。
- manifest signing。
- release notes / changelog 表示。
- GitHub Releases / GitHub Pages / 社内配布基盤連携。
- App Pack 単位更新。
- runtime 単位更新。
- update 前 backup。
- rollback。
- differential update。
- fully automatic update。
- publish GUI。
- update policy channel: `stable`, `beta`, `internal`。
- managed rollout: staged rollout, minimum supported version, forced update warning。

## 未決定事項

| 項目 | 判断待ち内容 | 推奨 |
| --- | --- | --- |
| remote manifest 配布場所 | GitHub Releases、GitHub Pages、社内 Web、ファイルサーバーのどれを使うか。 | Beta は管理された HTTPS endpoint を使う。 |
| code signing | Beta で署名なしを許容するか。 | 内部限定なら後回し可。ただし sha256 は必須。社内 policy が署名必須なら停止。 |
| manifest authenticity | sha256 だけで Beta を始めるか、manifest signing を先に入れるか。 | Beta は HTTPS + sha256、正式版で signing。 |
| installer URL schema | `toolhub.installer.file` の相対解決だけで足りるか、optional `url` を足すか。 | 相対解決を基本にし、必要なら optional `url` を追加。 |
| update 操作権限 | 通常利用者にも download / installer 起動を許可するか、管理者画面だけにするか。 | per-user install のため通常利用者操作を許可し、管理者画面で詳細診断を提供。 |
| runtime archive 承認 | Python runtime / Web runtime archive の作成元、保管場所、sha256 承認者。 | release build machine の手順として固定し、Git には含めない。 |
| uninstall 時 user data | uninstall UI で user data 削除 option を出すか。 | Beta 既定では削除しない。削除 option は正式版で検討。 |

## 次にCodexへ依頼する実装候補

実装開始時は、まず [24_beta_installer_updater_execution_handoff.md](24_beta_installer_updater_execution_handoff.md) を読む。ユーザー不在でも停止条件に当たらない限り、同 handoff の順番で実装、検証、報告まで進める。

1. Phase 1-B 検証: `scripts/beta_sandbox/README.md` に従い、Windows Sandbox、clean Windows user profile、または VM で `ToolHub_Setup_0.1.0.exe` の install / first launch / sample app / uninstall / reinstall / user data preservation を記録してください。
2. Phase 2 検証: 実 endpoint または mock manifest で `check_updates_remote` の `no_update` / `update_available` / fetch failure を確認してください。
3. Phase 3 検証: 実 installer または mock file で `download_update_installer` の download / size mismatch / sha256 mismatch / verified launch gating を確認してください。
4. Phase 4 実装: 再起動後 version 確認と failure diagnosis 表示を追加してください。check / download / launch result log と release readiness report 連携は実装済みです。
5. Phase 5 設計: signature、backup、rollback、App Pack 単位更新、runtime 単位更新、CI / GitHub Releases 連携の正式版設計を分割してください。
