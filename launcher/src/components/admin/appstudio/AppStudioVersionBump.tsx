import type { AppStudioVersionBumpMode } from "../../../lib/appStudioTypes";
import { bumpAppVersion, compareSimpleSemVer } from "../../../lib/appStudioVersion";

interface Props {
  currentVersion: string;
  mode: AppStudioVersionBumpMode;
  manualVersion: string;
  newVersion: string;
  onModeChange: (mode: AppStudioVersionBumpMode) => void;
  onManualVersionChange: (value: string) => void;
}

const MODES: AppStudioVersionBumpMode[] = ["patch", "minor", "major", "manual"];

export function AppStudioVersionBump({
  currentVersion,
  mode,
  manualVersion,
  newVersion,
  onModeChange,
  onManualVersionChange,
}: Props) {
  const bump = bumpAppVersion(currentVersion, mode, manualVersion);
  const comparison = compareSimpleSemVer(currentVersion, newVersion);
  const warning = bump.warning || (comparison === 0 ? "New version is the same as current version." : undefined);
  const error = comparison === 1 ? "New version is older than current version." : undefined;

  return (
    <section className="studio-step">
      <div>
        <span className="studio-step-index">3</span>
        <h4>Version</h4>
      </div>
      <div className="admin-two-column">
        <label className="admin-field">
          <span>Current version</span>
          <input type="text" value={currentVersion || "-"} readOnly />
        </label>
        <label className="admin-field">
          <span>New version</span>
          <input type="text" value={newVersion} readOnly={mode !== "manual"} onChange={(event) => onManualVersionChange(event.target.value)} />
        </label>
      </div>
      <div className="studio-segmented" role="radiogroup" aria-label="Version bump">
        {MODES.map((candidate) => (
          <button key={candidate} type="button" className={mode === candidate ? "active" : ""} onClick={() => onModeChange(candidate)}>
            {candidate}
          </button>
        ))}
      </div>
      {mode === "manual" ? (
        <label className="admin-field">
          <span>Manual version</span>
          <input type="text" value={manualVersion} placeholder="1.2.4" onChange={(event) => onManualVersionChange(event.target.value)} />
        </label>
      ) : null}
      {warning ? <p className="admin-muted">{warning}</p> : null}
      {error ? <p className="admin-error">{error}</p> : null}
    </section>
  );
}
