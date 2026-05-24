# VirtualBox Installer Validation Plan

この文書は、現在 ToolHub に登録されている有効アプリを含めた installer を作成し、VirtualBox 上の Windows にインストールして、ランチャー内から各アプリが正常に表示・起動できるかを確認するための方針です。

ファイル名には初期計画時の `two_app` が残っていますが、現行の確認対象は `release/app_manifest.json` の enabled app 全件です。

これは確認方針であり、実施済み証跡ではありません。実行結果は `scripts/beta_vm/results/latest_vm_install_result.json` / `.md` と、必要に応じて `docs/06_acceptance_checklist.md` に記録します。

## 0. 確認対象

現在の `release/app_manifest.json` で `enabled=true` のアプリを対象にします。2026-05-25 時点の read-only report では、enabled with source は 6 件です。

| app id | 表示名 | 起動方式 | runtime |
| --- | --- | --- | --- |
| `pdf_workbench` | `PDF Workbench` | `python_shared_env` / GUI | `python-shared-env:py313-win_amd64-runtime-37c71daf` |
| `app_20251123_excelbatchreplace` | `ExcelBatchReplace` | `python_shared_env` / GUI | `python-shared-env:py313-win_amd64-pywin32310-dd4d21f1` |
| `app_20260201_agendasnap` | `20260201 AgendaSnap` | `python_shared_env` / GUI | `python-shared-env:py313-win_amd64-flet0283-fletdesktop0283-cac27e37` |
| `run_3dx_create_ids` | `COMPASSのID一括取得` | `python_shared_env` / GUI | `python-shared-env:py313-win_amd64-playwright1550-27ead7db` |
| `run_3dx_download_pdfs` | `COMPASSの文書一括ダウンロード` | `python_shared_env` / GUI | `python-shared-env:py313-win_amd64-playwright1550-27ead7db` |
| `run_xcgate_upload` | `XCgate電子帳票登録` | `python_shared_env` / GUI | `python-shared-env:py313-win_amd64-playwright1550-27ead7db` |

確認の目的は、次の 3 点を分けて判定することです。

1. installer と payload が clean Windows VM に正しく配置される。
2. ToolHub ランチャーが有効アプリ全件のカードを表示し、各アプリを runner 経由で起動できる。
3. 各アプリの最小業務シナリオが、必要な外部前提を満たした状態で成功する。

## 1. Host 側事前確認

1. 変更対象を固定する。
   - `release/app_manifest.json` の有効アプリが上記 6 件であることを確認する。
   - 各 `apps/<app_id>/app.yaml` が存在することを確認する。
   - 各アプリの `requirements.lock` が存在することを確認する。
2. runtime の前提を確認する。
   - 現行有効アプリは `python_shared_env` 方式なので、`runtime/python/python.exe` と `runtime/envs/<env_id>/Lib/site-packages` が installer payload に含まれる必要がある。
   - VM 上で Python / pip package を別途導入して動いた場合は、配布検証としては成功扱いにしない。
3. 開発ツール依存を除外する前提を確認する。
   - VM には Python、Node.js、npm、Rust、cargo、Tauri CLI、pip package を事前導入しない。
   - AgendaSnap は Flet runtime、COMPASS / XCgate 系は Web automation runtime を使うため、shared env と Web automation runtime の両方を確認対象にする。
   - `ExcelBatchReplace` の業務機能まで確認する場合は、Microsoft Excel デスクトップ版だけを外部業務前提として明示する。Excel 未導入 VM では、Excel COM を使う本機能の成功判定は `Not run` とする。

## 2. Host 側 build / package

Host のリポジトリ直下で順に実行します。

```powershell
python main.py --check
```

```powershell
.\scripts\check_all.ps1
```

```powershell
.\scripts\package_app_pack.ps1
```

runtime 実体を installer に含める検証では、placeholder ではなく実体 runtime を必須にします。

```powershell
.\scripts\verify_runtime.ps1 -RequireRuntime
```

installer を作成します。

```powershell
.\scripts\build_release.ps1 -RequireRuntime
```

作成後、配布物を厳格に確認します。

```powershell
.\scripts\verify_release.ps1 -RequireInstaller -RequireAppPacks -RequireRuntime -Strict
```

ここで失敗した場合は VM 検証へ進みません。失敗内容を「build / package 未完了」として扱い、installer を手動修正して VM に持ち込まないでください。

## 3. VM 検証 package 作成

VirtualBox に渡す package は既存スクリプトで作成します。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\beta_vm\prepare_vm_test_package.ps1 -DryRun
```

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\beta_vm\prepare_vm_test_package.ps1
```

