# PDF Workbench 起動ウィンドウ残存 調査まとめ

作成日: 2026-05-25

## 結論

ToolHub から PDF Workbench を起動したときに「メインウィンドウは表示されるが、起動ウィンドウが残る」原因は、ToolHub runner ではなく PDF Workbench 側の splash window 終了処理にある。

PDF Workbench は起動完了時に main window を表示した後、`splashscreen` window に対して `close()` を呼ぶ実装になっている。しかし Tauri の `close()` は強制破棄ではなく「閉じる要求」を出す API であり、失敗または未破棄になっても現在の実装では戻り値を捨てている。そのため、main window は表示されたのに splash window が残る状態を検知できない。

実行時確認でも、PDF Workbench の同一プロセス内に以下 2 つの Tauri Window が同時に残るケースを確認した。

- main window: `1380x805`, visible
- splash window: `574x398`, visible

## 現象

ユーザー観察:

- ToolHub で `pdf_workbench` を起動する。
- PDF Workbench のメインウィンドウは表示される。
- ただし起動ウィンドウが消えずに残る。

初期仮説として ToolHub 側の `LaunchProgressDialog` も確認した。ToolHub の起動状態ダイアログは成功後も手動で閉じる設計になっているため、別の紛らわしい UI 要因ではある。ただし今回の実行時検証では、残っていたウィンドウは ToolHub の React ダイアログではなく、`pdf-workbench.exe` プロセス内の Tauri splash window だった。

## 調査範囲

確認した主な範囲:

- ToolHub のアプリ定義: `apps/pdf_workbench/app.yaml`
- ToolHub 側の runner wrapper: `apps/pdf_workbench/src/pdf_workbench_toolhub/launcher.py`
- ToolHub 側の起動 UI: `launcher/src/App.tsx`, `launcher/src/components/LaunchProgressDialog.tsx`
- PDF Workbench 側の Tauri 設定: `C:\Users\kuroron\Documents\RD\20260215_PDFApplication\src-tauri\tauri.conf.json`
- PDF Workbench 側の起動完了処理: `C:\Users\kuroron\Documents\RD\20260215_PDFApplication\src-tauri\src\lib.rs`
- PDF Workbench 側の frontend 呼び出し: `C:\Users\kuroron\Documents\RD\20260215_PDFApplication\src\App.tsx`
- Tauri 2.11.1 の `close()` / `destroy()` 実装

## 実行時の裏取り

### 1. ToolHub runner 経由

ToolHub runner 経由で `pdf_workbench` を起動し、Win32 API で PDF Workbench プロセスのトップレベルウィンドウを列挙した。

観察結果:

- 起動直後は main window が hidden。
- その後 `574x398` の splash window が visible。
- main window が visible になった後も、同じ PID 内に splash window が残るケースを確認。
- runner の起動結果自体は `ok: true`。

つまり runner は「プロセスが起動した」と判断して正常終了するが、PDF Workbench 内部の splash window の破棄までは検証していない。

### 2. `pdf-workbench.exe` 直接起動

ToolHub を経由せず、同梱 payload の `apps/pdf_workbench/src/assets/payload/pdf-workbench.exe` を直接起動しても同じ現象を確認した。

代表観察:

```text
direct t+12.5s
visible=True class=Tauri Window title=PDF Workbench rect=574x398+817+422
visible=True class=Tauri Window title=PDF Workbench rect=1380x805+25+25
```

このため、原因は ToolHub launcher / runner 固有ではなく、PDF Workbench executable 側に切り分けられる。

### 3. 再現性

同じ payload EXE を複数回直接起動し、11 秒後のウィンドウ状態を確認した。

結果:

- 4 回中 2 回で splash window が残存。
- 4 回中 2 回では splash window は消えた。

この結果から、現象は常時再現ではなくタイミング依存または Tauri close 処理の不安定挙動として発生している。

### 4. payload と PDFApplication release EXE の同一性

ToolHub に同梱されている payload と、PDFApplication 側の release EXE は同一ハッシュだった。

```text
SHA256: 396AD036055EB1D94A469741ED5ABEAED0CD4B5B20E5D16BE23E11D1BEE834D9
```

確認対象:

- `C:\Users\kuroron\Documents\RD\20260426_Toolhub\apps\pdf_workbench\src\assets\payload\pdf-workbench.exe`
- `C:\Users\kuroron\Documents\RD\20260215_PDFApplication\src-tauri\target\release\pdf-workbench.exe`

したがって、ToolHub へのコピーや登録時に別の EXE へ差し替わった問題ではない。

## コード上の原因

PDF Workbench の Tauri 設定では、main と splashscreen の 2 ウィンドウが定義されている。

- `main`: `visible: false`
- `splashscreen`: `visible: true`, `alwaysOnTop: true`, `skipTaskbar: true`

