import { X } from "lucide-react";
import type { ToolApp } from "../lib/types";

interface Props {
  app: ToolApp | null;
  onClose: () => void;
}

function SectionList({ title, items }: { title: string; items: string[] }) {
  return (
    <section className="detail-section">
      <h3>{title}</h3>
      {items.length > 0 ? (
        <ul>
          {items.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      ) : (
        <p>記載はありません。</p>
      )}
    </section>
  );
}

export function AppDetailDialog({ app, onClose }: Props) {
  if (!app) {
    return null;
  }

  return (
    <div className="dialog-backdrop" role="presentation" onMouseDown={onClose}>
      <section className="dialog-panel" role="dialog" aria-modal="true" aria-labelledby="detail-title" onMouseDown={(event) => event.stopPropagation()}>
        <header className="dialog-header">
          <div>
            <p className="dialog-kicker">アプリ説明</p>
            <h2 id="detail-title">{app.name}</h2>
          </div>
          <button className="icon-button" type="button" onClick={onClose} title="閉じる">
            <X size={20} aria-hidden="true" />
          </button>
        </header>

        <section className="detail-section">
          <h3>概要</h3>
          <p>{app.detail.description}</p>
        </section>

        <SectionList title="できること" items={app.detail.useCases} />
        <SectionList title="使い方" items={app.search.examples} />
        <SectionList title="入力するもの" items={app.detail.inputs} />
        <SectionList title="出力されるもの" items={app.detail.outputs} />
        <SectionList title="注意事項" items={app.detail.notes} />

        <details className="admin-details">
          <summary>管理者向け情報</summary>
          <dl>
            <div>
              <dt>管理番号</dt>
              <dd>{app.id}</dd>
            </div>
            <div>
              <dt>バージョン</dt>
              <dd>{app.admin?.version ?? "未設定"}</dd>
            </div>
            <div>
              <dt>管理者</dt>
              <dd>{app.admin?.owner ?? "未設定"}</dd>
            </div>
            <div>
              <dt>要件ファイル</dt>
              <dd>{app.admin?.requirements ?? "未設定"}</dd>
            </div>
          </dl>
        </details>
      </section>
    </div>
  );
}

