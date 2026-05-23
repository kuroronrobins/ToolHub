import { FileQuestion, Info, Play } from "lucide-react";
import type { KeyboardEvent } from "react";
import type { ToolApp } from "../lib/types";

interface Props {
  app: ToolApp;
  onLaunch: (app: ToolApp) => void;
  onDetail: (app: ToolApp) => void;
}

export function AppCard({ app, onLaunch, onDetail }: Props) {
  function handleCardKeyDown(event: KeyboardEvent<HTMLElement>) {
    if (event.target !== event.currentTarget) {
      return;
    }

    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      onDetail(app);
    }
  }

  return (
    <article
      className="app-card"
      role="button"
      tabIndex={0}
      aria-label={`${app.name}の説明を見る`}
      onClick={() => onDetail(app)}
      onKeyDown={handleCardKeyDown}
    >
      <div className="app-icon" aria-hidden="true">
        {app.iconDataUrl ? (
          <img src={app.iconDataUrl} alt="" />
        ) : app.iconSvg ? (
          <img src={`data:image/svg+xml;utf8,${encodeURIComponent(app.iconSvg)}`} alt="" />
        ) : (
          <FileQuestion size={60} />
        )}
      </div>

      <div className="card-content">
        <div className="card-title-block">
          <h2>{app.name}</h2>
          <p>{app.shortDescription}</p>
        </div>

        <div className="tag-row" aria-label={`${app.name}のカテゴリ`}>
          {app.categories.map((category) => (
            <span key={category} className="tag">
              {category}
            </span>
          ))}
        </div>
      </div>

      <div className="card-actions">
        <button
          className="primary-button launch-button"
          type="button"
          onClick={(event) => {
            event.stopPropagation();
            onLaunch(app);
          }}
        >
          <Play size={17} aria-hidden="true" />
          起動
        </button>
        <button
          className="icon-button detail-icon-button"
          type="button"
          onClick={(event) => {
            event.stopPropagation();
            onDetail(app);
          }}
          title="説明を見る"
          aria-label={`${app.name}の説明を見る`}
        >
          <Info size={18} aria-hidden="true" />
        </button>
      </div>
    </article>
  );
}

