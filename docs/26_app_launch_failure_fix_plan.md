# App Launch Failure Fix Plan

Created: 2026-05-10

## Implementation Status

実装済み。
この文書は、ホーム画面で「起動しました」と表示されるのにアプリ画面が立ち上がらない問題について、調査結果、修正方針、実装内容を整理するものです。

今回の実装で対応した範囲:

- runner が detached 起動直後の異常終了を検知し、成功扱いにしない。
- detached 起動時の stdout / stderr をアプリ別ログへ保存し、起動直後クラッシュの原因を追跡できるようにする。
- App Studio の frozen-folder ビルドで Flet アプリを検出した場合、`flet-desktop` を同一バージョンで build_env に補完する。
- PyInstaller profile に `flet_desktop` hidden import と `flet` / `flet_desktop` collect-all を追加する。
- App Studio の配布物検証で frozen exe の短時間 smoke check を行い、即時クラッシュを承認前に fail として検出する。

注意:

- 既存登録済みアプリの古い frozen exe は、修正済み App Studio で再登録または再ビルドするまで中身は更新されない。
- すでに起動失敗していた Flet 系アプリは、再ビルド後に `flet-desktop` 同梱済みの配布物へ置き換える必要がある。

運用補修結果:

- `legacy_flet_system_20260510` は修正済み App Studio で再ビルド、承認、有効化済み。
- `app_20260201_agendasnap` は修正済み App Studio で再ビルド、承認、有効化済み。
- `run_xcgate_upload` は `xcgate_flows/src` を data 同梱する profile 補正後に再ビルド、承認、有効化済み。
- `app_20260215_pdfapplication` は登録元 `source_entry` の `app.py` が存在しないため再ビルド不可。既存 frozen-folder に `flet_desktop==0.84.0` を補修同梱し、App Pack と manifest hash を更新済み。

## Purpose

ToolHub のホーム画面から登録済みアプリを起動した際に、以下の問題が発生している。

- 起動ダイアログには「起動しました」と表示される。
- 実際には対象アプリの画面が表示されない。
- `legacy_flet_system_20260510` だけでなく、複数の登録済みアプリで同様の見え方になる。

本件の目的は、単一アプリだけを個別に直すのではなく、以下を分けて修正することです。

1. ToolHub runner が起動直後の異常終了を成功扱いしてしまう共通問題。
2. App Studio の frozen-folder ビルドが Flet desktop runtime を同梱できていない問題。
3. 各アプリ固有の packaging / import エラーを正しくログへ出し、管理者が特定できるようにする問題。

## Observed Symptoms

### User Visible Behavior

- ホーム画面でアプリカードの「起動」を押す。
- 起動状態モーダルに以下が表示される。

```text
起動しました。
```

- ただし、アプリ本体のウィンドウは表示されない。

### Runner Log Behavior

`legacy_flet_system_20260510` の実行ログでは、runner は成功として記録している。

```json
{
  "app_id": "legacy_flet_system_20260510",
  "exit_code": null,
  "pid": 20712,
  "stdout": "",
  "stderr": "",
  "user_message": "起動しました。"
}
```

ここで重要なのは、`exit_code: null` が「成功」を意味していないことです。現在の GUI/exe 起動経路では、起動直後に終了したかどうかを runner が見ていません。

### Direct Executable Behavior

同じ exe を ToolHub 経由ではなく直接実行すると、実際の失敗理由が確認できた。

`legacy_flet_system_20260510`:

```text
Installing flet-desktop 0.85.0 package...
Unable to install "flet-desktop" package.
ModuleNotFoundError: No module named 'flet_desktop'
NameError: name 'exit' is not defined
[PYI-22212:ERROR] Failed to execute script 'app' due to unhandled exception!
```

`app_20260215_pdfapplication`:

```text
Installing flet-desktop 0.84.0 package...
Unable to install "flet-desktop" package.
ModuleNotFoundError: No module named 'flet_desktop'
NameError: name 'exit' is not defined
[PYI-28896:ERROR] Failed to execute script 'app' due to unhandled exception!
```

`app_20260201_agendasnap`:

```text
Installing flet-desktop 0.84.0 package...
Unable to install "flet-desktop" package.
ModuleNotFoundError: No module named 'flet_desktop'
NameError: name 'exit' is not defined
[PYI-12864:ERROR] Failed to execute script 'main' due to unhandled exception!
```

`run_xcgate_upload`:

```text
ModuleNotFoundError: No module named 'src.main'
[PYI-22256:ERROR] Failed to execute script 'run_xcgate_upload' due to unhandled exception!
```

## Root Cause Details

### Root Cause 1: GUI/exe runner falsely reports startup success

対象ファイル:

- `runner/toolhub_runner/base_runner.py`
- `runner/toolhub_runner/exe_runner.py`
- `runner/toolhub_runner/python_runner.py`
- `launcher/src-tauri/src/runner.rs`

現在の GUI/exe 起動では、`BaseRunner.start_detached()` が `subprocess.Popen()` を呼び出した時点で成功扱いにしている。

```python
process = subprocess.Popen(
    command,
    cwd=str(self.manifest.app_dir),
    env=env,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
    close_fds=True,
)
pid = process.pid
ok = True
events.append(RunnerEvent(type="success", message="起動しました", progress=100))
```

この実装では、以下を検出できない。

- exe が起動直後に `exit_code=1` で落ちた。
- Python GUI が import error で即終了した。
- PyInstaller exe が missing module で即終了した。
- stderr に重要な原因が出ている。

さらに `stdout=subprocess.DEVNULL` / `stderr=subprocess.DEVNULL` のため、即時クラッシュ時のエラー内容も捨てられる。

このため、ToolHub 側では「起動プロセスの作成に成功した」だけで「アプリが起動した」と表示している。

### Root Cause 2: Flet desktop runtime is missing from frozen-folder packages

対象ファイル:

- `tools/app_studio/app_studio/build_profile.py`
- `tools/app_studio/app_studio/app_env_builder.py`
- `tools/app_studio/app_studio/lock_generator.py`
- `tools/app_studio/app_studio/frozen_folder_builder.py`
- `tools/app_studio/app_studio/runtime_checker.py`

Flet 系アプリの `requirements.lock` には `flet` は含まれているが、`flet-desktop` が含まれていない。

確認例:

```text
app_20260201_agendasnap:       flet==0.84.0
app_20260215_pdfapplication:   flet==0.84.0
legacy_flet_system_20260510:   flet==0.85.0
```

一方で、PyInstaller で固めた exe 実行時に Flet は `flet_desktop` を import しようとする。パッケージ内に存在しないため、`ModuleNotFoundError` で終了する。

Flet 側は不足時に `flet-desktop==<flet version>` のインストールを試みるが、frozen exe の runtime では pip install に依存できない。そのため、ビルド時点で `flet-desktop` を同梱する必要がある。

### Root Cause 3: App Studio distribution check skips frozen exe smoke execution

対象ファイル:

- `tools/app_studio/app_studio/runtime_checker.py`

現在の frozen-folder 検証では、exe の存在、app.yaml の entry、requirements.lock などは確認するが、生成 exe の短時間起動確認はスキップしている。

```text
frozen smoke execution: warn
Skipped automatically for exe/frozen-folder mode.
```

このため、今回のような「exe は存在するが、起動すると即時クラッシュする」状態が登録・承認を通過できる。

### Root Cause 4: Some apps have independent packaging defects

`run_xcgate_upload` は Flet とは別原因で失敗している。

```text
ModuleNotFoundError: No module named 'src.main'
```

これは PyInstaller packaging 時に `src.main` が同梱または import 解決できていないことを示す。

