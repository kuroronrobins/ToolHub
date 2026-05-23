import { CheckCircle2, CircleAlert, FileCheck2, FolderCheck, Hammer, Loader2, PlayCircle, RefreshCw, ShieldCheck, TriangleAlert, UploadCloud } from "lucide-react";
import { useState } from "react";
import { appStudioPublishBuildVerify, appStudioPublishDryRun, appStudioPublishPreflight, appStudioPublishPrepareTarget, appStudioPublishRelease, appStudioPublishRemoteVerify } from "../../../lib/appStudioApi";
import type { AppStudioPublishAsset, AppStudioPublishCheck, AppStudioPublishPreflightResult, AppStudioPublishRunResult, AppStudioRemoteVerificationCheck, AppStudioRemoteVerificationReport } from "../../../lib/appStudioTypes";
import { formatAdminError } from "../adminUi";

export function AppStudioPublishPanel() {
  const [result, setResult] = useState<AppStudioPublishPreflightResult | null>(null);
  const [dryRunResult, setDryRunResult] = useState<AppStudioPublishRunResult | null>(null);
  const [prepareTargetResult, setPrepareTargetResult] = useState<AppStudioPublishRunResult | null>(null);
  const [buildVerifyResult, setBuildVerifyResult] = useState<AppStudioPublishRunResult | null>(null);
  const [remoteVerifyResult, setRemoteVerifyResult] = useState<AppStudioPublishRunResult | null>(null);
  const [publishResult, setPublishResult] = useState<AppStudioPublishRunResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [dryRunBusy, setDryRunBusy] = useState(false);
  const [prepareTargetBusy, setPrepareTargetBusy] = useState(false);
  const [buildVerifyBusy, setBuildVerifyBusy] = useState(false);
  const [remoteVerifyBusy, setRemoteVerifyBusy] = useState(false);
  const [publishBusy, setPublishBusy] = useState(false);
  const [downloadInstallerForVerify, setDownloadInstallerForVerify] = useState(false);
  const [confirmPublish, setConfirmPublish] = useState(false);
  const [allowDirty, setAllowDirty] = useState(false);
  const [allowExistingRelease, setAllowExistingRelease] = useState(false);
  const [updateManifestInstallerUrl, setUpdateManifestInstallerUrl] = useState(false);
  const [draft, setDraft] = useState(false);
  const [prerelease, setPrerelease] = useState(false);
  const [downloadInstallerAfterPublish, setDownloadInstallerAfterPublish] = useState(false);
  const [releaseNotes, setReleaseNotes] = useState("");
  const [error, setError] = useState("");

  async function runPreflight() {
    setBusy(true);
    setError("");
    try {
      setResult(await appStudioPublishPreflight());
    } catch (preflightError) {
      setError(formatAdminError(preflightError, "公開準備の確認に失敗しました。"));
    } finally {
      setBusy(false);
    }
  }

  async function runDryRun() {
    setDryRunBusy(true);
    setError("");
    try {
      const nextResult = await appStudioPublishDryRun();
      setDryRunResult(nextResult);
      setResult(nextResult.preflight);
    } catch (dryRunError) {
      setError(formatAdminError(dryRunError, "公開 dry-run に失敗しました。"));
    } finally {
      setDryRunBusy(false);
    }
  }

  async function runPrepareTarget() {
    setPrepareTargetBusy(true);
    setError("");
    try {
      const nextResult = await appStudioPublishPrepareTarget();
      setPrepareTargetResult(nextResult);
      setResult(nextResult.preflight);
    } catch (targetError) {
      setError(formatAdminError(targetError, "リリース対象フォルダの作成に失敗しました。"));
    } finally {
      setPrepareTargetBusy(false);
    }
  }

  async function runBuildVerify() {
    setBuildVerifyBusy(true);
    setError("");
    try {
      const nextResult = await appStudioPublishBuildVerify();
      setBuildVerifyResult(nextResult);
      setResult(nextResult.preflight);
    } catch (buildError) {
      setError(formatAdminError(buildError, "release build / verify に失敗しました。"));
    } finally {
      setBuildVerifyBusy(false);
    }
  }

  async function runRemoteVerify() {
    setRemoteVerifyBusy(true);
    setError("");
    try {
      const nextResult = await appStudioPublishRemoteVerify({
        manifestUrl: result?.updateManifestUrl ?? result?.latestManifestUrl ?? null,
        expectedVersion: result?.version ?? null,
        downloadInstaller: downloadInstallerForVerify,
      });
      setRemoteVerifyResult(nextResult);
      setResult(nextResult.preflight);
    } catch (verifyError) {
      setError(formatAdminError(verifyError, "remote manifest の確認に失敗しました。"));
    } finally {
      setRemoteVerifyBusy(false);
    }
  }

  async function runPublishRelease() {
    setPublishBusy(true);
    setError("");
    try {
      const nextResult = await appStudioPublishRelease({
        confirmPublish,
        allowDirty,
        allowExistingRelease,
        updateManifestInstallerUrl,
        draft,
        prerelease,
        downloadInstallerForRemoteVerify: downloadInstallerAfterPublish,
        releaseNotes: releaseNotes.trim() ? releaseNotes : null,
      });
      setPublishResult(nextResult);
      setResult(nextResult.preflight);
    } catch (publishError) {
      setError(formatAdminError(publishError, "GitHub Release の公開に失敗しました。"));
    } finally {
      setPublishBusy(false);
    }
  }

  const anyBusy = busy || dryRunBusy || prepareTargetBusy || buildVerifyBusy || remoteVerifyBusy || publishBusy;
  const canPublish = confirmPublish && !anyBusy;
  const uploadAssets = result?.releaseTargetAssets?.filter((asset) => asset.upload) ?? [];
  const releaseTargetReady = uploadAssets.length > 0 && uploadAssets.every((asset) => asset.targetExists);
  const publishReadiness = [
    {
      label: "preflight",
      ok: result?.ok === true,
      message: result ? (result.ok ? "公開前チェックは失敗なしです。" : "公開前チェックに失敗項目があります。") : "公開前確認をまだ実行していません。",
    },
    {
      label: "dry-run",
      ok: dryRunResult?.ok === true,
      message: dryRunResult ? (dryRunResult.ok ? "publish dry-run は通過済みです。" : "publish dry-run が失敗しています。") : "publish dry-run は未実行です。",
    },
    {
      label: "target folder",
      ok: releaseTargetReady,
      message: result
        ? releaseTargetReady
          ? "GitHub Release に載せる対象フォルダを確認できます。"
          : "publish target作成で、upload対象ファイルだけをまとめたフォルダを作成してください。"
        : "リリース対象フォルダは未確認です。",
    },
    {
      label: "build / verify",
      ok: buildVerifyResult?.ok === true,
      message: buildVerifyResult ? (buildVerifyResult.ok ? "release build / verify は通過済みです。" : "release build / verify が失敗しています。") : "release build / verify は未実行です。",
    },
    {
      label: "dirty tree",
      ok: !result?.dirtyFiles?.length || allowDirty,
      message: result?.dirtyFiles?.length
        ? allowDirty
          ? "dirty tree を明示許可しています。分類を確認してください。"
          : "未コミット変更があります。実 publish は script 側でも -AllowDirty が必要です。"
        : result
          ? "未コミット変更はありません。"
          : "未コミット変更は未確認です。",
    },
  ];

  return (
    <section className="admin-panel-section nested-section">
      <div className="admin-section-head">
        <div>
          <p className="dialog-kicker">公開準備</p>
          <h3>GitHub Release 配布前確認</h3>
        </div>
        <span className={`admin-status-pill ${result?.ok ? "ok" : ""}`}>{result ? (result.ok ? "Ready" : "Review") : "Not checked"}</span>
      </div>

      <div className="admin-card-grid">
        <button className="admin-work-card" type="button" onClick={() => void runPreflight()} disabled={anyBusy}>
          {busy ? <Loader2 className="studio-spinner" size={22} aria-hidden="true" /> : <RefreshCw size={22} aria-hidden="true" />}
          <strong>{busy ? "確認中" : "公開前確認"}</strong>
          <span>manifest、installer、GitHub remote、readiness reportを読み取り専用で確認します。</span>
        </button>
        <button className="admin-work-card" type="button" onClick={() => void runDryRun()} disabled={anyBusy}>
          {dryRunBusy ? <Loader2 className="studio-spinner" size={22} aria-hidden="true" /> : <PlayCircle size={22} aria-hidden="true" />}
          <strong>{dryRunBusy ? "dry-run中" : "publish dry-run"}</strong>
          <span>build、verify、tag、uploadをスキップし、公開scriptの事前判定だけを実行します。</span>
        </button>
        <button className="admin-work-card" type="button" onClick={() => void runPrepareTarget()} disabled={anyBusy}>
          {prepareTargetBusy ? <Loader2 className="studio-spinner" size={22} aria-hidden="true" /> : <FolderCheck size={22} aria-hidden="true" />}
          <strong>{prepareTargetBusy ? "作成中" : "publish target作成"}</strong>
          <span>GitHub Releaseへuploadするファイルだけを確認用フォルダにまとめます。</span>
        </button>
        <button className="admin-work-card" type="button" onClick={() => void runBuildVerify()} disabled={anyBusy}>
          {buildVerifyBusy ? <Loader2 className="studio-spinner" size={22} aria-hidden="true" /> : <Hammer size={22} aria-hidden="true" />}
          <strong>{buildVerifyBusy ? "build/verify中" : "release build / verify"}</strong>
          <span>runtime必須で release build を実行し、installer、App Pack、runtime を strict 検証します。</span>
        </button>
        <button className="admin-work-card" type="button" onClick={() => void runRemoteVerify()} disabled={anyBusy}>
          {remoteVerifyBusy ? <Loader2 className="studio-spinner" size={22} aria-hidden="true" /> : <ShieldCheck size={22} aria-hidden="true" />}
          <strong>{remoteVerifyBusy ? "確認中" : "remote verify"}</strong>
          <span>公開済み manifest を取得し、version、installer URL、sha256、sizeを確認します。</span>
        </button>
        <button className="admin-work-card danger" type="button" onClick={() => void runPublishRelease()} disabled={!canPublish}>
          {publishBusy ? <Loader2 className="studio-spinner" size={22} aria-hidden="true" /> : <UploadCloud size={22} aria-hidden="true" />}
          <strong>{publishBusy ? "公開中" : "GitHub publish"}</strong>
          <span>build、verify、tag、Release作成、asset upload、remote verifyを実行します。</span>
        </button>
        <div className="admin-work-card static">
          <FileCheck2 size={22} aria-hidden="true" />
          <strong>publish command</strong>
          <span>実公開は .\scripts\publish_github_release.ps1 を明示実行します。dirty tree は既定で拒否します。</span>
        </div>
      </div>
      <label className="admin-toggle">
        <input
          type="checkbox"
          checked={downloadInstallerForVerify}
          disabled={anyBusy}
          onChange={(event) => setDownloadInstallerForVerify(event.currentTarget.checked)}
        />
        remote verify で installer も取得して sha256 を確認する
      </label>
      <details className="admin-details" open>
        <summary>実 publish options</summary>
        <PublishReadinessChecklist items={publishReadiness} />
        <div className="admin-two-column">
          <label className="admin-toggle">
            <input type="checkbox" checked={confirmPublish} disabled={anyBusy} onChange={(event) => setConfirmPublish(event.currentTarget.checked)} />
            GitHub Release への公開を実行する
          </label>
          <label className="admin-toggle">
            <input type="checkbox" checked={allowDirty} disabled={anyBusy} onChange={(event) => setAllowDirty(event.currentTarget.checked)} />
            dirty tree での publish を許可
          </label>
          <label className="admin-toggle">
            <input type="checkbox" checked={allowExistingRelease} disabled={anyBusy} onChange={(event) => setAllowExistingRelease(event.currentTarget.checked)} />
            既存 Release への上書きを許可
          </label>
          <label className="admin-toggle">
            <input type="checkbox" checked={updateManifestInstallerUrl} disabled={anyBusy} onChange={(event) => setUpdateManifestInstallerUrl(event.currentTarget.checked)} />
            manifest に installer URL を書き込む
          </label>
          <label className="admin-toggle">
            <input type="checkbox" checked={draft} disabled={anyBusy} onChange={(event) => setDraft(event.currentTarget.checked)} />
            Draft Release として作成
          </label>
          <label className="admin-toggle">
            <input type="checkbox" checked={prerelease} disabled={anyBusy} onChange={(event) => setPrerelease(event.currentTarget.checked)} />
            Pre-release として作成
          </label>
          <label className="admin-toggle">
            <input type="checkbox" checked={downloadInstallerAfterPublish} disabled={anyBusy} onChange={(event) => setDownloadInstallerAfterPublish(event.currentTarget.checked)} />
            publish 後に installer download verify まで実行
          </label>
        </div>
        <label className="admin-field">
          Release notes
          <textarea className="studio-textarea" rows={4} value={releaseNotes} disabled={anyBusy} onChange={(event) => setReleaseNotes(event.currentTarget.value)} placeholder="未入力なら script の標準 release note を使います。" />
        </label>
        <p className="admin-muted">実 publish は `publish_github_release.ps1` を DryRun なしで実行します。通常は preflight、dry-run、release build / verify を確認してから実行してください。</p>
      </details>

      {result ? <PublishSummary result={result} /> : null}
      {dryRunResult ? <PublishRunSummary result={dryRunResult} title="publish dry-run result" /> : null}
      {prepareTargetResult ? <PublishRunSummary result={prepareTargetResult} title="publish target result" /> : null}
      {buildVerifyResult ? <PublishRunSummary result={buildVerifyResult} title="release build / verify result" /> : null}
      {remoteVerifyResult ? <PublishRunSummary result={remoteVerifyResult} title="remote verify result" /> : null}
      {publishResult ? <PublishRunSummary result={publishResult} title="GitHub publish result" /> : null}
      {error ? <p className="admin-error" role="alert">{error}</p> : null}
    </section>
  );
}

