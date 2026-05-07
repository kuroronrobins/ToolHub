import { Download } from "lucide-react";
import type { UpdateSummary } from "../lib/updateTypes";

interface Props {
  summary: UpdateSummary | null;
  onOpen: () => void;
  onDismiss: () => void;
}

export function UpdateNotice({ summary, onOpen, onDismiss }: Props) {
  if (!summary || summary.status !== "update_available") {
    return null;
  }

  return (
    <section className="update-notice" role="status">
      <Download size={20} aria-hidden="true" />
      <div>
        <strong>更新候補があります</strong>
        <p>更新候補があります。ただし現在は確認のみで、適用は管理者機能です。</p>
      </div>
      <div className="notice-actions">
        <button className="primary-button" type="button" onClick={onOpen}>
          詳細を確認
        </button>
        <button className="secondary-button" type="button" onClick={onDismiss}>
          閉じる
        </button>
      </div>
    </section>
  );
}

