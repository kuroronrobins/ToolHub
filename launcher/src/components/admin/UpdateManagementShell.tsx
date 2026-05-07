import { PackageCheck, RefreshCw, UploadCloud } from "lucide-react";
import { useState } from "react";
import { checkUpdatesMvp } from "../../lib/api";
import type { UpdateItem, UpdateSummary } from "../../lib/updateTypes";

const STATUS_LABELS: Record<string, string> = {
  source_not_configured: "更新元未設定",
  no_update: "更新候補なし",
  update_available: "更新候補あり",
};

const CONFIG_SOURCE_LABELS: Record<string, string> = {
  user: "ユーザー設定",
  default: "default設定",
  missing: "未確認",
};

const UNSUPPORTED_ACTION_LABELS: Record<string, string> = {
  download: "ダウンロード",
  extract: "展開",
  replace: "置換",
  backup: "バックアップ",
  rollback: "ロールバック",
  signature_verification: "署名検証",
};

export function UpdateManagementShell() {
  const [summary, setSummary] = useState<UpdateSummary | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function checkUpdates() {
    setBusy(true);
    setError("");
    try {
      setSummary(await checkUpdatesMvp());
    } catch (updateError) {
      setError(updateError instanceof Error ? updateError.message : "更新確認に失敗しました。");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="admin-panel-section">
      <div className="admin-section-head">
        <div>
          <p className="dialog-kicker">更新管理</p>
          <h3>配布と更新の確認</h3>
        </div>
        <span className="admin-status-pill">Shell</span>
      </div>
      <div className="admin-card-grid">
        <button className="admin-work-card" type="button" onClick={() => void checkUpdates()} disabled={busy}>
          <RefreshCw size={22} aria-hidden="true" />
          <strong>{busy ? "確認中" : "更新確認MVP"}</strong>
          <span>ローカルmanifestと更新元URLの設定を読み取ります。ダウンロードや適用は行いません。</span>
        </button>
        <button className="admin-work-card" type="button" disabled>
          <PackageCheck size={22} aria-hidden="true" />
          <strong>App Pack確認</strong>
          <span>App Pack の整合性確認に接続予定</span>
        </button>
        <button className="admin-work-card danger" type="button" disabled>
          <UploadCloud size={22} aria-hidden="true" />
          <strong>publish準備</strong>
          <span>将来は再認証を必須にする操作</span>
        </button>
      </div>
      {summary ? (
        <>
        <div className={`admin-image-test-result ${summary.status === "no_update" ? "ok" : "warn"}`}>
          <div><span>status</span><strong>{statusLabel(summary.status)}</strong></div>
          <div><span>current version</span><strong>{summary.currentVersion ?? "-"}</strong></div>
          <div><span>local manifest version</span><strong>{summary.localManifestVersion ?? "-"}</strong></div>
          <div><span>update source configured</span><strong>{summary.updateSourceConfigured ? "設定済み" : "未設定"}</strong></div>
          <div><span>update source URL</span><strong>{summary.updateSourceUrl ?? "-"}</strong></div>
          <div><span>config source</span><strong>{configSourceLabel(summary.configSource)}</strong></div>
          <div className="wide"><span>config path</span><strong>{summary.configPath ?? "-"}</strong></div>
          <div className="wide"><span>local manifest path</span><strong>{summary.localManifestPath ?? "-"}</strong></div>
          <div className="wide"><span>app manifest path</span><strong>{summary.appManifestPath ?? "-"}</strong></div>
          <div className="wide"><span>message</span><strong>{summary.message}</strong></div>
        </div>
        <details className="admin-details">
          <summary>更新候補</summary>
          <div className="version-list">
            {summary.core ? <UpdateCandidateRow item={summary.core} /> : null}
            {summary.runner ? <UpdateCandidateRow item={summary.runner} /> : null}
            {summary.apps.map((item) => (
              <UpdateCandidateRow key={item.label} item={item} />
            ))}
            {summary.runtimeUpdate ? <div className="version-row"><span>Web自動化用ランタイム</span><strong>更新あり</strong></div> : null}
            {!summary.core && !summary.runner && !summary.apps.length && !summary.runtimeUpdate ? (
              <div className="version-row"><span>更新候補</span><strong>なし</strong></div>
            ) : null}
          </div>
        </details>
        <details className="admin-details">
          <summary>確認メモと未実装操作</summary>
          {summary.notes?.length ? (
            <ul className="update-note-list">
              {summary.notes.map((note) => (
                <li key={note}>{note}</li>
              ))}
            </ul>
          ) : (
            <p className="admin-muted">追加メモはありません。</p>
          )}
          {summary.unsupportedActions?.length ? (
            <p className="admin-muted">未実装: {summary.unsupportedActions.map((action) => UNSUPPORTED_ACTION_LABELS[action] ?? action).join("、")}</p>
          ) : null}
        </details>
        </>
      ) : null}
      {error ? <p className="admin-error">{error}</p> : null}
    </section>
  );
}

function UpdateCandidateRow({ item }: { item: UpdateItem }) {
  return (
    <div className="version-row">
      <span>{item.label}</span>
      <strong>
        {item.currentVersion} -&gt; {item.nextVersion}
      </strong>
    </div>
  );
}

function statusLabel(status: UpdateSummary["status"]): string {
  if (!status) {
    return "-";
  }
  return STATUS_LABELS[status] ?? status;
}

function configSourceLabel(source: UpdateSummary["configSource"]): string {
  if (!source) {
    return "-";
  }
  return CONFIG_SOURCE_LABELS[source] ?? source;
}
