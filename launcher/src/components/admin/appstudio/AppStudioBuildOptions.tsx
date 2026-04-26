import type { AppStudioBuildMode, AppStudioImportRequest } from "../../../lib/appStudioTypes";

interface Props {
  request: AppStudioImportRequest;
  onChange: (next: AppStudioImportRequest) => void;
}

const BUILD_MODES: AppStudioBuildMode[] = ["auto", "app-env", "frozen-folder", "existing-exe"];

export function AppStudioBuildOptions({ request, onChange }: Props) {
  function update(partial: Partial<AppStudioImportRequest>) {
    onChange({ ...request, ...partial });
  }

  return (
    <section className="studio-step">
      <div>
        <span className="studio-step-index">3</span>
        <h4>Build方式</h4>
      </div>
      <div className="studio-segmented" role="radiogroup" aria-label="Build方式">
        {BUILD_MODES.map((mode) => (
          <button
            key={mode}
            type="button"
            className={request.buildMode === mode ? "active" : ""}
            onClick={() => update({ buildMode: mode })}
          >
            {mode}
          </button>
        ))}
      </div>

      <div className="studio-option-grid">
        <label className="admin-toggle">
          <input
            type="checkbox"
            checked={request.generateLock}
            onChange={(event) => update({ generateLock: event.target.checked })}
          />
          <span>requirements.lock生成</span>
        </label>
        <label className="admin-toggle">
          <input
            type="checkbox"
            checked={request.createAppEnv}
            onChange={(event) => update({ createAppEnv: event.target.checked })}
          />
          <span>app_env作成</span>
        </label>
        <label className="admin-toggle">
          <input
            type="checkbox"
            checked={request.rebuildAppEnv}
            onChange={(event) => update({ rebuildAppEnv: event.target.checked })}
          />
          <span>app_env再作成</span>
        </label>
        <label className="admin-toggle">
          <input
            type="checkbox"
            checked={request.buildFrozenFolder}
            onChange={(event) => update({ buildFrozenFolder: event.target.checked })}
          />
          <span>frozen-folder build</span>
        </label>
        <label className="admin-toggle">
          <input
            type="checkbox"
            checked={request.verifyRuntime}
            onChange={(event) => update({ verifyRuntime: event.target.checked })}
          />
          <span>runtime検証</span>
        </label>
      </div>
    </section>
  );
}
