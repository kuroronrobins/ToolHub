import { Download, ExternalLink, RefreshCw } from "lucide-react";
import { useState } from "react";
import { checkUpdatesRemote, downloadUpdateInstaller, launchVerifiedUpdateInstaller } from "../../lib/api";
import type { UpdateDownloadResult, UpdateItem, UpdateLaunchResult, UpdateSummary } from "../../lib/updateTypes";

const STATUS_LABELS: Record<string, string> = {
  source_not_configured: "更新元未設定",
  no_update: "更新候補なし",
  update_available: "更新候補あり",
  remote_manifest_fetch_failed: "更新情報の取得失敗",
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
  const [downloadResult, setDownloadResult] = useState<UpdateDownloadResult | null>(null);
  const [launchResult, setLaunchResult] = useState<UpdateLaunchResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function checkUpdates() {
    setBusy(true);
    setError("");
    setDownloadResult(null);
    setLaunchResult(null);
    try {
      setSummary(await checkUpdatesRemote());
    } catch (updateError) {
      setError(updateError instanceof Error ? updateError.message : "更新確認に失敗しました。");
    } finally {
      setBusy(false);
    }
  }

  async function downloadInstaller() {
    if (!summary?.installerUrl || !summary.installerSha256) {
      return;
    }
    setBusy(true);
    setError("");
    setLaunchResult(null);
    try {
      setDownloadResult(
        await downloadUpdateInstaller({
          manifestUrl: summary.remoteManifestUrl ?? summary.updateSourceUrl ?? null,
          installerUrl: summary.installerUrl,
          installerFile: summary.installerFile ?? null,
          expectedSha256: summary.installerSha256,
          expectedSize: summary.installerSize ?? null,
        }),
      );
    } catch (downloadError) {
      setError(downloadError instanceof Error ? downloadError.message : "installer download failed.");
    } finally {
      setBusy(false);
    }
  }

  async function launchInstaller() {
    if (!downloadResult?.verified || !downloadResult.cachePath || !summary?.installerSha256) {
      return;
    }
    setBusy(true);
    setError("");
    try {
      setLaunchResult(
        await launchVerifiedUpdateInstaller({
          cachePath: downloadResult.cachePath,
          expectedSha256: summary.installerSha256,
        }),
      );
    } catch (launchError) {
      setError(launchError instanceof Error ? launchError.message : "installer launch failed.");
    } finally {
      setBusy(false);
    }
  }

  const canDownload = Boolean(summary?.installerUrl && summary.installerSha256 && !busy);
  const canLaunch = Boolean(downloadResult?.verified && downloadResult.cachePath && summary?.installerSha256 && !busy);

  return (
    <section className="admin-panel-section">
      <div className="admin-section-head">
        <div>
          <p className="dialog-kicker">配布と更新</p>
          <h3>更新確認とインストーラー管理</h3>
        </div>
        <span className="admin-status-pill">Shell</span>
      </div>
      <div className="admin-card-grid">
        <button className="admin-work-card" type="button" onClick={() => void checkUpdates()} disabled={busy}>
          <RefreshCw size={22} aria-hidden="true" />
          <strong>{busy ? "確認中" : "更新確認"}</strong>
          <span>配布元の更新情報を取得し、現在versionと比較します。</span>
        </button>
        <button className="admin-work-card" type="button" onClick={() => void downloadInstaller()} disabled={!canDownload}>
          <Download size={22} aria-hidden="true" />
          <strong>installer取得</strong>
          <span>update_cacheへ保存し、配布元のsha256で検証します。</span>
        </button>
        <button className="admin-work-card danger" type="button" onClick={() => void launchInstaller()} disabled={!canLaunch}>
          <ExternalLink size={22} aria-hidden="true" />
          <strong>installer起動</strong>
          <span>sha256検証済みのToolHub_Setup.exeだけを起動します。必要に応じてToolHubを閉じてください。</span>
        </button>
      </div>
      {summary ? (
        <>
        <div className={`admin-image-test-result ${summary.status === "no_update" ? "ok" : "warn"}`}>
          <div><span>status</span><strong>{statusLabel(summary.status)}</strong></div>
          <div><span>current version</span><strong>{summary.currentVersion ?? "-"}</strong></div>
          <div><span>local manifest version</span><strong>{summary.localManifestVersion ?? "-"}</strong></div>
          <div><span>remote manifest version</span><strong>{summary.remoteManifestVersion ?? "-"}</strong></div>
          <div><span>update source configured</span><strong>{summary.updateSourceConfigured ? "設定済み" : "未設定"}</strong></div>
          <div><span>update source URL</span><strong>{summary.updateSourceUrl ?? "-"}</strong></div>
          <div><span>config source</span><strong>{configSourceLabel(summary.configSource)}</strong></div>
          <div className="wide"><span>remote manifest URL</span><strong>{summary.remoteManifestUrl ?? "-"}</strong></div>
          <div className="wide"><span>installer URL</span><strong>{summary.installerUrl ?? "-"}</strong></div>
          <div className="wide"><span>installer sha256</span><strong>{summary.installerSha256 ?? "-"}</strong></div>
          <div className="wide"><span>update cache</span><strong>{summary.updateCachePath ?? "-"}</strong></div>
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
        {downloadResult || launchResult ? (
          <details className="admin-details" open>
            <summary>installer update operation</summary>
            <div className="version-list">
              {downloadResult ? (
                <>
                  <div className="version-row"><span>download status</span><strong>{downloadResult.status}</strong></div>
                  <div className="version-row"><span>source kind</span><strong>{downloadResult.sourceKind}</strong></div>
                  <div className="version-row"><span>verified</span><strong>{downloadResult.verified ? "yes" : "no"}</strong></div>
                  <div className="version-row"><span>size</span><strong>{downloadResult.actualSize ?? "-"}</strong></div>
                  <div className="version-row"><span>sha256</span><strong>{downloadResult.actualSha256 ?? "-"}</strong></div>
                  <div className="version-row"><span>cache</span><strong>{downloadResult.cachePath ?? "-"}</strong></div>
                  <div className="version-row"><span>failure reason</span><strong>{downloadResult.failureReason ?? "-"}</strong></div>
                  <div className="version-row"><span>message</span><strong>{downloadResult.message}</strong></div>
                </>
              ) : null}
              {launchResult ? (
                <>
                  <div className="version-row"><span>launch status</span><strong>{launchResult.status}</strong></div>
                  <div className="version-row"><span>source kind</span><strong>{launchResult.sourceKind}</strong></div>
                  <div className="version-row"><span>verified</span><strong>{launchResult.verified ? "yes" : "no"}</strong></div>
                  <div className="version-row"><span>failure reason</span><strong>{launchResult.failureReason ?? "-"}</strong></div>
                  <div className="version-row"><span>message</span><strong>{launchResult.message}</strong></div>
                </>
              ) : null}
            </div>
          </details>
        ) : null}
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