作成先:

```text
scripts\beta_vm\package\ToolHub_Beta_VM_Test\
```

この folder 全体を VirtualBox の共有フォルダ、または VM 内のローカルフォルダへコピーします。VM 内では installer、manifest、script を編集しません。

## 4. VirtualBox VM 準備

1. clean Windows VM を用意する。
   - 可能なら snapshot を取得してから開始する。
   - 以前の ToolHub インストール残骸がある VM は clean proof ではなく dirty rerun として扱う。
2. 開発ツールがない状態を維持する。
   - Python、Node.js、npm、Rust、cargo、Tauri CLI、pip package を導入しない。
3. 業務アプリ確認用のサンプルを用意する。
   - `PDF Workbench`: 破壊してよい小さな PDF サンプルと出力先フォルダを用意する。
   - `ExcelBatchReplace`: 破壊してよい Excel サンプル、テンプレート、バックアップ先を用意する。業務機能まで確認する場合は Microsoft Excel デスクトップ版を用意する。
   - `AgendaSnap`: 外部 API key や音声入力が必要な機能は `Not run` にし、GUI 起動と設定画面遷移までを最小確認にできる。
   - `COMPASS` / `XCgate` 系: 本番認証情報や業務サイト接続が必要な処理は `Not run` にし、GUI 起動、設定読込、ログイン前までの安全な画面遷移を最小確認にできる。
4. VM の結果 folder を共有または後で host へコピーできるようにする。

## 5. VM 内 installer 実行

VM 内の package root で実行します。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\vm_install_test.ps1 -SharedRoot . -ResultsDir .\results -PauseForManualGuiChecks
```

確認する主な項目:

1. installer の `sha256` / `size` が `release\manifest.json` と一致する。
2. インストール先が `%LOCALAPPDATA%\Programs\ToolHub\` になっている。
3. user data 先が `%LOCALAPPDATA%\ToolHub\` として分離されている。
4. install dir と user data dir が衝突していない。
5. payload に `runner\`、`apps\`、`runtime\`、`config.default\`、`release\manifest.json`、`release\app_manifest.json` が含まれる。
6. `runtime\envs\py313-win_amd64-runtime-37c71daf\Scripts\python.exe` が存在する。
7. `runtime\envs\py313-win_amd64-pywin32310-dd4d21f1\Scripts\python.exe` が存在する。
8. ToolHub がデスクトップショートカットまたはスタートメニューから起動する。
9. `%LOCALAPPDATA%\ToolHub\data\logs\` にログが作成され、致命的な launcher / runner error がない。

## 6. ランチャー表示確認

ToolHub 起動後に、利用者画面で次を確認します。

1. アプリカードが有効アプリ全件分表示される。
2. `PDF Workbench`、`ExcelBatchReplace`、`20260201 AgendaSnap`、`COMPASSのID一括取得`、`COMPASSの文書一括ダウンロード`、`XCgate電子帳票登録` が表示される。
3. 検索やカテゴリ絞り込み後も、対象アプリを選択できる。
4. 管理者向け内部情報や不要な技術詳細が利用者画面に露出していない。

アプリが 0 件、または想定外の件数で表示された場合は、アプリ起動確認へ進まず、`release/app_manifest.json`、installed payload の `apps\`、launcher log、`likely_failure_category` を確認します。

## 7. アプリ別起動確認

### 7.1 PDF Workbench

1. ToolHub の `PDF Workbench` カードから起動する。
2. GUI が表示されることを確認する。
3. runner / shared runtime / module import のエラーが表示されないことを確認する。
4. 用意した小さな PDF サンプルで、アプリ側の最小非破壊操作を 1 件実行する。
5. 期待した出力または処理結果が得られることを確認する。
6. `%LOCALAPPDATA%\ToolHub\data\logs\` とアプリ側ログに、致命的なエラーが残っていないことを確認する。

PDF サンプルでの実操作を行わなかった場合は、`起動確認のみ完了 / 業務機能は Not run` と記録します。

### 7.2 ExcelBatchReplace

1. ToolHub の `ExcelBatchReplace` カードから起動する。
2. GUI が表示されることを確認する。
3. runner / shared runtime / module import / `pywin32` のエラーが表示されないことを確認する。
4. Microsoft Excel デスクトップ版が使える VM で、破壊してよい Excel サンプルを指定する。
5. 値のみ、または最小の安全な置換シナリオを 1 件実行する。
6. 対象ファイルまたは出力ファイルの期待セルが変更されていることを確認する。
7. バックアップを有効にした場合は、バックアップ先にファイルが作成されることを確認する。
8. `%LOCALAPPDATA%\ToolHub\data\logs\` とアプリ側ログに、致命的なエラーが残っていないことを確認する。

Excel 未導入 VM では、GUI 起動と依存エラーの出方までは確認できますが、Excel 操作を伴う業務機能は成功扱いにしません。

### 7.3 その他の有効アプリ

`20260201 AgendaSnap`、`COMPASSのID一括取得`、`COMPASSの文書一括ダウンロード`、`XCgate電子帳票登録` は、まず ToolHub カードから GUI が起動し、runner / shared runtime / module import の致命的エラーがないことを確認します。

外部 API key、音声入力、本番サイト認証、業務データ操作が必要な処理は、準備できていない場合は `Not run` と記録します。外部前提なしで安全に確認できる画面表示、設定読込、ログイン前画面までを最小確認として扱います。

## 8. アンインストール / 再インストール確認

1. ToolHub を終了する。
2. Windows のアプリ一覧、または uninstall entry から ToolHub をアンインストールする。
3. `%LOCALAPPDATA%\Programs\ToolHub\` が削除されることを確認する。
4. `%LOCALAPPDATA%\ToolHub\` が削除されず残ることを確認する。
5. 同じ installer で再インストールする。
6. ToolHub を再起動し、有効アプリ全件のカードが再表示されることを確認する。
7. 必要に応じて代表アプリの起動確認だけを再実行する。

アンインストール時に user data を削除する選択肢が表示された場合は選択しません。誤って user data を消した場合、その VM 結果は user data preservation の証跡として使いません。

## 9. 結果回収と判定

VM から結果を host に戻し、host のリポジトリ直下で要約します。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\beta_vm\import_vm_test_result.ps1
```

