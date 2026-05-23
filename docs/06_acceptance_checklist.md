# Acceptance Checklist

このチェックリストは初回実装の自己検収結果を記録する場所です。

## Real-Machine Verification

新しいPCで確認済み:

- [x] `python main.py --dev` でToolHubランチャーが起動する
- [x] ランチャーにアプリカードが表示される
- [x] 登録済み検証アプリがウィンドウを開く
- [x] CLI形式の登録済み検証アプリがrunner経由で `ok: true` を返し、ログを保存する
- [x] Web操作の登録済み検証アプリがrunner経由で `ok: true` を返し、ログを保存する
- [x] Web操作の検証アプリは、登録内容に応じてヘッドレス起動を正常として確認する

## Functional

- [x] プロジェクト直下で `python main.py` を実行するとToolHub起動を試行できる
- [x] `python main.py --dev` で開発モード起動を試行できる
- [x] `python main.py --release` でビルド済み実行ファイルのみ起動を試行できる
- [x] `python main.py --check` で環境確認ができる
- [x] ランチャーが起動できる
- [x] `apps/` 配下の `app.yaml` を自動検出できる構造がある
- [x] アプリカードが表示される
- [x] カードにアイコン、名称、短い説明、カテゴリを表示する実装がある
- [x] メイン画面に管理者向け情報が表示されない実装である
- [x] カテゴリで絞り込める実装がある
- [x] 検索で絞り込める実装がある
- [x] 説明を見るを押すと詳細が表示される実装がある
- [x] GUI形式の登録済み検証アプリを起動できる
- [x] CLI形式の登録済み検証アプリを起動できる
- [x] Web自動化の登録済み検証アプリを他アプリと同様のrunner経由で起動できる
- [x] エラー時に利用者向けメッセージが出る
- [x] 詳細ログが保存される

## UI

- [x] 利用者画面に内部技術名が出ていない実装である
- [x] メイン画面がシンプルである実装である
- [x] アイコン、名称、説明、カテゴリだけでアプリ概要が分かる実装である
- [x] 空状態がある
- [x] 検索結果なし状態がある
- [x] 起動中状態がある
- [x] エラー状態がある

## Maintainability

- [x] 新規アプリは `apps/` にフォルダ追加するだけで登録できる
- [x] `app.yaml` 仕様がdocsに記載されている
- [x] `docs/31_app_registration_app_authoring_guidelines.md` に従って新規アプリを作れる
- [x] ランチャー本体に個別アプリ固有処理がない
- [x] `main.py` に個別アプリ固有処理がない
- [x] `main.py` にUIロジックがない
- [x] Web自動化用の特殊処理が各アプリに散らばっていない
- [x] runner層に起動処理が集約されている

## Distribution

- [x] `main.py` がある
- [x] `scripts/dev_start.ps1` がある
- [x] `scripts/check_all.ps1` がある
- [x] `scripts/build_release.ps1` がある
- [x] `scripts/create_app_template.ps1` がある
- [x] READMEだけで開発開始の流れが分かる
- [x] `docs/` に設計資料がある
- [x] `release/manifest.json` の雛形がある

## Installer / Distribution

- [x] `ToolHub_Setup.exe` を正式配布物とする方針がREADMEに記載されている
- [x] インストール先がdocsに記載されている
- [x] ユーザーデータ保存先がdocsに記載されている
- [x] ユーザーがPython / Node.js / Rust / Web自動化用ランタイムを手動導入しない方針がdocsに記載されている
- [x] `scripts/package_installer.ps1` が存在する
- [x] `scripts/verify_release.ps1` が存在する
- [x] `release/manifest.json` が拡張されている
- [x] `release/app_manifest.json` が存在する
- [x] ToolHub Core / Runner / Apps / Runtime / User Data の更新単位がdocsに記載されている
- [x] per-user install方針がdocsに記載されている
- [x] 完全単一exeを正式方式にしない理由がdocsに記載されている
- [x] フォルダ配布を正式方式にしない理由がdocsに記載されている
- [x] 実際の `ToolHub_Setup.exe` が生成されている
- [ ] `ToolHub_Setup.exe` のコード署名が完了している

## Update Design

