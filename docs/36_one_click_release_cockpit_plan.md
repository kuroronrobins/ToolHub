# One-Click Release Cockpit Plan

この文書は、開発者が新規アプリ追加や ToolHub 本体更新を行ったあと、開発者用 ToolHub からワンクリックで GitHub Release に登録し、利用者へ更新配布できるようにする実装方針です。

## Goal

- 開発者は Python / dev 起動版 ToolHub から、現在のメイン作業ツリーを最新版として公開できる。
- 公開時に build、verify、commit、push、GitHub Release 作成、remote verify を一連の進捗として確認できる。
- 公開時に AI が更新内容の文案を作成し、開発者が確認・編集してから公開できる。
- 利用者は更新通知を邪魔に感じず、必要なときだけ更新内容を確認できる。
- 利用者向け更新内容には技術的な詳細を出さず、追加アプリ・使いやすさ・安定性など利用者に関係する内容だけを表示する。

## Implementation Status

2026-05-24 時点の実装開始範囲:

- `release/manifest.json` の `release_notes` を Rust updater が読み取り、React の更新通知と更新詳細ダイアログに渡す。
- メイン画面の更新通知は軽い要約だけを表示し、詳細は `更新内容を見る` から確認する。
- 管理者向け詳細は既存の折りたたみ領域に残し、利用者向け表示には commit、sha256、manifest、runtime などを出さない。
- Release Cockpit の公開パネルに、公開プロセスの段階表示、AI文案作成、GitHub Release notes 編集、manifest 用 `release_notes` JSON 保存を追加する。
- AI が利用できない場合も公開作業を止めず、編集用の fallback 文案を作成する。
- `一括公開を実行` で公開前確認、文案作成、manifest 保存、release target 作成、build / verify、dry-run、GitHub Release publish を順番に呼び出す。
- 実 publish は既存の確認 checkbox が有効な場合だけ実行し、誤クリックでは公開されない構造にする。

## Non-Goals

- インストール済み exe 版 ToolHub から GitHub Release を作成することは対象外。
- 一般利用者環境に Git、GitHub CLI、Node、Rust、release 権限を要求しない。
- ToolHub 自身による差分更新、原子的置換、署名検証、ロールバックはこの計画では実装しない。
- AI 文案を無確認で公開しない。必ず開発者の確認・編集を挟む。

## Operating Boundary

Release Cockpit は dev source root でのみ有効にする。

有効条件:

- `manifest::root_type` が dev source root である。
- Git worktree が存在する。
- `scripts/publish_github_release.ps1` が存在する。
- `node`, `npm`, `cargo`, `rustc`, `gh`, `git` が利用可能。
- `release/manifest.json` と `release/app_manifest.json` が存在する。

無効条件:

- installed resource root。
- user data root。
- GitHub Release 作成に必要な CLI / 認証がない。
- runtime 実体がない状態で `-RequireRuntime` release を作ろうとしている。

インストール済み exe では、管理者画面に Release Cockpit を表示してもよいが、操作は無効にし「開発者用 Python 起動で実行してください」と表示する。

## User Experience

### Developer Flow

管理者画面に `公開準備` または `Release Cockpit` タブを用意する。

主操作:

- `公開前チェック`
- `更新内容をAIで作成`
- `最新版を公開`

公開前に表示する情報:

- 次の version
- GitHub repository
- release tag
- 追加・更新・削除されたアプリ
- ToolHub 本体変更の有無
- release target folder
- 予定 installer 名
- 現在の Git branch / target commit

`最新版を公開` 実行中は phase ごとに状態を表示する。

Phase:

1. Preflight
2. Version Bump
3. Release Notes
4. App Pack
5. Build Installer
6. Verify Local Release
7. Commit
8. Push
9. GitHub Release
10. Remote Verify
11. Installed Update Detection Check

各 phase の表示:

- `pending`
- `running`
- `passed`
- `failed`
- `skipped`

失敗時は以下を表示する。

