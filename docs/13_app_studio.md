# GUI Build方式・AI提案・結果表示補足

通常新規登録 GUI は BuildMode を選ばせません。Python ソースから配布用 frozen-folder exe を作成して登録する固定フローです。

旧来の `auto` / `app-env` / `existing-exe` / Python 直接実行は、既存 manifest 互換や古いログを読むための概念として残っていますが、通常新規登録 GUI の選択肢ではありません。Entry が `.exe` の場合は、既存 exe 登録ではなく Python ソースを選び直す必要があります。

GUIでは、Suggest が生成した `proposed_app.yaml` と `icon_work/` をAI/fallback提案として読み込めます。表示対象は、表示名、short_description、detail.description、categories、search keywords、examples、use_cases、inputs、outputs、notes、icon prompt、更新時の release notes 草案、`icon_candidate_1.png`、`icon_final.png`、`icon_candidate_1.url.txt`、`icon_fallback.svg`、互換用の `icon_final.svg` です。AI提案は自動確定せず、採用ボタンで表示名やicon promptなど編集可能な入力欄へ反映します。APIキー未設定、AI無効、OpenAI packageなし、API失敗時も CLI 側の deterministic fallback で動きます。secret scan でAI送信対象にリスクがある場合はAI送信しません。

AI提案パネルはCLIへ渡すAI環境の診断も表示します。表示対象は AI enabled、API key source、Text model、Image model、CLI env ready です。APIキー本文は表示しません。`metadata_ai_report` と `icon_work/ai_generation_report.md` から、metadata/image それぞれの `status`、`model`、`parse_status`、`content_type`、`saved_candidate`、`fallback_reason` も確認できます。

AI/APIキー管理には「画像生成テスト（実API呼び出し）」があります。このボタンは実際に OpenAI 画像生成APIを呼び、APIキー、Image model、`size`、`quality`、`output_format`、`b64_json`/`url` 返却を確認します。結果には ok/failed、model、api、status、content_type、resolution、fallback_reason、error_category、error概要を表示します。APIキー本文は表示しません。

`gpt-image-2` で `Your organization must be verified` または `Verify Organization` を含む 403 系エラーが返る場合、そのOpenAI組織ではモデル利用に組織認証が必要です。App Studio では `error_category: organization_verification_required` として扱い、`gpt-image-2 は現在のOpenAI組織では利用できません。OpenAI Platformで組織認証を完了するか、別のImage modelを設定してください。認証後、反映まで最大15分程度かかる場合があります。` と案内します。組織認証は OpenAI Platform の Organization settings で行い、反映後に画像生成テストを再実行してください。

画像生成テストの直近結果が `ok:false` の間、App Studio GUI はAI画像候補と再生成が使えない状態として警告します。メタデータ編集や手動入力は継続できますが、fallback画像はAI画像ではなくローカル生成の暫定プレースホルダーです。API失敗中は `modern`、`vivid`、`colored_pencil`、`realistic` などの style preset の効果を評価できません。

AI/APIキー管理では候補モデル `gpt-image-2`、`gpt-image-1.5`、`gpt-image-1`、`gpt-image-1-mini` を順番に実APIテストできます。成功したモデルは「このモデルを使用」で Image model 入力欄へ反映し、保存すると以後の App Studio 実行で使われます。候補モデル確認は実API呼び出しのため、OpenAI API利用料金が発生する場合があります。

Icon候補の `source` が `api_generate` または `api_edit` のものだけを通常のAI生成候補として扱います。`fallback` / `fallback_after_api_failure` は API未実行または API失敗時の暫定プレースホルダーであり、AI生成成功とは扱いません。GUIでは API候補数、fallback候補数、使用モデル、スタイル、直近の画像API失敗理由を候補一覧上部に表示します。fallback PNG を使う場合は、候補カード上で明示的に採用する必要があります。

Icon生成には `iconStylePreset` を使います。選択肢は `modern`、`vivid`、`realistic`、`colored_pencil`、`watercolor`、`flat_vector`、`3d_soft`、`glassmorphism`、`clay`、`custom` です。`custom` では自由入力のスタイル指示を優先し、後段の固定 prompt が色鉛筆風・写実風・ビビッド等の指定を汎用の polished/glass/3D 表現で上書きしないようにします。

再生成時に修正元PNGが選ばれている場合、CLI はそのPNGを一時ファイルとして渡し、OpenAI SDK の画像編集API経路を試みます。画像編集APIが失敗した場合は `candidate_manifest.json` と GUI に失敗理由を残し、fallback候補は暫定プレースホルダーとして分離表示します。画像候補の自動採点は、MVPでは vision model 評価ではなく、prompt/concept 評価に PNG の小サイズ視認性・コントラスト・余白の簡易検査を加えた deterministic rule-based 評価です。Vision 評価を実行していない場合は `image_evaluation_status: fallback_rule_based` または `not_run` として明示します。

GUIでは CLI process の `exit_code` / `process_ok` と、`execution_test_result.json` の `overall_status` / `approval_allowed` を分けて表示します。通常新規登録の frozen-folder では runner dry execution や Playwright ログイン未確認により `overall_status: warn` になることがあります。警告は `approval_blocking_warning`、`non_blocking_warning`、`info` に分類され、`approval_allowed: true` かつ `approval_blocking_warnings_count: 0` の場合は、デフォルトの慎重モードでも承認できます。App Packが見つからない場合は App Pack 欄だけ `not found` と表示します。Apply後はGUIが `app_studio_read_result` を再実行し、生成済みJSONの内容を表示へ反映します。

## AI提案メタデータとmetadata_override

Metadata editor は、現在の編集値と AI/fallback 提案値を項目ごとに並べて表示します。`Adopt` はその項目だけを編集値へコピーし、`Revert` は採用直前の値へ戻します。`Adopt all proposals` は表示中の提案項目だけをまとめて採用します。AI提案は読み込み・生成だけでは確定しません。

GUIで編集できる metadata は `short_description`、`description`、`categories`、`keywords`、`examples`、`use_cases`、`inputs`、`outputs`、`notes` です。更新GUIでは `release_notes` と `change_summary` も同じ editor で扱います。配列項目はMVPとして改行またはカンマ区切りの textarea です。

