# VirtualBox Two-App Installer Validation Plan

この文書は、現在 ToolHub に登録されている 2 つのアプリを含めた installer を作成し、VirtualBox 上の Windows にインストールして、ランチャー内から両アプリが正常に起動・動作するかを確認するための方針です。

これは確認方針であり、実施済み証跡ではありません。実行結果は `scripts/beta_vm/results/latest_vm_install_result.json` / `.md` と、必要に応じて `docs/06_acceptance_checklist.md` に記録します。

## 0. 確認対象

現在の `release/app_manifest.json` で `enabled=true` のアプリを対象にします。

| app id | 表示名 | 起動方式 | runtime |
| --- | --- | --- | --- |
| `pdf_workbench` | `PDF Workbench` | `python_shared_env` / GUI | `python-shared-env:py313-win_amd64-runtime-37c71daf` |
| `app_20251123_excelbatchreplace` | `ExcelBatchReplace` | `python_shared_env` / GUI | `python-shared-env:py313-win_amd64-pywin32310-dd4d21f1` |

確認の目的は、次の 3 点を分けて判定することです。

1. installer と payload が clean Windows VM に正しく配置される。
2. ToolHub ランチャーが 2 つのアプリカードを表示し、各アプリを runner 経由で起動できる。
3. 各アプリの最小業務シナリオが、必要な外部前提を満たした状態で成功する。

## 1. Host 側事前確認

1. 変更対象を固定する。
   - `release/app_manifest.json` の有効アプリが上記 2 件だけであることを確認する。
   - `apps/pdf_workbench/app.yaml` と `apps/app_20251123_excelbatchreplace/app.yaml` が存在することを確認する。
   - 2 件の `requirements.lock` が存在することを確認する。
2. runtime の前提を確認する。
   - 両アプリは `python_shared_env` 方式なので、`runtime/python/python.exe` と `runtime/envs/<env_id>/Lib/site-packages` が installer payload に含まれる必要がある。
   - VM 上で Python / pip package を別途導入して動いた場合は、配布検証としては成功扱いにしない。
3. 開発ツール依存を除外する前提を確認する。
   - VM には Python、Node.js、npm、Rust、cargo、Tauri CLI、pip package を事前導入しない。
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

1. アプリカードが 2 件表示される。
2. `PDF Workbench` が表示される。
3. `ExcelBatchReplace` が表示される。
4. 検索やカテゴリ絞り込み後も、対象アプリを選択できる。
5. 管理者向け内部情報や不要な技術詳細が利用者画面に露出していない。

アプリが 0 件、1 件、または想定外の件数で表示された場合は、アプリ起動確認へ進まず、`release/app_manifest.json`、installed payload の `apps\`、launcher log、`likely_failure_category` を確認します。

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

## 8. アンインストール / 再インストール確認

1. ToolHub を終了する。
2. Windows のアプリ一覧、または uninstall entry から ToolHub をアンインストールする。
3. `%LOCALAPPDATA%\Programs\ToolHub\` が削除されることを確認する。
4. `%LOCALAPPDATA%\ToolHub\` が削除されず残ることを確認する。
5. 同じ installer で再インストールする。
6. ToolHub を再起動し、2 つのアプリカードが再表示されることを確認する。
7. 必要に応じて 2 アプリの起動確認だけを再実行する。

アンインストール時に user data を削除する選択肢が表示された場合は選択しません。誤って user data を消した場合、その VM 結果は user data preservation の証跡として使いません。

## 9. 結果回収と判定

VM から結果を host に戻し、host のリポジトリ直下で要約します。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\beta_vm\import_vm_test_result.ps1
```

最低限保存する証跡:

- `scripts\beta_vm\results\latest_vm_install_result.json`
- `scripts\beta_vm\results\latest_vm_install_result.md`
- ToolHub 画面で 2 アプリが表示されている screenshot
- 各アプリの起動後画面 screenshot
- PDF / Excel の最小業務シナリオに使ったサンプル名と期待結果
- 失敗時の launcher / runner / app log 抜粋

## 10. Pass / Fail 基準

Pass とする条件:

1. Host 側 build / package / release verify が pass している。
2. VM に開発ツールを導入せずに installer が完了している。
3. `%LOCALAPPDATA%\Programs\ToolHub\` と `%LOCALAPPDATA%\ToolHub\` が分離されている。
4. installer payload に 2 アプリと各 shared runtime が含まれている。
5. ToolHub が起動し、2 つのアプリカードが表示されている。
6. `PDF Workbench` が ToolHub から起動し、最小業務シナリオが成功している。
7. `ExcelBatchReplace` が ToolHub から起動し、Excel を含む最小業務シナリオが成功している。
8. アンインストール後も user data が保持され、再インストール後も 2 アプリが表示される。

Fail または Incomplete とする例:

- installer hash / size が manifest と一致しない。
- install dir が `%LOCALAPPDATA%\ToolHub\` になり、user data root と衝突している。
- アプリカードが 2 件表示されない。
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
