import { Download } from "lucide-react";
import { shouldShowUserUpdateNotice, updateNoticeTargetLabel } from "../lib/updateNotice";
import type { UpdateSummary } from "../lib/updateTypes";

interface Props {
  summary: UpdateSummary | null;
  onOpen: () => void;
  onDismiss: () => void;
}

export function UpdateNotice({ summary, onOpen, onDismiss }: Props) {
  if (!shouldShowUserUpdateNotice(summary)) {
    return null;
  }

  return (
    <section className="update-notice" role="status">
      <Download size={20} aria-hidden="true" />
      <div>
        <strong>{updateNoticeTargetLabel(summary)} を利用できます</strong>
        <p>不具合修正、配布アプリ、ランタイムの更新を反映できます。作業前の更新を推奨します。</p>
      </div>
      <div className="notice-actions">
        <button className="primary-button" type="button" onClick={onOpen}>
          更新する
        </button>
        <button className="secondary-button" type="button" onClick={onDismiss}>
          あとで
        </button>
      </div>
    </section>
  );
}

