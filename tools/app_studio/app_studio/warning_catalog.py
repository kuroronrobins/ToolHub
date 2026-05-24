from __future__ import annotations

from collections.abc import Mapping
from typing import Any


ALERT_CATALOG: dict[str, dict[str, str | bool]] = {
    "secret.apply_blocked": {
        "severity": "critical",
        "show_to_admin": True,
        "title": "秘密情報が登録対象に含まれている可能性があります",
        "summary": "APIキー、token、password などの実値らしい文字列が登録対象に見つかったため、承認すると配布物に秘密情報が混入する恐れがあります。",
        "why_dangerous": "配布物やApp Packに秘密情報が入ると、利用者PCや共有先から認証情報が漏えいする可能性があります。",
        "admin_action": "secret_scan_report.md を開き、該当値を削除または無効化してください。実値は環境変数、Windows Credential Manager、またはユーザー管理領域から読み込む形に変更してから再登録してください。",
    },
    "registration.failed": {
        "severity": "critical",
        "show_to_admin": True,
        "title": "登録検証に失敗しました",
        "summary": "登録後のアプリ定義、実行ファイル、ランタイム、またはApp Packに失敗があります。",
        "why_dangerous": "この状態で承認すると、利用者がアプリを起動できない、または配布物が壊れた状態になる可能性があります。",
        "admin_action": "表示されたチェック名と詳細を確認し、欠落ファイル、run.entry、requirements.lock、runtime、App Pack のいずれが原因かを直してから再実行してください。",
    },
    "app_manifest.missing": {
        "severity": "critical",
        "show_to_admin": True,
        "title": "app.yaml が登録されていません",
        "summary": "登録後の apps/<app_id>/ に app.yaml が見つかりません。",
        "why_dangerous": "ToolHub は app.yaml を読んでアプリの起動方法を判断するため、この状態ではランチャーに正しく表示・起動できません。",
        "admin_action": "登録処理のコピー結果と source root を確認し、app.yaml が apps/<app_id>/ 直下に作成される状態で App Studio Apply を再実行してください。",
    },
    "app_manifest.invalid": {
        "severity": "critical",
        "show_to_admin": True,
        "title": "app.yaml を読み込めません",
        "summary": "登録後の app.yaml が壊れている、または ToolHub の manifest 形式に合っていません。",
        "why_dangerous": "manifest を読み込めないアプリはランチャーに表示できず、承認しても利用者が起動できません。",
        "admin_action": "execution_test_result.json の app.yaml parse 詳細を確認し、YAML構文、run.runner、run.entry、runtime 設定を直してから再登録してください。",
    },
    "app_manifest.entry_mismatch": {
        "severity": "critical",
        "show_to_admin": True,
        "title": "app.yaml の起動先が生成物と一致していません",
        "summary": "app.yaml の run.entry が、登録後に検証した起動ファイルを指していません。",
        "why_dangerous": "別ファイルや存在しないファイルを起動しようとして、ランチャーからの起動に失敗する可能性があります。",
        "admin_action": "app.yaml の run.entry と App Studio の entry 設定を一致させ、生成物を作り直してから再登録してください。",
    },
    "run.entry_missing": {
        "severity": "critical",
        "show_to_admin": True,
        "title": "起動ファイルが登録されていません",
        "summary": "app.yaml の run.entry が指すファイルが登録後の apps/<app_id>/ に存在しません。",
        "why_dangerous": "利用者がランチャーから起動しても、runner が起動対象を見つけられず失敗します。",
        "admin_action": "登録元の entry と source root を確認し、run.entry が apps/<app_id>/ 配下へコピーされる形で再登録してください。",
    },
    "run_entry_policy.invalid": {
        "severity": "critical",
        "show_to_admin": True,
        "title": "配布用の起動方式が不正です",
        "summary": "通常配布用の登録で、run.entry が許可されない形式になっています。",
        "why_dangerous": "配布方式と起動方式が合わないため、承認後に利用者環境でアプリを起動できない可能性があります。",
        "admin_action": "shared-env は Python entry、frozen-folder は生成済み exe を指すように build mode と run.entry を揃えて再登録してください。",
    },
    "runner.unsupported": {
        "severity": "critical",
        "show_to_admin": True,
        "title": "未対応の runner が指定されています",
        "summary": "app.yaml の run.runner が ToolHub の App Studio 検証対象外です。",
        "why_dangerous": "runner が未対応だと、ToolHub が起動方法を判断できず、承認後の起動に失敗します。",
        "admin_action": "run.runner を python_shared_env、python_app_env、cli、exe のいずれかの対応方式に直して再登録してください。",
    },
    "runtime.missing": {
        "severity": "critical",
        "show_to_admin": True,
        "title": "必要なPython実行環境が見つかりません",
        "summary": "app.yaml が要求する shared runtime または Python runtime が ToolHub 側に存在しません。",
        "why_dangerous": "アプリ本体が正しく登録されていても、依存ライブラリを読み込めず起動に失敗します。",
        "admin_action": "requirements.lock の生成と shared runtime 作成結果を確認し、runtime/envs/<env_id> が存在する状態で再登録してください。",
    },
    "runtime.env_id_missing": {
        "severity": "critical",
        "show_to_admin": True,
        "title": "共有ランタイムIDが未設定です",
        "summary": "python_shared_env 登録なのに env_id が選択されていません。",
        "why_dangerous": "どの共有ランタイムで起動すべきか判断できず、登録後の起動に失敗します。",
        "admin_action": "App Studio の通常登録フローで requirements.lock から shared runtime を作成し、run.env_id が入る状態で Apply を再実行してください。",
    },
    "runtime.collect_all_missing": {
        "severity": "warning",
        "show_to_admin": True,
        "title": "共有ランタイムに必要な収集対象パッケージがありません",
        "summary": "build_profile.collect_all に指定されたパッケージを shared runtime で import 確認できませんでした。",
        "why_dangerous": "PyInstaller/共有ランタイムで必要なサブパッケージが欠けると、利用者環境で起動直後または特定機能の実行時に失敗します。",
        "admin_action": "requirements.lock と build_profile.collect_all を見直し、対象パッケージが shared runtime に入る状態で再登録してください。",
    },
    "requirements_lock.missing": {
        "severity": "critical",
        "show_to_admin": True,
        "title": "requirements.lock が登録されていません",
        "summary": "共有ランタイム方式に必要な requirements.lock が apps/<app_id>/ にありません。",
        "why_dangerous": "依存バージョンを固定できず、別PCや更新後に同じ環境を再現できない可能性があります。",
        "admin_action": "通常登録フローで requirements.lock を生成し、App Studio Apply を再実行してください。",
    },
    "frozen.executable_missing": {
        "severity": "critical",
        "show_to_admin": True,
        "title": "配布用 exe が見つかりません",
        "summary": "frozen-folder 登録で必要な実行ファイルが登録後のフォルダにありません。",
        "why_dangerous": "ランチャーは exe を起動できないため、承認しても利用者がアプリを開けません。",
        "admin_action": "PyInstaller のビルド結果、run.entry、apps/<app_id>/bin 配下の配置を確認してから再登録してください。",
    },
    "frozen.build_profile_missing": {
        "severity": "warning",
        "show_to_admin": True,
        "title": "exe化用の build_profile.json がありません",
        "summary": "frozen-folder の配布検証で、必要ファイルを確認するための build_profile.json が見つかりません。",
        "why_dangerous": "必要な設定ファイルやデータファイルの同梱漏れを自動判定できず、利用者環境で一部機能が壊れる可能性があります。",
        "admin_action": "App Studio が生成した build_profile.json を確認し、必要ファイルを add_data または required_files に入れてから再登録してください。",
    },
    "frozen.build_profile_invalid": {
        "severity": "critical",
        "show_to_admin": True,
        "title": "build_profile.json を読み込めません",
        "summary": "build_profile.json が壊れているため、exe化後の必要ファイル検証を実行できません。",
        "why_dangerous": "配布に必要なファイルの欠落を検出できず、承認後に起動失敗や機能不全が起きる可能性があります。",
        "admin_action": "build_profile.json の JSON 構文と add_data / required_files を修正し、App Studio Apply を再実行してください。",
    },
    "data_files.missing": {
        "severity": "critical",
        "show_to_admin": True,
        "title": "必要なデータファイルが配布物に入っていません",
        "summary": "build_profile で必要と判断された設定、テンプレート、モデル、ブラウザ関連ファイルなどが登録後の配布物に見つかりません。",
        "why_dangerous": "アプリ本体は起動しても、設定読込、テンプレート利用、自動処理などの実務機能が失敗する可能性があります。",
        "admin_action": "build_profile.add_data / required_files と .toolhubignore を確認し、必要ファイルが配布物に含まれる状態で再登録してください。",
    },
    "pyinstaller.layout_risk": {
        "severity": "warning",
        "show_to_admin": True,
        "title": "PyInstaller の配置形式に配布リスクがあります",
        "summary": "PyInstaller onedir のデータ配置が ToolHub の期待する形式とずれている可能性があります。",
        "why_dangerous": "exe の横にあるべきデータが _internal 側に入り、起動時の相対パス参照や更新時の配置で失敗する可能性があります。",
        "admin_action": "frozen_folder_build_report.md の PyInstaller command を確認し、--contents-directory . を使う形で再ビルドしてください。",
    },
    "build_env.packaged": {
        "severity": "critical",
        "show_to_admin": True,
        "title": "ビルド用環境が配布物に混入しています",
        "summary": "App Studio の build_env が final_app の中に入っています。",
        "why_dangerous": "本来配布しないビルド用 Python 環境やキャッシュが利用者PCへ配られ、容量増加や不要ファイル混入につながります。",
        "admin_action": "source root、output_dir、build_env の配置を見直し、build_env が final_app / apps/<app_id> / App Pack に入らない状態で再登録してください。",
    },
    "package.size_large": {
        "severity": "warning",
        "show_to_admin": True,
        "title": "配布物のサイズが大きすぎる可能性があります",
        "summary": "生成された配布物が大きく、不要な依存関係やデータファイルを含んでいる可能性があります。",
        "why_dangerous": "配布、更新、バックアップに時間がかかり、利用者PCの容量を圧迫します。意図しないデータ混入の兆候である場合もあります。",
        "admin_action": "build_profile.add_data、collect_all、不要なモデル・キャッシュ・ブラウザバイナリを確認し、必要最小限にしてから再登録してください。",
    },
    "add_data.source_large": {
        "severity": "warning",
        "show_to_admin": True,
        "title": "同梱予定データが大きすぎる可能性があります",
        "summary": "build_profile.add_data の候補に大きなフォルダまたはファイルが含まれています。",
        "why_dangerous": "ログ、キャッシュ、生成物、不要な実行環境を誤って配布物へ含める原因になります。",
        "admin_action": "add_data の source を見直し、必要な設定・テンプレート・静的資産だけを同梱してください。",
    },
    "forbidden_payload": {
        "severity": "critical",
        "show_to_admin": True,
        "title": "配布してはいけないファイルが登録対象に含まれています",
        "summary": "認証状態、ログ、キャッシュ、一時ファイル、build_env など、配布対象外のファイルが apps/<app_id>/ に入りました。",
        "why_dangerous": "利用者環境へ不要な状態ファイルや認証情報を配ってしまう可能性があります。",
        "admin_action": ".toolhubignore、source root、build_profile.add_data を見直し、対象ファイルを登録対象から外して再登録してください。",
    },
    "frozen.child_process_contract": {
        "severity": "warning",
        "show_to_admin": True,
        "title": "exe化後に子プロセス起動が壊れる可能性があります",
        "summary": "sys.executable -m <module> のような子プロセス起動が検出されました。",
        "why_dangerous": "PyInstaller後は sys.executable が python.exe ではなくアプリexeを指すため、子プロセスが想定どおり起動しない場合があります。",
        "admin_action": "app.exe --window <name> のような明示的な entry-point dispatcher に置き換えてから再検証してください。",
    },
    "build_required_marker": {
        "severity": "critical",
        "show_to_admin": True,
        "title": "未ビルドを示すマーカーが残っています",
        "summary": "BUILD_REQUIRED.txt が登録後のアプリ配下に残っています。",
        "why_dangerous": "必要なビルド成果物が未作成のまま配布され、利用者環境で起動できない可能性があります。",
        "admin_action": "ビルドを完了させ、BUILD_REQUIRED.txt が消えた状態で再登録してください。",
    },
    "smoke.missing_safe_flag": {
        "severity": "warning",
        "show_to_admin": True,
        "title": "安全な起動検証用フラグがありません",
        "summary": "GUIアプリらしい構造ですが、--toolhub-smoke または --smoke が見つからないため自動起動検証を安全に実行できません。",
        "why_dangerous": "本物の画面や外部サービスを開かずに起動可否を確認できないため、承認前に起動不能を見逃す可能性があります。",
        "admin_action": "アプリの entry に --toolhub-smoke などの軽量検証モードを追加し、GUIや外部接続を開かずに依存関係と起動準備だけ確認できるようにしてください。",
    },
    "smoke.failed": {
        "severity": "critical",
        "show_to_admin": True,
        "title": "起動検証で失敗しました",
        "summary": "登録後の配布物を ToolHub の想定環境で起動したところ、即時終了、例外、timeout、または fatal error が発生しました。",
        "why_dangerous": "承認しても、利用者が通常ランチャーから起動した時に同じ失敗が起きる可能性が高いです。",
        "admin_action": "runtime_check_report.md の output tail を確認し、entry、依存関係、相対パス、必要ファイル、--toolhub-smoke の実装を修正して再登録してください。",
    },
    "distribution.approval_blocking": {
        "severity": "warning",
        "show_to_admin": True,
        "title": "承認前に確認が必要な配布リスクがあります",
        "summary": "配布物検証で、承認を止めるべきリスクが検出されました。",
        "why_dangerous": "利用者環境で起動不能、ファイル欠落、または配布形式の破損につながる可能性があります。",
        "admin_action": "runtime_check_report.md と execution_test_report.md を確認し、approval_blocking_warning に分類された詳細を解消してから再実行してください。",
    },
    "runner.execution_failed": {
        "severity": "critical",
        "show_to_admin": True,
        "title": "runner の起動確認に失敗しました",
        "summary": "ToolHub runner 経由の起動確認で失敗しました。",
        "why_dangerous": "登録はできても、利用者が通常ランチャーから起動すると同じ失敗が起きる可能性があります。",
        "admin_action": "runner_result.json とアプリの実行ログを確認し、entry、依存関係、runtime、標準入力の要否を修正してください。",
    },
    "secret.non_blocking_manual_check": {
        "severity": "info",
        "show_to_admin": False,
        "title": "秘密情報の手動確認メモ",
    },
    "runtime.playwright_smoke_skipped": {
        "severity": "info",
        "show_to_admin": False,
        "title": "Playwright の自動起動検証をスキップ",
    },
    "runner.dry_execution_skipped": {
        "severity": "info",
        "show_to_admin": False,
        "title": "runner dry execution をスキップ",
    },
    "build_profile.reference": {
        "severity": "info",
        "show_to_admin": False,
        "title": "build profile の参考情報",
    },
    "data_files.reference": {
        "severity": "info",
        "show_to_admin": False,
        "title": "データファイル検証の参考情報",
    },
    "runtime.manual_check": {
        "severity": "info",
        "show_to_admin": False,
        "title": "手動確認が必要な外部連携",
    },
    "runtime.legacy_check_skipped": {
        "severity": "info",
        "show_to_admin": False,
        "title": "旧runtime検証をスキップ",
    },
    "run_entry_policy.unusual": {
        "severity": "info",
        "show_to_admin": False,
        "title": "特殊な起動ファイル名の参考情報",
    },
    "build_env.not_found": {
        "severity": "info",
        "show_to_admin": False,
        "title": "build_env 未作成の参考情報",
    },
    "smoke.reference": {
        "severity": "info",
        "show_to_admin": False,
        "title": "起動検証の参考情報",
    },
    "generic.non_blocking_warning": {
        "severity": "info",
        "show_to_admin": False,
        "title": "参考情報",
    },
}