- [x] App Pack方式がdocsに記載されている
- [x] `app_manifest.json` の仕様がdocsに記載されている
- [x] sha256検証方針がdocsに記載されている
- [x] 更新前バックアップ方針がdocsに記載されている
- [x] ロールバック方針がdocsに記載されている
- [x] User Dataを更新で消さない方針がdocsに記載されている
- [x] Web自動化用ランタイムをHeavy Runtimeとして扱う方針がdocsに記載されている
- [x] `scripts/package_app_pack.ps1` でApp Pack zipとsha256を生成できる
- [x] `scripts/verify_release.ps1` でApp Pack sha256を検証できる
- [x] remote manifest を取得し、現在 version と比較できる
- [x] installer を `update_cache` へ download し、sha256 / size を検証できる
- [x] 検証済み `ToolHub_Setup_<version>.exe` だけを起動できる
- [x] updater safety の Rust unit tests で `http://` 拒否、unsupported scheme 拒否、local fixture copy、`update_cache` 境界、installer file name 制限、更新後 version 確認 annotation を検証している
- [x] GitHub Release verifier fixture tests で local installer の sha256 match / mismatch を検証している
- [x] GitHub Release への publish dry-run / remote verify / 実 publish 導線がある
- [x] GitHub Release endpoint check script で Release 存在、必須 asset、latest manifest URL を read-only で分類できる
- [ ] 実 GitHub Release endpoint と実 installer で update flow を確認する
- [ ] 実 GitHub Release `v0.1.0` を作成し、`latest/download/manifest.json` が 200 で取得できる状態にする。2026-05-24 の read-only 確認では `latest/download/manifest.json` は 404、`gh release view v0.1.0` は `release not found`。
- [ ] clean Windows VM / clean user profile で更新後 version 上昇を確認する
- [ ] ToolHub 内での展開、原子的置き換え、ロールバックの実処理は未実装

## Regression

- [x] `python main.py --check` が引き続き動作する
- [x] 既存`app.yaml`プラグイン方式が維持されている
- [x] メイン画面に管理者情報を出さない方針が維持されている
- [x] 利用者画面に内部技術名を出さない方針が維持されている
- [x] runner層に起動処理が集約されている
- [x] `main.py` は開発用ブートストラップに留まっている

## main.py Self-Check