したがって、「全アプリが立ち上がらない」という見え方の共通原因は runner の誤成功表示ですが、実体エラーはアプリごとに異なる。

## Non Goals

今回の修正では、以下は行わない。

- 個別 app_id を launcher / Rust backend にハードコードしない。
- end user runtime で `pip install flet-desktop` を実行しない。
- `apps/<app_id>/app.yaml` の既存仕様を破壊しない。
- GUI アプリを blocking 実行へ全面変更しない。
- Flet アプリのソースコードを一律に書き換えない。
- `run_xcgate_upload` の個別 import 問題を Flet 修正に混ぜない。

## Fix Strategy

### Phase 1: Fix detached runner startup verification

最優先。

`BaseRunner.start_detached()` を、単に `Popen` 成功で完了する実装から、短時間の起動監視を行う実装へ変更する。

#### Proposed Behavior

1. プロセスを起動する。
2. stdout / stderr を一時ログファイルへリダイレクトする。
3. 短い grace period を待つ。
4. grace period 内に終了した場合:
   - exit code を保存する。
   - stdout / stderr を保存する。
   - `ok=false` とする。
   - UI には「起動直後に終了しました」と表示する。
   - 管理者向けログには exit code と stderr tail を残す。
5. grace period 後も生存している場合:
   - `ok=true` とする。
   - pid を保存する。
   - UI には「起動しました」と表示する。

#### Grace Period

初期値は 2 秒程度を推奨する。

理由:

- import error / missing DLL / missing module は通常 2 秒以内に終了する。
- GUI 起動を長く待つとホーム画面の操作感が悪くなる。
- Flet / Tkinter / PyInstaller の即時クラッシュ検出には十分。

将来的には `app.yaml` に以下のような任意設定を追加できるが、初回修正では必須にしない。

```yaml
run:
  startup_probe_seconds: 2
```

#### stdout / stderr Handling

`subprocess.PIPE` を長時間保持すると、起動後の GUI アプリが大量出力した場合に pipe 詰まりを起こす可能性がある。

そのため、detached 起動では次を推奨する。

- stdout / stderr は log directory 配下の一時ファイルへ redirect する。
- 起動直後に終了した場合だけ、その内容を読み取って JSON log へ保存する。
- 生存している場合は pid と stdout/stderr log path を記録する。

#### User Message

利用者向け:

```text
アプリは起動直後に終了しました。管理者にログ確認を依頼してください。
```

管理者向け:

```text
exit_code=1
stderr_tail=ModuleNotFoundError: No module named 'flet_desktop'
```

#### Tests

追加するテスト:

- GUI mode で child process が即時 `exit 1` した場合、`ok=false` になる。
- 即時終了時に stderr が run log に保存される。
- child process が grace period 後も生存している場合、`ok=true` かつ pid が保存される。
- 存在しない exe の場合、既存通り `ok=false` になる。

### Phase 2: Add Flet desktop runtime support to App Studio frozen-folder builds

Flet が検出された場合、App Studio が自動で `flet-desktop` を runtime dependency として扱う。

#### Detection

以下のいずれかで Flet 利用を検出する。

- `requirements.txt` / `requirements.lock` に `flet` がある。
- dependency analyzer の import roots に `flet` がある。
- source file に `import flet` または `from flet` がある。

#### Dependency Rule

`flet` があり、`flet-desktop` がない場合:

1. build_env 内で解決済みの `flet` version を取得する。
2. `flet-desktop==<same version>` を build_env にインストールする。
3. `requirements.lock` に `flet-desktop==<same version>` を含める。
4. build report / lock report に自動補完したことを記録する。

例:

```text
flet==0.85.0
flet-desktop==0.85.0
```

既に `flet-desktop` が明示されている場合は、ユーザー指定を尊重する。ただし、`flet` と major/minor が明らかに不一致の場合は warning にする。

#### PyInstaller Rule

Flet が検出された場合、build profile に次を追加する。