編集値がある場合、GUI は `%LOCALAPPDATA%\ToolHub\data\app_studio\metadata_overrides\` に一時JSONを書き、CLIへ `--metadata-override <path>` を渡します。空欄や空配列は上書きしません。JSONには APIキーや secret を入れず、ログには値本文ではなく `metadata_override_keys` だけを記録します。不正JSONは CLI エラーとして扱い、型不一致や secret らしい値は警告として無視します。

metadata_override は CLI の metadata 生成後に merge され、`proposed_app.yaml`、`final_app/app.yaml`、Apply 後の `apps/<app_id>/app.yaml` に反映されます。反映先は `display.short_description`、`detail.description`、`display.categories`、`search.keywords`、`search.examples`、`detail.use_cases`、`detail.inputs`、`detail.outputs`、`detail.notes`、`release.release_notes`、`release.change_summary` です。結果パネルには metadata_override の使用有無と反映キーを表示します。

Icon候補はPNGを主表示にします。GUIで `candidate_png` または `final_png` を採用すると、管理者認証済みの Tauri command が `%LOCALAPPDATA%\ToolHub\data\app_studio\icon_overrides\` に一時JSONを書き、CLIへ `--icon-override <path>` を渡します。採用前のPNG候補はレビュー用だけで、Apply時に自動確定しません。fallback SVGを選ぶ場合はPNG overrideを渡さず、CLIの deterministic fallback PNG と互換用SVGを使います。

# ToolHub App Studio

## 通常新規登録フローの固定ポリシー

App Studio の通常新規登録フローは、通常ユーザー向け配布専用です。入力は Python ソースを基本とし、既存 exe 登録、Python 直接実行、利用者向け app_env 実行方式は通常 GUI から選択できません。

通常フローは、Python ソース入力 → 解析 → 内部 `build_env` 作成 → 依存インストール → `requirements.lock` 生成/更新 → PyInstaller frozen-folder build → frozen-folder 配布物検証 → `app.yaml` 生成/仮登録、の一本道です。`requirements.lock` 生成、frozen-folder build、配布物検証は常に ON です。

`app.yaml` の `run.entry` は `bin/<app_id>/<app_id>.exe` を指し、通常ユーザー向け配布で `.py` を実行入口にしません。`--onefile` は標準にせず、ToolHub の標準は PyInstaller `--onedir --clean --contents-directory .` の folder-based frozen output です。

`build_env` は exe 作成のためだけに使う内部作業環境です。`runtime/app_envs/<app_id>` には作らず、App Studio 出力ディレクトリ配下に作成します。利用者 PC に要求せず、`final_app`、App Pack、release、runtime には含めません。

再 Apply では、同一 app の `output_dir/build_env` を安全に再利用できます。App Studio は `output_dir/build_env/toolhub_build_env_cache.json` に requirements hash、base Python path/version、build tools package specs、build profile hash を保存し、一致する場合だけ build_env を残します。`output_dir/build_tmp/pip_cache` は App Studio 専用 pip cache として使い、PyInstaller / pyinstaller-hooks-contrib が要求 spec を満たしている場合は build tools install を skip します。強制的に作り直す場合は CLI の `--rebuild-build-env` を使います。

非 Python 資産は拡張子だけで一律に除外しません。メイン Python ファイルとローカル import 先を再帰的に解析し、`open(...)`、`Path(...)`、`Path(__file__).parent / ...`、`os.path.join(...)`、`read_text()`、`read_bytes()`、`pandas.read_csv(...)`、`pandas.read_excel(...)`、設定ファイル読み込みなどの固定パス参照から JSON / CSV / XLSX / YAML / TOML / INI / flow / txt / md を add-data 候補にします。`config`、`config.default`、`assets`、`templates`、`static`、`icons`、`images`、`flows` などの定番リソースフォルダも候補になります。

App Studio CLI は `--source-root <dir>` を指定できます。未指定時は従来互換として entry file の親フォルダを source root にします。指定時は entry file が source root 配下にあることを必須検証し、drive root のように広すぎる範囲は拒否します。GUI では「ソース範囲」に任意入力できます。

source root 直下に `.toolhubignore` がある場合、App Studio は最小限の gitignore 風 glob として読み込みます。空行、`#` コメント、`*` glob、末尾 `/` のディレクトリ指定、`!` による再許可を扱います。`work/`, `results/`, `.git`, `.venv`, `node_modules`, `ToolHub_AppStudio_Output`, `release`, `runtime`, `target`, `logs`, `screenshots`, `sessions`, `tmp`, `temp` などの生成物・別プロジェクト・出力系ディレクトリは既定で source walk から除外されます。`assets`, `templates`, `static`, `config`, `icons`, `images`, `flows` などのアプリ資産候補は、source scope 内かつ除外対象でない場合に従来どおり検出されます。

`.auth/`、Playwright storage state、cookie、session、token、credential 類は安全ファイルとしては扱いません。source root 内に存在し、`.toolhubignore` で明示除外されていない場合は Apply block の対象です。`.toolhubignore` で `.auth/` や `storage_state.json` を明示除外した場合は、source walk / secret scan / build profile / App Pack packaging から外し、`file_inventory_report.md` と `suggested_toolhubignore.md` に「sensitive runtime state を明示除外した」記録を残します。App 側は初回ログイン、手動ログイン、再認証、またはユーザー管理領域での runtime state 作成を用意してください。

`.auth/`、logs、screenshots、tmp/temp、仮想環境、build/dist、node_modules、`.git`、`.env`、pem/key、token/secret/password/api_key/credentials、storage_state/cookie/session らしいファイルは同梱しません。機微情報の可能性がある場合は blocked または manual check とし、`file_inventory.json` / `file_inventory.md` / `build_profile_report.md` / `runtime_check_report.md` で理由を確認できるようにします。動的パス参照は無理に全フォルダを同梱せず manual check とします。

配布物検証では、exe の存在、`run.entry` が exe を指すこと、build_profile の add-data が frozen-folder 内に存在すること、禁止ファイルが混入していないこと、`build_env` が混入していないこと、frozen-folder と add-data のサイズを確認します。Playwright を含むアプリでは `--collect-all playwright` を自動反映しますが、ブラウザバイナリ、ログイン、社内サイト操作、認証済み storage state は自動検証済みとは扱わず manual check とします。

