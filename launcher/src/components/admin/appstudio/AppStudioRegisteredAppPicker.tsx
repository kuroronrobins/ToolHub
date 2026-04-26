import type { AppStudioRegisteredApp } from "../../../lib/appStudioTypes";

interface Props {
  apps: AppStudioRegisteredApp[];
  selectedAppId: string;
  loading: boolean;
  onReload: () => void;
  onSelect: (app: AppStudioRegisteredApp) => void;
}

export function AppStudioRegisteredAppPicker({ apps, selectedAppId, loading, onReload, onSelect }: Props) {
  return (
    <section className="studio-step">
      <div>
        <span className="studio-step-index">1</span>
        <h4>Registered app</h4>
      </div>
      <div className="studio-preflight-head">
        <span className="admin-status-pill">{apps.length ? `${apps.length} apps` : "not loaded"}</span>
        <button className="secondary-button" type="button" onClick={onReload} disabled={loading}>
          Reload apps
        </button>
      </div>
      <div className="studio-app-picker">
        {apps.length ? (
          apps.map((app) => (
            <button
              key={app.appId}
              className={`studio-app-option ${selectedAppId === app.appId ? "active" : ""}`}
              type="button"
              onClick={() => onSelect(app)}
            >
              <strong>{app.name || app.appId}</strong>
              <span>{app.appId}</span>
              <span>version {app.version || "-"}</span>
              <span>{app.enabled ? "enabled=true" : "enabled=false"}</span>
              {app.warning ? <em>{app.warning}</em> : null}
            </button>
          ))
        ) : (
          <p className="admin-muted">Reload apps to choose an existing ToolHub app.</p>
        )}
      </div>
    </section>
  );
}