起動完了処理は `complete_startup`。

該当コード:

```rust
let main_window = app
    .get_webview_window("main")
    .ok_or_else(|| "main window was not found".to_string())?;

main_window.show().map_err(|error| error.to_string())?;
let _ = main_window.set_focus();

if let Some(splash_window) = app.get_webview_window("splashscreen") {
    let _ = splash_window.close();
}
```

問題点:

- main window の `show()` は失敗時にエラーを返す。
- splash window の `close()` は戻り値を `let _ = ...` で捨てている。
- `close()` 後に splash window が本当に消えたか確認していない。
- `close()` が効かなかった場合の `hide()` / `destroy()` fallback がない。
- ログにも残らないため、runner / ToolHub 側からは「起動成功」に見える。

Tauri 2.11.1 の実装確認では、`WebviewWindow.close()` は内部的に `Window.close()` へ委譲される。Tauri のコメント上も `close()` は `WindowEvent::CloseRequested` を発火する close request であり、別に `destroy()` が強制破棄 API として用意されている。

該当 API:

- `WebviewWindow::close()`: close request
- `WebviewWindow::destroy()`: event を発火せず強制的に window を閉じる

今回の splash はユーザーが編集内容を持つ通常 window ではなく起動表示用の一時 window なので、起動完了時は `destroy()` の方が目的に合っている。

## ToolHub 側でない理由

ToolHub 側にも成功後に残る起動状態ダイアログは存在する。

該当コード:

- `launcher/src/App.tsx`
  - `setLaunchStatus(result.ok ? "success" : "error")`
  - 成功後に `launchStatus` を自動で `idle` に戻していない。
- `launcher/src/components/LaunchProgressDialog.tsx`
  - `!app || status === "idle"` のときだけ非表示。
  - `success` 状態では閉じるボタンが出るだけで、自動クローズしない。

ただし今回の本件とは別問題として扱うべき。

理由:

- `pdf-workbench.exe` を ToolHub 経由ではなく直接起動しても splash 残存が再現した。
- 残存 window は ToolHub UI ではなく、`pdf-workbench.exe` の同一 PID 内の `Tauri Window` だった。
- ToolHub runner は PDF Workbench の子プロセスを起動し、一定時間生存していれば `ok: true` と判断するだけで、PDF Workbench 内部の splash lifecycle には関与しない。

したがって、PDF Workbench 専用の修正スレッドでは ToolHub 側へ個別アプリ専用分岐を入れず、PDF Workbench 側の splash 終了処理を修正するのが正しい。

## 推奨修正方針

PDF Workbench 側で以下を実施する。

1. `splash_window.close()` を `splash_window.destroy()` に変更する。
2. 可能なら `hide()` を先に呼んで見た目上即座に消し、その後 `destroy()` する。
3. `close()` / `hide()` / `destroy()` の失敗を握りつぶさず、少なくとも debug log または stderr に残す。
4. 起動完了後に `splashscreen` window が残っていないことを E2E / smoke で検証する。
5. 修正後に release EXE を再ビルドし、ToolHub payload へ再 stage する。

修正例の方向性:

```rust
if let Some(splash_window) = app.get_webview_window("splashscreen") {
    let _ = splash_window.hide();
    splash_window.destroy().map_err(|error| error.to_string())?;
}
```

より保守的にするなら、`destroy()` のエラーだけをログに残し、main window 表示自体は失敗扱いにしない選択もある。ただし現在のように完全に握りつぶすと再発調査が難しくなる。

## 修正後の検証観点

最低限確認すべきこと:

- `pdf-workbench.exe` を直接起動し、10 秒後に visible な Tauri Window が main 1 つだけであること。
- ToolHub runner 経由で `pdf_workbench` を起動し、10 秒後に PDF Workbench の splash window が残っていないこと。
- main window は引き続き表示されること。
- `--toolhub-smoke` が従来通り成功すること。
- ToolHub 側の app.yaml / runner I/F に変更がないこと。

可能なら複数回起動する。今回の不具合は 4 回中 2 回のようにタイミング依存で出たため、1 回だけの確認では不十分。

推奨回数:

- 直接起動: 5 回
- ToolHub runner 経由: 5 回

合格条件:

- 各回 10 秒後に `574x398` 前後の splash window が visible で残らない。
- visible な `Tauri Window title=PDF Workbench` は main window のみ。

## 引き継ぎメモ

今回の原因は「起動完了処理が呼ばれていない」ではない。main window が表示されているため、少なくとも `complete_startup` の `main_window.show()` までは到達している。

実装上の問題は、splash window の終了が best-effort の `close()` だけで、結果確認も fallback もないこと。専用修正スレッドでは PDF Workbench repo 側で `complete_startup` を中心に修正し、ToolHub 側には個別 workaround を入れない。