- 失敗 phase
- 失敗理由
- 実行した command
- 再実行可能か
- 手動対応が必要か
- 生成済み artifact / release target folder の位置

### User Flow

通常メイン画面では情報を多く出さない。

更新候補がある場合だけ、控えめな通知を出す。

例:

```text
新しいバージョンがあります
更新すると新機能や改善が反映されます
```

表示する操作:

- `更新する`
- `更新内容を見る`
- `あとで`

`更新内容を見る` を押したときだけ、利用者向け release notes を表示する。

利用者向け詳細に出す内容:

- 新しい version
- ひとこと概要
- 利用者向け highlights
- 追加されたアプリ
- 更新をおすすめする短い理由

利用者向け詳細に出さない内容:

- GitHub
- commit
- manifest
- sha256
- runner
- runtime
- App Pack
- PowerShell
- Rust / Node / Tauri
- 内部ファイルパス

## Release Notes Model

`release/manifest.json` に release notes を追加する。

```json
{
  "release_notes": {
    "schema_version": 1,
    "generated_by": "ai",
    "edited_by_admin": true,
    "user": {
      "title": "新しいバージョンがあります",
      "summary": "新しい業務アプリが追加され、より使いやすくなりました。",
      "highlights": [
        "会議メモ作成を支援するアプリを追加しました",
        "ファイル操作系のアプリを見つけやすくしました",
        "起動や更新確認がより安定しました"
      ],
      "recommended": true
    },
    "admin": {
      "summary": "Current main tree release with updated app catalog and updater fixes.",
      "changes": [
        "Added AgendaSnap app registration.",
        "Added 3DX / XCgate workflow apps.",
        "Updated updater GitHub Release fetch behavior."
      ],
      "validation": [
        "cargo test",
        "python main.py --check",
        "scripts/build_release.ps1 -SkipInstall -RequireRuntime",
        "remote manifest and installer sha256 verification"
      ]
    }
  }
}
```

互換性:

- `release_notes` がない古い manifest は許容する。
- 利用者 UI は notes がない場合、既定文言だけを表示する。
- notes の schema version が未知の場合、`user.summary` と `user.highlights` だけ best effort で表示する。

## AI Draft Policy

AI は文案候補を作るだけで、公開はしない。

入力に使う情報:

- Git diff summary
- `release/app_manifest.json` の差分
- 追加・更新された `apps/<app_id>/app.yaml`
- version 差分
- App Studio / ToolHub 本体の主要差分
- 前回 release tag
- 検証結果

ユーザー向け文案ルール:

- 技術用語を避ける。
- 1文目は利用者メリットを書く。
- 箇条書きは 3-5 個まで。
- アプリ追加がある場合は最優先で書く。
- 不安を煽らない。
- 「必ず更新してください」ではなく「更新をおすすめします」と書く。
- 内部実装やファイル名を書かない。

管理者向け文案ルール:

- 技術的変更を含めてよい。
- 追加アプリ、更新アプリ、ToolHub 本体変更、検証結果、artifact を含める。
- GitHub Release body に使える粒度にする。

AI draft は以下の形で保持する。

```json
{
  "release_notes_draft": {
    "created_at": "2026-05-24T00:00:00Z",
    "source": "ai",
    "user": {},
    "admin": {},
    "warnings": []
  }
}
```

保存先候補:

- 一時 draft: `data/app_studio/release_notes_drafts/<version>.json`
- 確定版: `release/manifest.json`

## One-Click Publish Behavior

`最新版を公開` は内部で既存 script を組み合わせる。

基本 command:

```powershell
.\scripts\build_release.ps1 -SkipInstall -RequireRuntime
.\scripts\publish_github_release.ps1 -Version <version> -Owner <owner> -Repo <repo> -Tag v<version> -ReleaseTitle "ToolHub v<version>" -ReleaseNotesFile <notes.md> -SkipBuild -SkipVerify -DownloadInstallerForRemoteVerify
```

