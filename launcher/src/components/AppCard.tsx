import { FileQuestion, Info, Play } from "lucide-react";
import type { ToolApp } from "../lib/types";

interface Props {
  app: ToolApp;
  onLaunch: (app: ToolApp) => void;
  onDetail: (app: ToolApp) => void;
}

export function AppCard({ app, onLaunch, onDetail }: Props) {
  return (
    <article className="app-card">
      <div className="card-head">
        <div className="app-icon" aria-hidden="true">
          {app.iconSvg ? <img src={`data:image/svg+xml;utf8,${encodeURIComponent(app.iconSvg)}`} alt="" /> : <FileQuestion size={28} />}
        </div>
        <div className="card-title-block">
          <h2>{app.name}</h2>
          <p>{app.shortDescription}</p>
        </div>
      </div>

      <div className="tag-row" aria-label="カテゴリ">
        {app.categories.map((category) => (
          <span key={category} className="tag">
            {category}
          </span>
        ))}
      </div>

      <div className="card-actions">
        <button className="primary-button" type="button" onClick={() => onLaunch(app)}>
          <Play size={18} aria-hidden="true" />
          起動
        </button>
        <button className="secondary-button" type="button" onClick={() => onDetail(app)}>
          <Info size={18} aria-hidden="true" />
          説明を見る
        </button>
      </div>
    </article>
  );
}