Windows では Playwright package data のパスが深くなりやすいため、PyInstaller の作業先は `ToolHub_AppStudio_Output/<app_id>/build_tmp/pyi/{d,b,s}` の短いパスに固定しています。`frozen_folder_build_report.md` の `pyinstaller_artifacts` で実際の `distpath` / `workpath` / `specpath` を確認できます。Playwright の package data copy failure を避けるために `.auth/` や storage state を同梱する対応は禁止です。

## 目的

ToolHub App Studio は、開発者が既存アプリのメインファイルを指定するだけで、ToolHub が検出できる `apps/<app_id>/app.yaml` 形式へ変換するための開発者向け CLI です。

ランチャー本体には App Studio 専用 UI や個別アプリ固有処理を入れません。解析、提案、仮登録、承認は `tools/app_studio` と `scripts/import_app.ps1` で扱います。

GUI 版 App Studio は管理者画面から開く方針です。通常ランチャー画面に App Studio や APIキー管理を直接出さず、初回管理者パスワード設定または管理者ログイン後の管理者ダッシュボードからのみ遷移します。

OpenAI APIキーは管理者画面の AI/APIキー管理で扱います。キー本体は設定JSON、`app.yaml`、App Pack、ログには保存せず、Windows では Credential Manager を使います。APIキー未設定時も App Studio は deterministic fallback で動作します。

## GUI新規登録フロー

管理者画面の App Studio から、新規アプリ登録の GUI フローを実行できます。GUI は既存の CLI 版 `tools/app_studio/main.py` を呼び出し、CLI の生成物と登録仕様をそのまま使います。

GUI で入力できる項目:

- Entry ファイルパス
- Entry 参照ボタン: Windows ではファイル選択ダイアログから Python ソースを選択します。`.exe` は通常新規登録の入力として扱いません。
- App ID
- 表示名
- Icon Prompt

GUI で固定表示される実行予定:

- `requirements.lock` 生成/更新
- 内部 `build_env` 作成と依存インストール
- PyInstaller `--onedir --clean --contents-directory .` による frozen-folder build
- frozen-folder 配布物検証

app_env 作成/再作成、BuildMode 選択、既存 exe 登録、Python 直接実行は通常新規登録 GUI から選べません。

GUI で実行できる操作:

- `Suggest`: 元フォルダ側の `ToolHub_AppStudio_Output/<app_id>/` に提案生成
- `Apply`: `apps/<app_id>/` へ仮登録し、`release/app_manifest.json` へ `enabled=false` で登録
- `Approve`: 実行確認結果を確認し、承認可能な場合に `enabled=true` へ変更

Apply 後は `execution_test_result.json`、`runtime_check_result.json`、App Pack、`enabled` 状態を GUI に表示します。`fail` がある場合は承認できません。GUIでは `AllowWarnings` と `StrictApproval` を選択できます。

`release/app_manifest.json` に entry が残っていても、`apps/<app_id>/app.yaml` が存在しないものは通常表示対象ではありません。`enabled=false` かつ source missing の entry は stale / hidden history として通常検証では警告扱いにできますが、Strict 検証や正式配布前には disabled 維持理由の確認、または将来の完全削除フローで整理する対象です。`enabled=true` で source missing の entry は通常ランチャー表示と更新確認に影響するため不整合です。

AppId / Name 自動提案:

- `main.py`, `app.py`, `__main__.py`, `launcher.py`, `run.py` のような汎用Entry名では親フォルダ名から提案します。
- それ以外はファイル名の stem から提案します。
- AppId は英小文字、数字、`_`、`-` に正規化し、空になった場合は `app` を使います。
- Name は `snake_case` / `kebab-case` を空白区切りの表示名へ変換します。

Preflight表示:

- Entry の存在
- AppId 形式
- Entry が Python ソースであること
- App Studio 実行に使う開発環境 Python の有無

通常新規登録の配布物検証は `runtime/python/python.exe` や `runtime/app_envs/<app_id>` の有無を承認ブロック理由にしません。exe 作成には出力ディレクトリ配下の内部 `build_env` を使います。Python が見つからない場合は Suggest / Apply を実行できませんが、通常ランチャー機能には影響しません。

承認モード:

- 既定は「配布リスクがある警告は承認しない」です。
- `StrictApproval`: `fail` と `approval_blocking_warning` は承認不可です。`non_blocking_warning` や `info` だけなら承認できます。
- `AllowWarnings`: 配布リスクのない警告を許容します。ただし exe欠落、required_files欠落、secret混入、`BUILD_REQUIRED.txt` 残存などの `fail` は承認できません。

Apply 中は `TOOLHUB_PROGRESS {...}` 行を stdout に出力し、`timing_report.json` / `timing_report.md` に工程別時間を記録します。GUI は実行中に現在工程、経過時間、目安時間、残り目安を表示します。目安は同じ app_id の過去実績または一般的な初回ビルド目安であり、環境や依存関係により変動します。

結果サマリーでは `selected_build_mode`、`exit_code`、最後に実行した action、次に必要な操作も表示します。

GUI実行ログ:

```text
%LOCALAPPDATA%\ToolHub\data\logs\admin\app_studio_gui.log
```

ログには action、exit code、app_id、固定 build mode、output_dir、CLI path、argv を記録します。APIキー、パスワード、secret値は記録しません。stdout/stderr 表示前にも `sk-` 形式のキーらしい文字列をマスクします。

GUI未対応またはMVPに留めている機能:

- 既存アプリ更新GUI MVPの詳細は `docs/15_app_studio_update_gui.md` を参照してください。
- 既存アプリ更新はMVPです。登録済みapp_idの選択、version bump、更新Entry指定、Suggest update / Apply update / Approve update までを対象にします。
- 完全な差分ビューア
- 削除/アンインストールの本実装
- publish の本実装
- 配布済みランチャーへの自動更新配信
- manifest署名

## 通常フローと legacy 方式

通常新規登録 GUI は `frozen-folder` 固定です。`app.yaml` は `run.runner: exe` と `run.entry: bin/<app_id>/<app_id>.exe` を使います。

`app-env`、`existing-exe`、Python 直接実行、旧 `auto` 判定は legacy / 既存互換の説明です。既存登録済み app や古い manifest を読むために内部型が残る場合がありますが、通常新規登録 GUI では露出しません。

## app-env方式 legacy

`app-env` は既存 app / 互換用の方式です。通常新規登録 GUI では利用者向け実行方式として使いません。

生成される `app.yaml` は `run.runner: python_app_env` を使います。

