import { Download } from "lucide-react";
import type { UpdateSummary } from "../lib/updateTypes";

interface Props {
  summary: UpdateSummary | null;
  onOpen: () => void;
  onDismiss: () => void;
}

export function UpdateNotice({ summary, onOpen, onDismiss }: Props) {
  if (!summary) {
    return null;
  }

  return (
    <section className="update-notice" role="status">
      <Download size={20} aria-hidden="true" />
      <div>
        <strong>{summary.title}</strong>
        <p>{summary.message}</p>
      </div>
      <div className="notice-actions">
        <button className="primary-button" type="button" onClick={onOpen}>
          今すぐ更新
        </button>
        <button className="secondary-button" type="button" onClick={onDismiss}>
          あとで
        </button>
      </div>
    </section>
  );
}