最低限保存する証跡:

- `scripts\beta_vm\results\latest_vm_install_result.json`
- `scripts\beta_vm\results\latest_vm_install_result.md`
- ToolHub 画面で有効アプリ全件が表示されている screenshot
- 各アプリの起動後画面 screenshot
- PDF / Excel の最小業務シナリオに使ったサンプル名と期待結果
- 失敗時の launcher / runner / app log 抜粋

## 10. Pass / Fail 基準

Pass とする条件:

1. Host 側 build / package / release verify が pass している。
2. VM に開発ツールを導入せずに installer が完了している。
3. `%LOCALAPPDATA%\Programs\ToolHub\` と `%LOCALAPPDATA%\ToolHub\` が分離されている。
4. installer payload に有効アプリ全件と各 shared runtime が含まれている。
5. ToolHub が起動し、有効アプリ全件のカードが表示されている。
6. 有効アプリ全件が ToolHub から起動し、runner / shared runtime / module import の致命的エラーがない。
7. `PDF Workbench` が ToolHub から起動し、最小業務シナリオが成功している。
8. `ExcelBatchReplace` が ToolHub から起動し、Excel を含む最小業務シナリオが成功している。Excel 未導入 VM の場合は業務機能を `Not run` として分離する。
9. AgendaSnap、COMPASS、XCgate 系の外部前提がない機能は `Not run` として分離し、安全な GUI 起動確認は pass / fail で記録する。
10. アンインストール後も user data が保持され、再インストール後も有効アプリ全件が表示される。

Fail または Incomplete とする例:

- installer hash / size が manifest と一致しない。
- install dir が `%LOCALAPPDATA%\ToolHub\` になり、user data root と衝突している。
- アプリカードが有効アプリ全件分表示されない。
- `runtime/envs/<env_id>/Scripts/python.exe` が payload にない。
- VM 側に入れた Python や pip package に依存して起動している。
- runner error、module import error、`pywin32` error、Excel COM error、PDF 処理 error が残る。
- Excel 未導入のため Excel 操作を確認していない。
- dirty VM の旧インストール残骸により、clean install の証跡にならない。

## 11. 実施後の反映

1. Pass の場合は `docs/06_acceptance_checklist.md` の VM / manual check 項目へ、実施日、installer hash、対象 app id、結果ファイル名を追記する。
2. Fail の場合は、`latest_vm_install_result.json` の `likely_failure_category` とログを起点に原因を分類する。
3. アプリ固有の不具合と ToolHub 配布・runner 不具合を分けて記録する。
4. 失敗した installer や manifest を VM 内で編集して再検証しない。修正は host repo で行い、build からやり直す。