- [x] `--help` が使い方を表示する
- [x] `--check` がフォルダ不足を検出する
- [x] Node.js/npm/Rust/cargo不足時に分かりやすいメッセージを出す
- [x] Tauriランチャー経由の起動ログが `%LOCALAPPDATA%\ToolHub\data\logs\launcher\` に保存され、runner直接実行時は `data/logs/` にフォールバックする
- [x] `--release` はビルド済み実行ファイルがない場合に開発起動へ進まない

## Release Build Flow

- [x] `build_release.ps1` が正式なリリース入口として整理されている
- [x] `build_release.ps1 -SkipBuild -AllowMissingBundle` が通る
- [x] `package_app_pack.ps1` がApp Packを生成できる
- [x] `prepare_runtime.ps1` がruntime雛形を作成できる
- [x] `package_installer.ps1` がstagingを作成できる
- [x] `package_installer.ps1` がbundle成果物を `release/dist_installer/` へ収集できる構造になっている
- [x] `verify_release.ps1` がmanifest / app pack / staging / runtimeを検証できる
- [x] `release/manifest.json` がinstaller file/type/sha256/sizeを保持する
- [x] `release/app_manifest.json` がApp Pack package/sha256/runtime要求を保持する
- [x] `npm run tauri build` でTauri標準のNSIS/MSI成果物を生成できた
- [x] 実際のTauri bundle成果物から `ToolHub_Setup_0.1.0.exe` を生成できた

## Environment

- [x] `check_all.ps1` がnode/npm/cargo/rustc/link.exe/cl.exeを確認する
- [x] Visual Studio Build Tools不足時の案内がある
- [x] `esbuild spawn EPERM` のトラブルシューティングがdocsにある
- [x] `package-lock.json` / `Cargo.lock` の管理方針がdocsにある
- [x] `launcher/package-lock.json` が存在する
- [x] `launcher/src-tauri/Cargo.lock` が存在する
- [ ] この環境で `link.exe` / `cl.exe` がPATH上にある

## Runtime

- [x] `runtime/README.md` がある
- [x] `runtime/app_envs/` が作成される
- [x] `runtime/web_automation_runtime/` が作成される
- [x] runtimeをGitに含めない方針がdocsと `.gitignore` にある
- [x] runtime同梱が未完了の場合、未完了としてdocsに明記されている
- [x] `runtime/python/python.exe` の実体が release build machine checkout にあり、`verify_runtime.ps1 -RequireRuntime` で検証されている
- [ ] `runtime/app_envs/<app_id>/` の実体が生成されている
- [x] Web自動化用ランタイム実体が release build machine checkout にあり、`verify_runtime.ps1 -RequireRuntime` で検証されている

## Beta Ready Checklist

この section は [docs/22_beta_installer_updater_plan.md](22_beta_installer_updater_plan.md) の Phase 0 で固定した Beta Ready 判定です。`[x]` は現在確認済み、`[ ]` は Beta Ready までに必要な未完了または未検証項目です。`manual check` は read-only script では確認できないため、Windows Sandbox、clean Windows user profile、または VM で確認します。

### Beta Blocker

- [x] [blocker] Beta 配布用 `ToolHub_Setup.exe` が current release build で生成され、`release/manifest.json` の installer `sha256` / `size` と一致する。
- [x] [blocker] `release/staging/installer_payload/staging_manifest.json` で installer payload を確認できる。
- [x] [blocker] `runner/`, `apps/`, `runtime/`, `config.default/`, `release/manifest.json`, `release/app_manifest.json`, `updater/`, `README.md` が配布物に含まれる。
- [ ] [blocker] `runtime/python/python.exe` が installer 同梱環境で使われる。
- [ ] [blocker] Web automation runtime が installer 同梱環境で使える。
- [x] [blocker] release build machine で `.\scripts\verify_runtime.ps1 -RequireRuntime` が pass する。
- [ ] [blocker] 利用者 PC に Python / Node.js / Rust / Tauri CLI / pip package を要求しないことを clean 環境で確認する。
- [x] [blocker] remote manifest fetch が実装されている。`check_updates_remote` で remote manifest を取得して現在 version と比較する。
- [x] [blocker] installer download が実装されている。`download_update_installer` で `%LOCALAPPDATA%\ToolHub\update_cache\` へ保存する。
- [x] [blocker] download 後の installer sha256 verify が実装されている。`download_update_installer` と `launch_verified_update_installer` で sha256 一致を必須にする。
- [x] [blocker] updater result log が実装されている。`%LOCALAPPDATA%\ToolHub\data\logs\updater\latest_update_result.json` に check / download / launch 結果を記録する。
- [x] [blocker] updater は `http://` を拒否し、Beta 本番 endpoint は `https://` 前提にする。`file://` / 相対パスは local test 専用。
- [x] [blocker] installer 起動時に `cachePath` を canonicalize し、`update_cache` 外、`.exe` / `.msi` 以外、`ToolHub_Setup` 以外の file name を拒否する。
- [x] [blocker] updater safety tests を `check_all.ps1` に組み込み、local fixture / unsafe source / unsafe path の退行を検出できる。

### Manual Check

