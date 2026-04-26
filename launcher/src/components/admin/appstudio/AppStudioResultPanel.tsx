import { CheckCircle2, CircleAlert, PackageCheck, ShieldCheck } from "lucide-react";
import type { ReactNode } from "react";
import type { AppStudioApprovalMode, AppStudioRunResult } from "../../../lib/appStudioTypes";

interface Props {
  result: AppStudioRunResult | null;
  lastAction: "suggest" | "apply" | "approve" | null;
  approvalMode: AppStudioApprovalMode;
  onApprovalModeChange: (mode: AppStudioApprovalMode) => void;
  busy: boolean;
  onApprove: () => void;
  onRefresh: () => void;
}

export function AppStudioResultPanel({ result, lastAction, approvalMode, onApprovalModeChange, busy, onApprove, onRefresh }: Props) {
  const warningOnly = Boolean(result && !result.ok && result.executionStatus === "warn" && result.approvalAllowed === true);
  const canApprove = Boolean(
    result?.appId &&
      lastAction === "apply" &&
      result.executionStatus !== "fail" &&
      result.approvalAllowed !== false &&
      (approvalMode === "allowWarnings" || result.executionStatus === "pass"),
  );
  const nextAction = nextActionText(result, lastAction, approvalMode);

  return (
    <section className="studio-side-section">
      <div className="admin-section-head">
        <div>
          <p className="dialog-kicker">結果</p>
          <h4>生成物と承認状態</h4>
        </div>
        <span className={`admin-status-pill ${result?.enabled || warningOnly ? "ok" : ""}`}>
          {result?.enabled ? "enabled=true" : warningOnly ? "警告 / 承認可" : "未承認"}
        </span>
      </div>

      {warningOnly ? (
        <p className="admin-muted">
          CLIの終了コードは0以外ですが、execution_test_result.json は warn かつ approval_allowed=true です。ログを確認してから承認してください。
        </p>
      ) : null}

      {result?.selectedBuildMode === "existing-exe" ? (
        <p className="admin-muted">
          existing-exe は既存の実行ファイルと関連ファイルを使います。dry execution が warn でスキップされる場合があります。
        </p>
      ) : null}

      <div className="studio-result-list">
        <ResultRow icon={<CheckCircle2 size={18} />} label="アプリID" value={result?.appId ?? "-"} />
        <ResultRow icon={<CheckCircle2 size={18} />} label="実行方式" value={result?.selectedBuildMode ?? "-"} />
        <ResultRow icon={<CheckCircle2 size={18} />} label="現在版" value={result?.currentVersion ?? "-"} />
        <ResultRow icon={<CheckCircle2 size={18} />} label="新しい版" value={result?.newVersion ?? "-"} />
        <ResultRow icon={<CheckCircle2 size={18} />} label="終了コード" value={result ? String(result.exitCode) : "-"} />
        <ResultRow icon={<CheckCircle2 size={18} />} label="処理結果" value={result ? boolLabel(result.ok) : "-"} />
        <ResultRow icon={<CheckCircle2 size={18} />} label="最後の操作" value={actionLabel(lastAction)} />
        <ResultRow icon={<CheckCircle2 size={18} />} label="出力先" value={result?.outputDir ?? "-"} />
        <ResultRow icon={<CheckCircle2 size={18} />} label="metadata override" value={metadataOverrideText(result)} />
        <ResultRow icon={<CheckCircle2 size={18} />} label="icon override" value={iconOverrideText(result)} />
        <ResultRow icon={<CircleAlert size={18} />} label="実行確認" value={result?.executionStatus ?? "unknown"} />
        <ResultRow icon={<CircleAlert size={18} />} label="承認可能" value={formatBool(result?.approvalAllowed)} />
        <ResultRow icon={<CircleAlert size={18} />} label="runtime" value={result?.runtimeStatus ?? "unknown"} />
        <ResultRow icon={<PackageCheck size={18} />} label="App Pack" value={result?.appPack ?? "未作成"} />
        <ResultRow icon={<ShieldCheck size={18} />} label="次の操作" value={nextAction} />
      </div>

      <fieldset className="studio-approval-mode">
        <legend>承認モード</legend>
        <label>
          <input
            type="radio"
            name="studio-approval-mode"
            checked={approvalMode === "allowWarnings"}
            onChange={() => onApprovalModeChange("allowWarnings")}
          />
          <span>AllowWarnings</span>
        </label>
        <label>
          <input
            type="radio"
            name="studio-approval-mode"
            checked={approvalMode === "strict"}
            onChange={() => onApprovalModeChange("strict")}
          />
          <span>StrictApproval</span>
        </label>
      </fieldset>
      <div className="admin-form-actions">
        <button className="secondary-button" type="button" onClick={onRefresh} disabled={busy || !result?.appId}>
          結果を再読み込み
        </button>
        <button className="primary-button" type="button" onClick={onApprove} disabled={busy || !canApprove}>
          <ShieldCheck size={17} aria-hidden="true" />
          承認して有効化
        </button>
      </div>
    </section>
  );
}

function ResultRow({ icon, label, value }: { icon: ReactNode; label: string; value: string }) {
  return (
    <div className="studio-result-row">
      <span aria-hidden="true">{icon}</span>
      <strong>{label}</strong>
      <p>{value}</p>
    </div>
  );
}

function formatBool(value: boolean | null | undefined): string {
  if (value === true) {
    return "yes";
  }
  if (value === false) {
    return "no";
  }
  return "unknown";
}

function boolLabel(value: boolean): string {
  return value ? "成功" : "失敗";
}

function actionLabel(action: "suggest" | "apply" | "approve" | null): string {
  if (action === "suggest") {
    return "登録内容を作成";
  }
  if (action === "apply") {
    return "仮登録";
  }
  if (action === "approve") {
    return "承認";
  }
  return "-";
}

function metadataOverrideText(result: AppStudioRunResult | null): string {
  if (!result?.metadataOverrideUsed) {
    return "未使用";
  }
  return result.metadataOverrideKeys?.length ? result.metadataOverrideKeys.join(", ") : "使用";
}

function iconOverrideText(result: AppStudioRunResult | null): string {
  if (!result?.iconOverrideUsed) {
    return result?.selectedIconSource ?? "未使用";
  }
  return result.selectedIconSource ?? "使用";
}

function nextActionText(
  result: AppStudioRunResult | null,
  lastAction: "suggest" | "apply" | "approve" | null,
  approvalMode: AppStudioApprovalMode,
): string {
  if (!result) {
    return "事前確認後、登録内容を作成してください。";
  }
  const warningOnly = result.executionStatus === "warn" && result.approvalAllowed === true;
  if (!result.ok && !warningOnly) {
    return "ログと生成レポートを確認してください。";
  }
  if (result.enabled) {
    return "承認済みです。";
  }
  if (lastAction === "suggest") {
    return "仮登録して実行確認してください。";
  }
  if (lastAction === "apply") {
    if (result.executionStatus === "fail" || result.approvalAllowed === false) {
      return "失敗チェックを解消してください。";
    }
    if (approvalMode === "strict" && result.executionStatus !== "pass") {
      return "StrictApprovalではpassが必要です。";
    }
    return "承認できます。";
  }
  return "結果を確認してください。";
}
