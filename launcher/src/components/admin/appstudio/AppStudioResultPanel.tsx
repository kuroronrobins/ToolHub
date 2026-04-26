import { CheckCircle2, CircleAlert, PackageCheck, ShieldCheck } from "lucide-react";
import type { ReactNode } from "react";
import type { AppStudioRunResult } from "../../../lib/appStudioTypes";

interface Props {
  result: AppStudioRunResult | null;
  lastAction: "suggest" | "apply" | "approve" | null;
  approvalMode: "allowWarnings" | "strict";
  onApprovalModeChange: (mode: "allowWarnings" | "strict") => void;
  busy: boolean;
  onApprove: () => void;
  onRefresh: () => void;
}

export function AppStudioResultPanel({ result, lastAction, approvalMode, onApprovalModeChange, busy, onApprove, onRefresh }: Props) {
  const canApprove = Boolean(
    result?.appId &&
      lastAction === "apply" &&
      result.ok &&
      result.executionStatus !== "fail" &&
      result.approvalAllowed !== false &&
      (approvalMode === "allowWarnings" || result.executionStatus === "pass"),
  );
  const nextAction = nextActionText(result, lastAction, approvalMode);

  return (
    <section className="studio-side-section">
      <div className="admin-section-head">
        <div>
          <p className="dialog-kicker">結果サマリー</p>
          <h4>生成物と承認状態</h4>
        </div>
        <span className={`admin-status-pill ${result?.enabled ? "ok" : ""}`}>{result?.enabled ? "enabled=true" : "未承認"}</span>
      </div>

      <div className="studio-result-list">
        <ResultRow icon={<CheckCircle2 size={18} />} label="app_id" value={result?.appId ?? "-"} />
        <ResultRow icon={<CheckCircle2 size={18} />} label="build_mode" value={result?.selectedBuildMode ?? "-"} />
        <ResultRow icon={<CheckCircle2 size={18} />} label="exit_code" value={result ? String(result.exitCode) : "-"} />
        <ResultRow icon={<CheckCircle2 size={18} />} label="last_action" value={lastAction ?? "-"} />
        <ResultRow icon={<CheckCircle2 size={18} />} label="output_dir" value={result?.outputDir ?? "-"} />
        <ResultRow icon={<CircleAlert size={18} />} label="execution" value={result?.executionStatus ?? "unknown"} />
        <ResultRow icon={<CircleAlert size={18} />} label="approval_allowed" value={formatBool(result?.approvalAllowed)} />
        <ResultRow icon={<CircleAlert size={18} />} label="runtime" value={result?.runtimeStatus ?? "unknown"} />
        <ResultRow icon={<PackageCheck size={18} />} label="App Pack" value={result?.appPack ?? "-"} />
        <ResultRow icon={<ShieldCheck size={18} />} label="next" value={nextAction} />
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
          再読込
        </button>
        <button className="primary-button" type="button" onClick={onApprove} disabled={busy || !canApprove}>
          <ShieldCheck size={17} aria-hidden="true" />
          Approve
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
    return "true";
  }
  if (value === false) {
    return "false";
  }
  return "unknown";
}

function nextActionText(
  result: AppStudioRunResult | null,
  lastAction: "suggest" | "apply" | "approve" | null,
  approvalMode: "allowWarnings" | "strict",
): string {
  if (!result) {
    return "Preflight後にSuggestまたはApplyを実行してください";
  }
  if (!result.ok) {
    return "ログとレポートを確認してください";
  }
  if (result.enabled) {
    return "承認済みです";
  }
  if (lastAction === "suggest") {
    return "Applyしてください";
  }
  if (lastAction === "apply") {
    if (result.executionStatus === "fail" || result.approvalAllowed === false) {
      return "failの解消が必要です";
    }
    if (approvalMode === "strict" && result.executionStatus !== "pass") {
      return "StrictApprovalではwarnを解消してください";
    }
    return "Approveできます";
  }
  return "結果を確認してください";
}