- [ ] [manual check] `ToolHub_Setup.exe` による実インストール検証が済んでいる。
- [ ] [manual check] `%LOCALAPPDATA%\Programs\ToolHub\` に配置される。
- [ ] [manual check] `%LOCALAPPDATA%\ToolHub\` に user data が分離される。
- [ ] [manual check] 初回起動時に default config が copy され、既存 user config を上書きしない。
- [ ] [manual check] アンインストールで `%LOCALAPPDATA%\ToolHub\` の user data を削除しない。
- [ ] [manual check] インストール済み環境で app card が表示される。
- [ ] [manual check] 登録済み検証アプリがある場合、インストール済み環境から起動できる。
- [ ] [manual check] Beta 配布用の remote manifest endpoint を決定し、`updates.manifest_url` または同等設定から取得できる。
- [ ] [manual check] 実 endpoint / 実 installer で remote check、download、sha256 match / mismatch、cache 外 path 拒否、verified launch gating を確認する。

### Phase 1-B Installation Test Record

2026-05-09 時点の Phase 1-B 準備結果:

- [x] installer artifact preflight: `release/dist_installer/ToolHub_Setup_0.1.0.exe` は存在し、`release/manifest.json` の `sha256` / `size` と一致する。
- [x] staging manifest preflight: `release/staging/installer_payload/staging_manifest.json` は存在する。
- [x] GitHub Release publish target: `publish_github_release.ps1 -PrepareTargetOnly` で `release/github_release_targets/v<version>/` に upload 対象 asset と `release_target_manifest.json` を作成し、公開対象フォルダを publish 前に確認できる実装にした。
- [x] GitHub Release target verification: `verify_release_target_folder.ps1` で target folder 内の upload asset、`checksums.sha256.txt`、`release_target_manifest.json`、installer `sha256` / `size` を検証できる。
- [x] Beta / Pre-release remote verify: prerelease publish では `latest` ではなく tag 固定 `releases/download/<tag>/manifest.json` を検証対象にする。
- [ ] current PC install / uninstall: 未実施。現在の Windows profile には既存の `%LOCALAPPDATA%\ToolHub\` user data が存在するため、clean install 検証としては使わない。
- [ ] clean Windows user profile または VM での install / launch / uninstall / reinstall 検証: 未実施。

2026-05-10 時点の Windows Sandbox 検証フロー:

- [x] `scripts/beta_sandbox/ToolHub_Beta_Install_Test.wsb` を作成し、host repo を read-only、`scripts/beta_sandbox/results/` を writeable で Sandbox に mount する。
- [x] `scripts/beta_sandbox/sandbox_install_test.ps1` を作成し、Sandbox 内で installer preflight、開発ツール不在、install dir、payload、runtime、first launch、user data、log、uninstall 結果を JSON / Markdown に記録する。
- [x] `scripts/beta_sandbox/run_sandbox_test.ps1 -DryRun` で host 側 artifact / manifest / mount 設定を事前確認できる。
- [ ] Windows Sandbox 実行結果: 現在 PC は Windows Home / Core で `Containers-DisposableClientVM` が存在しないため未実施。Sandbox 起動と installer GUI 操作は人間確認を伴うため、`scripts/beta_sandbox/results/latest_sandbox_install_result.*` を確認してから完了判定する。
- [ ] GUI manual check: app card 表示と、登録済み検証アプリがある場合の起動確認を Sandbox 結果内の `manual_check` として記録する。

2026-05-10 時点の Windows Sandbox 不可時の代替検証フロー:

- [x] `scripts/beta_isolated_path/run_isolated_path_test.ps1` を作成し、現在プロセスだけ PATH を最小化して Python / pip / Node.js / npm / Rust / cargo / Tauri CLI を見えなくする補助検証を用意した。host の環境変数は恒久変更しない。
- [x] PATH 隔離テストは `LOCALAPPDATA` / `APPDATA` を ignored results 配下へ向けて ToolHub を起動できる。ただし host 上の補助検証であり、開発ツールなし PC の完全証明ではない。
- [x] `scripts/beta_vm/vm_install_test.ps1` を作成し、VirtualBox / VMware / Hyper-V / 手動 VM の共有フォルダから installer 実行、sha256 / size、install dir、user data、runtime、first launch、uninstall、user data 保持を JSON / Markdown に記録できるようにした。
- [x] PATH 隔離テスト実行結果: `scripts/beta_isolated_path/results/latest_isolated_path_result.json` で `overall_status=pass`。Python / pip / Node.js / npm / Rust / cargo / Tauri CLI は isolated PATH から見えず、ToolHub は15秒以上起動し、隔離された `LOCALAPPDATA` 配下に `%LOCALAPPDATA%\ToolHub\` 相当の user data dir を作成した。
- [ ] PATH 隔離テストの log / json 作成結果: warning。隔離 user data dir と `data/logs/` dir は作成されたが、初回起動だけでは `.log` / `.json` file は作成されなかった。
- [x] VM 検証パッケージ作成フロー: `scripts/beta_vm/prepare_vm_test_package.ps1` で `scripts/beta_vm/package/ToolHub_Beta_VM_Test/` に clean VM コピー用 package を作成できる。package / results は `.gitkeep` 以外 Git 管理しない。
- [x] VM 検証パッケージ生成結果: `ToolHub_Beta_VM_Test` package を生成済み。package 内 installer は `sha256=44855bbd6f4cb82ad1bf9d50116835c0407b1d201df54c3d7c141e288bf9aebf`, `size=290289588` で `release/manifest.json` と一致する。
- [x] VM 結果取り込み補助: `scripts/beta_vm/import_vm_test_result.ps1` で VM から戻した `latest_vm_install_result.json` の主要 check を表示できる。
- [ ] VM 本検証結果: 初回 VM 実行では ToolHub window は起動したが、アプリ一覧は 0 件で、期待 install dir `%LOCALAPPDATA%\Programs\ToolHub\` が存在しなかった。原因は未確定のため Phase 1-B は未完了。
- [x] VM 診断強化: `vm_install_test.ps1` は期待 install dir 固定ではなく、Start Menu shortcut、uninstall registry、running process、known install dirs から実 install location / 起動 exe / payload layout / launcher logs / `likely_failure_category` を記録する。
- [x] VM 原因調査結果: 初回 VM 結果から、実 install dir / 起動 exe は `%LOCALAPPDATA%\ToolHub\toolhub.exe` であり、予定していた user data root `%LOCALAPPDATA%\ToolHub\` と衝突していた。Tauri resources は `_up_\_up_` 配下に展開されていた可能性が高い。
- [x] VM 向け修正: Tauri resources を map 指定に変更し、NSIS hook で per-user install dir を `%LOCALAPPDATA%\Programs\ToolHub` に固定する。Rust root resolution は installed root と legacy `_up_\_up_` root を認識する。
- [x] dirty VM 追加診断: 新 installer hash は正しかったが、installer が `%LOCALAPPDATA%\ToolHub\apps\...` へ書き込もうとして失敗した。生成 NSIS では hook が初回 `SetOutPath $INSTDIR` の後に挿入されるため、hook 内で `$INSTDIR` を固定した後に `SetOutPath $INSTDIR` も再設定する。
- [x] VM 診断補強: `vm_install_test.ps1` は install 前の旧/new dir 残存、tester-recorded write error path、`dirty_vm_previous_install_residue` を JSON / Markdown に記録する。
- [ ] VM 再実行結果: 修正後に再生成した package を clean Windows VM にコピーし、`latest_vm_install_result.json` の `discovered_install_dirs`, `install_dir_user_data_collision`, `discovered_toolhub_exes`, `launched_toolhub_exe`, `payload_layout_summary`, `resource_root_candidate`, `likely_failure_category` を確認する。

現在 PC の read-only 事前確認:

| 項目 | 結果 | 備考 |
| --- | --- | --- |
| installer path | `release/dist_installer/ToolHub_Setup_0.1.0.exe` | `sha256=57b222c4c8f15ccf755ae55a1cb3abd8d0328a601b97afce857e390319993319`, `size=290362631` |
| expected install dir | `%LOCALAPPDATA%\Programs\ToolHub\` | 現在 profile では存在しないことを read-only で確認。 |
| expected user data dir | `%LOCALAPPDATA%\ToolHub\` | 現在 profile では存在することを read-only で確認。中身の変更、削除、installer 実行はしていない。 |
| install result | 未実施 | clean profile / VM で実施する。 |
| first launch | 未実施 | install 後に確認する。 |
| app card | 未実施 | install 後に確認する。 |
| validation app launch | 未実施 | 登録済み検証アプリがある場合に確認する。 |
| uninstall | 未実施 | install 後に確認する。 |
| user data preservation | 未実施 | uninstall / reinstall 後に確認する。 |

clean profile / VM で記録する結果:

| チェック | 期待結果 | 結果 |
| --- | --- | --- |
| `ToolHub_Setup_0.1.0.exe` 実行 | per-user install が完了する | 未実施 |
| install dir | `%LOCALAPPDATA%\Programs\ToolHub\` に `ToolHub.exe` と payload が配置される | 初回 VM では期待 dir が存在しなかった。診断強化後に実 install location を再確認する。 |
| first launch | ToolHub が起動する | 未実施 |
| user data dir | `%LOCALAPPDATA%\ToolHub\` が作成される | 未実施 |
| existing config preservation | 既存 `config/launcher.yaml` を上書きしない | 未実施 |
| app card | インストール済み環境で app card が表示される | 未実施 |
| validation app launch | 登録済み検証アプリがインストール済み環境で起動できる | 未実施 |
| bundled Python | PATH Python ではなく同梱 `runtime/python/python.exe` を使う | 未実施 |
| Web automation runtime | 同梱 `runtime/web_automation_runtime/` が使える | 未実施 |
| no user dev dependencies | Python / Node.js / Rust / Tauri CLI / pip package なしで動く | 未実施 |
| uninstall | ToolHub 本体をアンインストールできる | 未実施 |
| user data after uninstall | `%LOCALAPPDATA%\ToolHub\` が残る | 未実施 |
| reinstall | 再インストールできる | 未実施 |
| user data after reinstall | 既存 user data が残る | 未実施 |
### Warning / Follow-up

- [x] [warning] `scripts/report_release_readiness.ps1` の `beta_ready` section で blocker / warning / manual check / future_formal_only を確認できる。
- [ ] [warning] `verify_release.ps1 -Strict` の `runtime/app_envs/<app_id>` 方針を frozen-folder app と矛盾しないように整理する。

### Future / Formal Release Only

- [ ] [future/formal] `ToolHub_Setup.exe` の code signing が完了している。Beta では後回し可能だが formal release blocker。
- [ ] [future/formal] manifest signing または信頼済み配布経路が決まっている。
- [ ] [future/formal] backup / rollback が実装されている。
- [ ] [future/formal] App Pack 単位更新と runtime 単位更新の正式版方針が決まっている。

## Self-Inspection Result

今回の安定化作業で実行したコマンド:

- `python main.py --check`: OK
- `python -m unittest discover -s runner/tests`: 16 tests OK
- Built-in app launch checks were retired after built-in app source removal.
- `scripts/check_all.ps1`: OK。`icon.ico`、`bundle.icon`、`bundle.resources` の存在確認を含む
- `scripts/build_release.ps1 -SkipInstall`: OK。Tauri標準NSIS/MSI bundle生成、`release/dist_installer/ToolHub_Setup_0.1.0.exe` 収集、installer sha256/size更新まで通過
- `scripts/verify_release.ps1 -RequireInstaller`: OK。installer file / sha256 / size、App Pack sha256、`pack_manifest.json` を確認

成功したチェック:

- release manifest JSON検証
- app manifest JSON検証
- lock file存在確認
- App Pack生成
- App Pack sha256検証
- App Pack内部の `app.yaml` / `pack_manifest.json` 確認
- runtime雛形作成
- installer staging作成
- staging manifest作成
- Tauri bundle targetがNSIS/MSIを含むことの確認
- Tauri Windows icon `launcher/src-tauri/icons/icon.ico` の存在とICO header確認
- Tauri `bundle.icon` と `bundle.resources` の主要パス存在確認
- Tauri標準NSIS/MSI bundle生成
- `release/dist_installer/ToolHub_Setup_0.1.0.exe` 生成
- installer sha256 / size検証
- `main.py` 静的境界確認
- Python runner単体テスト
- TypeScript型チェック
- CLI / Web操作サンプルの重複初期status削除確認
- Tauriランチャー経由のログ保存先を `%LOCALAPPDATA%\ToolHub\data\logs\` に統一し、runner直接実行時は `data/logs/` にフォールバックする実装確認

環境不足または環境制約で実行できなかったチェック:

- `scripts/check_all.ps1` 内のVitest/Vite build: sandbox内では `esbuild` の `spawn EPERM` によりWARN。sandbox外の `npm run tauri build` ではVite build通過
- 実インストール / アンインストール検証: 未実施
- コード署名: 未実装

未完了項目:

- Python runtime実体同梱
- app_env実体生成
- Web自動化用ランタイム実体同梱
- 自動更新本体
- コード署名
- 実インストール / アンインストール検証

次に人間が確認すべき項目:

- OneDriveやセキュリティソフトの影響がないローカルパスで `npm test` / `npm run build` を再実行する
- インストール先が `%LOCALAPPDATA%\Programs\ToolHub\` になることを確認する
- 初回起動時にユーザーデータが `%LOCALAPPDATA%\ToolHub\` に作成され、既存設定を上書きしないことを実機で確認する
- runtime実体を配置し、`verify_release.ps1 -RequireRuntime -Strict` を通す