```json
{
  "hidden_imports": ["flet_desktop"],
  "collect_all": ["flet", "flet_desktop"]
}
```

最小構成では `flet_desktop` の hidden import と collect-all が重要です。`flet` 側も assets / hooks / metadata を持つ可能性があるため、初期実装では両方を collect-all 対象にする。

#### Cache Handling

build_env cache が既に存在する場合でも、`flet-desktop` が欠けていれば補完インストールを実行する。

実装上は、以下のどちらかを選ぶ。

1. build_env cache key に dependency augmentation version を含め、cache miss で作り直す。
2. build_env 作成後に `ensure_framework_runtime_packages()` を毎回実行し、不足パッケージだけ追加する。

推奨は 2。

理由:

- 既存 cache を全破棄せずに修復できる。
- 今後 PySide / PyQt / Flet などの framework-specific runtime 補正を同じ場所に集約できる。

### Phase 3: Add frozen exe startup smoke check

App Studio の `verify_frozen_folder_distribution()` に、即時クラッシュ検出用の smoke check を追加する。

#### Proposed Check

1. `final_app/<run.entry>` を起動する。
2. 3 秒から 5 秒程度だけ監視する。
3. 監視中に終了した場合:
   - exit code が 0 でも、GUI exe としては warning または fail にする。
   - exit code が non-zero の場合は fail。
   - stdout / stderr tail を `execution_test_result.json` または runtime check report に保存する。
4. 監視後も生存している場合:
   - immediate crash はないと判断して pass。
   - テスト用に起動したプロセスを終了する。

#### Why Not Full UI Verification

自動 smoke check は「アプリ画面が正しく使える」ことまでは保証しない。

ただし、今回のような以下の問題は検出できる。

- missing module
- missing DLL
- invalid entry point
- PyInstaller boot failure
- import error
- runtime package missing

### Phase 4: Improve launch diagnostics in UI

runner が `ok=false` を返せるようになった後、UI は以下を出し分ける。

#### User Mode

```text
起動に失敗しました。
アプリは起動直後に終了しました。管理者にログ確認を依頼してください。
```

#### Admin Mode

管理画面またはログ診断には、以下を表示する。

- app_id
- command
- pid
- exit_code
- stdout tail
- stderr tail
- run log path
- result json path

Flet の代表例:

```text
ModuleNotFoundError: No module named 'flet_desktop'
```

`run_xcgate_upload` の代表例:

```text
ModuleNotFoundError: No module named 'src.main'
```

### Phase 5: Rebuild and re-register affected apps

共通修正後、以下のアプリは App Studio で再ビルドまたは更新登録する。

- `legacy_flet_system_20260510`
- `app_20260215_pdfapplication`
- `app_20260201_agendasnap`

再ビルド後に確認すること:

- `requirements.lock` に `flet-desktop==<flet version>` が入っている。
- PyInstaller command に `--collect-all flet_desktop` が含まれている。
- 直接 exe 実行で `No module named 'flet_desktop'` が出ない。
- ToolHub ホーム画面から起動して、起動直後終了にならない。

### Phase 6: Handle app-specific packaging errors separately

`run_xcgate_upload` は次の別チケットとして扱う。

```text
ModuleNotFoundError: No module named 'src.main'
```

想定修正:

- source root と entry の関係を再確認する。
- `src` が package として含まれているか確認する。
- `src/__init__.py` の有無を確認する。
- PyInstaller の `--paths` / `--hidden-import src.main` / `collect` 対象を調整する。
- 必要であれば entry script 側の import を package layout に合わせる。

この修正は Flet runtime 補正とは混ぜない。

## Files to Change

### Runner

- `runner/toolhub_runner/base_runner.py`
  - `start_detached()` に startup probe を追加する。
  - immediate exit 時の exit code / stdout / stderr を保存する。
- `runner/toolhub_runner/log_manager.py`
  - 必要に応じて stdout/stderr sidecar log path を run log に含める。
