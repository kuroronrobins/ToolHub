# App Registration Improvement Plan

作成日: 2026-05-08

## 目的

ToolHub の App Studio / アプリ登録プロセスについて、現時点で見えている失敗要因、待機時間の原因、検証漏れ、アイコン生成の fallback 化を整理し、次ステップで実装する改善リストとして使える形にする。

この文書は調査結果と改善バックログであり、実装済みの項目は「実施状況」に記録する。

## 現在の登録フローの要約

通常の App Studio 登録は、管理者が Python スクリプトを用意したあと、ToolHub 側が以下を実行する前提になっている。

1. Python entry point と周辺ファイルを解析する。
2. secret scan / file inventory / import analysis を行う。
3. metadata / README / icon 候補を作る。
4. `build_env` を作成し、必要パッケージをインストールする。
5. `requirements.lock` を生成する。
6. PyInstaller の frozen folder を作る。
7. `apps/<app_id>/` に登録する。
8. App Pack zip を作る。
9. `release/app_manifest.json` に disabled 状態で登録する。
10. approve 後に enabled にする。

通常の App 登録では、管理者が runtime archive を作る必要はない。runtime archive は ToolHub 本体の配布用共通 runtime であり、個別 App Pack とは別物である。

## 最重要の結論

現在の問題は、主に次の 5 系統に分かれる。

1. 登録成功判定が甘く、壊れた App Pack / 壊れた `apps/<app_id>` を成功扱いできてしまう。
2. App Studio が対象外ファイルまで広く含め、secret scan と PyInstaller の両方を重くしている。
3. Apply 時に毎回 `build_env` 作成、pip install、PyInstaller clean build を行うため、再登録や再試行が遅い。
4. アイコン生成は AI 設定不足と secret scan の AI submission block により、実質 fallback へ流れやすい。
5. 失敗理由の分類と UI への表示が弱く、管理者が次に何を直せばよいか分かりにくい。

## 実施状況

### 2026-05-08 Phase 0

壊れた登録を成功扱いしないための検証強化を開始し、以下を実装した。

- `scripts/package_app_pack.ps1` で `app.yaml` の `run.entry` と `display.icon` を app directory 内の相対パスとして検証する。
- `scripts/package_app_pack.ps1` で local file 欠落時に zip 作成前に fail する。
- `scripts/package_app_pack.ps1` で zip 作成後、`app.yaml`、`pack_manifest.json`、`README.md`、`requirements.txt`、`display.icon`、`run.entry` が App Pack 内に含まれることを検証する。
- `scripts/verify_release.ps1` で local `run.entry` / `display.icon` と App Pack 内 `run.entry` / `display.icon` を検証する。
- App Studio 本体の `registrar.package_app_pack()` でも同じく `run.entry` / `display.icon` 欠落を App Pack 作成時に fail する。
- App Studio approval の targeted verification で、App Pack 内に `run.entry` が含まれることを確認する。
- App Studio unit test に、`run.entry` 欠落時の packaging failure と zip 内 `run.entry` 検証を追加した。

この変更により、現在の checkout に残っている frozen-folder app の exe 欠落は `verify_release.ps1` で fail として検出される。これは想定どおりであり、次に対象アプリを再 build して `apps/<app_id>/bin/...exe` と App Pack を復元する必要がある。

実行確認:

- PowerShell parser で `scripts/package_app_pack.ps1` と `scripts/verify_release.ps1` の構文を確認済み。
- `python -m py_compile tools/app_studio/app_studio/registrar.py tools/app_studio/app_studio/approval.py` は成功。
- `python -m unittest discover -s tools/app_studio/tests` は成功。
- `scripts/package_app_pack.ps1 -AppId addnum_pdf -NoManifestUpdate` は、`addnum_pdf run.entry file is missing` で想定どおり fail。
- `scripts/verify_release.ps1` は、`addnum_pdf`、`app_20260201_agendasnap`、`officetopdf_toc`、`run_xcgate_upload` の local `run.entry` 欠落と App Pack 内 `run.entry` 欠落を想定どおり NG として検出。

### 2026-05-08 Phase 1-A

source scope を明示・制御する最初の改善を実装した。

- App Studio CLI に `--source-root` を追加した。未指定時は従来どおり entry file の親フォルダを使う。
- `ImportOptions` / `StudioContext` / `import_plan.json` に `source_root_origin`、`entry_relative`、`source_root_warnings`、`source_scope` summary を追加した。
- GUI の新規登録画面に任意入力の「ソース範囲」を追加し、Rust command 層から CLI へ `--source-root` を渡すようにした。
- entry が explicit source root 配下にない場合は fail する。drive root のような広すぎる explicit source root は fail する。
- inventory の既定除外を強化し、`.git`, `.hg`, `.svn`, `.venv`, `venv`, `env`, `__pycache__`, `.pytest_cache`, `node_modules`, `dist`, `build`, `work`, `works`, `result`, `results`, `output`, `outputs`, `ToolHub_AppStudio_Output`, `release`, `runtime`, `target` などを source walk から除外する。
- source root 直下の `.toolhubignore` を最小限の gitignore 風 glob として読み込む。空行、`#` コメント、`*` glob、末尾 `/` の directory-only pattern、`!` negation を扱う。
- `file_inventory.md` と新規 `file_inventory_report.md` に source scope summary、source root warning、除外ディレクトリ一覧を出力する。
- secret scan は inventory がある場合、included / blocked / manual_check / scan対象指定の record に限定して走るようにした。既定除外・`.toolhubignore` 除外ディレクトリ内の無関係ファイルは secret scan 対象外になる。
- build profile report に source scope と PyInstaller option 件数を出すようにした。
- excluded file が `paths` / `hidden_imports` / `add_data` に入らないことを unit test で確認した。

未実装または次フェーズ送り:

- source scope の interactive preview と除外ルール編集 UI は未実装。今回は文字入力と report 出力まで。
- build profile の本格 editor / diff UI は未実装。
- build_env cache、pip cache、PyInstaller `--clean` 見直し、AI icon 診断は今回の対象外。
- PowerShell wrapper `scripts/import_app.ps1` への `-SourceRoot` 追加は未実装。CLI 本体と GUI の経路を優先した。

### 2026-05-08 Phase 1-A 実アプリ検収

`run_xcgate_upload` 相当の実アプリソースを対象に、明示 `--source-root` の効果を検収した。

- 対象 entry: `C:\Users\kuroron\Documents\RD\20251103_XCgateAutoUpload\run_xcgate_upload.py`
- 指定 source_root: `C:\Users\kuroron\Documents\RD\20251103_XCgateAutoUpload`
- app_id は既存登録を上書きしないよう、検収用に `run_xcgate_upload_scope_check` を使用した。
- `app.yaml` に記録されていた旧 source_entry `C:\Users\kuroron\Downloads\XCgate_AutoUpload-main\XCgate_AutoUpload-main\run_xcgate_upload.py` は存在しなかったため、RD 配下に残っていた実ソースを使用した。

検収結果:

- Phase 1-A の初期実装では `xcgate_flows/logs` 配下の 19 file が excluded file として secret scan 対象に残っていた。これは runtime/user-output directory を file 単位で scan していたことが原因。
- `logs`, `log`, `screenshots`, `sessions`, `tmp`, `temp` は source walk からディレクトリ単位で除外するように修正した。
- 修正後の dry-run / suggest / apply では、`file_inventory_report.md` の excluded directories に `.git`, `ToolHub_AppStudio_Output`, `xcgate_flows/logs` が出力された。
- 修正後の inventory summary は included 26、excluded 23、blocked 1、manual_check 1、excluded_directory 3。
- secret scan は 20 findings から 1 finding に減少し、実測の secret_scan phase は約 1.47 秒から約 0.02 秒に短縮した。
- 残った Apply block は `xcgate_flows/.auth/mega_state.json` のみ。分類は `secret scan block` で、source scope 混入や PyInstaller hook failure ではない。
- AI submission block は false。secret scan による AI fallback 連鎖は、この検収では解消している。
- build profile は `paths = ["xcgate_flows"]`、`add_data` は `xcgate_flows/config.yaml` と `xcgate_flows/flows/*.flow` の 3 件、`collect_all = ["playwright"]`。`work/`, `results/`, `ToolHub_AppStudio_Output`, ToolHub repo, 別 project, `runtime`, `release`, `target` は PyInstaller profile に混入していない。
- Apply は secret scan block で停止したため、build_env 作成、requirements.lock 生成、PyInstaller 実行、frozen_folder_build_report 生成、apps/release 更新には到達していない。

判断:

- source scope 混入と secret scan 遅延は Phase 1-A の範囲で改善できている。
- `run_xcgate_upload` の次の blocker は `.auth` の認証済み状態ファイルを source root から外す、または管理者が `.toolhubignore` で明示除外したうえで安全性を確認する運用判断。
- PyInstaller hook failure の再検収は `.auth` block を解消した後に行う。現時点では PyInstaller まで到達していないため、hook failure が解消済みとは書かない。
- Phase 2 の build_env cache / pip cache / PyInstaller clean 見直しには進める。ただし、`run_xcgate_upload` の apply 完走検収は `.auth` block 解消後に再実行する。

### 2026-05-08 Phase 1-B

Playwright などの認証済み runtime state を App Pack に同梱しないまま、管理者が `.toolhubignore` で明示除外した場合だけ Apply を進められるようにした。

実装内容:

- `.toolhubignore` で `.auth/` などの sensitive runtime state directory が明示除外された場合、source walk / secret scan / build profile から除外しつつ、`SourceInventory.sensitive_excluded_directories` に記録する。
- `storage_state.json`、cookie、session、token、credential 類の sensitive file が `.toolhubignore` で明示除外された場合、file record は `exclude` / `sensitive_runtime_state` として残し、`SourceInventory.sensitive_excluded_files` に記録する。
- `file_inventory_report.md` に `Sensitive Runtime State Excluded by .toolhubignore` セクションを追加した。
- `suggested_toolhubignore.md` を追加し、未除外の blocked sensitive state がある場合は追加候補を、明示除外済みの場合は除外済み state を出力する。
- `import_plan.json` と `build_profile_report.md` に sensitive excluded count / detail を出すようにした。
- `.toolhubignore` を PowerShell などで UTF-8 BOM 付き作成しても、先頭コメントが pattern として誤読されないように `utf-8-sig` で読むようにした。
- PyInstaller が Playwright の package data copy で落ちるケースを `pyinstaller_collect_all_data_copy_failure` として `frozen_folder_build_report.md` に分類表示するようにした。

実アプリ検収:

- 対象 entry: `C:\Users\kuroron\Documents\RD\20251103_XCgateAutoUpload\run_xcgate_upload.py`
- 指定 source_root: `C:\Users\kuroron\Documents\RD\20251103_XCgateAutoUpload`
- app_id は検収用に `run_xcgate_upload_phase1b_check` を使用した。
- 外部 source root に最小限の `.toolhubignore` を追加した。内容は `.auth/` のみ。
- dry-run / suggest では `secret_findings=0`、`apply_blocked_by_secret_scan=false`、`ai_blocked_by_secret_scan=false`。
- `import_plan.json` の source scope は included 26、excluded 24、blocked 0、manual_check 1、excluded_directory 4、sensitive_excluded_directory 1、sensitive_excluded_file 0。
- `file_inventory_report.md` では `xcgate_flows/.auth` が `sensitive directory excluded by explicit .toolhubignore` として記録された。
- `secret_scan_report.md` は total findings 0、blocking findings 0、Apply blocked false。
- build profile は `paths = ["xcgate_flows"]`、`add_data` は `xcgate_flows/config.yaml` と `xcgate_flows/flows/*.flow` の 3 件、`collect_all = ["playwright"]`。`.auth/`、`mega_state.json`、storage state、ToolHub repo、別 project、`work/`, `results/`, `ToolHub_AppStudio_Output`, `runtime`, `release`, `target` は add_data に入っていない。
- hidden imports には `src.auth.save_state` / `xcgate_flows.src.auth.save_state` という Python module は入るが、これは `.auth/` directory や認証済み state file の同梱ではない。
- apply は secret scan を越え、`build_env_creation`、`requirements_lock_generation`、`build_tools_install`、`pyinstaller_build` まで到達した。
- PyInstaller は COLLECT 中に `FileNotFoundError` で失敗した。対象は `playwright\driver\package\lib\tools\cli-client\skill\references\element-attributes.md` の copy であり、分類は `pyinstaller_collect_all_data_copy_failure`、`source_scope_related=false`。
- PyInstaller 失敗のため `apps/run_xcgate_upload_phase1b_check` と `release/app_packs/run_xcgate_upload_phase1b_check-0.1.0.zip` は作成されていない。
- `final_app` 配下に `.auth/`, `mega_state.json`, `storage_state.json`, cookie/session 類がないことを確認した。

残課題:

- `run_xcgate_upload` の登録完走には Playwright の `--collect-all playwright` / PyInstaller hooks-contrib / package data copy failure の対処が必要。これは source scope や `.auth` block ではなく、PyInstaller / Playwright packaging の問題。
- `timing_report.json` は `build_frozen_folder()` が `ok=False` を返した場合でも、例外が出ていないため `pyinstaller_build` phase を `pass` と記録している。最終 result は fail だが、phase 表示が紛らわしいため AR-025 として追跡する。
- Phase 2 の build_env cache / pip cache / PyInstaller clean 見直しには進める。ただし、`run_xcgate_upload` の App Pack 完走には Phase 1-C または Phase 4 として Playwright packaging failure の修正が必要。

検証:

- `python -m py_compile` は Phase 1-B 対象 Python ファイルで成功。
- `python -m unittest discover -s tools/app_studio/tests` は成功。
- `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/check_all.ps1` は exit code 0。内部の release manifest verification では既知の未復元 App Pack として `addnum_pdf`, `app_20260201_agendasnap`, `officetopdf_toc`, `run_xcgate_upload` の local `run.entry` 欠落と App Pack 内 `run.entry` 欠落が報告された。

### 2026-05-08 Phase 1-C

Playwright package data copy failure の原因を、source scope / secret scan / `.auth` 由来ではなく Windows の深い PyInstaller COLLECT 出力パスとして切り分けた。

実装内容:

- PyInstaller の `--distpath` / `--workpath` / `--specpath` を `ToolHub_AppStudio_Output/<app_id>/build_tmp/pyi/{d,b,s}` に短縮した。
- `frozen_folder_build_report.md` に `pyinstaller_artifacts` を出し、実際に使われた dist/work/spec path を確認できるようにした。
- Playwright COLLECT の `FileNotFoundError` が 260 文字付近の Windows path に到達している場合、`pyinstaller_windows_long_path_collect_failure` / `source_scope_related=false` として分類するようにした。
- `--collect-all playwright` は維持した。Playwright package data は build に必要であり、今回の失敗原因は過剰な source scope や `.auth` 混入ではなく、出力先パス長だったため。
- 既存 app_id を再 apply する場合の退避処理で、深い Playwright 配下を `backups/app_studio/.../<app_id>/app/` に copytree すると再び long path failure になるため、既存 app は `app.zip` として浅い場所へ退避するようにした。

実アプリ検収:

- 対象 entry: `C:\Users\kuroron\Documents\RD\20251103_XCgateAutoUpload\run_xcgate_upload.py`
- 指定 source_root: `C:\Users\kuroron\Documents\RD\20251103_XCgateAutoUpload`
- app_id は検収用に `run_xcgate_upload_phase1c_check` を使用した。
- production の `apps/` / `release/` を更新しないため、一時 repo `C:\Users\kuroron\AppData\Local\Temp\toolhub_phase1c_repo_20260508_1129` で apply を実行した。
- `import_plan.json` の source scope は included 26、excluded 24、blocked 0、manual_check 1、sensitive_excluded_directory 1。
- `file_inventory_report.md` では `.git`, `ToolHub_AppStudio_Output`, `xcgate_flows/logs`, `__pycache__`, `xcgate_flows/.auth` が除外され、`.auth` は `sensitive directory excluded by explicit .toolhubignore` として記録された。
- `secret_scan_report.json` は total findings 0、Apply block なし。
- `build_profile_report.md` は `collect_all = ["playwright"]` を維持し、add_data は `xcgate_flows/config.yaml` と `xcgate_flows/flows/*.flow` の 3 件。`.auth/`, `mega_state.json`, storage state / cookie / session 類は add_data に入っていない。
- `frozen_folder_build_report.md` は status `PASS`。PyInstaller 6.20.0 で COLLECT が `completed successfully` まで進み、以前の `element-attributes.md` copy failure は再現しなかった。
- App Pack `run_xcgate_upload_phase1c_check-0.1.0.zip` が生成された。zip 内 entry は 580 件で、`app.yaml` と `bin/run_xcgate_upload_phase1c_check/run_xcgate_upload_phase1c_check.exe` が存在する。
- zip 内に `.auth/`, `mega_state.json`, `storage_state.json`, cookie/session/token/credential の runtime state 実体がないことを確認した。Playwright package 内の説明用 `storage-state.md` は認証済み state 実体ではない。
- `execution_test_result.json` は `overall_status=warn`, `approval_allowed=true`。warning は GUI/browser/login/file-picker と Playwright manual check であり、承認ブロックではない。

残課題:

- `run_xcgate_upload` は frozen-folder と App Pack 生成まで到達したが、Playwright のブラウザバイナリ、ログイン、社内サイト操作、ファイル選択は manual check のまま。
- 検収 run の timing では `build_env_creation` 約 21 秒、`build_tools_install` 約 23 秒、`pyinstaller_build` 約 31 秒、`registration_copy` 約 45 秒。Phase 2 では build_env / pip cache だけでなく、大きい frozen-folder の登録コピー・zip 作成時間も追跡対象にする。
- production の既存 `run_xcgate_upload` App Pack 復元や既存 app_id への本番 apply は今回の対象外。

検証:

- `python -m py_compile` は Phase 1-C 対象 Python ファイルで成功。
- `python -m unittest discover -s tools/app_studio/tests` は 108 tests 成功。
- `run_xcgate_upload` 相当アプリの dry-run / suggest / apply は一時 repo で成功し、App Pack 生成まで到達。
- `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/check_all.ps1` は exit code 0。内部の release manifest verification では既知の未復元 App Pack として `addnum_pdf`, `app_20260201_agendasnap`, `officetopdf_toc`, `run_xcgate_upload` の local `run.entry` 欠落と App Pack 内 `run.entry` 欠落が報告された。

### 2026-05-08 Phase 1-D

Phase 1-C で検収用 app_id ではなく、本番 app_id `run_xcgate_upload` を再登録し、Phase 0 以降に見えていた local `run.entry` 欠落 / App Pack 内 `run.entry` 欠落を解消した。

実施内容:

- 対象 entry: `C:\Users\kuroron\Documents\RD\20251103_XCgateAutoUpload\run_xcgate_upload.py`
- 指定 source_root: `C:\Users\kuroron\Documents\RD\20251103_XCgateAutoUpload`
- app_id: `run_xcgate_upload`
- 外部 source root の `.toolhubignore` は既に `.auth/` を明示除外していたため、外部 source root 側の追加変更は行っていない。
- App Studio apply により `apps/run_xcgate_upload/`、`release/app_packs/run_xcgate_upload-0.1.0.zip`、`release/app_manifest.json` の `run_xcgate_upload` entry を更新した。
- 既存 app は `backups/app_studio/20260508_122605/run_xcgate_upload/app.zip` に自動退避された。
- App Studio fallback で既存の具体的な XC-Gate 向け metadata が汎用文言へ戻っていたため、表示 metadata は既存の具体的な説明へ戻し、対象 App Pack だけ再パッケージした。
- `scripts/package_app_pack.ps1` による再パッケージ後、`release/app_manifest.json` に UTF-8 BOM が付いて `scripts/test_app_delete_plan.ps1` が失敗したため、manifest は UTF-8 no BOM に戻した。script 側の恒久対応は AR-027 として追跡する。
- `enabled` は通常 apply 方針どおり `false` のまま維持した。approval / enabled 化は行っていない。

検収結果:

- Apply は `file_inventory`、`secret_scan`、`build_env_creation`、`requirements_lock_generation`、`build_tools_install`、`pyinstaller_build`、`distribution_check`、`registration_copy`、`execution_checks` まで到達し、exit code 0。
- `apps/run_xcgate_upload/app.yaml` は存在し、`run.entry` は `bin/run_xcgate_upload/run_xcgate_upload.exe`。
- `apps/run_xcgate_upload/bin/run_xcgate_upload/run_xcgate_upload.exe` が存在する。exe size は 3,448,740 bytes。
- `release/app_packs/run_xcgate_upload-0.1.0.zip` が存在し、zip 内 entry は 584 件。
- App Pack 内に `run_xcgate_upload/app.yaml`、`run_xcgate_upload/pack_manifest.json`、`run_xcgate_upload/bin/run_xcgate_upload/run_xcgate_upload.exe` が存在する。
- App Pack 内に `.auth/`, `mega_state.json`, `storage_state.json`, cookie/session/token/credential の runtime state 実体がないことを確認した。
- `release/app_manifest.json` の `run_xcgate_upload` package は `app_packs/run_xcgate_upload-0.1.0.zip`、sha256 は `b001040d14e42fef2e057f2ac13aec0943f818facea13182bb1059ec15cb4467`。zip の SHA256 と一致する。
- `execution_test_result.json` は `overall_status=warn`, `approval_allowed=true`。warning は frozen-folder mode の smoke skip、Playwright manual check、runner dry execution skip で、approval blocking reason はない。
- `frozen_folder_build_report.md` は status `PASS`。PyInstaller 6.20.0 で `--collect-all playwright` を維持し、COLLECT は `completed successfully`。
- `verify_release.ps1` では `run_xcgate_upload` の local `run.entry` と App Pack 内 `run.entry` がどちらも `OK` になった。

残る既知 NG:

- `addnum_pdf`: local `run.entry` 欠落、App Pack 内 `run.entry` 欠落。
- `app_20260201_agendasnap`: local `run.entry` 欠落、App Pack 内 `run.entry` 欠落。
- `officetopdf_toc`: local `run.entry` 欠落、App Pack 内 `run.entry` 欠落。
- installer file / installer staging manifest は引き続き warning。

検証:

- `python tools/app_studio/main.py import --entry "C:\Users\kuroron\Documents\RD\20251103_XCgateAutoUpload\run_xcgate_upload.py" --source-root "C:\Users\kuroron\Documents\RD\20251103_XCgateAutoUpload" --app-id run_xcgate_upload --apply` は成功。
- `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/package_app_pack.ps1 -AppId run_xcgate_upload` は metadata 復元後の App Pack 再生成に成功。
- `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify_release.ps1` は exit code 1。理由は上記 3 app の既知 NG であり、`run_xcgate_upload` の NG は解消済み。
- `python -m py_compile tools/app_studio/app_studio/frozen_folder_builder.py tools/app_studio/app_studio/registrar.py` は成功。
- `python -m unittest discover -s tools/app_studio/tests` は 108 tests 成功。
- `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/check_all.ps1` は exit code 0。内部の release manifest verification は上記 3 app の既知 NG により warning 扱いだが、`run_xcgate_upload` は local / App Pack 内 `run.entry` とも OK。
- Phase 2 の build_env cache / pip cache / PyInstaller clean 見直しへ進める。ただし、`run_xcgate_upload` の実ログイン、社内サイト操作、ファイル選択は manual check のまま。

### 2026-05-08 Phase 1-E

Phase 2 で App Pack 再生成や manifest 更新を繰り返す前に、release JSON / App Pack metadata JSON の書き込み encoding を UTF-8 no BOM に固定した。

実装内容:

- `scripts/utf8_no_bom.ps1` を追加し、PowerShell 5.1 でも動く `New-Object System.Text.UTF8Encoding -ArgumentList $false` ベースの `Write-Utf8NoBomFile` / `Write-JsonUtf8NoBomFile` / `Test-Utf8Bom` を用意した。
- `scripts/package_app_pack.ps1` の `pack_manifest.json` と `release/app_manifest.json` 書き込みを UTF-8 no BOM helper に変更した。
- `scripts/package_installer.ps1` の `staging_manifest.json`、`release/manifest.json`、staging 側 `release/manifest.json` 書き込みを UTF-8 no BOM helper に変更した。
- `scripts/rebuild_app_manifest.ps1` と `scripts/test_app_delete_plan.ps1` の `release/app_manifest.json` 書き込みを UTF-8 no BOM helper に変更した。
- `scripts/test_utf8_no_bom.ps1` を追加し、一時 JSON への書き出しで先頭 bytes が UTF-8 BOM ではないこと、非 ASCII 文字を含む JSON が parse できることを検証するようにした。
- `scripts/check_all.ps1` に `release/manifest.json` / `release/app_manifest.json` の BOM 検査、helper test、関連 packaging script の PowerShell parser 構文確認を追加した。

検証:

- 既存 `release/app_manifest.json` と `release/manifest.json` の内容差分は発生させていない。BOM 検査のみ実施する。
- App Pack は再生成していない。読み取り確認では、Phase 1-E 前に生成済みの既存 App Pack 内 `pack_manifest.json` には UTF-8 BOM が残っている。今回の範囲では zip を変更せず、次回 `scripts/package_app_pack.ps1` で再生成される対象から UTF-8 no BOM になる。

反映確認:

- `git ls-remote origin refs/heads/develop` は `d24f1989c9c83c77045d0516b089bbff0be90c6e` を返し、local `HEAD` / `origin/develop` と一致した。
- GitHub API で `develop` の `scripts/package_app_pack.ps1` を取得し、`scripts/utf8_no_bom.ps1` の dot-source、staging `pack_manifest.json` の `Write-JsonUtf8NoBomFile`、`release/app_manifest.json` の `Write-JsonUtf8NoBomFile` を確認した。
- GitHub API で `develop` の `scripts/check_all.ps1` を取得し、`release/manifest.json` / `release/app_manifest.json` の BOM 検査と `scripts/test_utf8_no_bom.ps1` 実行を確認した。
- GitHub API で `develop` の `scripts/utf8_no_bom.ps1` を取得し、`Write-Utf8NoBomFile`、`Write-JsonUtf8NoBomFile`、`Test-Utf8Bom` の定義を確認した。
- 認証なしの raw URL では古い内容が返る場合があったため、反映確認は `git ls-remote` と GitHub API の `ref=develop` を正とする。

### 2026-05-08 Phase 2-A

Apply 再試行時の `build_env_creation` / pip install / build tools install を高速化するため、App Studio の内部 `build_env` を同一 app の output workspace 内で再利用できるようにした。今回は PyInstaller `--clean`、PyInstaller build artifact、`registration_copy`、App Pack zip 差分更新には進んでいない。

実装内容:

- `export_suggestion()` の output reset 時に、`build_env` と `build_tmp/pip_cache` だけを退避・復元し、再 Apply でも内部 build environment と App Studio 専用 pip cache が残るようにした。
- `create_build_env()` に cache key / metadata 検証を追加した。cache metadata は `output_dir/build_env/toolhub_build_env_cache.json` に保存する。
- cache key は `app_id`、requirements install source path、requirements hash、base Python executable path、base Python version、build tools package specs、build profile hash から作る。
- cache hit 条件は、metadata schema / cache key / key parts 一致、`build_env` 内 Python の存在、pip probe 成功、cached Python version 一致。どれかが満たされなければ安全側で rebuild する。
- `run_command()` は明示された `pip_cache_dir` がある場合、`PIP_NO_CACHE_DIR=1` を外し、`PIP_CACHE_DIR=output_dir/build_tmp/pip_cache` を設定する。
- `install_build_tools()` は `PyInstaller>=6,<7` と `pyinstaller-hooks-contrib>=2024.0` の installed version を確認し、満たしていれば pip install を skip する。満たさない場合だけ install / refresh する。
- CLI に `--rebuild-build-env` を追加し、必要な場合は cache を使わず build_env を強制再作成できるようにした。
- `timing_report` には `build_env_cache` と `build_tools_cache` の hit / miss と理由を追加した。

検証:

- unit test で requirements hash 一致時の reuse、requirements hash 変更時の rebuild、Python version metadata mismatch 時の rebuild、build tools version satisfied 時の install skip、明示 pip cache env を確認した。
- 軽量 fixture の Apply 2 回 unit test では、1 回目は cache miss / build_env 作成 / build tools install、2 回目は cache hit / build_env reuse / build tools install skip になることを確認した。実 CLI での wall-clock 比較と `run_xcgate_upload` 相当アプリの 2 回 Apply 比較は Phase 2-A follow-up として残す。

### 2026-05-08 Phase 2-A 実アプリ検収

`run_xcgate_upload` 相当アプリを本番 app_id ではなく検収用 app_id `xcg_p2a` で一時 ToolHub repo に登録し、同じ output workspace で Apply を 2 回実行した。source は `C:\Users\kuroron\Documents\RD\20251103_XCgateAutoUpload\run_xcgate_upload.py`、source_root は `C:\Users\kuroron\Documents\RD\20251103_XCgateAutoUpload`。外部 source root の `.toolhubignore` には既に `.auth/` があり、変更していない。

検収結果:

- 1 回目 Apply: exit 0、actual_total_seconds 113.401、`build_env_cache=miss`、cache_miss_reason `build_env does not exist`。
- 2 回目 Apply: exit 0、actual_total_seconds 67.377、`build_env_cache=hit`、cache_miss_reason `none`。
- `build_env_creation` は 24.071 秒から 1.159 秒に短縮した。
- `build_tools_install` は 24.826 秒から 0.826 秒に短縮し、`build_tools_cache=hit` になった。metadata 上の installed version は PyInstaller 6.20.0、pyinstaller-hooks-contrib 2026.5。
- `requirements_lock_generation` は 1.576 秒から 0.947 秒、`pyinstaller_build` は 35.175 秒から 15.235 秒になった。ただし今回は PyInstaller `--clean` 見直しや build artifact reuse は実施していない。
- `registration_copy` は 25.569 秒から 46.251 秒になり、2 回目 Apply の最大待ち時間として残った。registration_copy / App Pack zip 高速化は Phase 2-A 対象外。
- 2 回目 App Pack には run.entry `xcg_p2a/bin/xcg_p2a/xcg_p2a.exe` が含まれ、`.auth/`、`mega_state.json`、`storage_state.json`、auth/cookie/session/token/credential state JSON は含まれていなかった。
- runtime check は Playwright / GUI / login の manual check warning のみで overall `warn`、execution checks は overall `warn`、approval_allowed `true`。

補足:

- 最初に長い検収用 app_id と `%TEMP%` の深い一時 repo path を組み合わせた実行では、App Pack staging copy が Windows path length に当たり失敗した。cache 由来ではなく検収ハーネス由来のため、短い検収用 app_id `xcg_p2a` と runner/runtime junction 付き一時 repo で再検収した。

### 2026-05-08 Phase 2-B

`registration_copy` / App Pack 生成時間を分解するため、App Studio の `apply_registration()` / `package_app_pack()` / `backup_existing()` に step-level timing を追加した。App Pack 仕様、zip 構造、必須 entry 検証、SHA256 計算、manifest 更新は維持した。

実装内容:

- `ToolHub_AppStudio_Output/<app_id>/registration_copy_breakdown.json` と `registration_copy_report.md` を追加した。
- `timing_report` には `registration_copy.<step>` の mark を追加した。二重計上を避けるため、substep mark の `duration_seconds` は 0 とし、実測秒数は `detail.measured_duration_seconds` と breakdown report に出す。
- `backup_existing_app_zip`、`backup_manifest`、`remove_existing_app`、`copy_final_app_to_apps`、`manifest_update_before_pack`、`package_app_pack_total`、`staging_reset`、`copy_app_to_pack_staging`、`cleanup_generated_cache`、`write_pack_manifest`、`compress_app_pack`、`inspect_app_pack_required_entries`、`sha256_app_pack`、`manifest_update_after_pack`、`copy_pack_to_output_mirror` を分解して記録する。
- App Pack zip と backup zip は ZIP_DEFLATED のまま `compresslevel=1` にした。App Pack zip の再利用、差分更新、SHA256 省略、必須 entry 検証省略はしていない。

実アプリ検収:

- 本番 app_id `run_xcgate_upload` は使わず、短い検収用 app_id `xcg_p2b` と一時 ToolHub repo で実行した。
- source は `C:\Users\kuroron\Documents\RD\20251103_XCgateAutoUpload\run_xcgate_upload.py`、source_root は `C:\Users\kuroron\Documents\RD\20251103_XCgateAutoUpload`。外部 source root の `.toolhubignore` は変更していない。
- 最終 run は exit 0、actual_total_seconds 49.871、`build_env_cache=hit`、`build_tools_cache=hit`、`pyinstaller_build` 11.605 秒、`registration_copy` 34.430 秒。
- 最終 breakdown は `backup_existing_app_zip` 17.844 秒、`package_app_pack_total` 15.983 秒、内訳の `compress_app_pack` 15.302 秒。copy 系は `copy_final_app_to_apps` 0.421 秒、`copy_app_to_pack_staging` 0.455 秒、`copy_pack_to_output_mirror` 0.019 秒で、支配要因ではなかった。
- 検収中に backup zip を ZIP_STORED にする比較も行ったが、`backup_existing_app_zip` が 15.316 秒で良化しなかったため採用しない。
- App Pack zip には run.entry `xcg_p2b/bin/xcg_p2b/xcg_p2b.exe` が含まれ、`.auth/`、`mega_state.json`、`storage_state.json`、auth/cookie/session/token/credential state JSON は含まれていなかった。
- production の `apps/run_xcgate_upload/`、`release/app_manifest.json`、`release/manifest.json` は変更していない。
- 補足: `timing_report.json` は Python `json` では valid だったが、PowerShell `ConvertFrom-Json` では既存の mojibake label を含む report の解析に失敗するケースがあった。Phase 2-B の検収では Python `json` で機械確認した。

判断:

- Phase 2-B で内訳は見えるようになった。現時点の最大要因は backup zip と App Pack zip の圧縮であり、単純な directory copy や SHA256 ではない。
- Phase 2-C では、App Pack 仕様を壊さない範囲で backup の世代管理・圧縮方針、staging を介さない pack 作成経路、zip compression level / size tradeoff を検討する。ただし App Pack 生成 skip、既存 App Pack 再利用、差分 App Pack、SHA256 省略、必須 entry 検証省略は引き続き禁止。

### 2026-05-08 Phase 2-C

`registration_copy` の支配要因だった backup zip と App Pack zip 作成を比較し、全アプリ共通の標準経路として安全に短縮できる部分だけを変更した。App Pack 仕様、zip 構造、必須 entry 検証、SHA256 計算、manifest 更新は維持した。

比較結果:

- backup は、ZIP_DEFLATED level 1 が 22.932 秒 / 52.3 MB、ZIP_STORED が 0.596 秒 / 127.8 MB、move/rename が実 move 0.002 秒だった。rollback 用の既存 app dir 完全保持と Windows long path 耐性を両立できるため、標準 backup strategy は `move_existing_app_directory` とした。
- App Pack は、direct zip の ZIP_DEFLATED level 1 が 2.263 秒 / 52.3 MB、ZIP_STORED が 0.356 秒 / 127.8 MBだった。ZIP_STORED は配布サイズが約 2.4 倍になるため採用せず、標準 App Pack strategy は `direct_zip_from_apps_dir`、compression は `ZIP_DEFLATED` level 1 のままとした。
- 採用しなかった案: App Pack zip の再利用、差分 zip、SHA256 省略、必須 entry 検証省略、backup 省略、app 種類ごとの zip 方式切り替えは安全性または標準経路の一貫性を壊すため採用しない。

実装内容:

- 既存 app の backup は `backups/app_studio/<timestamp>/<app_id>/app/` へ move して保持する。manifest backup は従来どおり保持する。
- App Pack は `release/staging/app_studio_pack` への app copy を行わず、`apps/<app_id>` から直接 zip を作成する。`pack_manifest.json` は zip entry として書き込む。
- `registration_copy_breakdown.json` / `registration_copy_report.md` に、backup strategy、backup safety note、App Pack strategy、compression method / level、entry count、size、elapsed、採用しなかった案を出す。
- app_id、Playwright 有無、GUI/CLI、大きい/小さいによる恒常的分岐は追加していない。

実アプリ検収:

- 本番 app_id `run_xcgate_upload` は使わず、短い検収用 app_id `xcg_p2c` と一時 ToolHub repo で実行した。
- source は `C:\Users\kuroron\Documents\RD\20251103_XCgateAutoUpload\run_xcgate_upload.py`、source_root は `C:\Users\kuroron\Documents\RD\20251103_XCgateAutoUpload`。外部 source root の `.toolhubignore` は変更していない。
- 2 回目 Apply は exit 0、actual_total_seconds 30.842、`build_env_cache=hit`、`build_tools_cache=hit`、`pyinstaller_build` 11.337 秒、`registration_copy` 15.581 秒。
- breakdown は `backup_existing_total` 0.031 秒、内訳の `backup_existing_app_move` 0.002 秒、`copy_final_app_to_apps` 0.500 秒、`package_app_pack_total` 14.999 秒、内訳の `compress_app_pack` 14.941 秒、`sha256_app_pack` 0.038 秒。
- App Pack size は 52,291,499 bytes、entry count は 580。manifest の sha256 は実 zip と一致した。
- App Pack zip には run.entry `xcg_p2c/bin/xcg_p2c/xcg_p2c.exe` が含まれ、`.auth/`、`mega_state.json`、`storage_state.json`、auth/cookie/session/token/credential state JSON は含まれていなかった。
- production の `apps/run_xcgate_upload/`、`release/app_manifest.json`、`release/manifest.json` は変更していない。

