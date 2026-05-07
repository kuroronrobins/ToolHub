import { AlertTriangle, Archive, Eye, EyeOff, RefreshCw, RotateCcw, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import {
  appStudioLifecycleListApps,
  appStudioLifecycleListBackups,
  appStudioLifecycleRestoreBackup,
  appStudioLifecycleSetEnabled,
  appStudioLifecycleSoftDelete,
} from "../../../lib/appStudioApi";
import type {
  AppStudioLifecycleActionResult,
  AppStudioLifecycleApp,
  AppStudioLifecycleBackup,
} from "../../../lib/appStudioTypes";

const STATUS_LABELS: Record<string, string> = {
  active: "表示中",
  disabled_with_source: "非表示",
  disabled_stale: "sourceなし",
  enabled_missing_source: "危険",
  source_missing_from_manifest: "manifest未登録",
  invalid_manifest: "定義エラー",
};

const STATUS_CLASS: Record<string, string> = {
  active: "ok",
  disabled_with_source: "muted",
  disabled_stale: "warn",
  enabled_missing_source: "danger",
  source_missing_from_manifest: "warn",
  invalid_manifest: "danger",
};

export function AppStudioLifecycleManager() {
  const [apps, setApps] = useState<AppStudioLifecycleApp[]>([]);
  const [backups, setBackups] = useState<AppStudioLifecycleBackup[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<AppStudioLifecycleApp | null>(null);
  const [deleteConfirm, setDeleteConfirm] = useState("");
  const [restoreTarget, setRestoreTarget] = useState<AppStudioLifecycleBackup | null>(null);
  const [restoreConfirm, setRestoreConfirm] = useState("");

  useEffect(() => {
    void reload();
  }, []);

  async function reload() {
    setLoading(true);
    setError("");
    try {
      const [nextApps, nextBackups] = await Promise.all([
        appStudioLifecycleListApps(),
        appStudioLifecycleListBackups(),
      ]);
      setApps(nextApps);
      setBackups(nextBackups);
    } catch (loadError) {
      setError(errorMessage(loadError, "アプリ状態を読み込めませんでした。"));
    } finally {
      setLoading(false);
    }
  }

  async function applyResult(result: AppStudioLifecycleActionResult) {
    setMessage(result.message);
    setApps(result.apps);
    setBackups(await appStudioLifecycleListBackups());
  }

  async function runSetEnabled(app: AppStudioLifecycleApp, enabled: boolean) {
    setBusy(`${app.appId}:enabled`);
    setError("");
    setMessage("");
    try {
      await applyResult(await appStudioLifecycleSetEnabled(app.appId, enabled));
    } catch (actionError) {
      setError(errorMessage(actionError, enabled ? "再表示できませんでした。" : "非表示にできませんでした。"));
    } finally {
      setBusy("");
    }
  }

  async function runSoftDelete() {
    if (!deleteTarget) {
      return;
    }
    setBusy(`${deleteTarget.appId}:delete`);
    setError("");
    setMessage("");
    try {
      await applyResult(await appStudioLifecycleSoftDelete(deleteTarget.appId, deleteConfirm));
      setDeleteTarget(null);
      setDeleteConfirm("");
    } catch (actionError) {
      setError(errorMessage(actionError, "バックアップ付き削除に失敗しました。"));
    } finally {
      setBusy("");
    }
  }

  async function runRestore() {
    if (!restoreTarget) {
      return;
    }
    setBusy(`${restoreTarget.backupId}:restore`);
    setError("");
    setMessage("");
    try {
      await applyResult(await appStudioLifecycleRestoreBackup(restoreTarget.backupId, restoreConfirm));
      setRestoreTarget(null);
      setRestoreConfirm("");
    } catch (actionError) {
      setError(errorMessage(actionError, "復元に失敗しました。"));
    } finally {
      setBusy("");
    }
  }

  const counts = useMemo(() => lifecycleCounts(apps), [apps]);
  const backupsByApp = useMemo(() => {
    const map = new Map<string, AppStudioLifecycleBackup[]>();
    for (const backup of backups) {
      map.set(backup.appId, [...(map.get(backup.appId) ?? []), backup]);
    }
    return map;
  }, [backups]);

  return (
    <section className="studio-lifecycle">
      <div className="studio-lifecycle-head">
        <div>
          <h4>アプリライフサイクル管理MVP</h4>
          <p>非表示、再表示、バックアップ付き削除、復元だけを扱います。完全削除は未実装です。</p>
        </div>
        <button className="secondary-button" type="button" onClick={() => void reload()} disabled={loading || !!busy}>
          <RefreshCw size={17} aria-hidden="true" />
          再読込
        </button>
      </div>

      <div className="studio-lifecycle-summary">
        {Object.entries(counts).map(([status, count]) => (
          <span key={status} className={`studio-lifecycle-pill ${STATUS_CLASS[status] ?? "muted"}`}>
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

      <div className="studio-lifecycle-table-wrap">
        <table className="studio-lifecycle-table">
          <thead>
            <tr>
              <th>状態</th>
              <th>App ID</th>
              <th>表示名</th>
              <th>version</th>
              <th>source</th>
              <th>package</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {apps.map((app) => (
              <LifecycleRow
                key={app.appId}
                app={app}
                backups={backupsByApp.get(app.appId) ?? []}
                busy={busy}
                onSetEnabled={runSetEnabled}
                onDelete={setDeleteTarget}
                onRestore={setRestoreTarget}
              />
            ))}
            {!apps.length && !loading ? (
              <tr>
                <td colSpan={7}>表示できるアプリ状態がありません。</td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>

      {deleteTarget ? (
        <div className="studio-lifecycle-confirm">
          <div>
            <strong>バックアップ付き削除: {deleteTarget.appId}</strong>
            <p>先に `backups/app_lifecycle/` へ保存し、成功した場合だけ `apps/{deleteTarget.appId}/` を退避します。App Pack zip とmanifest entryは削除しません。</p>
          </div>
          <label>
            確認入力
            <input value={deleteConfirm} onChange={(event) => setDeleteConfirm(event.target.value)} placeholder={`DELETE ${deleteTarget.appId}`} />
          </label>
          <div className="studio-lifecycle-actions">
            <button className="secondary-button danger-button" type="button" onClick={() => void runSoftDelete()} disabled={busy !== "" || deleteConfirm.trim() !== `DELETE ${deleteTarget.appId}`}>
              <Archive size={16} aria-hidden="true" />
              バックアップへ退避
            </button>
            <button className="secondary-button" type="button" onClick={() => setDeleteTarget(null)} disabled={busy !== ""}>
              キャンセル
            </button>
          </div>
        </div>
      ) : null}

      <details className="admin-details">
        <summary>復元候補と未実装操作</summary>
        <div className="studio-backup-list">
          {backups.map((backup) => (
            <div key={backup.backupId} className="studio-backup-row">
              <div>
                <strong>{backup.appId}</strong>
                <span>{backup.operation} / {backup.createdAt}</span>
                {backup.restoreBlockedReason ? <small>{backup.restoreBlockedReason}</small> : null}
              </div>
              <button className="secondary-button" type="button" disabled={!backup.restorable || busy !== ""} onClick={() => setRestoreTarget(backup)}>
                <RotateCcw size={16} aria-hidden="true" />
                復元
              </button>
            </div>
          ))}
          {!backups.length ? <p className="admin-muted">復元候補はありません。</p> : null}
        </div>
        <button className="admin-work-card danger" type="button" disabled>
          <Trash2 size={20} aria-hidden="true" />
          <strong>完全削除</strong>
          <span>manifest entry、App Pack zip、backup、ユーザーデータの削除は未実装です。</span>
        </button>
      </details>

      {restoreTarget ? (
        <div className="studio-lifecycle-confirm">
          <div>
            <strong>復元: {restoreTarget.appId}</strong>
            <p>backupの app source を `apps/{restoreTarget.appId}/` へコピーします。復元後は `enabled=false` のままです。</p>
          </div>
          <label>
            確認入力
            <input value={restoreConfirm} onChange={(event) => setRestoreConfirm(event.target.value)} placeholder={`RESTORE ${restoreTarget.appId}`} />
          </label>
          <div className="studio-lifecycle-actions">
            <button className="primary-button" type="button" onClick={() => void runRestore()} disabled={busy !== "" || restoreConfirm.trim() !== `RESTORE ${restoreTarget.appId}`}>
              <RotateCcw size={16} aria-hidden="true" />
              復元する
            </button>
            <button className="secondary-button" type="button" onClick={() => setRestoreTarget(null)} disabled={busy !== ""}>
              キャンセル
            </button>
          </div>
        </div>
      ) : null}
    </section>
  );
}

function LifecycleRow({
  app,
  backups,
  busy,
  onSetEnabled,
  onDelete,
  onRestore,
}: {
  app: AppStudioLifecycleApp;
  backups: AppStudioLifecycleBackup[];
  busy: string;
  onSetEnabled: (app: AppStudioLifecycleApp, enabled: boolean) => Promise<void>;
  onDelete: (app: AppStudioLifecycleApp) => void;
  onRestore: (backup: AppStudioLifecycleBackup) => void;
}) {
  const restorableBackup = backups.find((backup) => backup.restorable);
  const statusClass = STATUS_CLASS[app.lifecycleStatus] ?? "muted";
  const rowBusy = busy.startsWith(`${app.appId}:`);
  return (
    <tr>
      <td>
        <span className={`studio-lifecycle-pill ${statusClass}`}>{statusLabel(app.lifecycleStatus)}</span>
      </td>
      <td>
        <strong>{app.appId}</strong>
        {app.warning ? <small>{app.warning}</small> : null}
      </td>
      <td>{app.name}</td>
      <td>{app.version ?? "-"}</td>
      <td>{app.hasSource ? "あり" : "なし"}</td>
      <td>{app.packageExists ? "あり" : "なし"}</td>
      <td>
        <div className="studio-lifecycle-row-actions">
          {app.lifecycleStatus === "active" ? (
            <>
              <button className="secondary-button" type="button" disabled={rowBusy || busy !== ""} onClick={() => void onSetEnabled(app, false)}>
                <EyeOff size={15} aria-hidden="true" />
                非表示
              </button>
              <button className="secondary-button danger-button" type="button" disabled={rowBusy || busy !== ""} onClick={() => onDelete(app)}>
                <Archive size={15} aria-hidden="true" />
                バックアップ付き削除
              </button>
            </>
          ) : null}
          {app.lifecycleStatus === "disabled_with_source" ? (
            <>
              <button className="primary-button" type="button" disabled={rowBusy || busy !== ""} onClick={() => void onSetEnabled(app, true)}>
                <Eye size={15} aria-hidden="true" />
                再表示
              </button>
              <button className="secondary-button danger-button" type="button" disabled={rowBusy || busy !== ""} onClick={() => onDelete(app)}>
                <Archive size={15} aria-hidden="true" />
                バックアップ付き削除
              </button>
            </>
          ) : null}
          {app.lifecycleStatus === "enabled_missing_source" ? (
            <button className="secondary-button" type="button" disabled={rowBusy || busy !== ""} onClick={() => void onSetEnabled(app, false)}>
              <EyeOff size={15} aria-hidden="true" />
              無効化
            </button>
          ) : null}
          {app.lifecycleStatus === "disabled_stale" ? (
            <button className="secondary-button" type="button" disabled={!restorableBackup || busy !== ""} onClick={() => restorableBackup && onRestore(restorableBackup)}>
              <RotateCcw size={15} aria-hidden="true" />
              復元候補
            </button>
          ) : null}
          {app.lifecycleStatus === "source_missing_from_manifest" || app.lifecycleStatus === "invalid_manifest" ? (
            <button className="secondary-button" type="button" disabled>
              未対応
            </button>
          ) : null}
        </div>
        <small>{app.recommendedAction}</small>
      </td>
    </tr>
  );
}

function lifecycleCounts(apps: AppStudioLifecycleApp[]): Record<string, number> {
  return apps.reduce<Record<string, number>>((counts, app) => {
    counts[app.lifecycleStatus] = (counts[app.lifecycleStatus] ?? 0) + 1;
    return counts;
  }, {});
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