CHECK_STATUS_ALERTS: dict[str, dict[str, str]] = {
    "app.yaml exists": {"fail": "app_manifest.missing"},
    "app.yaml parse": {"fail": "app_manifest.invalid"},
    "app.yaml run.entry": {"fail": "app_manifest.entry_mismatch"},
    "runner supported": {"fail": "runner.unsupported"},
    "frozen-folder executable": {"fail": "frozen.executable_missing"},
    "frozen-folder executable exists": {"fail": "frozen.executable_missing"},
    ".py run.entry blocked": {"fail": "run_entry_policy.invalid"},
    "distribution run.entry policy": {"fail": "run_entry_policy.invalid", "warn": "run_entry_policy.unusual"},
    "shared-env id": {"fail": "runtime.env_id_missing"},
    "shared-env runtime": {"fail": "runtime.missing", "warn": "runtime.missing"},
    "shared-env python": {"fail": "runtime.missing"},
    "python runtime": {"warn": "runtime.missing", "fail": "runtime.missing"},
    "requirements.lock exists": {"fail": "requirements_lock.missing", "warn": "requirements_lock.missing"},
    "requirements.lock registered": {"fail": "requirements_lock.missing", "warn": "requirements_lock.missing"},
    "requirements.lock": {"fail": "requirements_lock.missing", "warn": "requirements_lock.missing"},
    "build mode": {"warn": "build_profile.reference"},
    "managed build python": {"warn": "build_profile.reference"},
    "frozen build profile": {"warn": "frozen.build_profile_missing", "fail": "frozen.build_profile_invalid"},
    "profile data files": {"warn": "data_files.reference", "fail": "data_files.missing"},
    "hidden imports": {"warn": "build_profile.reference"},
    "playwright browser dependency": {"warn": "runtime.manual_check"},
    "frozen data files": {"warn": "data_files.reference", "fail": "data_files.missing"},
    "required add-data files": {"warn": "data_files.reference", "fail": "data_files.missing"},
    "shared-env collect_all imports": {"warn": "runtime.collect_all_missing", "fail": "runtime.collect_all_missing"},
    "pyinstaller layout command": {"warn": "pyinstaller.layout_risk", "fail": "pyinstaller.layout_risk"},
    "forbidden registered payload": {"fail": "forbidden_payload", "warn": "forbidden_payload"},
    "forbidden payload files": {"fail": "forbidden_payload", "warn": "forbidden_payload"},
    "forbidden payload files after smoke": {"fail": "forbidden_payload", "warn": "forbidden_payload"},
    "build_env separation": {"fail": "build_env.packaged", "warn": "build_env.not_found"},
    "shared-env app source size": {"warn": "package.size_large"},
    "frozen-folder size": {"warn": "package.size_large"},
    "add-data source size": {"warn": "add_data.source_large"},
    "registered build_required marker": {"fail": "build_required_marker", "warn": "build_required_marker"},
    "build_required marker removed": {"fail": "build_required_marker", "warn": "build_required_marker"},
    "frozen child-process contract": {"warn": "frozen.child_process_contract", "fail": "frozen.child_process_contract"},
    "playwright manual check": {"warn": "runtime.manual_check"},
    "legacy runtime check": {"warn": "runtime.legacy_check_skipped"},
}

