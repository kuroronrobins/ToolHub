# ToolHub App Registration App Authoring Guidelines

作成日: 2026-05-16

## 目的

ToolHub に Python アプリを登録したあとも、単体実行時と同じ動作を再現できるように、アプリ作成時点で守るべきルールを定義する。

特に GUI アプリ、Flet アプリ、PyInstaller frozen-folder 化されるアプリでは、`sys.executable`、作業ディレクトリ、設定ファイル位置、子プロセス起動の意味が変わる。この差分をアプリ側で吸収できる形にしておく。

この文書は人間が作業するときにも、Codex に「このアプリを ToolHub 登録対応に修正して」と依頼するときにも使える指示書とする。

## 基本原則

- ToolHub 登録対象の entry point は 1 つにする。
- `main.py` は直接実行、`python main.py`、frozen exe の全てで同じ入口として動くようにする。
- import しただけで GUI、外部通信、録音、ブラウザ起動、ファイル削除などを開始しない。
- runtime dependency は root 直下の `requirements.txt` または `pyproject.toml` に集約する。
- `.venv`、`venv`、`build`、`dist`、`ToolHub_AppStudio_Output`、ログ、録音、認証情報、キャッシュは登録対象に含めない。
- GUI アプリは ToolHub の runner に長時間待たせない。起動後は launcher に制御が戻る前提で設計する。
- GUI アプリの entry process は、ToolHub の起動確認が終わるまで生存する。子プロセスだけ起動して親プロセスが即終了する構成にしない。
- サブ画面、設定画面、補助プロセスは frozen exe でも同じ entry point から起動できるようにする。

## 現在の ToolHub 登録方式

現行の App Studio 通常登録では、Python ソースアプリは `shared-env` として登録される。

- `app.yaml` の runner は `python_shared_env` になる。
- 依存関係は `requirements.lock` から選ばれた versioned shared runtime にインストールされる。
- 同じ dependency lock を持つアプリは、同じ共有ランタイムを再利用できる。
- アプリ本体は `apps/<app_id>/` に配置され、ランタイムは `runtime/envs/<env_id>/` に分離される。

したがって、アプリ側は「自分専用 venv が常に隣にある」前提ではなく、ToolHub が選んだ Python で entry point が実行される前提で作る。

明示的に frozen-folder や既存 exe を選ぶ場合を除き、通常の Python アプリは shared-env で成立する構成を優先する。

## 推奨ディレクトリ構成

単純なアプリ:

```text
my_app/
  main.py
  requirements.txt
  README.md
  .toolhubignore
  my_app/
    __init__.py
    app.py
    ui/
    config/
```

package 型のアプリ:

```text
my_app/
  pyproject.toml
  requirements.txt
  README.md
  .toolhubignore
  src/
    my_app/
      __init__.py
      main.py
      ui/
```

避ける構成:

```text
my_app/
  main.py
  old_version/
    requirements.txt
  helper/
    requirements.txt
  venv/
  logs/
  ToolHub_AppStudio_Output/
```

ToolHub は source root 直下の dependency file を使う。`pyproject.toml` の `[project].dependencies`、root 直下の `requirements.txt`、root 直下の `requirements.lock` が主な入力になる。

古いサブプロジェクトや helper 用の `requirements.txt` は自動選択しない。必要な依存が nested requirements にしかない場合は、source root を狭めるか、root 直下に正しい `requirements.txt` を用意する。

## Entry Point

`main.py` はアプリ全体の唯一の外部入口にする。

推奨:

```python
from my_app.launcher import main


if __name__ == "__main__":
    raise SystemExit(main())
```

避ける:

```python
import my_app.ui

my_app.ui.start()
```

理由:

- App Studio は entry point を解析、smoke、packaging、runner 起動に使う。
- import 時点で処理が始まると、自動検証と frozen 化で失敗しやすい。

## GUI と CLI の分離

GUI アプリでも `argparse` を使ってよい。ただし `argparse` があるだけで CLI アプリとみなされないよう、アプリ側も起動モードを明示する。

