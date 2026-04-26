import { CheckCircle2, RotateCcw } from "lucide-react";

interface Props {
  label: string;
  value?: string;
  proposal?: string | null;
  rows?: number;
  status: string;
  warning?: string;
  canRevert: boolean;
  onChange: (value: string) => void;
  onAdopt: () => void;
  onRevert: () => void;
}

export function AppStudioMetadataField({
  label,
  value,
  proposal,
  rows = 3,
  status,
  warning,
  canRevert,
  onChange,
  onAdopt,
  onRevert,
}: Props) {
  const proposedValue = proposal?.trim() ?? "";
  return (
    <div className="studio-metadata-field">
      <div className="studio-metadata-field-head">
        <strong>{label}</strong>
        <span className={`studio-metadata-status ${statusClass(status)}`}>{statusLabel(status)}</span>
      </div>
      <div className="studio-metadata-columns">
        <label className="admin-field">
          <span>編集中</span>
          <textarea className="studio-textarea" rows={rows} value={value ?? ""} onChange={(event) => onChange(event.target.value)} />
        </label>
        <div className="studio-proposal-cell">
          <span>AI提案</span>
          <pre>{proposedValue || "-"}</pre>
          <div className="studio-action-row">
            <button className="secondary-button" type="button" onClick={onAdopt} disabled={!proposedValue}>
              <CheckCircle2 size={16} aria-hidden="true" />
              採用
            </button>
            <button className="secondary-button" type="button" onClick={onRevert} disabled={!canRevert}>
              <RotateCcw size={16} aria-hidden="true" />
              元に戻す
            </button>
          </div>
        </div>
      </div>
      {warning ? <p className="admin-warning">{warning}</p> : null}
    </div>
  );
}

function statusClass(status: string): string {
  if (status === "adopted") {
    return "ok";
  }
  if (status === "diff" || status === "empty") {
    return "warn";
  }
  return "";
}

function statusLabel(status: string): string {
  if (status === "adopted") {
    return "採用済み";
  }
  if (status === "diff") {
    return "差分あり";
  }
  if (status === "empty") {
    return "未入力";
  }
  if (status === "no proposal") {
    return "提案なし";
  }
  return status;
}