判断:

- `registration_copy` は Phase 2-B の 34.430 秒から 15.581 秒まで短縮した。主な改善は backup zip を move backup に置き換えたことによる。
- 残る支配要因は App Pack の ZIP_DEFLATED 圧縮であり、配布サイズを維持する限り大きな短縮余地は限定的。Phase 2-D に進む場合は、App Pack サイズとの tradeoff を明示した compression policy、または zip 実装自体の検証が対象になる。

### 2026-05-08 Phase 2-D

App Pack zip 圧縮時間について、速度・サイズ・配布影響を比較し、全アプリ共通の標準 compression policy を明確化した。App Pack 仕様、zip 構造、必須 entry 検証、SHA256 計算、manifest 更新は維持した。

比較結果:

| method | compresslevel | compress elapsed | size | entry count | required entry | sensitive state |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| `ZIP_DEFLATED` | 0 | 17.187 秒 | 121.9 MB | 580 | OK | 0 |
| `ZIP_DEFLATED` | 1 | 2.510 秒 | 49.9 MB | 580 | OK | 0 |
| `ZIP_DEFLATED` | 6 | 5.580 秒 | 45.4 MB | 580 | OK | 0 |
| `ZIP_DEFLATED` | 9 | 13.500 秒 | 45.2 MB | 580 | OK | 0 |
| `ZIP_STORED` | - | 0.351 秒 | 121.8 MB | 580 | OK | 0 |

方針:

- 標準 App Pack compression policy は `balanced_size_speed` とし、全アプリ共通で `ZIP_DEFLATED` / `compresslevel=1` を継続する。
- `ZIP_STORED` は最速だが、App Pack が約 2.4 倍になり、`release/app_packs` の保存容量と将来の update 配布サイズを増やすため採用しない。
- `ZIP_DEFLATED` level 0 は Python `zipfile` で valid だが、実質無圧縮でサイズが大きく、今回の実測では `ZIP_STORED` より遅かったため採用しない。
- `ZIP_DEFLATED` level 6 / 9 は level 1 より約 4.5 MB 小さいが、圧縮時間が伸びるため normal App Studio registration の標準にはしない。
- app_id、Playwright 有無、GUI/CLI、大きい/小さいによる恒常的な compression 切り替えは追加していない。

実装内容:

- `registration_copy_breakdown.json` / `registration_copy_report.md` に `selected_policy=balanced_size_speed`、policy note、distribution note、compression method / level、不採用案を出すようにした。
- `compress_app_pack` record に compression policy / method / level / entry count / size を明示した。
- zip 生成方式、必須 entry 検証、SHA256 計算、manifest 更新、App Pack mirror copy は従来どおり維持した。

実アプリ検収:

- 本番 app_id `run_xcgate_upload` は使わず、短い検収用 app_id `xcg_p2d` と一時 ToolHub repo で実行した。
- source は `C:\Users\kuroron\Documents\RD\20251103_XCgateAutoUpload\run_xcgate_upload.py`、source_root は `C:\Users\kuroron\Documents\RD\20251103_XCgateAutoUpload`。外部 source root の `.toolhubignore` は変更していない。
- Apply は exit 0、actual_total_seconds 27.586、`build_env_cache=hit`、`build_tools_cache=hit`、`pyinstaller_build` 11.422 秒、`registration_copy` 12.483 秒。
- breakdown は `copy_final_app_to_apps` 0.796 秒、`package_app_pack_total` 11.642 秒、内訳の `compress_app_pack` 11.580 秒、`inspect_app_pack_required_entries` 0.012 秒、`sha256_app_pack` 0.037 秒。
- App Pack size は 52,292,693 bytes、entry count は 580。manifest の sha256 は実 zip と一致した。
- App Pack zip には run.entry `xcg_p2d/bin/xcg_p2d/xcg_p2d.exe` が含まれ、`.auth/`、`mega_state.json`、`storage_state.json`、auth/cookie/session/token/credential state JSON は含まれていなかった。
- production の `apps/run_xcgate_upload/`、`release/app_manifest.json`、`release/manifest.json` は変更していない。検収中に誤って生成した `apps/xcg_p2d/` と `release/app_packs/xcg_p2d-0.1.0.zip` は、`xcg_p2d` のみを対象に削除し、manifest entry も戻した。

判断:

- Phase 2-D では compression policy を変えず、現行の `ZIP_DEFLATED` level 1 を標準として明文化した。速度だけなら `ZIP_STORED` が速いが、App Pack / update payload の増加が大きい。
- 残る `compress_app_pack` の短縮は、Python 標準 `zipfile` の compression policy 変更だけでは tradeoff が大きい。Phase 2-E に進む場合は、registration_copy 以外の UI 待機体験改善、または配布サイズ許容を明示した運用設定案を別途検討する。

### 2026-05-08 残り 3 app の復元計画

`verify_release.ps1` で既知 NG として残っている `addnum_pdf`、`app_20260201_agendasnap`、`officetopdf_toc` について、復元可能性を read-only で確認した。今回は本番 app_id での Apply、App Pack 再生成、`release/app_manifest.json` 更新、enabled 変更は行っていない。

現在の NG:

| app_id | enabled | local run.entry | App Pack run.entry | release pack sha256 |
| --- | --- | --- | --- | --- |
| `addnum_pdf` | false | missing | missing | OK |
| `app_20260201_agendasnap` | true | missing | missing | OK |
| `officetopdf_toc` | true | missing | missing | OK |

source_entry / output_mirror 調査:

| app_id | source_entry | source_entry | source_root 候補 | output_mirror / 復元材料 | 分類 |
| --- | --- | --- | --- | --- | --- |
| `addnum_pdf` | `C:\Users\kuroron\Downloads\drive-download-20260427T120504Z-3-001\AddNum_PDF.py` | missing | 親 directory も missing | output_mirror missing、既存 App Pack も run.entry missing | C |
| `app_20260201_agendasnap` | `C:\Users\kuroron\Documents\RD\20260201_AgendaSnap\main.py` | exists | `C:\Users\kuroron\Documents\RD\20260201_AgendaSnap` | output_mirror exists、`final_app` run.entry exists、mirror App Pack run.entry exists | A |
| `officetopdf_toc` | `C:\Users\kuroron\Downloads\drive-download-20260427T120504Z-3-001\OfficeToPDF_TOC.py` | missing | 親 directory も missing | output_mirror missing、既存 App Pack も run.entry missing | C |

補足:

- `AddNum_PDF.py` と `OfficeToPDF_TOC.py` は、`C:\Users\kuroron\Downloads` と `C:\Users\kuroron\Documents\RD` の限定検索では見つからなかった。
- `app_20260201_agendasnap` は現行 App Studio の dry-run で exit 0、included_files 61、secret_findings 6。source root 直下に `.git`、`.pytest_tmp`、`sessions`、`ToolHub_AppStudio_Output` があるが、Phase 1-A 以降の既定除外で大きな混入は避けられる見込み。ただし `.toolhubignore` は存在しない。
- `app_20260201_agendasnap` の古い App Studio output には `execution_test_result.json` があり、`overall_status=warn`、`approval_allowed=true`。ただし report 形式は Phase 1-A 前で、`source_scope` や `registration_copy_report.md` はない。

復元優先順位:

1. `app_20260201_agendasnap`: enabled=true かつ source / output_mirror が存在するため最優先。まず検収用 app_id または一時 repo で Apply し、source scope、secret scan、build profile、App Pack safety を確認する。その後、本番 app_id で再登録する。
2. `officetopdf_toc`: enabled=true だが source_entry が存在しないため、元 source の再入手または source_entry 修正が先。復元できるまで enabled=true の壊れた配布物として扱うリスクが残る。
3. `addnum_pdf`: enabled=false で配布影響は低い。source_entry が存在しないため、復元は `officetopdf_toc` と同じく元 source 再入手後。復元しない場合は disabled のまま archive / full delete 候補にする。

推奨 next action:

- `app_20260201_agendasnap`:
  - entry: `C:\Users\kuroron\Documents\RD\20260201_AgendaSnap\main.py`
  - source_root: `C:\Users\kuroron\Documents\RD\20260201_AgendaSnap`
  - 先に検収用 app_id または一時 repo で Apply。
  - 既存 metadata を維持したい場合は、`apps/app_20260201_agendasnap/app.yaml` の display/detail/search を metadata override 化するか、Apply 後に差分確認して本番登録前に調整する。
  - App Pack safety: run.entry、`.auth` / storage state / cookie / session / token / credential state JSON 非混入、required entry inspection、SHA256、execution_test_result の `approval_allowed` を確認する。
- `officetopdf_toc`:
  - まず `OfficeToPDF_TOC.py` の所在を確認する。元の `drive-download-20260427T120504Z-3-001` directory を復元するか、別場所にある source を指定し直す。
  - source が見つかるまでは本番 app_id で Apply しない。
  - enabled=true のため、復元できない場合は一時的な disabled 化、または full delete / archive を別作業で判断する。
- `addnum_pdf`:
  - まず `AddNum_PDF.py` の所在を確認する。source が見つかれば `officetopdf_toc` と同じ source_root にできる可能性がある。
  - enabled=false のため復元優先度は低い。復元しない場合は disabled のまま archive / full delete 候補にする。

次に Codex へ依頼すべき復元作業:

1. `app_20260201_agendasnap` を検収用 app_id / 一時 repo で App Studio Apply し、source scope / secret scan / build profile / App Pack safety を確認する。
2. その検収が通ったら、本番 app_id `app_20260201_agendasnap` で再登録し、`verify_release.ps1` の AgendaSnap NG を解消する。
3. `OfficeToPDF_TOC.py` と `AddNum_PDF.py` の元 source を再入手またはパス修正してから、それぞれ同じ検収 -> 本番再登録の順で進める。

### 2026-05-08 `app_20260201_agendasnap` 本番復元

復元可能性 A と判定した `app_20260201_agendasnap` を、標準 App Studio flow で検収後に本番 app_id へ再登録した。App Pack 仕様、runner I/F、release manifest schema は変更していない。`addnum_pdf` と `officetopdf_toc` は未復元のまま触っていない。

検収用 Apply:

- app_id: `agendasnap_restore_check`
- repo: 一時 repo `C:\Users\kuroron\AppData\Local\Temp\toolhub_agendasnap_restore_check_repo`
- entry: `C:\Users\kuroron\Documents\RD\20260201_AgendaSnap\main.py`
- source_root: `C:\Users\kuroron\Documents\RD\20260201_AgendaSnap`
- result: Apply exit 0、PyInstaller 成功、App Pack 生成成功、`execution_test_result` は `overall_status=warn` / `approval_allowed=true`
- source scope: included 61、excluded 40、blocked 0、manual_check 0、excluded directories 22
- secret scan: findings 6、blocking 0、warning 0、manual_check 0、Apply block なし。AI submission は secret scan により block。
- App Pack safety: `run.entry` は zip 内に存在。`.auth`、`mega_state.json`、`storage_state.json`、cookie / session / token / credential state JSON 実体は非混入。
- timing: build_env_creation 102.405s、build_tools_install 29.828s、pyinstaller_build 55.675s、registration_copy 5.923s。

本番 Apply:

- app_id: `app_20260201_agendasnap`
- result: Apply exit 0、PyInstaller 成功、App Pack 生成成功、`execution_test_result` は `overall_status=warn` / `approval_allowed=true`
- local `run.entry`: `apps/app_20260201_agendasnap/bin/app_20260201_agendasnap/app_20260201_agendasnap.exe` が存在。
- App Pack: `release/app_packs/app_20260201_agendasnap-0.1.0.zip` が生成され、zip 内 `app_20260201_agendasnap/bin/app_20260201_agendasnap/app_20260201_agendasnap.exe` が存在。
- App Pack safety: `.auth`、`mega_state.json`、`storage_state.json`、cookie / session / token / credential state JSON 実体は非混入。
- manifest: `release/app_manifest.json` の `app_20260201_agendasnap` sha256 は実 zip hash と一致。
- enabled: 既存 manifest は `enabled=true` だったが、標準 App Studio Apply の通常方針により `enabled=false` になった。approval / enabled=true 化は今回実施していない。
- metadata: `app.yaml` / README / requirements.txt の内容差分は発生しなかったため、metadata 復元作業は不要。App Studio の標準生成に伴い icon と build metadata は更新された。
- timing: build_env_creation 94.721s、build_tools_install 27.747s、pyinstaller_build 46.205s、registration_copy 5.751s。

復元後の `verify_release.ps1`:

- `app_20260201_agendasnap` の local `run.entry` 欠落と App Pack 内 `run.entry` 欠落は解消。
- 残る既知 NG は `addnum_pdf` と `officetopdf_toc`。どちらも source_entry が存在しないため、次は元 source の再入手または source_entry 修正が必要。

### 2026-05-08 `officetopdf_toc` full delete 計画

`officetopdf_toc` は source_entry `C:\Users\kuroron\Downloads\drive-download-20260427T120504Z-3-001\OfficeToPDF_TOC.py` と親 directory が存在せず、ユーザー判断により復元対象から外す。今回は production full delete は実行せず、既存 planner の dry-run と executor dry-run で repo 管理物だけを削除対象にできることを確認した。

現在の状態:

- manifest: `enabled=true`、package `app_packs/officetopdf_toc-0.1.0.zip`、sha256 は既存 zip と一致。
- `verify_release.ps1`: local `run.entry` `apps/officetopdf_toc/bin/officetopdf_toc/officetopdf_toc.exe` が missing。App Pack 内 `officetopdf_toc/bin/officetopdf_toc/officetopdf_toc.exe` も missing。

`scripts/plan_app_delete.ps1 -AppId officetopdf_toc -Json` の delete targets:

| category | action | path | exists |
| --- | --- | --- | --- |
| `managed_generated` | delete App Pack zip | `release/app_packs/officetopdf_toc-0.1.0.zip` | true |
| `managed_generated` | delete runtime app_env | `runtime/app_envs/officetopdf_toc` | false |
| `managed_required` | delete apps/<app_id>/ | `apps/officetopdf_toc` | true |
| `managed_required` | remove app_manifest entry | `release/app_manifest.json` の `officetopdf_toc` entry | true |

excluded targets:

- external reference: `C:\Users\kuroron\Downloads\drive-download-20260427T120504Z-3-001\OfficeToPDF_TOC.py`
- external reference: `C:\Users\kuroron\Downloads\drive-download-20260427T120504Z-3-001\ToolHub_AppStudio_Output\officetopdf_toc`
- user data: `%LOCALAPPDATA%\ToolHub\data`、`logs`、`browser_profiles`、`app_state`、`app_state\officetopdf_toc`
- shared runtime: `runtime/python`、`runtime/web_automation_runtime`

安全確認:

- warnings: 0
- blocking reasons: 0
- executor dry-run safety_errors: 0
- staging targets: 0
- staging candidates: 0
- backup/history targets: 0
- delete targets に external source path、external output mirror、user data、shared runtime、他 app は含まれていない。
- PowerShell production `-Apply` は設計上使わない。production full delete は authenticated admin UI の Delete tab から plan 表示後に Tauri command `app_studio_full_delete_apply` で実行する。PowerShell `execute_app_delete.ps1 -Apply` は temporary fixture 専用で、production root には使わない。

次アクション:

1. Admin UI の App Studio Delete tab で `officetopdf_toc` の plan を表示する。
2. 表示された delete targets / excluded targets が上記と一致し、blocking reasons がないことを確認する。
3. UI の full delete を実行する。
4. 実行後に `scripts/verify_release.ps1` を再実行し、`officetopdf_toc` の NG が消え、残る既知 NG が `addnum_pdf` のみになったことを確認する。

### 2026-05-08 `officetopdf_toc` full delete 事後検証

Admin UI / Tauri command 経由で実行済みの `officetopdf_toc` full delete について、Codex 側では full delete を再実行せず、削除後状態だけを検証した。

削除後状態:

- `apps/officetopdf_toc/`: missing。
- `release/app_packs/officetopdf_toc-*.zip`: 該当なし。
- `release/app_manifest.json`: `officetopdf_toc` entry なし。
- `runtime/app_envs/officetopdf_toc/`: missing。
- `scripts/plan_app_delete.ps1 -AppId officetopdf_toc -Json`: 削除後 dry-run では manifest entry / app dir が既に missing の warning 2 件のみ。shared runtime と user data は excluded target のまま。

除外対象の確認:

- `%LOCALAPPDATA%\ToolHub\data`: exists。
- `runtime/python`: exists。
- `runtime/web_automation_runtime`: exists。
- `apps/app_20260201_agendasnap/`: exists。
- `apps/run_xcgate_upload/`: exists。
- 外部 source path と external output mirror は引き続き missing。これらは事前 plan でも delete target ではなく、今回の full delete 対象外。

検証結果:

- `scripts/verify_release.ps1`: exit code 0。`officetopdf_toc` の local `run.entry` 欠落 / App Pack 内 `run.entry` 欠落 NG は解消。
- 想定では残 NG は `addnum_pdf` のみだったが、現在の `release/app_manifest.json` と `apps/` 一覧には `addnum_pdf` も存在せず、今回の `verify_release.ps1` では NG 0。
- `scripts/check_all.ps1`: exit code 0。release manifest verification、delete plan / executor safety tests、App Studio tests、frontend checks、Rust check は pass。installer 未生成と MSVC shell 未設定は既存 warning。
- 本番差分は `apps/officetopdf_toc/` の削除と `release/app_manifest.json` からの `officetopdf_toc` entry removal に限定されている。`release/manifest.json`、`apps/app_20260201_agendasnap/`、`apps/run_xcgate_upload/`、runtime / data / logs には今回対象の差分なし。

## 調査で確認した根拠

### 1. release 検証が壊れた登録を見逃す

現状の `scripts/verify_release.ps1` は App Pack zip の存在、hash、`app.yaml`、`pack_manifest.json` の有無を中心に確認している。一方で、`app.yaml` の `run.entry` が実際に存在するか、zip 内に含まれているかは確認していない。

現時点の `apps/*/app.yaml` では、次のように `run.entry` が存在しないアプリがある。

| app_id | run.entry | local file exists |
| --- | --- | --- |
| `addnum_pdf` | `bin/addnum_pdf/addnum_pdf.exe` | false |
| `app_20260201_agendasnap` | `bin/app_20260201_agendasnap/app_20260201_agendasnap.exe` | false |
| `officetopdf_toc` | `bin/officetopdf_toc/officetopdf_toc.exe` | false |
| `run_xcgate_upload` | `bin/run_xcgate_upload/run_xcgate_upload.exe` | false |

さらに、現時点の `release/app_packs/*.zip` には `.exe` が含まれていない App Pack がある。それでも `scripts/verify_release.ps1` は成功する。

原因:

- `verify_release.ps1` が `run.entry` を parse していない。
- `package_app_pack.ps1` が zip 作成前に `run.entry` の存在を必須検証していない。
- `apps/*/bin/` は `.gitignore` 対象のため、生成済み exe がない状態でも repo 上では見逃しやすい。

影響:

- 登録済み・release 検証済みのように見えても、実際にはアプリ起動に失敗する。
- アプリ登録失敗の再現性が悪くなり、利用者環境で初めて壊れていることに気づく。

### 2. 待機時間の大部分が secret scan / build_env / PyInstaller に集中している

`data/logs/app_studio/security_checker_timing_report.json` の最新 suggest では、合計約 141.7 秒のうち secret scan が約 129.9 秒を占めていた。

過去の apply 実行ログでは、合計約 448 秒のうち `build_env_creation` が約 336 秒、`pyinstaller_build` が約 82 秒を占めていた。

原因:

- source root が広く、対象外の clone repo、work directory、結果出力、生成物まで scan 対象になっている。
- `build_env` が毎回 rebuild され、pip install の再利用がない。
- PyInstaller が `--clean` で毎回 build cache を捨てている。
- Apply が Suggest 相当の解析、metadata、icon、export も再実行している。
- timing estimate が app_id 単位の直近総時間だけを使い、action、source hash、profile、cache 状態を区別していない。

影響:

- 小さな修正や再試行でも数分単位で待つ。
- Suggest と Apply の見積もりがずれる。
- 管理者が「止まっている」と感じやすい。

### 3. source root が広すぎると PyInstaller が関係ない依存まで拾う

`security_checker_frozen_folder_build_report.md` では、PyInstaller command に unrelated repo 配下の多数の Python file / data file が含まれていた。例として、ToolHub 自体、別プロジェクト、clone repo、作業ディレクトリ配下のファイルが `--add-data` や hidden import 候補に混ざっていた。

その結果、`hook-webrtcvad.py` が要求する `__PyInstaller_hooks_0_webrtcvad` import に失敗し、PyInstaller build が止まっている。

原因:

- entry point の親や周辺ディレクトリを source として扱う際の除外ルールが不足している。
- `work/`, `results/`, clone repo, generated output, unrelated project directory を明確に除外できていない。
- hidden import 推定が広すぎ、対象アプリの import graph ではなく、同一 source tree 内のファイルを過剰に拾っている。
- PyInstaller hook / hooks-contrib の組み合わせが動的で、既知安定版に固定されていない。

影響:

- build が遅くなる。
- アプリ本体と関係ない依存の hook failure で登録が失敗する。
- secret scan の対象も増え、AI submission block につながる。

### 4. アイコン生成が fallback へ流れる原因は複数ある

`icon_work/ai_generation_report.md` では、AI icon prompt generation と image generation が skip され、fallback 候補のみが作られていた。

確認された要因:

- AI が有効化されていない。
- API key が検出されていない。
- secret scan が AI submission を block している。
- 実際の image generation status が `skipped` / model `not_configured` になっている。
- fallback candidate count は 3、API candidate count は 0。

`secret_scan_report.json` では、`blocks_apply=false` である一方、`affects_ai_submission=true` の finding が多数あり、AI 送信だけが止まる状態になっていた。

原因:

- `OPENAI_API_KEY` または Credential Manager 側の API key 設定がない。
- `TOOLHUB_APP_STUDIO_AI_ENABLED` が有効化されていない。
- App Studio が「実際に AI へ送る payload」ではなく、含まれる package 全体の secret scan 結果で AI 送信を止めている。
- source root が広いため、無関係なファイル内の medium finding が AI block に影響している。
- image model / organization verification / quota / rate limit / unsupported parameter の診断が登録フロー前に十分表示されていない。

影響:

- アイコン生成は毎回 fallback になりやすい。
- 管理者には「AI が失敗した」ように見えるが、実際は AI 未設定、secret block、model 問題のどれかを区別しづらい。
- fallback が正常動作なのか、設定不備なのか判断できない。

### 5. 失敗診断と進捗表示が弱い

CLI は progress line を出しているが、Rust backend 側は subprocess の出力を最後にまとめて受け取る実装になっている箇所があり、長時間 phase の live progress 表示に弱い。

また、PyInstaller の failure は report file には残るが、利用者に対しては「何を直せばよいか」の分類が不足している。

原因:

- stdout / stderr を streaming parse して phase update に変換する backend 処理が不足している。
- PyInstaller failure classifier がない。
- secret scan / AI skip / model error / missing key / broad source root の診断が UI 上で分離されていない。
- Apply failure 後に「最短で直すための次アクション」を提示する仕組みがない。

影響:

- 長い待機中に状況が分からない。
- 再試行しても同じ原因で失敗しやすい。
- 管理者が build profile や source root の修正にたどり着きにくい。

## 改善バックログ

| ID | 優先度 | 領域 | 課題 | 原因 | 改善案 | 検証観点 |
| --- | --- | --- | --- | --- | --- | --- |
| AR-001 | P0 | 登録検証 | `run.entry` が存在しない App Pack を成功扱いできる | package / verify が `run.entry` を見ていない | `package_app_pack.ps1` と `verify_release.ps1` で app.yaml を parse し、local / zip 内の `run.entry` 存在を必須チェックする | 既存の exe 欠落 App Pack が fail になる |
| AR-002 | P0 | 登録検証 | approve 前後の release 検証が壊れたアプリを見逃す | App Pack 構造検証が浅い | App Pack 内の `app.yaml`, `pack_manifest.json`, `README`, icon, `run.entry`, forbidden files を検証する | `scripts/verify_release.ps1` が欠落 payload を検出する |
| AR-003 | P0 | source scope | unrelated repo / generated files が登録対象に混ざる | source root と除外ルールが不足 | App Studio に source root の明示指定、preview、除外ルール、`.toolhubignore` 相当を追加する | `work/`, `results/`, clone repo が inventory / secret scan / PyInstaller に入らない |
| AR-004 | P0 | failure prevention | PyInstaller が関係ない hook failure で落ちる | hidden import / add-data 推定が広すぎる | import graph 起点を entry point に限定し、build profile の exclude / hidden-import override を UI で扱う | `webrtcvad` のような無関係 hook が入らない |
| AR-005 | P0 | icon AI | AI icon が毎回 fallback になる | AI disabled / missing key / secret block が区別されない | 登録前に AI 診断を実行し、AI disabled、missing key、secret block、model error を別々に表示する | fallback 理由が UI と report で一致する |
| AR-006 | P1 | secret scan | AI 送信だけ過剰に block される | package 全体の finding で AI submission を止めている | 実際に AI へ送る prompt payload だけを別途 scan し、package finding とは分ける | package 内 warning があっても AI payload が安全なら icon AI が動く |
| AR-007 | P1 | performance | Apply が毎回 `build_env` を作り直す | env cache がない | requirements hash + Python version + build profile hash で `build_env` を再利用する | 2026-05-08 Phase 2-A で実装済み。`output_dir/build_env/toolhub_build_env_cache.json` に cache key を保存し、2 回目 Apply で一致すれば build_env を再利用する |
| AR-008 | P1 | performance | pip install が毎回遅い | wheel / pip cache 活用が明示されていない | App Studio 専用 wheel cache を使い、offline / cached install を優先する | 2026-05-08 Phase 2-A で一部実装済み。`output_dir/build_tmp/pip_cache` を `PIP_CACHE_DIR` として使う。offline 優先は未実装 |
| AR-009 | P1 | performance | PyInstaller が毎回 clean build される | `--clean` 固定で cache を捨てる | 通常再試行では incremental build、問題時だけ clean build にする | clean なし再試行の build 時間が短縮される |
| AR-010 | P1 | performance | Suggest 後の Apply が同じ解析をやり直す | Suggest artifact を Apply が再利用しない | metadata / README / icon / inventory / secret scan を source hash 付きで保存し、Apply で再利用する | Suggest 済みアプリの Apply 前半 phase が skip される |
| AR-011 | P1 | progress UX | 長時間 phase が止まって見える | subprocess output の streaming が弱い | Rust backend で App Studio CLI stdout を streaming parse し、phase progress を UI に反映する | build_env / PyInstaller 中に UI が更新される |
| AR-012 | P1 | timing | 見積もりが action と実測に合わない | app_id 単位の前回総時間だけを使う | action、source hash、profile、cache hit 状態ごとに timing history を分ける | Suggest と Apply の見積もりが混ざらない |
| AR-013 | P1 | PyInstaller | hooks-contrib / PyInstaller の新しさで壊れる | version range が広い | 既知安定版を lock し、更新は検証後に行う | 同じ app が日によって hook failure しにくくなる |
| AR-014 | P1 | Python runtime | 開発機の Python version に依存する | build Python が固定されていない | App Studio build 用 Python version を決め、診断に表示する | 未対応 Python で build する前に警告が出る |
| AR-015 | P1 | failure UX | PyInstaller error が利用者に難しすぎる | failure classifier がない | common failure を分類し、source scope、missing package、hook failure、binary dependency などの対処を出す | failure report に分類と推奨アクションが出る |
| AR-016 | P2 | build profile | 管理者が profile 調整しづらい | profile editor / dry-run が弱い | hidden imports / excludes / data files の preview と編集 UI を追加する | profile 変更前後の PyInstaller command 差分が見える |
| AR-017 | P2 | icon UX | fallback が失敗に見える | fallback と AI skip の意味が表示されない | fallback は正常代替、AI skip は設定/scan理由として分けて表示する | 管理者が fallback 採用か AI 設定修正か選べる |
| AR-018 | P2 | approval | approve が全体 release verify に依存し遅い | target app だけの軽量検証がない | approve 前は対象 app / target App Pack の検証を優先し、全体 verify は別コマンドに分ける | approve の待ち時間が短縮される |
| AR-019 | P2 | smoke test | App Pack が起動可能か検証していない | entry file 存在以上の実行検証がない | optional smoke command / CLI check / launch dry-run を app.yaml に追加できるようにする | 登録後に最低限の起動確認ができる |
| AR-020 | P2 | reports | 調査に必要な情報が複数 report に分散 | summary index がない | App Studio run summary に phase time、skip reason、failure reason、重要 report path を集約する | 1 つの summary から原因調査を開始できる |
| AR-021 | P2 | App Pack spec | `requirements.lock` の扱いが仕様と実装で曖昧 | spec では source of truth に含まれるが sample app には存在せず、package / verify は必須にしていない | runner / build_mode 別に `requirements.lock` を必須・任意・警告のどれにするか決め、package / verify / docs を揃える | sample app と frozen-folder app の両方で意図した結果になる |
| AR-022 | P2 | validator consistency | PowerShell と Python で app.yaml path 検証が重複している | packaging / release verify / App Studio registrar が別々に YAML scalar と相対パスを処理している | 共通 validator 化、または同じ fixture を使う golden test を追加して挙動差を防ぐ | `run.entry` / `display.icon` の edge case が各経路で同じ結果になる |
| AR-023 | P1 | source scope UX | source scope preview がまだ report 中心で、登録前に十分操作できない | GUI では source root 入力だけで、include/exclude一覧の事前表示がない | preflight で inventory preview を軽量実行し、主要除外ディレクトリと included count を表示する | 管理者が Apply 前に混入を発見できる |
| AR-024 | P2 | CLI wrapper | `scripts/import_app.ps1` から `--source-root` を指定できない | Phase 1-A では CLI 本体と GUI の経路を優先した | `-SourceRoot` を wrapper に追加し、docs の PowerShell 例も更新する | PowerShell wrapper でも明示 source root を使える |
| AR-025 | P1 | timing / failure UX | PyInstaller が `ok=False` で返っても timing phase が `pass` 表示になる | timing context は例外の有無だけで phase status を決めている | result object を返す phase では `ok=False` を timing に反映する | `timing_report` と GUI progress が最終 failure と矛盾しない |
| AR-026 | P1 | performance / registration | Playwright など大きい frozen-folder の `registration_copy` / App Pack 作成が長い | 既存 app backup、`apps/<app_id>` copy、staging copy、zip 作成で深い tree を複数回走査している | Phase 2 以降で登録コピーと zip 作成の timing を分解し、不要な再コピー削減や pack 作成経路の見直しを検討する | 2026-05-08 Phase 2-B で breakdown を追加。Phase 2-C で backup を `move_existing_app_directory`、App Pack 作成を `direct_zip_from_apps_dir` に標準化。Phase 2-D で compression 候補を比較し、標準 policy は `ZIP_DEFLATED` level 1 継続に決定。実アプリ `xcg_p2d` の `registration_copy` は 12.483 秒、主要因は `compress_app_pack` 11.580 秒 |
| AR-027 | P2 | packaging script | `scripts/package_app_pack.ps1` が `release/app_manifest.json` を UTF-8 BOM 付きで書くと一部 PowerShell test が BOM を JSON 本文として扱い失敗する | Windows PowerShell の `Set-Content -Encoding UTF8` が BOM 付きで保存する | manifest / JSON 書き込みを UTF-8 no BOM helper に統一する | 2026-05-08 Phase 1-E で実装済み。`check_all.ps1` に release JSON の BOM 検査と helper test を追加 |
| AR-028 | P3 | app pack metadata | 既存 App Pack zip 内の `pack_manifest.json` に Phase 1-E 前の UTF-8 BOM が残る | 過去の `Set-Content -Encoding UTF8` 生成物で、今回は App Pack 再生成をしない方針 | 次回 App Pack 再生成時に UTF-8 no BOM へ自然更新する。全 App Pack の metadata-only repack が必要なら別作業で対象と検証範囲を決める | 既存 zip を不用意に変更せず、今後の生成物は no BOM になる |