## frozen-folder方式

`frozen-folder` は通常新規登録の固定方式です。PyInstaller `--onedir --clean --contents-directory .` で実ビルドを行います。

PyInstaller が未導入、またはビルド環境に問題がある場合は、Apply を成功扱いにせず `frozen_folder_build_report.md` に理由と対処案を残します。実ビルド成果物は `bin/<app_id>/<app_id>.exe` を `run.entry` として扱います。

`--onefile` は標準にしません。起動が遅くなりやすく、利用者体験とログ調査の面で ToolHub の標準配布方式に合わないためです。

AgendaSnap 級の複雑アプリ、音声/GUI/外部DLL/重い依存を含むアプリでは、`frozen-folder` 方式を第一候補にします。

## アイコン修正プロンプト

`-IconPrompt` を指定すると、`icon_work/icon_prompt_revision.md` に修正指示を保存します。App Studio の標準アイコン成果物はPNGです。AI画像生成APIが b64 PNG を返した場合は `icon_work/icon_candidate_1.png` に保存し、GUIで人間が採用したPNGだけを `icon_work/icon_final.png`、`final_app/icon.png`、Apply後の `apps/<app_id>/icon.png` に反映します。

APIキー未設定、AI無効、OpenAI packageなし、API失敗、high/medium secret検出時はAI送信せず deterministic fallback PNG を生成します。fallback/互換用SVGは `icon_work/icon_fallback.svg` と `final_app/icon.svg` に残します。fallback PNG は 512x512 の暫定画像で、API生成成功とは扱いません。モデル名はコードに固定せず、GUIでは管理者画面の Image model 設定、CLIでは `TOOLHUB_APP_STUDIO_IMAGE_MODEL` から読みます。既定候補は OpenAI 公式ドキュメントで GPT Image 系として案内されている `gpt-image-2` です。実環境で利用できるかは「画像生成テスト（実API呼び出し）」で確認してください。

`icon_work/candidate_manifest.json` には候補ごとの `source`、`api`、`model`、`status`、`resolution`、`content_type`、`fallback_reason`、`error_category`、`score_basis`、`image_evaluation_status` に加え、`semantic_score`、`specificity_score`、`small_size_score`、`aesthetic_score`、`revision_follow_score`、`generic_risk_score`、`quality_total`、`quality_label`、`quality_reasons`、`quality_warnings` を保存します。互換のため `icon_candidate_1.png` は引き続き読み込めますが、manifest のない古い候補は `legacy` として扱います。

## 実行確認と人間承認

`-Apply` は仮登録のみ行い、`release/app_manifest.json` の `enabled` は必ず `false` で開始します。

Apply 後に App Studio は `execution_test_report.md` を生成します。人間が内容を確認した後、次のコマンドで承認します。

```powershell
.\scripts\approve_imported_app.ps1 -AppId "agendasnap"
```

承認時に `enabled=true` へ変更し、App Pack を再生成し、可能な範囲で `scripts/verify_release.ps1` を実行します。

## 元フォルダ側へ成果物を保存する仕様

Entry が `C:\work\MyApp\main.py` の場合、成果物は次へ保存されます。

```text
C:\work\MyApp\ToolHub_AppStudio_Output\<app_id>\
```

主な中身:

- `import_plan.json`
- `file_inventory.md`
- `file_inventory.json`
- `dependency_report.json`
- `secret_scan_report.md`
- `suggested_toolhubignore.md`（sensitive runtime state の明示除外または推奨除外がある場合）
- `timing_report.json` / `timing_report.md`
- `registration_copy_breakdown.json` / `registration_copy_report.md`（Apply 後半の backup / copy / App Pack zip / SHA256 / output mirror の内訳）
- `build_plan.md`
- `proposed_app.yaml`
- `proposed_README.md`
- `proposed_requirements.txt`
- `icon_work/`
- `final_app/`
- `app_pack/`
- `execution_test_report.md`
- `approval_record.md`

## 上書き仕様

`ToolHub_AppStudio_Output/<app_id>/` が既に存在する場合は削除して作り直します。削除前に、削除対象が Entry の親フォルダ配下であることを検証します。

Apply 時に同じ `app_id` が既に存在する場合は、`backups/app_studio/YYYYMMDD_HHMMSS/<app_id>/` へ既存 `apps/<app_id>/` と `release/app_manifest.json` をバックアップしてから上書きします。既存 app 本体は、Playwright などの深い package data path で Windows の path 長制限に当たりにくいよう、`app.zip` として退避します。

## 秘密情報検査

secret scan は無効化しません。ただし、`high` という単純な severity だけで Apply を止めず、配布物に入るか、AI送信対象になるか、file inventory で安全に除外されているかを分けて判定します。

原則として Apply を止めるもの:

- `included_files` または build_profile の add-data に入る実値らしい API key / token / password / secret
- `.env`、`*.pem`、`*.key`
- `storage_state`、cookie、session、credentials、client_secret などの認証状態ファイル
- `file_inventory.json` で `blocked` のもの
- 人間確認なしでは配布物混入リスクを否定できない high finding

`.auth/` や storage state を開発中に source root 内へ置く必要がある場合は、source root 直下の `.toolhubignore` に `.auth/` や対象ファイル名を明示してください。明示除外された sensitive runtime state は secret scan と PyInstaller profile から外れますが、除外記録は inventory / suggestion report に残ります。明示除外なしで Apply を通すことはありません。

原則として Apply の即時停止ではなく warning / manual check にするもの:

- README や docs の `OPENAI_API_KEY` という環境変数名だけの説明
- `api_key: "<your key>"`、`token: "dummy"`、`password: "example"` のような明確な placeholder
- Pythonコード内の `api_key`、`token`、`credentials` などの変数名だけで、実値が含まれないもの
- logs、sessions、screenshots、tmp/temp など、file inventory で配布対象外と判定されたもの

AI送信停止と Apply 停止は別判定です。README に `OPENAI_API_KEY` が書かれている場合などは、AI metadata/icon 提案を fallback にしても、配布物に秘密情報が混入しないなら Apply は進められます。

`secret_scan_report.md` には Summary、Blocking Findings、Warnings / Manual Checks、Excluded from Package、False Positive Candidates を出力します。各 finding には `path`、`severity`、`kind`、`inventory_status`、`included_in_package`、`affects_ai_submission`、`blocks_apply`、`block_reason`、`recommended_action` が記録されます。GUI で secret scan により停止した場合は blocking 件数、warning 件数、manual check 件数、レポートパス、上位 blocking finding を表示します。