Release Cockpit は raw command を直接 UI に貼るだけでなく、phase result として構造化して保持する。

```json
{
  "phase": "remote_verify",
  "status": "passed",
  "started_at": "...",
  "finished_at": "...",
  "command": "...",
  "summary": "remote manifest version and installer sha256 verified",
  "artifacts": []
}
```

公開完了条件:

- Git worktree が clean。
- `origin/develop` に push 済み。
- tag `v<version>` が target commit を指している。
- GitHub Release が作成済み。
- latest manifest が `<version>` を返す。
- latest installer URL が download できる。
- downloaded installer の size / sha256 が manifest と一致する。
- release target folder verification が pass。

## Versioning

既定は patch bump。

例:

- installed latest `0.1.3`
- next release `0.1.4`

UI では手動 override を許可するが、以下を禁止する。

- 既存 latest 以下の version。
- 既存 tag と同じ version。
- `release/manifest.json`, `Cargo.toml`, `tauri.conf.json`, `package.json` の version 不一致。

## Release Target Folder

公開対象は必ず以下へ集約する。

```text
release/github_release_targets/v<version>/
|- ToolHub_Setup_<version>.exe
|- manifest.json
|- app_manifest.json
|- checksums.sha256.txt
`- release_target_manifest.json
```

UI はこのフォルダを明示する。

管理者は公開前・公開後にこのフォルダを確認できる。

## Backend Commands

Tauri command として追加する候補:

- `release_cockpit_preflight`
- `release_cockpit_generate_notes_draft`
- `release_cockpit_save_notes_draft`
- `release_cockpit_plan_publish`
- `release_cockpit_run_publish`
- `release_cockpit_read_latest_run`
- `release_cockpit_open_target_folder`

既存 App Studio command と責務が近いため、実装場所は `launcher/src-tauri/src/app_studio_commands.rs` か、新規 `release_cockpit_commands.rs` を検討する。

推奨は新規 module:

```text
launcher/src-tauri/src/release_cockpit_commands.rs
launcher/src-tauri/src/release_cockpit_types.rs
launcher/src/components/admin/release/ReleaseCockpit.tsx
launcher/src/components/admin/release/ReleaseNotesEditor.tsx
launcher/src/components/admin/release/ReleaseProgressTimeline.tsx
```

既存 App Studio publish preflight と共有できる処理は helper 化する。

## Frontend Components

管理者側:

- `ReleaseCockpit`
- `ReleasePreflightPanel`
- `ReleaseNotesEditor`
- `ReleaseProgressTimeline`
- `ReleaseArtifactPanel`
- `ReleaseResultPanel`

利用者側:

- `UpdateBanner`
- `UpdateDetailDialog`
- `ReleaseNotesSummary`

メイン画面では `UpdateBanner` を小さく保つ。

`UpdateDetailDialog` は必要時だけ開く。

## Data Flow

```text
dev ToolHub
  -> preflight
  -> AI notes draft
  -> admin edits notes
  -> version bump
  -> build_release.ps1
  -> publish_github_release.ps1
  -> GitHub Release latest manifest
  -> installed ToolHub check_updates_remote
  -> update_available
  -> user opens update details
  -> user runs installer update
