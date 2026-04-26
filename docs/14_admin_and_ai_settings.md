# 管理者画面とAI設定

## 目的

管理者画面は、通常利用者向けのアプリランチャーとは分離した運用者向け領域です。App Studio、AI/APIキー管理、更新管理、ログ/診断は管理者ログイン後にのみ開けます。

通常ランチャー画面には App Studio の機能を直接置きません。通常利用者は従来通りアプリ一覧、検索、カテゴリ、起動を使えます。

## 初回管理者パスワード設定

初回は右上の管理者画面ボタンから、管理者パスワード設定画面を開きます。

保存先:

```text
%LOCALAPPDATA%\ToolHub\config\admin_auth.json
```

保存内容は PBKDF2-HMAC-SHA256 のハッシュ、salt、iterations、作成/更新日時です。パスワード平文や単純SHA256は保存しません。

パスワード要件:

- 8文字以上
- 空白のみは禁止
- 確認入力と一致すること

## 管理者ログインとセッション

ログイン成功後、管理者セッションはメモリ上だけで保持します。

- 有効時間は30分
- ToolHub終了で失効
- ログアウトで失効
- ログイン済み状態をファイル保存しない

セッション期限切れ後に管理者コマンドを実行すると、再ログインを求めます。

## パスワードを忘れた場合

次のファイルを削除すると、初回管理者パスワード設定に戻ります。

```text
%LOCALAPPDATA%\ToolHub\config\admin_auth.json
```

この操作は管理者の責任で行ってください。削除しても App Pack や登録済みアプリは削除されません。

## AI/APIキー管理

管理者画面の AI/APIキー管理では次を設定できます。

- AI機能 ON/OFF
- Text model
- Image model
- OpenAI APIキー登録/更新
- OpenAI APIキー削除
- キー存在確認ベースの接続テスト

設定ファイル:

```text
%LOCALAPPDATA%\ToolHub\config\app_studio_ai.json
```

設定JSONには APIキー本体を書きません。保存するのは `ai_enabled`、`text_model`、`image_model`、`api_key_source`、`updated_at` です。

## APIキー保存場所

Windows では Windows Credential Manager を使います。

```text
Target:  ToolHub/OpenAI
Account: OPENAI_API_KEY
```

APIキーの読み取り優先順位:

1. Windows Credential Manager
2. 環境変数 `OPENAI_API_KEY`
3. 未設定なら fallback

非Windows環境では Credential Manager 保存は未対応として返します。ただし通常ランチャーやアプリ起動はその影響を受けません。

画面とログには APIキー全文を出しません。状態表示は `sk-...abcd` のようなマスク形式です。

## 管理者操作ログ

保存先:

```text
%LOCALAPPDATA%\ToolHub\data\logs\admin\admin.log
```

記録する操作:

- `admin_password_created`
- `admin_login_success`
- `admin_login_failed`
- `admin_logout`
- `ai_settings_saved`
- `api_key_saved`
- `api_key_deleted`

記録しない情報:

- 管理者パスワード
- APIキー全文
- APIキー入力値
- その他 secret 値

## App Studio GUIの位置づけ

App Studio GUI は管理者セッションが有効な場合だけ利用できます。React 側の表示制御だけでなく、Rust/Tauri command 側でも `session.require_authenticated()` を必ず通します。

新規登録GUIは CLI 版 `tools/app_studio/main.py` を直接呼び出します。処理内容、成果物、`enabled=false` 仮登録、App Pack生成、Approve の流れはCLI版と同じです。

Python実行優先順位:

1. `runtime/python/python.exe`
2. 管理者の開発環境の `python`
3. 管理者の開発環境の `py`

Python が見つからない場合、App Studio GUI は分かりやすいエラーを表示します。通常ランチャー画面と通常アプリ起動は影響を受けません。

App Studio GUI には実行前 Preflight があり、Entry存在、AppId形式、BuildMode、runtime Python、開発環境 Python fallback の状態を確認できます。`runtime/python/python.exe` が未配置でも開発中は fallback を使えますが、正式配布前は runtime 配置後に再確認してください。

Entry は Windows では参照ボタンから選択できます。非対応環境やダイアログ失敗時は手入力で続行します。

承認時は `AllowWarnings` と `StrictApproval` を選べます。`AllowWarnings` は `fail` がなければ承認可能、`StrictApproval` は `pass` のみ承認可能です。

GUI実行ログ:

```text
%LOCALAPPDATA%\ToolHub\data\logs\admin\app_studio_gui.log
```

記録する内容は Suggest / Apply / Approve の開始と終了、exit code、app_id、build_mode、output_dir です。APIキー、管理者パスワード、secret値は記録しません。

既存アプリ更新、削除/アンインストール、公開準備はシェル表示に留めています。

削除、publish、APIキー更新などの危険操作は、将来再認証を必須にする前提です。