function PublishReadinessChecklist({ items }: { items: Array<{ label: string; ok: boolean; message: string }> }) {
  return (
    <div className="publish-readiness-list">
      {items.map((item) => {
        const Icon = item.ok ? CheckCircle2 : TriangleAlert;
        return (
          <div className={`publish-readiness-item ${item.ok ? "ok" : "warn"}`} key={item.label}>
            <Icon size={17} aria-hidden="true" />
            <div>
              <strong>{item.label}</strong>
              <span>{item.message}</span>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function PublishSummary({ result }: { result: AppStudioPublishPreflightResult }) {
  return (
    <>
      <div className={`admin-image-test-result ${result.ok ? "ok" : "warn"}`}>
        <div><span>version</span><strong>{result.version ?? "-"}</strong></div>
        <div><span>tag</span><strong>{result.tag ?? "-"}</strong></div>
        <div><span>branch</span><strong>{result.branch ?? "-"}</strong></div>
        <div><span>remote</span><strong>{result.remoteUrl ?? "-"}</strong></div>
        <div><span>installer</span><strong>{result.installerFile ?? "-"}</strong></div>
        <div><span>installer exists</span><strong>{result.installerExists ? "yes" : "no"}</strong></div>
        <div><span>beta blockers</span><strong>{result.betaReadyBlockers}</strong></div>
        <div><span>warnings</span><strong>{result.betaReadyWarnings}</strong></div>
        <div><span>manual checks</span><strong>{result.betaReadyManualChecks}</strong></div>
        <div><span>dirty files</span><strong>{result.dirtyFiles.length}</strong></div>
        <div><span>release dirty</span><strong>{result.dirtyReleaseFiles?.length ?? 0}</strong></div>
        <div><span>runtime/data dirty</span><strong>{result.dirtyRuntimeDataFiles?.length ?? 0}</strong></div>
        <div className="wide"><span>release dir</span><strong>{result.releaseDir}</strong></div>
        <div className="wide"><span>release target folder</span><strong>{result.releaseTargetDir}</strong></div>
        <div className="wide"><span>release target manifest</span><strong>{result.releaseTargetManifestPath}</strong></div>
        <div className="wide"><span>update manifest URL</span><strong>{result.updateManifestUrl ?? "-"}</strong></div>
        <div className="wide"><span>latest manifest URL</span><strong>{result.latestManifestUrl ?? "-"}</strong></div>
        <div className="wide"><span>tag manifest URL</span><strong>{result.tagManifestUrl ?? "-"}</strong></div>
        <div className="wide"><span>release URL</span><strong>{result.releaseUrl ?? "-"}</strong></div>
        <div className="wide"><span>installer path</span><strong>{result.installerPath ?? "-"}</strong></div>
      </div>

      <details className="admin-details" open>
        <summary>リリース対象フォルダ</summary>
        <ReleaseTargetAssets assets={result.releaseTargetAssets ?? []} />
      </details>

      <details className="admin-details" open>
        <summary>公開前チェック</summary>
        <div className="studio-preflight-grid">
          {result.checks.map((check) => (
            <PublishCheckItem key={check.id} check={check} />
          ))}
        </div>
      </details>

      <details className="admin-details">
        <summary>未コミット変更 ({result.dirtyFiles.length})</summary>
        <DirtyFileGroups result={result} />
      </details>

      <details className="admin-details">
        <summary>実行コマンド</summary>
        <div className="version-list">
          <div className="version-row"><span>dry-run</span><strong>.\scripts\publish_github_release.ps1 -DryRun -SkipBuild -SkipVerify -SkipTag -SkipRemoteVerify -AllowDirty</strong></div>
          <div className="version-row"><span>prepare target</span><strong>.\scripts\publish_github_release.ps1 -PrepareTargetOnly -SkipBuild -SkipVerify -SkipTag -SkipRemoteVerify -AllowDirty</strong></div>
          <div className="version-row"><span>publish</span><strong>.\scripts\publish_github_release.ps1</strong></div>
          <div className="version-row"><span>beta publish</span><strong>.\scripts\publish_github_release.ps1 -Prerelease -Tag v&lt;version&gt;-beta.1</strong></div>
          <div className="version-row"><span>remote verify</span><strong>.\scripts\verify_github_release_assets.ps1 -ManifestUrl {result.latestManifestUrl ?? "<manifest_url>"} -ExpectedVersion {result.version ?? "<version>"}</strong></div>
          <div className="version-row"><span>beta verify</span><strong>.\scripts\verify_github_release_assets.ps1 -ManifestUrl {result.tagManifestUrl ?? "<tag_manifest_url>"} -ExpectedVersion {result.version ?? "<version>"}</strong></div>
        </div>
      </details>
    </>
  );
}

function ReleaseTargetAssets({ assets }: { assets: AppStudioPublishAsset[] }) {
  if (!assets.length) {
    return <p className="admin-muted">リリース対象ファイルはまだ解決されていません。</p>;
  }

  return (
    <div className="dirty-file-groups">
      {assets.map((asset) => (
        <section className={`dirty-file-group ${asset.targetExists ? "normal" : "warn"}`} key={asset.name}>
          <strong>{asset.name} - {asset.targetExists ? "target ready" : asset.sourceExists || asset.generated ? "target pending" : "source missing"}</strong>
          <ul className="update-note-list">
            <li>source: {asset.sourcePath ?? (asset.generated ? "generated in target folder" : "-")}</li>
            <li>target: {asset.targetPath}</li>
            <li>source sha256: {asset.sourceSha256 ?? "-"}</li>
            <li>target sha256: {asset.targetSha256 ?? "-"}</li>
            <li>size: {asset.targetSize ?? asset.sourceSize ?? "-"}</li>
          </ul>
        </section>
      ))}
    </div>
  );
}

function DirtyFileGroups({ result }: { result: AppStudioPublishPreflightResult }) {
  if (!result.dirtyFiles.length) {
    return <p className="admin-muted">未コミット変更はありません。</p>;
  }

  return (
    <div className="dirty-file-groups">
      <DirtyFileGroup title="release / publish 境界" files={result.dirtyReleaseFiles ?? []} tone="warn" />
      <DirtyFileGroup title="runtime / data / config" files={result.dirtyRuntimeDataFiles ?? []} tone="warn" />
      <DirtyFileGroup title="source / docs" files={result.dirtySourceFiles ?? []} tone="normal" />
      <DirtyFileGroup title="other" files={result.dirtyOtherFiles ?? []} tone="normal" />
    </div>
  );
}

function DirtyFileGroup({ title, files, tone }: { title: string; files: string[]; tone: "normal" | "warn" }) {
  return (
    <section className={`dirty-file-group ${tone}`}>
      <strong>{title} ({files.length})</strong>
      {files.length ? (
        <ul className="update-note-list">
          {files.map((item) => (
            <li key={`${title}-${item}`}>{item}</li>
          ))}
        </ul>
      ) : (
        <p className="admin-muted">該当なし</p>
      )}
    </section>
  );
}

function PublishRunSummary({ result, title }: { result: AppStudioPublishRunResult; title: string }) {
  return (
    <details className="admin-details" open>
      <summary>{title}</summary>
      <div className={`admin-image-test-result ${result.ok ? "ok" : "warn"}`}>
        <div><span>status</span><strong>{result.ok ? "pass" : "fail"}</strong></div>
        <div><span>exit code</span><strong>{result.exitCode}</strong></div>
        <div><span>duration</span><strong>{result.processWallClockSeconds.toFixed(2)}s</strong></div>
        <div className="wide"><span>started</span><strong>{result.startedAt}</strong></div>
        <div className="wide"><span>finished</span><strong>{result.finishedAt}</strong></div>
        <div className="wide"><span>message</span><strong>{result.userMessage}</strong></div>
        <div className="wide"><span>command</span><strong>{result.commandLine}</strong></div>
      </div>
      {result.report ? <RemoteVerificationReport report={result.report} /> : null}
      <pre className="studio-log">{joinRunLogs(result)}</pre>
    </details>
  );
}

function RemoteVerificationReport({ report }: { report: AppStudioRemoteVerificationReport }) {
  return (
    <>
      <div className={`admin-image-test-result ${report.ok ? "ok" : "warn"}`}>
        <div><span>remote status</span><strong>{report.ok ? "pass" : "fail"}</strong></div>
        <div><span>remote version</span><strong>{report.remote_version ?? "-"}</strong></div>
        <div><span>expected version</span><strong>{report.expected_version ?? "-"}</strong></div>
        <div><span>installer file</span><strong>{report.installer_file ?? "-"}</strong></div>
        <div className="wide"><span>manifest URL</span><strong>{report.manifest_url ?? "-"}</strong></div>
        <div className="wide"><span>installer URL</span><strong>{report.installer_url ?? "-"}</strong></div>
        <div className="wide"><span>installer sha256</span><strong>{report.installer_sha256 ?? "-"}</strong></div>
        <div className="wide"><span>downloaded installer</span><strong>{report.downloaded_installer ?? "-"}</strong></div>
      </div>
      {report.checks?.length ? (
        <div className="studio-preflight-grid">
          {report.checks.map((check, index) => (
            <RemoteVerificationCheckItem key={`${check.id ?? "check"}-${index}`} check={check} />
          ))}
        </div>
      ) : null}
    </>
  );
}

function RemoteVerificationCheckItem({ check }: { check: AppStudioRemoteVerificationCheck }) {
  const severity = check.status === "pass" ? "ok" : check.status === "fail" ? "fail" : "warn";
  const Icon = check.status === "pass" ? CheckCircle2 : check.status === "fail" ? CircleAlert : TriangleAlert;

  return (
    <div className={`studio-preflight-item ${severity}`}>
      <Icon size={18} aria-hidden="true" />
      <div>
        <strong>{check.id ?? "check"}</strong>
        <small>{check.message ?? check.status ?? "-"}</small>
      </div>
    </div>
  );
}

function PublishCheckItem({ check }: { check: AppStudioPublishCheck }) {
  const severity = check.status === "pass" ? "ok" : check.status === "fail" ? "fail" : "warn";
  const Icon = check.status === "pass" ? CheckCircle2 : check.status === "fail" ? CircleAlert : TriangleAlert;

  return (
    <div className={`studio-preflight-item ${severity}`}>
      <Icon size={18} aria-hidden="true" />
      <div>
        <strong>{check.id}</strong>
        <small>{check.message}</small>
      </div>
    </div>
  );
}

function joinRunLogs(result: AppStudioPublishRunResult): string {
  return [
    `exitCode: ${result.exitCode}`,
    `ok: ${String(result.ok)}`,
    `processWallClockSeconds: ${result.processWallClockSeconds.toFixed(3)}`,
    "",
    "[stdout]",
    result.stdout.trim() || "(empty)",
    "",
    "[stderr]",
    result.stderr.trim() || "(empty)",
  ].join("\n");
}