```

## Error Handling

Preflight で止める条件:

- installed root から実行している。
- Git worktree がない。
- `gh auth status` が失敗。
- `origin` が GitHub repo として解決できない。
- version が latest 以下。
- runtime が必要だが不足。
- release notes user summary が空。
- release notes highlights が空。
- release target folder の verify が失敗。

実行中に止める条件:

- build 失敗。
- local verify 失敗。
- commit 失敗。
- push 失敗。
- GitHub Release 作成失敗。
- remote verify 失敗。

再実行方針:

- Build / verify 失敗: 修正後に同じ version で再実行可。
- GitHub Release 作成前の失敗: 同じ version で再実行可。
- GitHub Release 作成後の upload / verify 失敗: release 状態を検出し、既存 release を使うか中止するかを明示する。
- latest が期待 version を返さない場合: release publish 状態と prerelease / draft 設定を確認する。

## Security and Privacy

- AI 入力に secret を含めない。
- Git diff から API key、token、password らしき値を検出したら AI draft と release を止める。
- release logs に credential を出さない。
- GitHub Release body に内部パスや個人情報を出さない。
- 利用者向け release notes に管理者向け情報を混ぜない。

## Implementation Phases

### Phase 1: Manifest and User Update Details

- `release/manifest.json` に `release_notes` を追加できるようにする。
- updater response に `release_notes.user` を含める。
- 利用者 UI に `更新内容を見る` dialog を追加する。
- release notes がない場合の fallback 文言を実装する。

Validation:

```powershell
cd launcher
npm run build
cd src-tauri
cargo test
```

### Phase 2: Developer Preflight and Progress UI

- Release Cockpit tab を追加する。
- dev source root 以外では disabled にする。
- preflight command を追加する。
- phase timeline UI を追加する。
- release target folder の存在と予定 asset を表示する。

Validation:

```powershell
python main.py --check
cd launcher
npm run build
```

### Phase 3: AI Release Notes Draft

- Git diff / app manifest 差分 / app.yaml 差分を集約する。
- AI 文案生成 command を追加する。
- user notes と admin notes を分けて編集できる UI を追加する。
- AI 無効時は手動入力だけで進められるようにする。

Validation:

```powershell
cd launcher
npm run build
cd src-tauri
cargo test
```

### Phase 4: One-Click Publish Orchestration

- version bump を UI から実行する。
- build / verify / commit / push / release / remote verify を phase 実行する。
- result log を保存する。
- 成功時に GitHub Release URL と target folder を表示する。

Validation:

```powershell
.\scripts\build_release.ps1 -SkipInstall -RequireRuntime
.\scripts\publish_github_release.ps1 -Version <version> -Owner <owner> -Repo <repo> -Tag v<version> -SkipBuild -SkipVerify -DownloadInstallerForRemoteVerify
```

### Phase 5: End-to-End Installed Update Confirmation

- 既存 installed ToolHub を 1 つ前の version にしておく。
- latest release を公開する。
- installed ToolHub 起動時に `update_available` が出ることを確認する。
- `更新内容を見る` が利用者向け notes を表示することを確認する。
- installer 起動後に version が上がることを確認する。

Validation:

```powershell
Get-Content "$env:LOCALAPPDATA\ToolHub\data\logs\updater\latest_update_result.json"
```

## Acceptance Criteria

- 開発者用 ToolHub から `最新版を公開` を実行できる。
- 進捗 phase が UI に表示される。
- 失敗時に phase と原因が分かる。
- AI がユーザー向け・管理者向け文案を分けて作る。
- 開発者が文案を編集してから公開できる。
- GitHub latest manifest に release notes が含まれる。
- インストール済み ToolHub が新 version を検出する。
- 利用者はメイン画面を邪魔されず、必要時だけ更新内容を確認できる。
- 利用者向け notes に技術的詳細が表示されない。
- remote installer size / sha256 verify が通る。
- release target folder が明確に残る。

## Open Decisions

- version bump の既定を常に patch にするか、UI で minor / patch を選べるようにするか。
- Release Cockpit を App Studio 配下に置くか、管理者画面の独立タブにするか。
- AI draft の保存先を `data/app_studio` にするか、`data/release_cockpit` に分けるか。
- GitHub Release body に admin notes 全文を出すか、短い summary と validation のみにするか。
- release notes の多言語対応を最初から schema に入れるか。

## Recommended Defaults

- version bump は patch。
- Release Cockpit は管理者画面の独立タブ。
- draft 保存先は `data/release_cockpit/release_notes_drafts/`。
- manifest 確定版は `release/manifest.json` の `release_notes`。
- GitHub Release body は admin notes を使う。
- 利用者 UI は user notes だけを使う。
- インストール済み exe では Release Cockpit を disabled にする。
