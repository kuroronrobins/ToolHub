# App Studio GUI AI提案の補足

App Studio GUI のAI提案は管理者セッションが有効な場合だけ利用できます。GUIはCLI版 App Studio の Suggest を呼び出し、生成された `proposed_app.yaml` と `icon_work/` を読み込んで表示します。APIキー未設定、AI無効、OpenAI packageなし、API失敗時もfallbackで動作します。

AI提案は自動確定しません。管理者が提案内容を確認し、採用ボタンを押した項目だけGUI入力へ反映します。アイコンもPNG候補を主表示にし、採用したPNGだけを `icon.png` に反映します。high secret が検出された場合はAI送信しません。APIキー、プロンプト内のsecret値、画像b64全文はログへ出しません。

App Studio AI提案パネルでは、CLIへ渡す準備状況として AI enabled、API key source、Text model、Image model、CLI env ready を表示します。metadata/image の生成結果は `success`、`fallback`、`skipped`、`failed` と理由を分けて表示します。

Metadata editor で採用・編集した登録項目は、管理者認証済みの Tauri command が `%LOCALAPPDATA%\ToolHub\data\app_studio\metadata_overrides\` に一時JSONとして保存し、CLIへ `--metadata-override` で渡します。ログに残すのは `metadata_override_keys` だけで、値本文は記録しません。空欄は既存の CLI 生成値を上書きせず、APIキー未設定時も fallback metadata と GUI編集値の merge で動作します。

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

Image model の既定候補は `gpt-image-2` です。これは設定値として保存・変更でき、App Studio 実行時は管理者画面の設定から `TOOLHUB_APP_STUDIO_IMAGE_MODEL` として CLI に渡します。APIキー未設定またはAI無効の場合は画像生成APIを呼ばず、fallback PNG と互換用SVGで動作します。

Image model の表示候補は、推奨 `gpt-image-2`、互換候補 `gpt-image-1.5` / `gpt-image-1` / `gpt-image-1-mini` です。画像生成では `response_format` を渡さず、必要に応じて `output_format` / `quality` を外してリトライします。画像生成テストは実API呼び出しで、結果に model、api、content_type、fallback_reason、error_category を表示します。

`gpt-image-2` の画像生成テストで `Your organization must be verified` または `Verify Organization` を含むエラーが出た場合は、OpenAI組織の認証が必要です。ToolHub はこの状態を `organization_verification_required` と分類し、`gpt-image-2 は現在のOpenAI組織では利用できません。OpenAI Platformで組織認証を完了するか、別のImage modelを設定してください。認証後、反映まで最大15分程度かかる場合があります。` と表示します。APIキー本文は表示・保存しません。

AI/APIキー管理には、`gpt-image-2`、`gpt-image-1.5`、`gpt-image-1`、`gpt-image-1-mini` を順番に実APIテストする「候補モデルを順にテスト（実API呼び出し）」があります。各モデルについて未実行/成功/失敗、`error_category`、`fallback_reason` 概要を確認し、成功したモデルは「このモデルを使用」で Image model 入力欄へ反映できます。手入力モデルも引き続き利用できます。候補モデル確認は実API呼び出しのため、OpenAI API利用料金が発生する場合があります。

画像生成テストの直近結果が `ok:false` の間、App Studio はAI画像候補と再生成が利用できない状態として警告します。メタデータ生成・手動入力は継続できますが、AI画像候補は増えません。未採用時は ToolHub共通default icon を現在の `icon.png` として使い、API失敗時はアイコンPromptやスタイル補足の効果を画像候補として評価できません。

AIアイコン生成の失敗理由は、App Studio 登録フローでも `failure_class` として表示します。分類は `ai_disabled`、`missing_api_key`、`missing_image_model`、`organization_not_verified`、`unsupported_model`、`quota_or_rate_limit`、`authentication_failed`、`secret_scan_blocked`、`network_error`、`api_error`、`unknown` です。`gpt-image-2` が実APIレスポンスで `Your organization must be verified` を返した場合は `organization_not_verified` と表示し、OpenAI Platform の Organization verification または利用可能な Image model への明示的な切り替えを案内します。

App Studio の候補表示では、API画像候補だけを「AI生成候補」として扱います。API未実行・API失敗・secret scan block時は代替のローカル候補を作らず、失敗理由と次アクションを表示し、未採用時の現在アイコンとして ToolHub共通default icon を使います。default icon はAI生成候補ではありません。新規登録GUIではスタイルプリセットを選ばせず、ユーザーがアイコンPromptまたはスタイル補足へ文章で指定した内容を優先します。

アイコン再生成は、初回 Suggest 全体ではなく `icon-regenerate` サブコマンドを呼びます。既存の `icon_work/candidate_manifest.json` と候補PNGを読み、画像生成/編集APIだけを実行するため、file inventory、secret scan、dependency analysis、metadata生成は再実行しません。GUIでは候補数を 1/2/3 から選べ、既定は速度優先の1候補です。`draft` / `standard` / `high` の画像品質モードも選択できます。実際に画像APIへ渡した最終Promptと、画像API呼び出し秒数は候補一覧・Prompt表示・manifestで確認できます。

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
## 2026-05-08 update: image API failure and default icon

App Studio now shows API image candidates only when the image API actually returns a saved PNG or URL candidate. If image generation fails or is skipped, the UI shows the failure class, reason, and next action, then uses the ToolHub common default icon as the current `icon.png` until an uploaded icon or AI candidate is adopted. The default icon is not an AI candidate and is not shown in the candidate grid.
