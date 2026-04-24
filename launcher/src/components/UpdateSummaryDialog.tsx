import { X } from "lucide-react";
import type { UpdateItem, UpdateSummary } from "../lib/updateTypes";

interface Props {
  summary: UpdateSummary | null;
  onClose: () => void;
}

function VersionRow({ item }: { item: UpdateItem }) {
  return (
    <div className="version-row">
      <span>{item.label}</span>
      <strong>
        {item.currentVersion} -&gt; {item.nextVersion}
      </strong>
    </div>
  );
}

export function UpdateSummaryDialog({ summary, onClose }: Props) {
  if (!summary) {
    return null;
  }

  return (
    <div className="dialog-backdrop" role="presentation" onMouseDown={onClose}>
      <section className="dialog-panel compact" role="dialog" aria-modal="true" aria-labelledby="update-title" onMouseDown={(event) => event.stopPropagation()}>
        <header className="dialog-header">
          <div>
            <p className="dialog-kicker">更新</p>
            <h2 id="update-title">{summary.title}</h2>
          </div>
          <button className="icon-button" type="button" onClick={onClose} title="閉じる">
            <X size={20} aria-hidden="true" />
          </button>
        </header>

        <section className="detail-section">
          <h3>内容</h3>
          <p>{summary.message}</p>
        </section>

        <details className="admin-details">
          <summary>管理者向け詳細</summary>
          <div className="version-list">
            {summary.core ? <VersionRow item={summary.core} /> : null}
            {summary.runner ? <VersionRow item={summary.runner} /> : null}
            {summary.apps.map((item) => (
              <VersionRow key={item.label} item={item} />
            ))}
            {summary.runtimeUpdate ? <div className="version-row"><span>Web自動化用ランタイム</span><strong>更新あり</strong></div> : null}
          </div>
        </details>
      </section>
    </div>
  );
}

