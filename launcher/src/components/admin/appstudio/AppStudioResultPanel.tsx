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
          <p className="dialog-kicker">Result summary</p>
          <h4>Artifacts and approval status</h4>
        </div>
        <span className={`admin-status-pill ${result?.enabled || warningOnly ? "ok" : ""}`}>
          {result?.enabled ? "enabled=true" : warningOnly ? "warn / approval OK" : "not approved"}
        </span>
      </div>

      {warningOnly ? (
        <p className="admin-muted">
          CLI exit code is non-zero, but execution_test_result.json is warn and approval_allowed=true. Existing-exe and
          frozen-folder dry execution can be skipped and reported as warn. Review logs before approval.
        </p>
      ) : null}

      {result?.selectedBuildMode === "existing-exe" ? (
        <p className="admin-muted">
          existing-exe uses the provided executable and related files. Python dependency analysis is usually empty, and
          dry execution may be skipped with warn. AllowWarnings can approve this when other checks pass.
        </p>
      ) : null}

      <div className="studio-result-list">
        <ResultRow icon={<CheckCircle2 size={18} />} label="app_id" value={result?.appId ?? "-"} />
        <ResultRow icon={<CheckCircle2 size={18} />} label="build_mode" value={result?.selectedBuildMode ?? "-"} />
        <ResultRow icon={<CheckCircle2 size={18} />} label="current_ver" value={result?.currentVersion ?? "-"} />
        <ResultRow icon={<CheckCircle2 size={18} />} label="new_ver" value={result?.newVersion ?? "-"} />
        <ResultRow icon={<CheckCircle2 size={18} />} label="exit_code" value={result ? String(result.exitCode) : "-"} />
        <ResultRow icon={<CheckCircle2 size={18} />} label="process_ok" value={result ? String(result.ok) : "-"} />
        <ResultRow icon={<CheckCircle2 size={18} />} label="last_action" value={lastAction ?? "-"} />
        <ResultRow icon={<CheckCircle2 size={18} />} label="output_dir" value={result?.outputDir ?? "-"} />
        <ResultRow icon={<CircleAlert size={18} />} label="execution" value={result?.executionStatus ?? "unknown"} />
        <ResultRow icon={<CircleAlert size={18} />} label="approval_allowed" value={formatBool(result?.approvalAllowed)} />
        <ResultRow icon={<CircleAlert size={18} />} label="runtime" value={result?.runtimeStatus ?? "unknown"} />
        <ResultRow icon={<PackageCheck size={18} />} label="App Pack" value={result?.appPack ?? "not found"} />
        <ResultRow icon={<ShieldCheck size={18} />} label="next" value={nextAction} />
      </div>

      <fieldset className="studio-approval-mode">
        <legend>Approval mode</legend>
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
          Refresh
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
  approvalMode: AppStudioApprovalMode,
): string {
  if (!result) {
    return "Run Preflight, then Suggest or Apply.";
  }
  const warningOnly = result.executionStatus === "warn" && result.approvalAllowed === true;
  if (!result.ok && !warningOnly) {
    return "Review logs and generated reports.";
  }
  if (result.enabled) {
    return "Approved.";
  }
  if (lastAction === "suggest") {
    return "Run Apply.";
  }
  if (lastAction === "apply") {
    if (result.executionStatus === "fail" || result.approvalAllowed === false) {
      return "Resolve fail checks before approval.";
    }
    if (approvalMode === "strict" && result.executionStatus !== "pass") {
      return "StrictApproval requires pass.";
    }
    return "Approve is available.";
  }
  return "Review the result.";
}
