# ToolHub AgendaSnap Launch Parity Fix Plan

作成日: 2026-05-16

Status: historical remediation record. Current normal App Studio registration is `shared-env` / `python_shared_env`; AgendaSnap is registered as `python_shared_env` with `run.entry: src/main.py`. Keep this document as the root-cause and contract reference for GUI parity issues, not as the current registration flow.

## 目的

AgendaSnap を ToolHub に登録したとき、単体実行と同じ画面遷移、同じサブ画面起動、同じ起動完了判定になるようにする。

今回の不具合は次の 2 点で発生した。

- `main.py` に `argparse` があるだけで App Studio が `run.mode: cli` と判定し、GUI exe を CLI として待ち続けた。
- AgendaSnap がサブ画面起動に `sys.executable -m agendasnap.ui.<window>` を使っており、frozen exe では `sys.executable` が `python.exe` ではなくアプリ exe になった。

## 修正方針

### 1. ToolHub の `run.mode` 判定を GUI 優先にする

entry file だけでなく source root 配下の Python ファイルを確認し、Flet、tkinter、PyQt、PySide、wx、streamlit、gradio、`ft.app()` などの GUI シグナルがあれば `mode: gui` とする。

`argparse`、`sys.argv`、click、typer は CLI シグナルとして扱うが、GUI シグナルより優先しない。

期待結果:

- AgendaSnap は `argparse` を持っていても `mode: gui` になる。
- GUI 起動後、ToolHub の起動ダイアログは成功状態に移行できる。
- 純粋な CLI アプリは従来どおり `mode: cli` になる。

### 2. frozen exe で壊れるサブプロセス起動を検出する

source root 配下を走査し、次のようなローカル module 起動を検出する。

```python
subprocess.Popen([sys.executable, "-m", "my_app.ui.settings"])
```

検出した場合は approval-blocking warning とする。

理由:

- frozen exe では `sys.executable` がアプリ exe を指す。
- `app.exe -m my_app.ui.settings` は Python の `-m` 実行ではない。
- 多くの GUI アプリではメイン画面が二重起動する。

### 3. frozen GUI の自動検証は smoke flag を優先する

GUI exe を登録時にそのまま起動すると、実 UI、録音、ブラウザ、外部通信が始まる可能性がある。

ToolHub は source に `--toolhub-smoke` または `--smoke` がある場合だけ、frozen exe にその flag を渡して smoke 実行する。GUI アプリで safe smoke flag がない場合は approval-blocking warning にする。

### 4. AgendaSnap 側の修正は docs/31 に従う

AgendaSnap 側では `main.py` に window dispatcher を置き、次の入口を提供する。

```text
python main.py --toolhub-smoke
python main.py --window main
python main.py --window caption
python main.py --window settings
python main.py --window minutes
```

メイン画面からサブ画面を起動するときも、`sys.executable -m ...` ではなく entry point を再呼び出す。

## 実装対象

- `tools/app_studio/app_studio/app_contract.py`
  - source root から GUI/CLI シグナルを検出する。
  - safe smoke flag を検出する。
  - frozen で壊れる `sys.executable -m <local module>` を検出する。

- `tools/app_studio/app_studio/manifest_generator.py`
  - `infer_run_mode()` を GUI 優先の source scan に差し替える。

- `tools/app_studio/app_studio/runtime_checker.py`
  - frozen distribution check に child-process contract check を追加する。
  - frozen GUI smoke は `--toolhub-smoke` または `--smoke` を使う。

- `tools/app_studio/app_studio/execution_tester.py`
  - 登録済み app の execution report に `mode` と child-process contract check を出す。

- `tools/app_studio/tests/`
  - AgendaSnap 型の Flet サブ画面構成で `mode: gui` になること。
  - `sys.executable -m <local module>` が検出されること。
  - frozen GUI smoke が safe flag を使うこと。

## 完了条件

- AgendaSnap 型 source で `run.mode: gui` が生成される。
- frozen-folder でローカル module を `sys.executable -m` 起動している場合、approval-blocking warning が出る。
- `--smoke` または `--toolhub-smoke` を持つ GUI frozen exe は、その flag で smoke 実行される。
- 既存の shared-env、dependency、payload gate の修正を壊さない。
