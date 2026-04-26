import { CheckCircle2, RotateCcw } from "lucide-react";
import { joinMetadataList, splitMetadataText } from "../../../lib/appStudioMetadata";

interface Props {
  label: string;
  value?: string[];
  proposal?: string[];
  status: string;
  warning?: string;
  canRevert: boolean;
  onChange: (value: string[]) => void;
  onAdopt: () => void;
  onRevert: () => void;
}

export function AppStudioArrayField({ label, value, proposal, status, warning, canRevert, onChange, onAdopt, onRevert }: Props) {
  const proposedValue = joinMetadataList(proposal);
  return (
    <div className="studio-metadata-field">
      <div className="studio-metadata-field-head">
        <strong>{label}</strong>
        <span className={`studio-metadata-status ${statusClass(status)}`}>{status}</span>
      </div>
      <div className="studio-metadata-columns">
        <label className="admin-field">
          <span>Current</span>
          <textarea className="studio-textarea" rows={4} value={joinMetadataList(value)} onChange={(event) => onChange(splitMetadataText(event.target.value))} />
        </label>
        <div className="studio-proposal-cell">
          <span>AI proposal</span>
          <pre>{proposedValue || "-"}</pre>
          <div className="studio-action-row">
            <button className="secondary-button" type="button" onClick={onAdopt} disabled={!proposedValue}>
              <CheckCircle2 size={16} aria-hidden="true" />
              Adopt
            </button>
            <button className="secondary-button" type="button" onClick={onRevert} disabled={!canRevert}>
              <RotateCcw size={16} aria-hidden="true" />
              Revert
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
