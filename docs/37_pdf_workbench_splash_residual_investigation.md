# PDF Workbench 起動ウィンドウ残存 調査レポート

作成日: 2026-05-25

## Summary

ToolHub から `pdf_workbench` を起動したときに、PDF Workbench のメインウィンドウは表示されるが起動ウィンドウが消えずに残る原因は、ToolHub 側ではなく PDF Workbench 側の splash window 終了処理にある。

PDF Workbench は起動完了時に main window を表示した後、`splashscreen` window に対して `close()` を呼んでいる。しかし Tauri の `close()` は強制破棄ではなく「閉じる要求」を出す API であり、今回の実装では戻り値を `let _ = ...` で捨てている。そのため、閉じられなかった場合もエラーやログにならず、main window だけ表示されて splash window が残る。

## 現象

ユーザー観察:

- ToolHub で `pdf_workbench` を起動する。
- PDF Workbench のメインウィンドウは表示される。
- 起動ウィンドウが消えずに残り続ける。

調査中に ToolHub 側の起動状態ダイアログも確認したが、今回残っているウィンドウは ToolHub の React ダイアログではなく、`pdf-workbench.exe` プロセス内の Tauri splash window と切り分けた。

## 調査範囲

確認した主なファイル:

- `apps/pdf_workbench/app.yaml`
- `apps/pdf_workbench/src/main.py`
- `apps/pdf_workbench/src/pdf_workbench_toolhub/launcher.py`
- `launcher/src/App.tsx`
- `launcher/src/components/LaunchProgressDialog.tsx`
- `C:\Users\kuroron\Documents\RD\20260215_PDFApplication\src-tauri\tauri.conf.json`
- `C:\Users\kuroron\Documents\RD\20260215_PDFApplication\src-tauri\src\lib.rs`
- `C:\Users\kuroron\Documents\RD\20260215_PDFApplication\src\App.tsx`
- `C:\Users\kuroron\Documents\RD\20260215_PDFApplication\src\features\workbench\backend.ts`
- Tauri 2.11.1 の `WebviewWindow::close()` / `WebviewWindow::destroy()` 実装

## 実行時の裏取り

### ToolHub runner 経由

ToolHub runner 経由で `pdf_workbench` を起動し、Win32 API で PDF Workbench プロセスのトップレベルウィンドウを列挙した。

確認結果:

- 起動直後は main window が hidden。
- その後 `574x398` の splash window が visible。
- main window が visible になった後も、同じ PID 内に `574x398` の splash window が visible のまま残るケースを確認。
- runner の結果自体は `ok: true`。

代表的な観察:

```text
visible=True class=Tauri Window title=PDF Workbench rect=1380x805+...
visible=True class=Tauri Window title=PDF Workbench rect=574x398+817+422
```

runner は「起動プロセスが生存している」ことを確認して成功を返すだけで、PDF Workbench 内部の splash window が破棄されたかまでは見ていない。

### `pdf-workbench.exe` 直接起動

ToolHub を経由せず、同梱 payload の `apps/pdf_workbench/src/assets/payload/pdf-workbench.exe` を直接起動しても同じ現象を確認した。

代表的な観察:

```text
direct t+12.5s
visible=True class=Tauri Window title=PDF Workbench rect=574x398+817+422
visible=True class=Tauri Window title=PDF Workbench rect=1380x805+25+25
```

このため、原因は ToolHub launcher / runner 固有ではなく、PDF Workbench executable 側にある。

### 再現性

同じ payload EXE を複数回直接起動し、11 秒後のウィンドウ状態を確認した。

結果:

- 4 回中 2 回で splash window が残存。
- 4 回中 2 回では splash window は消えた。

現象は常時再現ではなく、タイミング依存または Tauri の close request 処理の不安定挙動として発生している。

### payload と release EXE の同一性

ToolHub に同梱されている payload と、PDFApplication 側の release EXE は同一 SHA256 だった。

```text
SHA256: 396AD036055EB1D94A469741ED5ABEAED0CD4B5B20E5D16BE23E11D1BEE834D9
```

