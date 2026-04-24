import { X } from "lucide-react";

interface Props {
  open: boolean;
  onClose: () => void;
}

export function AboutDialog({ open, onClose }: Props) {
  if (!open) {
    return null;
  }

  return (
    <div className="dialog-backdrop" role="presentation" onMouseDown={onClose}>
      <section className="dialog-panel compact" role="dialog" aria-modal="true" aria-labelledby="about-title" onMouseDown={(event) => event.stopPropagation()}>
        <header className="dialog-header">
          <div>
            <p className="dialog-kicker">情報</p>
            <h2 id="about-title">ToolHub</h2>
          </div>
          <button className="icon-button" type="button" onClick={onClose} title="閉じる">
            <X size={20} aria-hidden="true" />
          </button>
        </header>

        <section className="detail-section">
          <h3>概要</h3>
          <p>業務アプリを探して起動するためのデスクトップランチャーです。</p>
        </section>

        <details className="admin-details">
          <summary>管理者向け情報</summary>
          <dl>
            <div>
              <dt>Core</dt>
              <dd>0.1.0</dd>
            </div>
            <div>
              <dt>Runner</dt>
              <dd>0.1.0</dd>
            </div>
          </dl>
        </details>
      </section>
    </div>
  );
}