推奨する引数:

```text
python main.py --toolhub-smoke
python main.py --window main
python main.py --window settings
python main.py --window captions
python main.py --window minutes
```

実装例:

```python
from __future__ import annotations

import argparse


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--toolhub-smoke", action="store_true")
    parser.add_argument(
        "--window",
        choices=["main", "settings", "captions", "minutes"],
        default="main",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.toolhub_smoke:
        return run_smoke_check()
    return run_window(args.window)
```

## GUI 起動完了判定

ToolHub は GUI アプリを detached process として起動し、起動直後に fatal error がないか短時間確認する。

この確認時間内に entry process が終了すると、ユーザーには「アプリは起動直後に終了しました」と表示される。GUI アプリでは、メイン画面を持つ process が生存したままになるようにする。

避ける:

```python
def main() -> int:
    subprocess.Popen([sys.executable, "real_gui.py"])
    return 0
```

この形は、実際の GUI が起動していても、ToolHub から見ると entry process が即終了したように見える。

推奨:

```python
def main() -> int:
    return run_gui_main_window()
```

補助画面を別 process で開く場合も、メイン画面の process は自分のイベントループを維持する。短時間で完了するバッチ処理は GUI mode ではなく CLI / blocking 実行として扱う。

## Frozen exe 対応の子プロセス起動

PyInstaller などで frozen-folder 化すると、`sys.executable` は Python ではなくアプリ exe を指す。

そのため、次の形は禁止する。

```python
subprocess.Popen([sys.executable, "-m", "my_app.ui.settings_window"])
```

単体実行時は `python.exe -m ...` になり正しく動くが、ToolHub frozen 実行時は `my_app.exe -m ...` になる。アプリ exe が `-m` を解釈しない場合、メイン画面がもう一度起動するなどの不具合になる。

推奨は、常に自分の entry point に明示引数を渡す方式にする。

```python
import subprocess
import sys
from pathlib import Path


def entry_command(*args: str) -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, *args]
    return [sys.executable, str(Path(__file__).resolve().parents[1] / "main.py"), *args]


def open_settings_window() -> None:
    subprocess.Popen(entry_command("--window", "settings"), close_fds=True)
```

この方式なら、通常 Python 実行でも frozen exe 実行でも同じ `main.py` の dispatcher を通る。

## AgendaSnap 対応ルール

AgendaSnap のようにメイン画面、字幕画面、設定画面、議事録画面を別 Flet window として起動するアプリは、次の形へ修正する。

### 修正前の問題

```python
subprocess.Popen([
    sys.executable,
    "-m",
    "agendasnap.ui.caption_window",
    "--config",
    str(DEFAULT_CONFIG_PATH),
])
```

ToolHub frozen 実行時は `sys.executable` が `<app_id>.exe` のようなアプリ exe になるため、`app.exe -m agendasnap.ui.caption_window` が実行される。`main.py` が `-m` を無視すると、サブ画面ではなく新しいメイン画面が起動する。

### 修正後の形

`main.py` に window dispatcher を置く。

```python
def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.toolhub_smoke:
        return run_smoke(args.config)
    if args.window == "caption":
        return run_flet_module("agendasnap.ui.caption_window", args.forwarded_args)
    if args.window == "settings":
        return run_flet_module("agendasnap.ui.settings_window", args.forwarded_args)
    if args.window == "minutes":
        return run_flet_module("agendasnap.ui.minutes_window", args.forwarded_args)
    return run_flet_module("agendasnap.ui.mock_ui", args.forwarded_args)
```

メイン画面からサブ画面を開くときは、必ず自分の entry point に戻す。

```python
def open_caption_window(session_dir: Path | None) -> None:
    args = ["--window", "caption", "--config", str(DEFAULT_CONFIG_PATH)]
    if session_dir is not None:
        args.extend(["--session-dir", str(session_dir)])
    subprocess.Popen(entry_command(*args), close_fds=True)
```