## 使い方

解析のみ:

```powershell
.\scripts\import_app.ps1 -Entry "C:\path\to\main.py" -DryRun
```

提案生成:

```powershell
.\scripts\import_app.ps1 -Entry "C:\path\to\main.py" -Suggest
```

仮登録:

```powershell
.\scripts\import_app.ps1 -Entry "C:\path\to\main.py" -Apply
```

app_id と名称を指定:

```powershell
.\scripts\import_app.ps1 -Entry "C:\path\to\main.py" -AppId "agendasnap" -Name "AgendaSnap" -Apply
```

通常新規登録:

```powershell
.\scripts\import_app.ps1 -Entry "C:\path\to\main.py" -AppId "agendasnap" -Name "AgendaSnap" -Apply
```

アイコン修正プロンプト:

```powershell
.\scripts\import_app.ps1 -Entry "C:\path\to\main.py" -AppId "agendasnap" -Name "AgendaSnap" -IconPrompt "マイクとメモ帳を組み合わせ、ToolHub既存アイコンに合うシンプルな線画にする" -Suggest
```

## app_env実体作成 legacy

`app-env` 作成は通常新規登録 GUI の機能ではありません。以下は legacy / 既存互換フローの説明です。

```powershell
.\scripts\import_app.ps1 -Entry "C:\work\tool\main.py" -AppId "my_tool" -Name "My Tool" -BuildMode "app-env" -Apply -GenerateLock -CreateAppEnv
```

- `-CreateAppEnv`: `runtime/app_envs/<app_id>/` を作成します。
- `-RebuildAppEnv`: 既存 app_env を `backups/app_studio/...` へ退避して再作成します。
- `-SkipAppEnvBuild`: app_env 作成を明示的にスキップします。

`runtime/python/python.exe` があればそれを使います。ない場合は開発環境 Python を使い、`app_env_build_report.md` に明記します。

## requirements.lock生成

`-GenerateLock` を指定すると、`requirements.lock` を生成またはコピーします。

- 既存 `requirements.lock` がある場合はコピーを優先します。
- 通常新規登録では内部 `build_env` の `pip freeze` を使います。
- それ以外は `requirements.txt` の正規化結果を lock として保存します。
- 通常新規登録では lock 生成をスキップしません。

レポートは `lock_generation_report.md` と `data/logs/app_studio/<app_id>_lock_generation_report.md` に保存されます。`pip freeze` は過剰依存が混ざる可能性があるため、人間レビューを前提にします。

## frozen-folder実ビルド

通常新規登録では、Python アプリを常に `frozen-folder` 方式で PyInstaller `--onedir` 相当のフォルダビルドにします。

```powershell
.\scripts\import_app.ps1 -Entry "C:\work\AgendaSnap\agendasnap\app.py" -AppId "agendasnap" -Name "AgendaSnap" -Apply
```

- frozen-folder build は常に実行します。
- `-RebuildFrozenFolder` は互換用に残る場合がありますが、通常 Apply は毎回ビルドします。
- `-SkipFrozenBuild` は通常新規登録では使えません。

`--onefile` は標準では使いません。App Studio の frozen build は `bin/<app_id>/<app_id>.exe` を `run.entry` として扱います。PyInstaller が見つからない場合は失敗し、`frozen_folder_build_report.md` に理由を残します。

PyInstaller probe や build が obsolete `pathlib` backport の影響で失敗した場合、レポートに原因候補と対処案を出します。App Studio はユーザー環境を壊さないため、自動で `pip uninstall pathlib` は実行しません。

## frozen-folder配布物検証

通常新規登録では、旧 runtime/app_env 検証ではなく frozen-folder 配布物検証を実行します。

```powershell
.\scripts\import_app.ps1 -Entry "C:\work\tool\main.py" -AppId "my_tool" -Apply -VerifyRuntime
```

`-VerifyRuntime` は互換名として残っていますが、通常新規登録では次を確認し、`runtime_check_report.md` と `runtime_check_result.json` を元フォルダ側および `data/logs/app_studio/` に保存します。

- `final_app/bin/<app_id>/<app_id>.exe` の存在
- `app.yaml` の `run.entry` が exe を指すこと
- build_profile の add-data / required_files が frozen-folder 内に存在すること
- `BUILD_REQUIRED.txt` が残っていないこと
- `.auth`、logs、screenshots、tmp、credentials、token、secret、storage_state、`build_env` が配布物に混入していないこと
- frozen-folder と add-data のサイズ

開発中に `runtime/python/python.exe` や `runtime/app_envs/<app_id>` が未配置でも通常フローは壊しません。

```powershell
.\scripts\verify_release.ps1 -RequireRuntime -Strict
```

## 実行確認JSON

Apply 後、Markdown に加えて machine-readable な結果を生成します。

```text
execution_test_result.json
data/logs/app_studio/<app_id>_execution_test_result.json
```

形式:

```json
{
  "app_id": "agendasnap",
  "generated_at": "...",
  "overall_status": "pass",
  "approval_allowed": true,
  "checks": [
    { "name": "app.yaml parse", "status": "pass", "detail": "..." }
  ]
}
```

`fail` がある場合は承認不可です。`warn` は承認可否の観点で分類されます。`approval_blocking_warning` は配布品質や安全性に影響する未解決リスクとして承認不可です。`non_blocking_warning` は AI fallback、Playwright ログイン未確認、外部サービス実操作未確認などの参考警告で、配布物自体が成立している場合はデフォルトの慎重モードでも承認できます。

## 承認モード

```powershell
.\scripts\approve_imported_app.ps1 -AppId "agendasnap" -StrictApproval
```

- 既定: GUI は「配布リスクがある警告は承認しない」です。
- `-AllowWarnings`: 配布リスクのない警告を許容します。
- `-StrictApproval`: `fail` と `approval_blocking_warning` を拒否します。`non_blocking_warning` / `info` だけなら承認できます。

`execution_test_result.json` には `approval_blocking_warnings_count`、`non_blocking_warnings_count`、`info_count`、`unresolved_distribution_risks_count`、`approval_blocking_reasons`、`non_blocking_warning_summaries` が記録されます。required_files や add-data が配布物検証で pass した場合、ビルド前の「packaged data を確認する」注意書きだけで承認不可にはしません。

