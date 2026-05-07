import { AlertTriangle, Eye, EyeOff, FileSearch, RefreshCw, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import {
  appStudioDeletePlan,
  appStudioFullDeleteApply,
  appStudioManagementListApps,
  appStudioManagementSetEnabled,
} from "../../../lib/appStudioApi";
import type { AppStudioDeletePlan, AppStudioFullDeleteResult, AppStudioManagedApp } from "../../../lib/appStudioTypes";

const STATUS_LABELS: Record<string, string> = {
  active: "Active",
  disabled_with_source: "Hidden",
  disabled_stale: "Disabled stale",
  enabled_missing_source: "Enabled, source missing",
  source_missing_from_manifest: "Source missing from manifest",
  invalid_manifest: "Invalid manifest",
};

const STATUS_CLASS: Record<string, string> = {
  active: "ok",
  disabled_with_source: "muted",
  disabled_stale: "warn",
  enabled_missing_source: "danger",
  source_missing_from_manifest: "warn",
  invalid_manifest: "danger",
};

export function AppStudioDeleteManager() {
  const [apps, setApps] = useState<AppStudioManagedApp[]>([]);
  const [selectedPlan, setSelectedPlan] = useState<AppStudioDeletePlan | null>(null);
  const [lastDeleteResult, setLastDeleteResult] = useState<AppStudioFullDeleteResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  useEffect(() => {
    void reload();
  }, []);

  async function reload() {
    setLoading(true);
    setError("");
    try {
      setApps(await appStudioManagementListApps());
      setLastDeleteResult(null);
    } catch (loadError) {
      setError(errorMessage(loadError, "App management data could not be loaded."));
    } finally {
      setLoading(false);
    }
  }

  async function runSetEnabled(app: AppStudioManagedApp, enabled: boolean) {
    setBusy(`${app.appId}:enabled`);
    setError("");
    setMessage("");
    try {
      const result = await appStudioManagementSetEnabled(app.appId, enabled);
      setMessage(result.message);
      setApps(result.apps);
      setLastDeleteResult(null);
      if (selectedPlan?.appId === app.appId) {
        setSelectedPlan(await appStudioDeletePlan(app.appId));
      }
    } catch (actionError) {
      setError(errorMessage(actionError, enabled ? "The app could not be shown." : "The app could not be hidden."));
    } finally {
      setBusy("");
    }
  }

  async function showPlan(app: AppStudioManagedApp) {
    setBusy(`${app.appId}:plan`);
    setError("");
    setMessage("");
    try {
      setSelectedPlan(await appStudioDeletePlan(app.appId));
      setLastDeleteResult(null);
    } catch (planError) {
      setError(errorMessage(planError, "The deletion plan could not be prepared."));
    } finally {
      setBusy("");
    }
  }

  async function runFullDelete(app: AppStudioManagedApp) {
    if (!selectedPlan || selectedPlan.appId !== app.appId) {
      setError("Display the deletion plan before running full delete.");
      return;
    }
    setBusy(`${app.appId}:delete`);
    setError("");
    setMessage("");
    setLastDeleteResult(null);
    try {
      const result = await appStudioFullDeleteApply(app.appId, selectedPlan);
      setApps(result.apps);
      setLastDeleteResult(result);
      if (result.ok) {
        setMessage(result.message);
        setSelectedPlan(null);
      } else {
        setError(fullDeleteFailureMessage(result));
      }
    } catch (deleteError) {
      setError(errorMessage(deleteError, "Full deletion was refused."));
    } finally {
      setBusy("");
    }
  }

  const counts = useMemo(() => {
    return apps.reduce<Record<string, number>>((acc, app) => {
      acc[app.managementStatus] = (acc[app.managementStatus] ?? 0) + 1;
      return acc;
    }, {});
  }, [apps]);

  return (
    <section className="studio-delete">
      <div className="studio-delete-head">
        <div>
          <h4>App management</h4>
          <p>
            The app source of truth is <code>apps/&lt;app_id&gt;/</code>. This tab can hide or show indexed apps and
            run full deletion only after a deletion plan is visible and passes the final safety check.
          </p>
        </div>
        <button className="secondary-button" type="button" onClick={() => void reload()} disabled={loading || !!busy}>
          <RefreshCw size={17} aria-hidden="true" />
          Reload
        </button>
      </div>

      <div className="studio-delete-summary">
        {Object.entries(counts).map(([status, count]) => (
          <span key={status} className={`studio-delete-pill ${STATUS_CLASS[status] ?? "muted"}`}>
            {statusLabel(status)}: {count}
          </span>
        ))}
      </div>

      {message ? <p className="admin-success">{message}</p> : null}
      {error ? (
        <p className="admin-error">
          <AlertTriangle size={16} aria-hidden="true" />
          {error}
        </p>
      ) : null}

      <div className="studio-delete-table-wrap">
        <table className="studio-delete-table">
          <thead>
            <tr>
              <th>Status</th>
              <th>App ID</th>
              <th>Name</th>
              <th>Version</th>
              <th>Enabled</th>
              <th>Source</th>
              <th>App Pack</th>
              <th>Plan</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {apps.map((app) => (
              <tr key={app.appId}>
                <td>
                  <span className={`studio-delete-pill ${STATUS_CLASS[app.managementStatus] ?? "muted"}`}>
                    {statusLabel(app.managementStatus)}
                  </span>
                </td>
                <td>
                  <strong>{app.appId}</strong>
                  {app.warning ? <small>{app.warning}</small> : null}
                </td>
                <td>{app.name}</td>
                <td>{app.version ?? "-"}</td>
                <td>{app.enabled == null ? "-" : app.enabled ? "true" : "false"}</td>
                <td>{app.hasSource ? "yes" : "no"}</td>
                <td>{app.packageExists ? "yes" : "no"}</td>
                <td>
                  <span>{app.deleteTargetCount} targets</span>
                  <small>{app.excludedTargetCount} excluded</small>
                </td>
                <td>
                  <div className="studio-delete-row-actions">
                    {app.enabled ? (
                      <button
                        className="secondary-button"
                        type="button"
                        disabled={busy !== ""}
                        onClick={() => void runSetEnabled(app, false)}
                      >
                        <EyeOff size={15} aria-hidden="true" />
                        Hide
                      </button>
                    ) : app.enabled === false && app.hasSource ? (
                      <button
                        className="primary-button"
                        type="button"
                        disabled={busy !== ""}
                        onClick={() => void runSetEnabled(app, true)}
                      >
                        <Eye size={15} aria-hidden="true" />
                        Show
                      </button>
                    ) : null}
                    <button className="secondary-button" type="button" disabled={busy !== ""} onClick={() => void showPlan(app)}>
                      <FileSearch size={15} aria-hidden="true" />
                      Plan
                    </button>
                    <button
                      className="secondary-button danger-button"
                      type="button"
                      disabled={busy !== "" || !canRunFullDelete(app, selectedPlan)}
                      title={fullDeleteButtonTitle(app, selectedPlan)}
                      onClick={() => void runFullDelete(app)}
                    >
                      <Trash2 size={15} aria-hidden="true" />
                      Delete
                    </button>
                  </div>
                  <small>{app.recommendedAction}</small>
                </td>
              </tr>
            ))}
            {!apps.length && !loading ? (
              <tr>
                <td colSpan={9}>No app management records were found.</td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>

      {selectedPlan ? (
        <DeletionPlanPanel
          plan={selectedPlan}
          busy={busy === `${selectedPlan.appId}:delete`}
          deleteEnabled={canRunFullDelete(apps.find((app) => app.appId === selectedPlan.appId), selectedPlan)}
          onDelete={() => {
            const app = apps.find((candidate) => candidate.appId === selectedPlan.appId);
            if (app) {
              void runFullDelete(app);
            }
          }}
        />
      ) : null}
      {lastDeleteResult ? <FullDeleteResultPanel result={lastDeleteResult} /> : null}
    </section>
  );
}

function DeletionPlanPanel({
  plan,
  busy,
  deleteEnabled,
  onDelete,
}: {
  plan: AppStudioDeletePlan;
  busy: boolean;
  deleteEnabled: boolean;
  onDelete: () => void;
}) {
  return (
    <section className="studio-delete-plan">
      <div className="studio-delete-plan-head">
        <div>
          <h5>Deletion plan: {plan.appId}</h5>
          <p>
            Full delete removes repo-managed targets only. External references, user data, shared runtime folders, and
            staging candidates are excluded. The manifest row means removing only this app entry, not deleting the file.
          </p>
        </div>
        <button className="secondary-button danger-button" type="button" disabled={!deleteEnabled || busy} onClick={onDelete}>
          <Trash2 size={16} aria-hidden="true" />
          {busy ? "Deleting..." : "Run full delete"}
        </button>
      </div>

      <div className="studio-delete-plan-grid">
        <PlanMetric label="Manifest entry" value={plan.manifestEntryExists ? "yes" : "no"} />
        <PlanMetric label="Enabled" value={plan.manifestEnabled == null ? "-" : plan.manifestEnabled ? "true" : "false"} />
        <PlanMetric label="Version" value={plan.manifestVersion ?? "-"} />
        <PlanMetric label="Delete targets" value={String(plan.deleteTargets.length)} />
        <PlanMetric label="Excluded" value={String(plan.excludedTargets.length)} />
        <PlanMetric label="Staging candidates" value={String(plan.stagingCandidatePaths.length)} />
      </div>

      {plan.warnings.length ? (
        <div className="admin-warning">
          {plan.warnings.map((warning) => (
            <div key={warning}>{warning}</div>
          ))}
        </div>
      ) : null}

      {plan.blockingReasons.length ? (
        <div className="admin-error">
          {plan.blockingReasons.map((reason) => (
            <div key={reason}>{reason}</div>
          ))}
        </div>
      ) : null}

      <details open className="admin-details">
        <summary>Delete targets</summary>
        <TargetList targets={plan.deleteTargets} />
      </details>

      <details className="admin-details">
        <summary>Excluded targets</summary>
        <TargetList targets={plan.excludedTargets} />
      </details>
    </section>
  );
}

function FullDeleteResultPanel({ result }: { result: AppStudioFullDeleteResult }) {
  return (
    <section className="studio-delete-plan">
      <div className="studio-delete-plan-head">
        <div>
          <h5>Full delete result: {result.appId}</h5>
          <p>{result.message}</p>
        </div>
        <span className={`studio-delete-pill ${result.ok ? "ok" : "danger"}`}>{result.ok ? "completed" : "needs review"}</span>
      </div>
      <div className="studio-delete-plan-grid">
        <PlanMetric label="Deleted" value={String(result.deleted.length)} />
        <PlanMetric label="Already clean" value={String(result.alreadyClean.length)} />
        <PlanMetric label="Failed" value={String(result.failed.length)} />
        <PlanMetric label="Manifest entry removed" value={result.manifestEntryRemoved ? "yes" : "no"} />
        <PlanMetric label="Remaining targets" value={String(result.postCheckSummary.remainingDeleteTargetCount)} />
      </div>
      {result.failed.length ? (
        <details open className="admin-details">
          <summary>Failed targets</summary>
          <ResultRecordList records={result.failed} />
        </details>
      ) : null}
      <details className="admin-details">
        <summary>Deleted targets</summary>
        <ResultRecordList records={result.deleted} />
      </details>
      <details className="admin-details">
        <summary>Excluded targets preserved</summary>
        <TargetList targets={result.excluded} />
      </details>
    </section>
  );
}

function PlanMetric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function TargetList({ targets }: { targets: AppStudioDeletePlan["deleteTargets"] }) {
  if (!targets.length) {
    return <p className="admin-muted">No targets.</p>;
  }
  return (
    <div className="studio-delete-target-list">
      {targets.map((target) => (
        <div key={`${target.category}:${target.path}:${target.action}`} className="studio-delete-target-row">
          <span className={`studio-delete-pill ${target.deleteAllowed ? "warn" : "muted"}`}>{target.category}</span>
          <div>
            <strong>{target.action}</strong>
            <code>{target.path}</code>
            <small>
              {target.exists ? "exists" : "missing"} / {target.note}
            </small>
          </div>
        </div>
      ))}
    </div>
  );
}

function ResultRecordList({ records }: { records: AppStudioFullDeleteResult["deleted"] }) {
  if (!records.length) {
    return <p className="admin-muted">No records.</p>;
  }
  return (
    <div className="studio-delete-target-list">
      {records.map((record) => (
        <div key={`${record.status}:${record.comparisonKey}`} className="studio-delete-target-row">
          <span className={`studio-delete-pill ${record.status === "failed" ? "danger" : "warn"}`}>{record.status}</span>
          <div>
            <strong>{record.action}</strong>
            <code>{record.path}</code>
            <small>{record.note}</small>
          </div>
        </div>
      ))}
    </div>
  );
}

function statusLabel(status: string): string {
  return STATUS_LABELS[status] ?? status;
}

function canRunFullDelete(app: AppStudioManagedApp | undefined, plan: AppStudioDeletePlan | null): boolean {
  if (!app || !plan || plan.appId !== app.appId) {
    return false;
  }
  const supportedStatuses = new Set(["active", "disabled_with_source", "disabled_stale", "enabled_missing_source"]);
  return (
    supportedStatuses.has(app.managementStatus) &&
    plan.blockingReasons.length === 0 &&
    plan.deleteTargets.some((target) => target.deleteAllowed && target.exists)
  );
}

function fullDeleteButtonTitle(app: AppStudioManagedApp, plan: AppStudioDeletePlan | null): string {
  if (!plan || plan.appId !== app.appId) {
    return "Display the deletion plan before running full delete.";
  }
  if (plan.blockingReasons.length) {
    return "The deletion plan has blocking reasons.";
  }
  if (!canRunFullDelete(app, plan)) {
    return "This app state is not supported for full delete.";
  }
  return "Permanently remove repo-managed targets for this app.";
}

function fullDeleteFailureMessage(result: AppStudioFullDeleteResult): string {
  const failed = result.failed.map((record) => `${record.action}: ${record.note}`).join(" / ");
  const remaining = result.postCheckSummary.remainingDeleteTargets.join(" / ");
  return [result.message, failed ? `Failed: ${failed}` : "", remaining ? `Remaining: ${remaining}` : ""]
    .filter(Boolean)
    .join(" ");
}

function errorMessage(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message) {
    return `${fallback} ${error.message}`;
  }
  if (typeof error === "string" && error.trim()) {
    return `${fallback} ${error}`;
  }
  return fallback;
}