- `runner/tests/`
  - detached startup probe の単体テストを追加する。

### App Studio

- `tools/app_studio/app_studio/build_profile.py`
  - Flet 検出時の `hidden_imports` / `collect_all` を追加する。
- `tools/app_studio/app_studio/app_env_builder.py`
  - framework runtime package 補完処理を追加する。
- `tools/app_studio/app_studio/lock_generator.py`
  - 補完後の `pip freeze` に `flet-desktop` を含める。
- `tools/app_studio/app_studio/runtime_checker.py`
  - frozen exe startup smoke check を追加する。
- `tools/app_studio/tests/test_builders.py`
  - Flet 補完、PyInstaller args、smoke check のテストを追加する。

### Launcher UI

- `launcher/src/lib/appStudioRunResult.ts`
  - 起動直後終了の result 表示に必要なら型を拡張する。
- `launcher/src/components/...`
  - 起動失敗時に user message と admin details を分けて表示する。

## Validation Plan

### Unit Tests

```powershell
python -m pytest runner/tests
python -m pytest tools/app_studio/tests/test_builders.py
```

pytest が利用できない環境では、既存テスト方式に合わせて `unittest` またはプロジェクト既定のチェックを使う。

### Project Checks

```powershell
python main.py --check
.\scripts\check_all.ps1
```

### Frontend Build

UI を変更した場合:

```powershell
cd launcher
npm run build
```

### Manual Verification

1. `legacy_flet_system_20260510` を再登録または更新登録する。
2. `requirements.lock` に `flet-desktop==0.85.0` が入っていることを確認する。
3. 生成 exe を直接実行し、`No module named 'flet_desktop'` が出ないことを確認する。
4. ToolHub ホーム画面から起動し、画面が表示されることを確認する。
5. 意図的に壊した exe を起動し、ToolHub が「起動しました」ではなく失敗表示にすることを確認する。

## Risks and Decisions

### Risk: GUI app that exits quickly with code 0

`run.mode: gui` のアプリが数秒以内に `exit_code=0` で終了した場合、現在の仕様では「画面が表示されない」ため失敗または warning として扱うのが妥当。

必要になった場合のみ、将来の `app.yaml` 拡張で以下を検討する。

```yaml
run:
  startup_success_policy: spawn_only
```

ただし初回修正では導入しない。既存仕様を増やしすぎないため。

### Risk: collect_all flet increases package size

`--collect-all flet` / `--collect-all flet_desktop` により frozen-folder サイズが増える可能性がある。

ただし Flet desktop runtime が欠けると起動不能なので、まずは起動可能性を優先する。サイズ問題は runtime checker の size warning で扱う。

### Risk: App Studio smoke check opens windows

GUI exe を短時間起動するため、一瞬ウィンドウが表示される可能性がある。

対策:

- smoke check は短時間で終了する。
- grace period 後に生存していたらテスト用プロセスを終了する。
- login / file picker / browser flow の完全確認は引き続き manual check とする。

## Recommended Implementation Order

1. `BaseRunner.start_detached()` の false success を修正する。
2. runner tests を追加する。
3. Flet 検出と `flet-desktop` 補完を App Studio に追加する。
4. PyInstaller args に `flet` / `flet_desktop` collect rule を追加する。
5. frozen exe smoke check を追加する。
6. affected Flet apps を再ビルドする。
7. `run_xcgate_upload` の `src.main` import 問題を別途修正する。

## Expected Outcome

修正後は以下になる。

- 起動直後に落ちた GUI/exe は「起動しました」と表示されない。
- stderr に出ている本当の失敗理由が run log に残る。
- Flet 系 frozen-folder アプリは `flet_desktop` を同梱して起動できる。
- App Studio 登録時に「exe はあるが起動すると即落ちる」状態を検出できる。
- アプリ固有の packaging 問題を、共通 runner 問題と分けて調査できる。