### AgendaSnap の完了条件

- `python main.py` でメイン画面が起動する。
- `python main.py --window caption` で字幕画面だけが起動する。
- `python main.py --window settings` で設定画面だけが起動する。
- `python main.py --window minutes --session-dir <path>` で議事録画面だけが起動する。
- frozen exe で同じ引数を渡しても、メイン画面が余計に増えない。
- ToolHub 登録後、字幕、設定、議事録ボタンが単体起動時と同じ画面を開く。

## 設定ファイルとユーザーデータ

設定ファイルは source tree 内の default と、ユーザーごとの writable config を分ける。

推奨:

```text
my_app/
  my_app/config/default.yaml
```

実行時:

- default config は read-only として扱う。
- ユーザー設定、ログ、録音、生成物は `%LOCALAPPDATA%` などの user data 配下へ保存する。
- frozen exe の配置ディレクトリに実行ログやセッションデータを書き続けない。

理由:

- ToolHub の `apps/<app_id>` は登録済み配布物であり、設定や実施ログを混ぜると再登録、差分確認、削除が難しくなる。
- 録音や議事録はユーザーデータであり、アプリ配布物ではない。

## ToolHub 実行時の環境とパス解決

ToolHub runner はアプリ起動時に次の環境変数を設定する。

```text
TOOLHUB_ROOT=<ToolHub root>
TOOLHUB_APP_ID=<app_id>
TOOLHUB_APP_DIR=<ToolHub root>/apps/<app_id>
PYTHONIOENCODING=utf-8
PYTHONDONTWRITEBYTECODE=1
```

shared-env 登録では、さらに次が設定される。

```text
TOOLHUB_SHARED_ENV_ID=<env_id>
VIRTUAL_ENV=<ToolHub root>/runtime/envs/<env_id>
PYTHONNOUSERSITE=1
```

アプリの asset、default config、同梱テンプレートは、`Path.cwd()` 固定ではなく `__file__` または `TOOLHUB_APP_DIR` 基準で解決する。

推奨:

```python
import os
from pathlib import Path


def app_root() -> Path:
    if "TOOLHUB_APP_DIR" in os.environ:
        return Path(os.environ["TOOLHUB_APP_DIR"])
    return Path(__file__).resolve().parents[1]
```

ユーザーデータは `TOOLHUB_APP_DIR` には書かない。`%LOCALAPPDATA%` やアプリ側で決めた user data root に保存する。

## Requirements

root 直下に pip が読める `requirements.txt` を置く。`pyproject.toml` の `[project].dependencies` も入力として使えるが、最終的な登録物では `requirements.txt` と `requirements.lock` に正規化される前提で整理する。

App Studio は dependency file を次の順で扱う。

1. root 直下の `pyproject.toml` に `[project].dependencies` があれば使う。
2. root 直下の `requirements.txt` があれば使う。
3. root 直下の `requirements.lock` があれば参考にする。
4. どれもない場合は import 解析候補を出すだけで、自動で nested requirements を採用しない。

推奨:

```text
flet==0.28.3
flet-desktop==0.28.3
PyYAML==6.0.2
numpy==2.2.6
pyaudiowpatch==0.2.12.7
websockets==15.0.1
soundfile==0.13.1
```

避ける:

```text
numpy>=1.26  # 日本語コメント
```

注意:

- Windows の pip 実行環境では、コメントや文字コードで失敗することがある。
- requirements には実行時 dependency だけを書く。
- `pytest`、`ruff`、`black`、`mypy`、`pyinstaller` などの開発用 dependency は通常入れない。
- optional dependency は top-level import しない。
- shared-env では `requirements.lock` の内容が共有ランタイム選択に使われるため、不要な依存や開発用依存を混ぜない。

## .toolhubignore

source root 直下に `.toolhubignore` を置く。

### 実行コードを除外しない

`.toolhubignore` は、ログ、録音、認証情報、キャッシュ、build 生成物を除外するためのもの。
Python package として import されるディレクトリ名を広く除外しないこと。

