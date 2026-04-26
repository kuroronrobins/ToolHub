import { BUILD_MODE_INFO, buildModeTitle, recommendBuildMode } from "../../../lib/appStudioBuildInfo";
import type { AppStudioBuildMode, AppStudioImportRequest } from "../../../lib/appStudioTypes";

interface Props {
  request: AppStudioImportRequest;
  onChange: (next: AppStudioImportRequest) => void;
}

const BUILD_MODES: AppStudioBuildMode[] = ["auto", "app-env", "frozen-folder", "existing-exe"];

export function AppStudioBuildOptions({ request, onChange }: Props) {
  const selectedInfo = BUILD_MODE_INFO[request.buildMode];
  const recommendation = recommendBuildMode(request.entry);

  function update(partial: Partial<AppStudioImportRequest>) {
    onChange({ ...request, ...partial });
  }

  return (
    <section className="studio-step studio-build-options">
      <div>
        <span className="studio-step-index">B</span>
        <h4>実行方式</h4>
      </div>
      <div className="studio-segmented" role="radiogroup" aria-label="実行方式">
        {BUILD_MODES.map((mode) => (
          <button
            key={mode}
            type="button"
            className={`${request.buildMode === mode ? "active" : ""} ${recommendation.mode === mode ? "recommended" : ""}`.trim()}
            title={buildModeTitle(mode)}
            onClick={() => update({ buildMode: mode })}
          >
            {mode}
          </button>
        ))}
      </div>

      <div className="studio-build-help">
        <strong>{selectedInfo.title}</strong>
        <p>{selectedInfo.description}</p>
        <div className="studio-build-recommendation">
          <span>推奨: {recommendation.mode}</span>
          <p>{recommendation.reason}</p>
        </div>
        {recommendation.entryKind === "exe" ? (
          <ul>
            <li>既存exeとして登録します。</li>
            <li>Python依存解析は基本的に不要です。</li>
            <li>exeと同じフォルダのDLLや設定ファイルもbin配下にコピーされます。</li>
            <li>dry executionがスキップされてwarnになる場合があります。AllowWarningsなら承認できます。</li>
          </ul>
        ) : null}
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