承認時は `execution_test_result.json`、`apps/<app_id>/app.yaml`、`release/app_manifest.json`、App Pack 生成、可能な範囲の `verify_release.ps1` を確認します。失敗した場合は `enabled=true` にせず、途中で変更した場合も元に戻します。

## OpenAI API連携

AI 連携は明示的に有効化した場合だけ試行します。未設定時や失敗時は deterministic fallback を使います。

GUI では管理者画面の AI/APIキー管理から AI ON/OFF、Text model、Image model、OpenAI APIキーを管理します。CLI では従来通り環境変数を利用できます。

```powershell
$env:TOOLHUB_APP_STUDIO_AI_ENABLED="true"
$env:TOOLHUB_APP_STUDIO_TEXT_MODEL="<configurable-model>"
$env:TOOLHUB_APP_STUDIO_IMAGE_MODEL="<configurable-model>"
$env:OPENAI_API_KEY="..."
```

安全方針:

- `TOOLHUB_APP_STUDIO_AI_ENABLED` が `true` / `1` の場合だけAPI呼び出しを試みます。
- Tauri GUIから起動するCLIには、管理者画面のAI設定を優先して `TOOLHUB_APP_STUDIO_AI_ENABLED`、`TOOLHUB_APP_STUDIO_TEXT_MODEL`、`TOOLHUB_APP_STUDIO_IMAGE_MODEL` を渡します。
- APIキーはAI有効かつキー存在時だけ子プロセスへ `OPENAI_API_KEY` として渡します。Credential Managerが優先で、無ければ環境変数を使います。
- APIキーやモデル名が未設定ならfallbackします。
- `openai` Python package がない場合もfallbackします。
- secret scan で AI送信対象に秘密情報リスクがある場合はAI送信せず fallback します。Apply 停止とは別判定です。
- Entry全文は送らず、ファイル名、README抜粋、既存カテゴリなどの限定情報だけを使います。
- metadata提案は Responses API `responses.create` を使い、JSON parseに失敗した場合はfallbackします。
- 初回画像生成は Images API `images.generate` を使います。再生成の `tweak` / `refine` では、前回PNGがある場合に `images.edit` を優先します。`response_format` は渡しません。
- 標準アイコンは `icon.png` です。`app.yaml` は `display.icon: icon.png` と `display.icon_fallback: icon.svg` を出力します。
- 最終 `icon.svg` はfallback/互換用として保存し、既存SVGアイコンの表示互換性を保ちます。
- 画像APIが b64 PNG を返した場合は `icon_work/icon_candidate_1.png` に保存します。
- 画像APIが URL を返した場合は、ダウンロードせず `icon_work/icon_candidate_1.url.txt` に保存します。
- PNG/URL は人間レビュー用候補であり、PNG候補は人間がGUIで採用した場合だけ `icon.png` に反映します。

## 実運用推奨コマンド

通常新規登録:

```powershell
.\scripts\import_app.ps1 -Entry "C:\work\tool\main.py" -AppId "my_tool" -Name "My Tool" -Apply
```

Playwright や複数ファイルを含むアプリも同じ通常フロー:

```powershell
.\scripts\import_app.ps1 -Entry "C:\work\XCgate_AutoUpload\run_xcgate_upload.py" -AppId "run_xcgate_upload" -Name "Run XCgate Upload" -Apply
```

厳格承認:

```powershell
.\scripts\approve_imported_app.ps1 -AppId "agendasnap" -StrictApproval
```

## 実アプリ適用前チェックリスト

通常新規登録:

- `requirements.txt` または `pyproject.toml`、必要な nested requirements を確認する。
- `requirements.lock` が生成/更新されることを確認する。
- `build_env` が App Studio 出力ディレクトリ配下に作成され、`runtime/app_envs/<app_id>` が PyInstaller に使われていないことを確認する。
- PyInstaller / pyinstaller-hooks-contrib が `build_env` に導入されることを確認する。
- obsolete `pathlib` backport が入っていないことを確認する。
- `final_app/bin/<app_id>/<app_id>.exe` と `apps/<app_id>/bin/<app_id>/<app_id>.exe` が生成されることを確認する。
- `BUILD_REQUIRED.txt` が残っていないことを確認する。
- build_profile の add-data / required_files が frozen-folder 内に存在することを確認する。
- `execution_test_result.json` の `frozen-folder executable` が `pass` であることを確認する。
- `execution_test_result.json` が今回の Apply で更新され、`approval_allowed` が配布物検証結果に基づいていることを確認する。
- `--onefile` を使っていないことを確認する。
- Playwright のブラウザ操作、ログイン、社内サイト操作は manual check として実機で確認する。
- `.\scripts\approve_imported_app.ps1 -AppId "<app_id>" -StrictApproval` を実行する。

AI利用時:

- `TOOLHUB_APP_STUDIO_AI_ENABLED=true` を明示する。
- `OPENAI_API_KEY` が設定されていることを確認する。
- AI送信対象の secret finding がある場合はAI送信されず fallback になることを確認する。
- 生成アイコン候補PNG/URLは人間レビュー用であり、採用したPNGだけが `icon.png` に反映されることを確認する。
- `candidate_manifest.json` の `quality_label`、`quality_warnings`、`image_evaluation_status` を確認し、`fallback` / `fallback_after_api_failure` をAI生成成功候補と混同しない。
- 既存 `display.icon: icon.svg` のアプリが引き続き表示できることを確認する。

## App Studio Import Diagnostic Script

When App Studio approval shows only `Execution test result does not allow approval.`,
use the read-only diagnostic script to separate the direct approval gate from the
root cause in Apply/build artifacts.

```powershell
.\scripts\diagnose_app_studio_import.ps1 -AppId <app_id>
```

Useful options:

- `-Entry <main.py>`: also checks `ToolHub_AppStudio_Output/<app_id>` under the entry parent.
- `-OutputDir <path>`: explicitly points to an App Studio output mirror.
- `-NoWrite`: prints the report without saving `data/logs/app_studio/<app_id>_diagnostic_report.md`.
- `-AsJson`: prints a JSON summary.
- `-VerboseFiles`: includes detailed file evidence.

