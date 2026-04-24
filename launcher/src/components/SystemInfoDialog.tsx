import { X } from "lucide-react";

interface Props {
  open: boolean;
  onClose: () => void;
}

export function SystemInfoDialog({ open, onClose }: Props) {
  if (!open) {
    return null;
  }

  return (
    <div className="dialog-backdrop" role="presentation" onMouseDown={onClose}>
      <section className="dialog-panel compact" role="dialog" aria-modal="true" aria-labelledby="system-title" onMouseDown={(event) => event.stopPropagation()}>
        <header className="dialog-header">
          <div>
            <p className="dialog-kicker">管理者向け</p>
            <h2 id="system-title">システム情報</h2>
          </div>
          <button className="icon-button" type="button" onClick={onClose} title="閉じる">
            <X size={20} aria-hidden="true" />
          </button>
        </header>

        <section className="detail-section">
          <h3>配置方針</h3>
          <p>インストール先とユーザーデータ先を分離し、更新時にユーザーデータを保持します。</p>
        </section>

        <details className="admin-details" open>
          <summary>更新単位</summary>
          <ul className="plain-list">
            <li>ToolHub Core</li>
            <li>Runner</li>
            <li>Built-in Apps</li>
            <li>Heavy Runtime</li>
            <li>User Dataは更新対象外</li>
          </ul>
        </details>
      </section>
    </div>
  );
}