DETAIL_ALERTS: tuple[tuple[str, str], ...] = (
    ("safe smoke flag", "smoke.missing_safe_flag"),
    ("--toolhub-smoke", "smoke.missing_safe_flag"),
    ("--smoke", "smoke.missing_safe_flag"),
    ("startup produced a fatal error", "smoke.failed"),
    ("executable could not be started", "smoke.failed"),
    ("entry could not be started", "smoke.failed"),
    ("process exited during startup smoke check", "smoke.failed"),
    ("smoke command timed out", "smoke.failed"),
    ("shared env python is missing", "runtime.missing"),
    ("entry file is missing", "run.entry_missing"),
    ("entry file is not present", "run.entry_missing"),
    ("app directory is missing", "app_manifest.missing"),
    ("missing packaged data files", "data_files.missing"),
    ("forbidden files", "forbidden_payload"),
    ("build_env is inside final_app", "build_env.packaged"),
)


def build_admin_alerts(checks: list[Any]) -> list[dict[str, str]]:
    alerts: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for check in checks:
        alert = admin_alert_for_check(check)
        if not alert:
            continue
        key = (alert["id"], alert.get("source", ""))
        if key in seen:
            continue
        seen.add(key)
        alerts.append(alert)
    return alerts


def merge_admin_alerts(*alert_groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for alerts in alert_groups:
        for alert in alerts:
            key = (str(alert.get("id", "")), str(alert.get("source", "")))
            if key in seen:
                continue
            seen.add(key)
            merged.append(alert)
    return merged


def admin_alert_for_check(check: Any) -> dict[str, str] | None:
    alert_id = classify_check(check)
    item = ALERT_CATALOG.get(alert_id, ALERT_CATALOG["generic.non_blocking_warning"])
    if not item.get("show_to_admin", False):
        return None
    detail = str(_field(check, "detail") or "")
    name = str(_field(check, "name") or "")
    return {
        "id": alert_id,
        "severity": str(item.get("severity") or "warning"),
        "title": str(item.get("title") or name or "確認が必要です"),
        "summary": str(item.get("summary") or detail),
        "why_dangerous": str(item.get("why_dangerous") or ""),
        "admin_action": str(item.get("admin_action") or ""),
        "source": detail,
        "check_name": name,
    }


def classify_check(check: Any) -> str:
    raw_name = str(_field(check, "name") or "")
    name = raw_name.lower()
    detail = str(_field(check, "detail") or "").lower()
    status = str(_field(check, "status") or "").lower()
    category = str(_field(check, "approval_category") or "").lower()
    approval_blocking = bool(_field(check, "approval_blocking"))

    if "secret scan" == name:
        if status == "fail" or "block approval" in detail:
            return "secret.apply_blocked"
        return "secret.non_blocking_manual_check"
    if name in CHECK_STATUS_ALERTS and status in CHECK_STATUS_ALERTS[name]:
        alert_id = CHECK_STATUS_ALERTS[name][status]
        if alert_id == "data_files.reference" and "missing packaged data files" in detail:
            return "data_files.missing"
        if alert_id == "smoke.reference":
            return _classify_smoke_detail(detail, status)
        if alert_id == "run_entry_policy.unusual" and (approval_blocking or category == "approval_blocking_warning"):
            return "run_entry_policy.invalid"
        return alert_id
    if name in {"frozen smoke execution", "shared-env startup smoke"}:
        return _classify_smoke_detail(detail, status)
    if "run.entry" in name or "entry file" in detail or "entry file is not present" in detail:
        return "run.entry_missing"
    if "shared-env runtime" in name or "python runtime" in name or "runtime fallback" in name:
        if status in {"fail", "warn"}:
            return "runtime.missing"
    if "requirements.lock" in name and status in {"fail", "warn"}:
        return "requirements_lock.missing"
    if "forbidden registered payload" in name and status in {"fail", "warn"}:
        return "forbidden_payload"
    if "frozen child-process contract" in name and status in {"fail", "warn"}:
        return "frozen.child_process_contract"
    if "build_required" in name or "build_required" in detail:
        return "build_required_marker"
    if "distribution check" in name:
        if "startup smoke" in detail and "skipped" in detail and "playwright" in detail:
            return "runtime.playwright_smoke_skipped"
        if status == "fail":
            return _classify_detail(detail, "registration.failed")
        if approval_blocking or category == "approval_blocking_warning":
            return _classify_detail(detail, "distribution.approval_blocking")
        return "generic.non_blocking_warning"
    if "runner dry execution" in name:
        if status == "fail":
            return "runner.execution_failed"
        if "skipped" in detail:
            return "runner.dry_execution_skipped"
        return "generic.non_blocking_warning"
    if status == "fail":
        return _classify_detail(detail, "registration.failed")
    if status == "warn" and (approval_blocking or category == "approval_blocking_warning"):
        return _classify_detail(detail, "distribution.approval_blocking")
    return "generic.non_blocking_warning"


def _field(check: Any, key: str) -> Any:
    if isinstance(check, Mapping):
        return check.get(key, "")
    return getattr(check, key, "")


def _classify_detail(detail: str, default: str) -> str:
    for pattern, alert_id in DETAIL_ALERTS:
        if pattern in detail:
            return alert_id
    return default


def _classify_smoke_detail(detail: str, status: str) -> str:
    if "playwright" in detail and "skipped" in detail:
        return "runtime.playwright_smoke_skipped"
    if "does not look like a native executable" in detail:
        return "smoke.reference"
    if "no safe smoke flag" in detail or "--toolhub-smoke" in detail or "--smoke" in detail:
        return "smoke.missing_safe_flag"
    if status == "fail":
        return "smoke.failed"
    if "process exited during startup smoke check" in detail:
        return "smoke.reference"
    return "generic.non_blocking_warning"