The script does not run Apply, Approve, PyInstaller, or any app. It only reads
logs, `apps/<app_id>`, output mirror files, and `release/app_manifest.json`, then
classifies likely causes such as stale `execution_test_result.json`, frozen build
failure, registration copy not reached, missing add-data files, old app_env-based
PyInstaller logs, secret scan Apply blocks, possible secret scan overblocking,
AI-only secret scan fallback, or manifest registration gaps.

## App Studio normal registration policy

This section is authoritative for the current normal new-registration GUI.

The normal App Studio registration flow is distribution-only for ordinary users:

```text
Python source -> analyze -> build_env -> install dependencies -> requirements.lock
-> PyInstaller frozen-folder build -> distribution check -> app.yaml/register
```

The normal GUI does not let users choose BuildMode, app_env execution, Python direct execution, or existing-exe registration. Those names may still appear in legacy code paths, old logs, or compatibility documentation for existing apps, but they are not user-facing choices in the normal new-registration GUI.

Normal registration always generates or refreshes `requirements.lock`, always builds a PyInstaller frozen folder, and always runs a frozen-folder distribution/execution check before approval. `app.yaml` must point `run.entry` at the generated executable, usually `bin/<app_id>/<app_id>.exe`; it must not point at a `.py` file for normal distribution.

The build environment is internal. App Studio may create `build_env` under the output workspace to run PyInstaller and build tools, but this is separate from `runtime/app_envs/<app_id>`, is not a user runtime, and must not be copied into `final_app`, App Packs, `release`, or `runtime`.

PyInstaller uses folder output (`--onedir --clean --contents-directory .`) as the ToolHub standard. The verifier accepts older PyInstaller 6 `_internal` add-data placement as a compatibility warning when files are present there, but a current build using `--contents-directory .` is expected to place required add-data beside the executable. If an old failed `execution_test_result.json` is older than `app.yaml`, `build_profile.json`, or the generated exe, approval reports a stale execution result instead of hiding the reason behind a generic approval failure.

Legacy/compatibility notes:

- `app-env`, `existing-exe`, and Python direct execution are compatibility concepts for existing manifests, historical CLI paths, or old registered apps.
- The normal new-registration GUI intentionally does not expose existing-exe registration because ToolHub cannot verify that a user-provided exe is portable and complete.
- Any other section that lists BuildMode choices should be read as legacy background unless it explicitly says it applies to the current normal GUI.

## Approval, catalog visibility, and home refresh diagnostics

App Studio approval and home catalog visibility are separate checks. Approval first verifies the target app, enables the target entry in `release/app_manifest.json`, regenerates the App Pack, and then runs release verification. The home screen only shows apps that can be loaded from the same catalog root and are enabled in `release/app_manifest.json`.

When a newly approved app does not appear after pressing home Refresh, check these fields in the App Studio result panel or diagnostic report:

- `manifest_enabled`: whether `release/app_manifest.json` has `enabled: true` for the app.
- `approval_record_status`: `approved`, `approved_with_global_warnings`, `rolled_back`, or `failed`.
- `approval_failure_summary`: the direct approval or rollback reason.
- `verify_release_status` and `verify_release_failure_summary`: whether release verification failed and which lines failed.
- `catalog_visible`: whether the home catalog loader can see the app as enabled.
- `catalog_disabled_reason`: `disabled_by_manifest`, `app_yaml_missing`, `app_yaml_parse_error`, `runner_validation_error`, `not_found_in_catalog`, or another load error.
- `catalog_root` and `app_studio_repo_root`: the roots used by the catalog reader and App Studio.

App Studio approval no longer treats unrelated pre-existing global `verify_release.ps1` failures as an automatic rollback reason for a newly valid app. It records them as global warnings when they were already present before approval. The target app still rolls back if the target `app_id` has a verification failure, its `app.yaml` cannot be loaded, its `run.entry` is missing, App Pack generation fails, or a new release verification failure is introduced by approval.

The approval record at `data/logs/app_studio/<app_id>_approval_record.md` records `status`, `manifest_enabled_after`, `targeted_verification_status`, `verify_release_before`, `verify_release_after`, `pre_existing_failures`, `new_failures`, and `rollback_reason`. A status of `approved_with_global_warnings` means the app itself passed targeted approval, but unrelated release manifest issues still need cleanup before a strict release build.

## Timing reports and estimates

`timing_report.json` separates estimates from actual measurements:

- `estimated_total_seconds`: predicted Apply duration.
- `actual_total_seconds`: measured total from the Apply timing recorder.
- `prediction_error_seconds`: actual minus estimate.
- `prediction_source`: `history`, `heuristic`, or `unknown`.
- `wall_clock_total_seconds`: elapsed CLI wall-clock time.
- `cli_measured_total_seconds`: sum of measured App Studio phases.
- `unmeasured_overhead_seconds`: time outside measured phases.

The Tauri command result also records `process_wall_clock_seconds`, which is the desktop backend child-process duration. GUI wall-clock time can still be slightly longer because it includes UI state updates, result refresh, and rendering. The result panel shows actual time, estimated time, prediction difference, child-process time, measured phase total, and unmeasured overhead separately so that estimates are not mistaken for actual duration.

## App Studio icon candidates

App Studio now builds an icon design brief before image generation. The brief uses
safe app-specific signals such as `app_id`, app name, entry file name, README
excerpt, generated metadata, categories, keywords, use cases, inputs, outputs,
and dependency names. It must not include API keys, secrets, or local absolute
paths. If the secret scan finds high or medium findings that affect AI
submission, text and image AI calls are skipped and local fallback candidates are
used.

The brief is function-first, not noun-only. It records `app_kind`,
`primary_action`, `secondary_action`, `input_objects`, `output_objects`,
`action_flow`, `visual_priority`, `avoid_generic`, and
`composition_template`. App Studio normalizes common verbs such as
`merge`/`combine`/`join`/`concat` to `merge`, `split`/`separate`/`divide`
to `split`, and `search`/`find`/`retrieve` to `search`. It also normalizes
common objects such as PDF/documents, images/photos, audio/microphone/waveform,
CSV/Excel/tables, mail/calendar/chat, and database/server/cloud.

For common action-object pairs, the prompt prefers a functional composition
template. For example, PDF merge should show multiple PDFs converging into one
PDF; PDF split should show one PDF branching into several PDFs; transcription
should show a microphone or waveform becoming text; comparison should show two
objects side by side with a visible difference. Templates are intentionally
limited to a few strong objects so the icon stays readable at small sizes.