## 推奨実装順

### Phase 0: 壊れた登録を成功扱いしない

最初に `run.entry` 検証を強化する。これは待ち時間短縮ではないが、失敗した登録を成功扱いするリスクを止めるため最優先にする。

対象:

- `scripts/package_app_pack.ps1`
- `scripts/verify_release.ps1`
- 必要なら `tools/app_studio/app_studio/approval.py`

実装内容:

- `app.yaml` の `run.entry` を parse する。
- local `apps/<app_id>/<run.entry>` の存在を確認する。
- App Pack zip 内の `<app_id>/<run.entry>` の存在を確認する。
- 欠落時は warning ではなく fail にする。

### Phase 1: source scope を絞る

次に、待機時間と失敗率の両方に効く source scope の改善を行う。

対象:

- `tools/app_studio/app_studio/file_classifier.py`
- `tools/app_studio/app_studio/build_profile.py`
- `tools/app_studio/app_studio/frozen_folder_builder.py`
- App Studio UI / Rust command 層

実装内容:

- source root 明示指定を追加する。
- include / exclude preview を出す。
- `work/`, `results/`, generated output, clone repo, `.git`, virtualenv, cache 類を既定除外に追加する。
- `.toolhubignore` 相当の project-local ignore を検討する。

### Phase 2: 再試行を速くする

source scope を絞ったあと、cache と再利用を入れる。

対象:

- `app_env_builder.py`
- `lock_generator.py`
- `frozen_folder_builder.py`
- `timing.py`
- App Studio output artifact 管理

実装内容:

- `build_env` を requirements hash で再利用する。
- wheel cache を使う。
- Suggest artifact を Apply で再利用する。
- PyInstaller clean build を通常再試行から外す。
- timing history を action / source hash / profile hash 別にする。

### Phase 3: AI icon 生成を診断可能にする

fallback そのものは残しつつ、AI を使う場合に何が必要かを明確にする。

対象:

- `openai_client.py`
- `icon_generator.py`
- `secret_scanner.py`
- App Studio UI

実装内容:

- 登録前 AI diagnostics を必須表示する。
- AI disabled / missing key / secret block / model error を区別する。
- AI payload のみを対象にした secret scan を追加する。
- image model の利用可否を事前に診断する。
- fallback の採用と AI 再試行を UI 上で分ける。

### Phase 4: PyInstaller failure を直しやすくする

失敗時に管理者が修正できる状態にする。

対象:

- `frozen_folder_builder.py`
- build report generator
- build profile UI

実装内容:

- hook failure / missing module / binary dependency / broad source root / hidden import 過剰を分類する。
- report に原因分類と推奨修正を出す。
- known-good PyInstaller / hooks-contrib version を固定する。
- build profile の exclude / hidden import を UI から編集できるようにする。

## 今すぐ直すべきもの

次の改善は、実装リスクに対して効果が大きい。

1. `run.entry` の local / zip 存在検証を追加する。（2026-05-08 Phase 0 で実装済み）
2. `package_app_pack.ps1` で `run.entry` 欠落時に fail する。（2026-05-08 Phase 0 で実装済み）
3. `verify_release.ps1` で App Pack 内 `run.entry` 欠落時に fail する。（2026-05-08 Phase 0 で実装済み）
4. source scope preview と既定除外を強化する。（2026-05-08 Phase 1-A で CLI / GUI入力 / report / 既定除外 / `.toolhubignore` の初期実装済み。interactive preview は AR-023）
5. AI icon fallback の理由を UI / report で分離表示する。

## 2026-05-08 Phase 3 実施状況: AI icon fallback 診断

- AI画像生成の失敗理由を `ai_disabled`、`missing_api_key`、`missing_image_model`、`organization_not_verified`、`unsupported_model`、`quota_or_rate_limit`、`authentication_failed`、`secret_scan_blocked`、`network_error`、`api_error`、`unknown` に分類する診断を追加した。
- `gpt-image-2` が実APIレスポンスで `Your organization must be verified` を返す場合は `organization_not_verified` として扱う。OpenAI側の提供条件を断定せず、実APIエラーに基づく診断として記録する。
- `icon_work/ai_generation_report.md` と `icon_work/ai_generation_report.json` に、text prompt generation status、image generation status、image model、API候補数、fallback候補数、failure class、管理者向けメッセージ、次アクション、fallback作成理由を出す。
- `candidate_manifest.json` の `image_api_summary` にも同じ診断情報を追加し、GUIはAPI画像候補とローカル暫定アイコンを分離表示する。
- package全体のsecret scan結果と、実際に画像APIへ送るicon prompt payloadのsecret scan結果を分けて記録する。payloadに秘密情報の可能性がある場合は `secret_scan_blocked` として画像生成を止める。
- fallbackは残すが、AI生成候補・おすすめ・高品質候補とは扱わず、AI不可時の暫定アイコンとして表示する。

## 注意点

- runtime archive の自動生成や同梱方針をこの改善で大きく変える必要はない。
- App Pack と runtime archive の責務は分けたままにする。
- `app.yaml` の既存仕様は破壊しない。
- 既存 app が `run.entry` 欠落で fail するようになるため、検証強化の導入時には現在の欠落 app を修正するか、検証結果を known issue として扱う必要がある。
- `release/` や `runtime/` の実体を直接変更する前に、まず scripts / App Studio 側の検証強化から進める。
