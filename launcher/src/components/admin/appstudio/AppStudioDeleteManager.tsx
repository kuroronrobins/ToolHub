import { AlertTriangle, Eye, EyeOff, FileSearch, RefreshCw, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import {
  appStudioDeletePlan,
  appStudioManagementListApps,
  appStudioManagementSetEnabled,
} from "../../../lib/appStudioApi";
import type { AppStudioDeletePlan, AppStudioManagedApp } from "../../../lib/appStudioTypes";

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
    } catch (planError) {
      setError(errorMessage(planError, "The deletion plan could not be prepared."));
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
            display a deletion plan. Full deletion is not implemented here yet.
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
                      disabled
                      title="Full deletion will be implemented only after deletion plans are validated."
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

      {selectedPlan ? <DeletionPlanPanel plan={selectedPlan} /> : null}
    </section>
  );
}

function DeletionPlanPanel({ plan }: { plan: AppStudioDeletePlan }) {
  return (
    <section className="studio-delete-plan">
      <div className="studio-delete-plan-head">
        <div>
          <h5>Deletion plan: {plan.appId}</h5>
          <p>
            Execution is not implemented. External references, user data, and shared runtime folders are listed as
            excluded targets.
          </p>
        </div>
        <button className="secondary-button danger-button" type="button" disabled>
          <Trash2 size={16} aria-hidden="true" />
          Full deletion is not implemented
        </button>
      </div>

      <div className="studio-delete-plan-grid">
        <PlanMetric label="Manifest entry" value={plan.manifestEntryExists ? "yes" : "no"} />
        <PlanMetric label="Enabled" value={plan.manifestEnabled == null ? "-" : plan.manifestEnabled ? "true" : "false"} />
        <PlanMetric label="Version" value={plan.manifestVersion ?? "-"} />
        <PlanMetric label="Delete targets" value={String(plan.deleteTargets.length)} />
        <PlanMetric label="Excluded" value={String(plan.excludedTargets.length)} />
      </div>

      {plan.warnings.length ? (
        <div className="admin-warning">
          {plan.warnings.map((warning) => (
            <div key={warning}>{warning}</div>
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

function statusLabel(status: string): string {
  return STATUS_LABELS[status] ?? status;
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