Before image generation, App Studio asks the text model for icon concept JSON.
Concepts are split into `literal`, `balanced`, and `signature` directions and
include the concept, primary motif, secondary motif, composition, style family,
why the concept is specific to the app, and elements to avoid. Each image prompt
is built from one concept so candidates are different ideas rather than minor
variations of the same generic symbol.

Icon generation writes `icon_work/candidate_manifest.json` in addition to the
legacy `icon_candidate_1.png` / `icon_candidate_1.url.txt` files. The manifest
records each candidate id, source (`api`, `fallback`, or
`fallback_after_api_failure`), prompt, model, status, resolution, and whether it
is a fallback. The normal fallback PNG is generated at 512x512 instead of 64x64.
When the image API returns 1024x1024 PNG data, that original candidate is kept in
`icon_work` for review. Manifest schema v2 also stores the function
interpretation, concept metadata, and rule-based scores for semantic clarity,
specificity, small-size legibility, aesthetics, and diversity. The current MVP
also writes quality fields for the generated image candidate itself:
`semantic_score`, `specificity_score`, `small_size_score`, `aesthetic_score`,
`revision_follow_score`, `generic_risk_score`, `quality_total`,
`quality_label`, `quality_reasons`, and `quality_warnings`.

Vision evaluation is not required for registration and is not claimed when it
does not run. If PNG bytes are available, App Studio performs deterministic
rule-based checks by decoding the PNG with the standard library, sampling the
image at small sizes, and checking contrast, visible canvas usage, and
silhouette preservation. In that case `image_evaluation_status` is
`fallback_rule_based`. If only a URL candidate exists, or pixels cannot be
decoded, `image_evaluation_status` stays `not_run` or the note explains that
only prompt/concept checks were used.

The GUI shows each PNG candidate separately with its source, model, resolution,
status, score, quality label, warnings, concept summary, and adoption state. API
candidates are sorted ahead of fallback candidates, and the highest-quality
selectable candidate is marked as recommended. It also shows the
AI-interpreted function summary above the candidate list: primary function,
inputs, outputs, inferred action flow, recommended motif/composition, and
generic patterns to avoid. Pressing "このPNGを採用" stores a PNG override that is
applied on the next Suggest/Apply run, so the selected PNG becomes
`final_app/icon.png`. Removing the adoption returns to the deterministic fallback
for the current run. Older outputs that only have `icon_candidate_1.png` remain
readable.

Icon regeneration now uses the lightweight CLI subcommand `icon-regenerate`
instead of rerunning full Suggest. It reads the existing `outputDir`,
`icon_work/candidate_manifest.json`, and saved PNG candidates, then rebuilds
only the final image API prompt and new icon candidates. It does not rerun file
inventory, secret scan, dependency analysis, metadata generation, build plan, or
`export_suggestion`.

Regeneration defaults to one candidate for speed. The GUI exposes speed modes
for 1/2/3 candidates and image quality modes `draft`, `standard`, and `high`.
The final image API prompt always contains the raw user instruction under
`USER REVISION INSTRUCTION - MUST FOLLOW VERBATIM`, and that prompt is stored in
`candidate_manifest.json` for review. The GUI separates the user instruction,
AI/intermediate prompt, and final image API prompt so users can verify what was
actually sent to the image API.

The available revision modes are `tweak`, `refine`, `redesign`, and `fresh`.
`tweak` and `refine` prefer `images.edit` with the selected previous PNG when
available. `redesign` treats the previous image as reference only and prefers a
new composition. `fresh` does not send the previous PNG and weakens inheritance
from the previous prompt. Regeneration writes `icon_regeneration_timing.json`
with manifest read, prompt build, image API call, file write, and total timing.

## Delete Tab / App Management

Delete is now an App Management tab. The source of truth for an app is `apps/<app_id>/`, and
`release/app_manifest.json` is treated as a release index that can be rebuilt or checked from `apps/`.

Implemented operations:

- Hide: set the existing manifest entry to `enabled=false`.
- Show: set `enabled=true`, only when `apps/<app_id>/app.yaml` exists.
- Deletion plan: list repository-managed targets and excluded targets before full delete.
- Full delete: remove repo-managed app targets through the authenticated Delete tab after a safe plan is displayed.

Full delete removes:

- `apps/<app_id>/`
- the target entry in `release/app_manifest.json`
- target App Pack zip files
- strict `release/staging/` artifacts
- `runtime/app_envs/<app_id>/`
- App Studio and legacy lifecycle backups for the app

Not implemented / intentionally not provided:

- PowerShell production `-Apply`
- restore flows
- backup-based soft delete flows
- `DELETE <app_id>` style confirmation input

Deletion plans classify `managed_required`, `managed_generated`, and `managed_history` as future delete targets.
`external_reference`, `user_data`, and `shared_runtime` are always excluded. `build.source_entry`,
`build.output_mirror`, `%LOCALAPPDATA%/ToolHub/data/`, logs, browser profiles, app state, and shared runtime folders
must not be deleted by app management operations. See `docs/17_app_management_model.md`.

The PowerShell dry-run planner and the Tauri/Rust planner both expose normalized comparison keys. Production full
deletion is implemented in the authenticated Delete tab; temporary-app E2E remains covered by
`scripts/test_app_full_delete_e2e.ps1`. The implementation roadmap and phase status are managed in
`docs/18_app_delete_execution_plan.md`; the executor contract is in
`docs/19_full_delete_executor_design.md`.
Release-readiness cleanup classification for disabled stale entries, App Pack rebuild work, runtime packaging, and
installer build tasks is tracked in `docs/20_release_readiness_cleanup.md`.

## App Source Of Truth And Derived Release Data

After Apply, the canonical app source is `apps/<app_id>/`. App Studio writes the finalized `app.yaml`, README,
requirements files, icon files, `bin/`, and bundled assets there. The release manifest entry is derived from that app
source: `admin.version` provides the app version and `runtime.required_runtime` provides the runtime requirement when
present. The App Pack is generated from `apps/<app_id>/` and is treated as a derived artifact.

`build.source_entry`, `build.output_mirror`, and any other external absolute paths recorded in `app.yaml` are provenance
references. They help diagnose how an app was built, but they are not ToolHub-owned app source and must not become delete
targets in App Management.