確認対象:

- `C:\Users\kuroron\Documents\RD\20260426_Toolhub\apps\pdf_workbench\src\assets\payload\pdf-workbench.exe`
- `C:\Users\kuroron\Documents\RD\20260215_PDFApplication\src-tauri\target\release\pdf-workbench.exe`

したがって、ToolHub 側へのコピーや登録時に別の EXE へ差し替わった問題ではない。

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
- `close()` 後に splash window が実際に消えたか確認していない。
- `close()` が効かなかった場合の `hide()` / `destroy()` fallback がない。
- ログにも残らないため、ToolHub 側からは正常起動に見える。

Tauri 2.11.1 の実装確認では、`WebviewWindow::close()` は `WindowEvent::CloseRequested` を発火する close request であり、強制破棄用には別に `WebviewWindow::destroy()` が用意されている。

今回の splash window は起動中だけ表示する一時 window なので、起動完了時は `close()` より `destroy()` の方が目的に合う。

## ToolHub 側でない理由

ToolHub 側にも成功後に残る起動状態ダイアログはある。

確認した挙動:

- `launcher/src/App.tsx` は `setLaunchStatus(result.ok ? "success" : "error")` で成功状態にする。
- 成功後に自動で `launchStatus` を `idle` に戻していない。
- `LaunchProgressDialog` は `status === "idle"` になるまで表示される。

ただし、これは今回の PDF Workbench splash 残存とは別問題。

理由:

- ToolHub を経由せず `pdf-workbench.exe` を直接起動しても splash 残存が再現した。
- 残っていた window は `pdf-workbench.exe` の同一 PID 内にある `Tauri Window` だった。
- ToolHub runner は PDF Workbench の内部 window lifecycle に関与していない。

したがって、ToolHub launcher / runner に `pdf_workbench` 専用の workaround を入れるべきではない。修正対象は PDF Workbench 側。

## 推奨修正方針

PDF Workbench 側で以下を実施する。

1. `splash_window.close()` を `splash_window.destroy()` に変更する。
2. 見た目上の残存をさらに避けるなら、先に `hide()` を呼んでから `destroy()` する。
3. `destroy()` の失敗を完全に握りつぶさず、少なくともログまたは stderr に残す。
4. 修正後に release EXE を再ビルドする。
5. ToolHub の payload に再 stage する。

修正例の方向性:

```rust
if let Some(splash_window) = app.get_webview_window("splashscreen") {
    let _ = splash_window.hide();
    splash_window.destroy().map_err(|error| error.to_string())?;
}
```

より保守的にするなら、main window 表示の成功は維持しつつ、`destroy()` 失敗だけをログに残す実装でもよい。ただし現在のように完全に戻り値を握りつぶす状態は避ける。

## 修正後の検証観点

最低限確認すべきこと:

- `pdf-workbench.exe` を直接起動し、10 秒後に visible な Tauri Window が main 1 つだけであること。
- ToolHub runner 経由で `pdf_workbench` を起動し、10 秒後に PDF Workbench の splash window が残っていないこと。
- main window は引き続き表示されること。
- `--toolhub-smoke` が従来通り成功すること。
- ToolHub 側の `app.yaml` / runner I/F に変更がないこと。

今回の不具合はタイミング依存で出たため、1 回だけの確認では不十分。

推奨回数:

- 直接起動: 5 回
- ToolHub runner 経由: 5 回

合格条件:

- 各回 10 秒後に `574x398` 前後の splash window が visible で残らない。
- visible な `Tauri Window title=PDF Workbench` は main window のみ。

## 引き継ぎメモ

今回の原因は「起動完了処理が呼ばれていない」ではない。main window が表示されているため、少なくとも `complete_startup` の `main_window.show()` までは到達している。

問題は、splash window の終了が best-effort の `close()` だけで、結果確認も fallback もないこと。専用修正スレッドでは PDF Workbench repo 側で `complete_startup` を中心に修正し、ToolHub 側には個別 workaround を入れない。