悪い例:

```gitignore
audio/
```

`agendasnap.audio` のような実行コードがあるアプリでは、上記により `agendasnap/audio/` まで除外され、
登録後に `ModuleNotFoundError: No module named 'agendasnap.audio'` で失敗する。

録音データを除外したい場合は、コード package ではなく、実データの保存先だけを指定する。

```gitignore
sessions/
recordings/
logs/
tmp/
runtime_data/audio/
user_data/recordings/
```

推奨内容:

```gitignore
__pycache__/
*.pyc
*.pyo

.venv/
venv/
env/

build/
dist/
*.spec
ToolHub_AppStudio_Output/

logs/
log/
tmp/
temp/
sessions/
recordings/
screenshots/

.env
.env.*
.auth/
auth_state.json
storage_state.json
storage_state*.json
cookies.json
token.json
tokens.json
credentials.json
client_secret.json

.git/
.gitup/
.pytest_cache/
.mypy_cache/
.ruff_cache/
node_modules/
```

AgendaSnap では録音、議事録、session output を登録対象に含めない。必要な default config、UI module、asset だけを source として残す。

## Smoke Check

外部通信、録音、ブラウザ起動、GUI 表示を伴わない smoke check を用意する。

推奨:

```powershell
python main.py --toolhub-smoke
```

確認内容:

- package import が成功する。
- default config が読める。
- requirements に書いた主要 package が import できる。
- API key がなくても、存在確認だけで終了できる。
- 録音、STT 接続、LLM 呼び出し、ブラウザ操作は行わない。

## Codex へ依頼するときのプロンプト例

```text
docs/31_app_registration_app_authoring_guidelines.md に従って、この Python アプリを ToolHub 登録対応に修正してください。

要件:
- main.py を唯一の entry point にしてください。
- GUI のメイン画面とサブ画面は --window などの明示引数で dispatch してください。
- subprocess で sys.executable -m <module> を使っている箇所は、frozen exe でも動く entry point 再呼び出し方式に置き換えてください。
- --toolhub-smoke を追加し、外部通信、録音、ブラウザ起動、GUI 表示なしで依存関係と設定読み込みを検証できるようにしてください。
- requirements.txt または pyproject.toml を root 直下に整理し、実行時 dependency だけを記載してください。
- .toolhubignore を追加または更新し、venv、build、dist、ToolHub_AppStudio_Output、ログ、録音、認証情報、キャッシュを除外してください。
- shared-env 登録で使われることを前提に、不要な依存や開発用 dependency が requirements.lock に入らないようにしてください。
- GUI entry process が起動確認中に即終了しないようにしてください。
- 単体実行と ToolHub frozen 実行で同じ画面が開く構造にしてください。

完了後、python main.py --toolhub-smoke と、可能なら各 --window 引数の起動確認結果を報告してください。
```

## 最終確認チェックリスト

- [ ] `main.py` が唯一の外部 entry point である。
- [ ] `python main.py --toolhub-smoke` が副作用なしで成功する。
- [ ] GUI アプリの entry process が起動直後に終了しない。
- [ ] `sys.executable -m <module>` で自アプリのサブ画面を開いていない。
- [ ] frozen exe の場合は `app.exe --window <name>` でサブ画面が開く。
- [ ] `requirements.txt` が root 直下にあり、pip で読める。
- [ ] `pyproject.toml` を使う場合も、実行時 dependency が `[project].dependencies` に整理されている。
- [ ] `requirements.lock` に不要な開発用 dependency が混ざっていない。
- [ ] `.toolhubignore` があり、不要ファイルと機密ファイルを除外している。
- [ ] asset と default config は `__file__` または `TOOLHUB_APP_DIR` 基準で解決している。
- [ ] ログ、録音、議事録、ユーザー設定は配布物ではなく user data に保存される。
- [ ] ToolHub 登録後にメイン画面、字幕、設定、議事録が単体実行時と同じ挙動になる。
