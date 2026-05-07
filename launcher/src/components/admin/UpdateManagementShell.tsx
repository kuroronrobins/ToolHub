import { PackageCheck, RefreshCw, UploadCloud } from "lucide-react";
import { useState } from "react";
import { checkUpdatesMvp } from "../../lib/api";
import type { UpdateSummary } from "../../lib/updateTypes";

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
        <div className="admin-image-test-result">
          <div><span>status</span><strong>{summary.status}</strong></div>
          <div><span>current</span><strong>{summary.currentVersion ?? "-"}</strong></div>
          <div><span>manifest</span><strong>{summary.localManifestVersion ?? "-"}</strong></div>
          <div><span>source</span><strong>{summary.updateSourceConfigured ? summary.updateSourceUrl ?? "configured" : "not configured"}</strong></div>
          <div className="wide"><span>message</span><strong>{summary.message}</strong></div>
        </div>
      ) : null}
      {error ? <p className="admin-error">{error}</p> : null}
    </section>
  );
}
