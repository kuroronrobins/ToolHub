import { CheckCircle2, CircleAlert, PackageCheck, ShieldCheck } from "lucide-react";
import type { ReactNode } from "react";
import type { AppStudioRunResult } from "../../../lib/appStudioTypes";

interface Props {
  result: AppStudioRunResult | null;
  lastAction: "suggest" | "apply" | "approve" | null;
  busy: boolean;
  onApprove: () => void;
  onRefresh: () => void;
}

export function AppStudioResultPanel({ result, lastAction, busy, onApprove, onRefresh }: Props) {
  const canApprove = Boolean(
    result?.appId &&
      lastAction === "apply" &&
      result.ok &&
      result.executionStatus !== "fail" &&
      result.approvalAllowed !== false,
  );

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
        <ResultRow icon={<CheckCircle2 size={18} />} label="output_dir" value={result?.outputDir ?? "-"} />
        <ResultRow icon={<CircleAlert size={18} />} label="execution" value={result?.executionStatus ?? "unknown"} />
        <ResultRow icon={<CircleAlert size={18} />} label="approval_allowed" value={formatBool(result?.approvalAllowed)} />
        <ResultRow icon={<CircleAlert size={18} />} label="runtime" value={result?.runtimeStatus ?? "unknown"} />
        <ResultRow icon={<PackageCheck size={18} />} label="App Pack" value={result?.appPack ?? "-"} />
      </div>

      <p className="admin-muted">Strict承認は次フェーズで追加予定です。failがある場合は承認できません。</p>
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
