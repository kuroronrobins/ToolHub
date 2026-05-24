import { Download } from "lucide-react";
import { shouldShowUserUpdateNotice, updateNoticeTargetLabel } from "../lib/updateNotice";
import type { UpdateSummary } from "../lib/updateTypes";

interface Props {
  summary: UpdateSummary | null;
  onOpen: () => void;
  onDetails?: () => void;
  onDismiss: () => void;
}

export function UpdateNotice({ summary, onOpen, onDetails, onDismiss }: Props) {
  if (!shouldShowUserUpdateNotice(summary)) {
    return null;
  }

  const userNotes = summary.releaseNotes?.user;
  const title = userNotes?.title?.trim() || `${updateNoticeTargetLabel(summary)} を利用できます`;
  const body = userNotes?.summary?.trim() || "新しい機能や改善を反映できます。最新の状態で使うため更新をおすすめします。";

  return (
    <section className="update-notice" role="status">
      <Download size={20} aria-hidden="true" />
      <div>
        <strong>{title}</strong>
        <p>{body}</p>
      </div>
      <div className="notice-actions">
        <button className="primary-button" type="button" onClick={onOpen}>
          更新する
        </button>
        <button className="secondary-button" type="button" onClick={onDetails ?? onOpen}>
          更新内容を見る
        </button>
        <button className="secondary-button" type="button" onClick={onDismiss}>
          あとで
        </button>
      </div>
    </section>
  );
}

