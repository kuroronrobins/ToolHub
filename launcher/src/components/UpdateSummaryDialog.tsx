import { Download, ExternalLink, Loader2, X } from "lucide-react";
import { useState } from "react";
import { downloadUpdateInstaller, launchVerifiedUpdateInstaller } from "../lib/api";
import type { UpdateDownloadResult, UpdateItem, UpdateLaunchResult, UpdateSummary } from "../lib/updateTypes";

const UNSUPPORTED_ACTION_LABELS: Record<string, string> = {
  download: "ダウンロード",
  extract: "展開",
  replace: "置換",
  backup: "バックアップ",
  rollback: "ロールバック",
  signature_verification: "署名検証",
};

const CONFIG_SOURCE_LABELS: Record<string, string> = {
  user: "ユーザー設定",
  default: "default設定",
  missing: "未確認",
};

interface Props {
  summary: UpdateSummary | null;
  onClose: () => void;
}

function VersionRow({ item }: { item: UpdateItem }) {
  return (
    <div className="version-row">
      <span>{item.label}</span>
      <strong>
        {item.currentVersion} -&gt; {item.nextVersion}
      </strong>
    </div>
  );
}

export function UpdateSummaryDialog({ summary, onClose }: Props) {
  const [busy, setBusy] = useState<"download" | "launch" | null>(null);
  const [downloadResult, setDownloadResult] = useState<UpdateDownloadResult | null>(null);
  const [launchResult, setLaunchResult] = useState<UpdateLaunchResult | null>(null);
  const [error, setError] = useState("");

  if (!summary) {
    return null;
  }

  const canDownload = Boolean(summary.installerUrl && summary.installerSha256 && !busy);
  const canLaunch = Boolean(downloadResult?.verified && downloadResult.cachePath && summary.installerSha256 && !busy);
  const targetVersion = updateTargetVersion(summary);
  const userNotes = summary.releaseNotes?.user;
  const adminNotes = summary.releaseNotes?.admin;
  const userTitle = cleanText(userNotes?.title) || summary.title;
  const userSummary = cleanText(userNotes?.summary) || summary.message;
  const highlights = cleanList(userNotes?.highlights);
  const addedApps = cleanList(userNotes?.addedApps);

  async function handleDownload() {
    if (!summary?.installerUrl || !summary.installerSha256) {
      setError("更新ファイルの情報が不足しています。管理者に確認してください。");
      return;
    }
    setBusy("download");
    setError("");
    setLaunchResult(null);
    try {
      const result = await downloadUpdateInstaller({
        manifestUrl: summary.remoteManifestUrl ?? summary.updateSourceUrl ?? null,
        installerUrl: summary.installerUrl,
        installerFile: summary.installerFile ?? null,
        expectedSha256: summary.installerSha256,
        expectedSize: summary.installerSize ?? null,
      });
      setDownloadResult(result);
      if (!result.verified) {
        setError("更新ファイルを確認できませんでした。既存のToolHubは変更されていません。");
      }
    } catch (downloadError) {
      setError(downloadError instanceof Error ? downloadError.message : "更新ファイルを取得できませんでした。");
    } finally {
      setBusy(null);
    }
  }

  async function handleLaunch() {
    if (!downloadResult?.verified || !downloadResult.cachePath || !summary?.installerSha256) {
      setError("検証済みの更新ファイルがありません。先に更新を取得してください。");
      return;
    }
    setBusy("launch");
    setError("");
    try {
      const result = await launchVerifiedUpdateInstaller({
        cachePath: downloadResult.cachePath,
        expectedSha256: summary.installerSha256,
        targetVersion,
      });
      setLaunchResult(result);
      if (!result.ok) {
        setError("更新の開始に失敗しました。既存のToolHubは変更されていません。");
      }
    } catch (launchError) {
      setError(launchError instanceof Error ? launchError.message : "更新を開始できませんでした。");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="dialog-backdrop" role="presentation" onMouseDown={onClose}>
      <section className="dialog-panel compact" role="dialog" aria-modal="true" aria-labelledby="update-title" onMouseDown={(event) => event.stopPropagation()}>
        <header className="dialog-header">
          <div>
            <p className="dialog-kicker">更新</p>
            <h2 id="update-title">{userTitle}</h2>
          </div>
          <button className="icon-button" type="button" onClick={onClose} title="閉じる">
            <X size={20} aria-hidden="true" />
          </button>
        </header>

        <section className="detail-section">
          <h3>今回の更新</h3>
          <p>{userSummary}</p>
          {highlights.length ? (
            <ul className="update-highlight-list">
              {highlights.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          ) : null}
          {addedApps.length ? (
            <div className="update-added-apps">
              <strong>追加されたアプリ</strong>
              <div>
                {addedApps.map((item) => (
                  <span key={item}>{item}</span>
                ))}
              </div>
            </div>
          ) : null}
          <div className="version-list">
            <div className="version-row">
              <span>現在のToolHub</span>
              <strong>{summary.currentVersion ?? "-"}</strong>
            </div>
            <div className="version-row">
              <span>配布元のバージョン</span>
              <strong>{summary.remoteManifestVersion ?? summary.localManifestVersion ?? "未確認"}</strong>
            </div>
          </div>
          <div className="update-action-panel">
            <button className="primary-button" type="button" onClick={() => void handleDownload()} disabled={!canDownload}>
              {busy === "download" ? <Loader2 className="spin" size={17} aria-hidden="true" /> : <Download size={17} aria-hidden="true" />}
              更新を取得
            </button>
            <button className="secondary-button" type="button" onClick={() => void handleLaunch()} disabled={!canLaunch}>
              {busy === "launch" ? <Loader2 className="spin" size={17} aria-hidden="true" /> : <ExternalLink size={17} aria-hidden="true" />}
              更新を開始
            </button>
          </div>
          <p className="update-guidance-text">更新を開始したら、画面の案内に従ってToolHubを閉じてください。設定やログは保持されます。</p>
          {downloadResult ? (
            <p className={downloadResult.verified ? "admin-success" : "admin-warning"}>
              {downloadResult.verified ? "更新ファイルを確認しました。更新を開始できます。" : "更新ファイルの確認に失敗しました。"}
            </p>
          ) : null}
          {launchResult?.ok ? (
            <p className="admin-success">
              更新インストーラーを起動しました。次回起動時にversion {launchResult.targetVersion ?? targetVersion ?? "-"} を確認します。
            </p>
          ) : null}
          {error ? <p className="admin-error">{error}</p> : null}
        </section>

        <details className="admin-details">
          <summary>管理者向け詳細</summary>
          <div className="version-list">
            {summary.core ? <VersionRow item={summary.core} /> : null}
            {summary.runner ? <VersionRow item={summary.runner} /> : null}
            {summary.apps.map((item) => (
              <VersionRow key={item.label} item={item} />
            ))}
            {summary.runtimeUpdate ? <div className="version-row"><span>Web自動化用ランタイム</span><strong>更新あり</strong></div> : null}
            {!summary.core && !summary.runner && !summary.apps.length && !summary.runtimeUpdate ? (
              <div className="version-row"><span>更新候補</span><strong>なし</strong></div>
            ) : null}
            <div className="version-row"><span>設定種別</span><strong>{summary.configSource ? CONFIG_SOURCE_LABELS[summary.configSource] ?? summary.configSource : "-"}</strong></div>
            <div className="version-row"><span>設定ファイル</span><strong>{summary.configPath ?? "-"}</strong></div>
            <div className="version-row"><span>remote manifest</span><strong>{summary.remoteManifestUrl ?? "-"}</strong></div>
            <div className="version-row"><span>installer</span><strong>{summary.installerUrl ?? "-"}</strong></div>
            <div className="version-row"><span>installer sha256</span><strong>{summary.installerSha256 ?? "-"}</strong></div>
            <div className="version-row"><span>manifest</span><strong>{summary.localManifestPath ?? "-"}</strong></div>
            <div className="version-row"><span>app manifest</span><strong>{summary.appManifestPath ?? "-"}</strong></div>
          </div>
          {summary.notes?.length ? (
            <ul className="update-note-list">
              {summary.notes.map((note) => (
                <li key={note}>{note}</li>
              ))}
            </ul>
          ) : null}
          {summary.unsupportedActions?.length ? (
            <p className="admin-muted">未実装: {summary.unsupportedActions.map((action) => UNSUPPORTED_ACTION_LABELS[action] ?? action).join("、")}</p>
          ) : null}
          {adminNotes ? (
            <div className="admin-release-notes">
              {adminNotes.summary ? <p>{adminNotes.summary}</p> : null}
              {adminNotes.changes?.length ? (
                <>
                  <strong>changes</strong>
                  <ul className="update-note-list">
                    {adminNotes.changes.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                </>
              ) : null}
              {adminNotes.validation?.length ? (
                <>
                  <strong>validation</strong>
                  <ul className="update-note-list">
                    {adminNotes.validation.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                </>
              ) : null}
            </div>
          ) : null}
        </details>
      </section>
    </div>
  );
}

function updateTargetVersion(summary: UpdateSummary): string | null {
  return summary.remoteManifestVersion ?? summary.core?.nextVersion ?? null;
}

function cleanText(value?: string | null): string {
  return value?.trim() ?? "";
}

function cleanList(values?: string[] | null): string[] {
  return (values ?? []).map((value) => value.trim()).filter(Boolean).slice(0, 6);
}

