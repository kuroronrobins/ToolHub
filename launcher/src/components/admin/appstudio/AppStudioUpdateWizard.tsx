import { useEffect, useMemo, useState } from "react";
import type { ChangeEvent } from "react";
import { FileSearch, Play, Rocket } from "lucide-react";
import {
  appStudioListRegisteredApps,
  appStudioPickEntryFile,
  appStudioReadResult,
  appStudioUpdateApply,
  appStudioUpdateApprove,
  appStudioUpdatePreflight,
  appStudioUpdateSuggest,
} from "../../../lib/appStudioApi";
import { cleanEditableMetadata, cleanIconOverride, createEmptyAppStudioMetadata } from "../../../lib/appStudioMetadata";
import type {
  AppStudioAiProposal,
  AppStudioApprovalMode,
  AppStudioBuildMode,
  AppStudioIconOverride,
  AppStudioImportRequest,
  AppStudioPreflightResult,
  AppStudioRegisteredApp,
  AppStudioRunResult,
  AppStudioUpdateRequest,
  AppStudioVersionBumpMode,
} from "../../../lib/appStudioTypes";
import { bumpAppVersion, compareSimpleSemVer } from "../../../lib/appStudioVersion";
import { formatAdminError } from "../adminUi";
import { AppStudioAiProposalPanel } from "./AppStudioAiProposalPanel";
import { AppStudioBuildOptions } from "./AppStudioBuildOptions";
import { AppStudioMetadataEditor } from "./AppStudioMetadataEditor";
import { AppStudioPreflightPanel } from "./AppStudioPreflightPanel";
import { AppStudioRegisteredAppPicker } from "./AppStudioRegisteredAppPicker";
import { AppStudioResultPanel } from "./AppStudioResultPanel";
import { AppStudioRunLog } from "./AppStudioRunLog";
import { AppStudioVersionBump } from "./AppStudioVersionBump";

type StudioAction = "suggest" | "apply" | "approve";

const INITIAL_REQUEST: AppStudioUpdateRequest = {
  appId: "",
  entry: "",
  name: "",
  currentVersion: "",
  newVersion: "",
  buildMode: "auto",
  iconPrompt: "",
  metadata: createEmptyAppStudioMetadata(),
  createAppEnv: false,
  rebuildAppEnv: false,
  generateLock: false,
  buildFrozenFolder: false,
  verifyRuntime: false,
};

export function AppStudioUpdateWizard() {
  const [apps, setApps] = useState<AppStudioRegisteredApp[]>([]);
  const [request, setRequest] = useState<AppStudioUpdateRequest>(INITIAL_REQUEST);
  const [versionMode, setVersionMode] = useState<AppStudioVersionBumpMode>("patch");
  const [manualVersion, setManualVersion] = useState("");
  const [approvalMode, setApprovalMode] = useState<AppStudioApprovalMode>("allowWarnings");
  const [busy, setBusy] = useState(false);
  const [preflight, setPreflight] = useState<AppStudioPreflightResult | null>(null);
  const [result, setResult] = useState<AppStudioRunResult | null>(null);
  const [aiProposal, setAiProposal] = useState<AppStudioAiProposal | null>(null);
  const [lastAction, setLastAction] = useState<StudioAction | null>(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const selectedApp = apps.find((app) => app.appId === request.appId) ?? null;
  const bumped = useMemo(
    () => bumpAppVersion(request.currentVersion ?? "", versionMode, manualVersion),
    [manualVersion, request.currentVersion, versionMode],
  );
  const newVersion = bumped.version;
  const versionCompare = compareSimpleSemVer(request.currentVersion ?? "", newVersion);
  const canRun = Boolean(request.appId.trim() && request.entry.trim() && newVersion.trim() && !busy);

  useEffect(() => {
    void loadApps();
  }, []);

  async function loadApps() {
    setBusy(true);
    setError("");
    try {
      const loaded = await appStudioListRegisteredApps();
      setApps(loaded);
      setMessage("Registered apps were loaded.");
    } catch (loadError) {
      setError(formatAdminError(loadError, "Registered apps could not be loaded."));
    } finally {
      setBusy(false);
    }
  }

  function selectApp(app: AppStudioRegisteredApp) {
    setRequest((current) => ({
      ...current,
      appId: app.appId,
      name: app.name,
      currentVersion: app.version,
      buildMode: normalizeBuildMode(app.buildMode) ?? current.buildMode,
      metadata: createEmptyAppStudioMetadata(),
    }));
    setVersionMode("patch");
    setManualVersion("");
    setPreflight(null);
    setResult(null);
    setAiProposal(null);
    setLastAction(null);
  }

  function update(partial: Partial<AppStudioUpdateRequest>) {
    setRequest((current) => ({ ...current, ...partial }));
    setPreflight(null);
  }

  function handleEntryChange(event: ChangeEvent<HTMLInputElement>) {
    update({ entry: event.target.value });
  }

  async function browseEntry() {
    setError("");
    try {
      const selected = await appStudioPickEntryFile();
      if (selected) {
        update({ entry: selected });
      }
    } catch (browseError) {
      setError(formatAdminError(browseError, "Entry file dialog could not be opened. Use manual path input."));
    }
  }

  async function runPreflight(candidate: AppStudioUpdateRequest = request): Promise<AppStudioPreflightResult | null> {
    setError("");
    const cleaned = cleanRequest(candidate, newVersion);
    try {
      const check = await appStudioUpdatePreflight(cleaned);
      setPreflight(check);
      if (!check.ok) {
        setError("Preflight reported errors. Review the details before running update.");
      }
      return check;
    } catch (preflightError) {
      setError(formatAdminError(preflightError, "Update preflight could not run."));
      return null;
    }
  }

  async function run(action: "suggest" | "apply"): Promise<AppStudioRunResult | null> {
    setBusy(true);
    setError("");
    setMessage("");
    setLastAction(action);
    try {
      const cleaned = cleanRequest(request, newVersion);
      const check = await runPreflight(cleaned);
      if (!check?.ok) {
        return null;
      }
      const rawResult = action === "suggest" ? await appStudioUpdateSuggest(cleaned) : await appStudioUpdateApply(cleaned);
      const runResult = await refreshRunResult({
        ...rawResult,
        currentVersion: request.currentVersion,
        newVersion,
      });
      setResult(runResult);
      setMessage(messageForResult(runResult));
      if (!runResult.ok && !isWarningOnly(runResult)) {
        setError(runResult.userMessage);
      }
      return runResult;
    } catch (runError) {
      setError(formatAdminError(runError, "App Studio update could not run."));
      return null;
    } finally {
      setBusy(false);
    }
  }

  async function refreshRunResult(runResult: AppStudioRunResult): Promise<AppStudioRunResult> {
    const appId = runResult.appId ?? request.appId;
    const outputDir = runResult.outputDir ?? undefined;
    if (!appId && !outputDir) {
      return runResult;
    }
    try {
      const summary = await appStudioReadResult(appId || undefined, outputDir || undefined);
      return {
        ...runResult,
        outputDir: summary.outputDir ?? runResult.outputDir,
        appId: summary.appId ?? runResult.appId,
        selectedBuildMode: summary.selectedBuildMode ?? runResult.selectedBuildMode,
        executionStatus: summary.executionStatus ?? runResult.executionStatus,
        approvalAllowed: summary.approvalAllowed ?? runResult.approvalAllowed,
        runtimeStatus: summary.runtimeStatus ?? runResult.runtimeStatus,
        appPack: summary.appPack ?? runResult.appPack,
        enabled: summary.enabled ?? runResult.enabled,
        currentVersion: request.currentVersion,
        newVersion: summary.version ?? newVersion,
        metadataOverrideUsed: summary.metadataOverrideUsed ?? runResult.metadataOverrideUsed,
        metadataOverrideKeys: summary.metadataOverrideKeys ?? runResult.metadataOverrideKeys,
      };
    } catch {
      return runResult;
    }
  }

  async function approve() {
    const appId = result?.appId ?? request.appId;
    if (!appId) {
      setError("AppId is required for approval.");
      return;
    }
    setBusy(true);
    setError("");
    setMessage("");
    setLastAction("approve");
    try {
      const approveResult = await appStudioUpdateApprove(appId, approvalMode === "strict");
      const freshResult = await refreshRunResult({
        ...approveResult,
        currentVersion: request.currentVersion,
        newVersion,
      });
      setResult(freshResult);
      setMessage(messageForResult(freshResult));
      if (!freshResult.ok && !isWarningOnly(freshResult)) {
        setError(freshResult.userMessage);
      }
    } catch (approveError) {
      setError(formatAdminError(approveError, "Update approval could not run."));
    } finally {
      setBusy(false);
    }
  }

  async function refreshResult() {
    const appId = result?.appId ?? request.appId;
    const outputDir = result?.outputDir ?? undefined;
    if (!appId && !outputDir) {
      return;
    }
    setBusy(true);
    setError("");
    try {
      const freshResult = await refreshRunResult(
        result ?? {
          ok: true,
          exitCode: 0,
          stdout: "",
          stderr: "",
          userMessage: "Result was refreshed.",
          appId,
          outputDir,
        },
      );
      setResult(freshResult);
      setMessage("Result was refreshed.");
    } catch (refreshError) {
      setError(formatAdminError(refreshError, "Result could not be refreshed."));
    } finally {
      setBusy(false);
    }
  }

  const buildOptionsRequest: AppStudioImportRequest = {
    entry: request.entry,
    appId: request.appId,
    name: request.name,
    buildMode: request.buildMode,
    iconPrompt: request.iconPrompt,
    createAppEnv: request.createAppEnv,
    rebuildAppEnv: request.rebuildAppEnv,
    generateLock: request.generateLock,
    buildFrozenFolder: request.buildFrozenFolder,
    verifyRuntime: request.verifyRuntime,
  };

  function adoptAiProposal(values: { name?: string; iconPrompt?: string }) {
    update({
      name: values.name ?? request.name,
      iconPrompt: values.iconPrompt ?? request.iconPrompt,
    });
    setMessage("AI proposal was copied into the editable fields. Review before Apply update.");
  }

  function adoptIconOverride(iconOverride: AppStudioIconOverride) {
    update({ iconOverride });
    setMessage("PNG icon candidate was selected. It will be used on the next Apply update.");
  }

  return (
    <div className="studio-wizard-layout">
      <section className="studio-wizard-main">
        <div className="admin-section-head">
          <div>
            <p className="dialog-kicker">Existing app update</p>
            <h3>App Studio Update Wizard</h3>
          </div>
          <span className="admin-status-pill">MVP</span>
        </div>

        <AppStudioRegisteredAppPicker apps={apps} selectedAppId={request.appId} loading={busy} onReload={() => void loadApps()} onSelect={selectApp} />

        <section className="studio-step">
          <div>
            <span className="studio-step-index">2</span>
            <h4>Current app</h4>
          </div>
          <div className="studio-result-list">
            <SummaryRow label="app_id" value={(selectedApp?.appId ?? request.appId) || "-"} />
            <SummaryRow label="name" value={selectedApp?.name ?? request.name ?? "-"} />
            <SummaryRow label="current_version" value={request.currentVersion || "-"} />
            <SummaryRow label="enabled" value={selectedApp ? String(selectedApp.enabled) : "-"} />
            <SummaryRow label="runner" value={selectedApp?.runner ?? "-"} />
            <SummaryRow label="current_entry" value={selectedApp?.entry ?? "-"} />
          </div>
        </section>

        <AppStudioVersionBump
          currentVersion={request.currentVersion ?? ""}
          mode={versionMode}
          manualVersion={manualVersion}
          newVersion={newVersion}
          onModeChange={setVersionMode}
          onManualVersionChange={setManualVersion}
        />

        <AppStudioMetadataEditor
          metadata={request.metadata}
          proposal={aiProposal?.metadata ?? null}
          includeReleaseFields
          onChange={(metadata) => update({ metadata })}
        />

        <section className="studio-step">
          <div>
            <span className="studio-step-index">4</span>
            <h4>Update entry</h4>
          </div>
          <div className="studio-entry-row">
            <label className="admin-field">
              <span>Entry file path</span>
              <input type="text" value={request.entry} placeholder="C:\\work\\mytool\\main.py" onChange={handleEntryChange} />
            </label>
            <button className="secondary-button" type="button" onClick={() => void browseEntry()} disabled={busy} title="Choose Entry file">
              <FileSearch size={17} aria-hidden="true" />
              Browse
            </button>
          </div>
        </section>

        <AppStudioBuildOptions
          request={buildOptionsRequest}
          onChange={(next) => {
            update({
              buildMode: next.buildMode,
              createAppEnv: next.createAppEnv,
              rebuildAppEnv: next.rebuildAppEnv,
              generateLock: next.generateLock,
              buildFrozenFolder: next.buildFrozenFolder,
              verifyRuntime: next.verifyRuntime,
            });
          }}
        />

        <section className="studio-step">
          <div>
            <span className="studio-step-index">6</span>
            <h4>Icon prompt</h4>
          </div>
          <label className="admin-field">
            <span>Icon Prompt</span>
            <textarea
              className="studio-textarea"
              value={request.iconPrompt ?? ""}
              placeholder="Simple business app icon revision prompt."
              onChange={(event) => update({ iconPrompt: event.target.value })}
            />
          </label>
        </section>

        <AppStudioAiProposalPanel
          appId={request.appId}
          outputDir={result?.outputDir}
          result={result}
          busy={busy}
          onGenerate={() => run("suggest")}
          onAdopt={adoptAiProposal}
          onIconAdopt={adoptIconOverride}
          selectedIconSource={request.iconOverride?.selectedIconSource}
          onProposalLoaded={setAiProposal}
        />

        <AppStudioPreflightPanel result={preflight} busy={busy} onRun={() => void runPreflight()} />

        <div className="studio-action-row">
          <button className="secondary-button" type="button" onClick={() => void run("suggest")} disabled={!canRun || versionCompare === 1}>
            <Play size={17} aria-hidden="true" />
            Suggest update
          </button>
          <button className="primary-button" type="button" onClick={() => void run("apply")} disabled={!canRun || versionCompare === 1}>
            <Rocket size={17} aria-hidden="true" />
            Apply update
          </button>
        </div>

        {bumped.warning ? <p className="admin-muted">{bumped.warning}</p> : null}
        {versionCompare === 1 ? <p className="admin-error">New version is older than current version.</p> : null}
        {message ? <p className={result && !result.ok && isWarningOnly(result) ? "admin-muted" : "admin-success"}>{message}</p> : null}
        {error ? <p className="admin-error" role="alert">{error}</p> : null}
      </section>

      <aside className="studio-wizard-side">
        <section className="studio-side-section">
          <div className="admin-section-head">
            <div>
              <p className="dialog-kicker">Update summary</p>
              <h4>Version and next action</h4>
            </div>
            <span className="admin-status-pill">{lastAction ?? "idle"}</span>
          </div>
          <div className="studio-result-list">
            <SummaryRow label="app_id" value={request.appId || "-"} />
            <SummaryRow label="current_version" value={request.currentVersion || "-"} />
            <SummaryRow label="new_version" value={newVersion || "-"} />
            <SummaryRow label="build_mode" value={request.buildMode} />
            <SummaryRow label="next" value={updateNextAction(result, lastAction, approvalMode, versionCompare)} />
          </div>
        </section>
        <AppStudioRunLog busy={busy} result={result} />
        <AppStudioResultPanel
          result={result}
          lastAction={lastAction}
          approvalMode={approvalMode}
          onApprovalModeChange={setApprovalMode}
          busy={busy}
          onApprove={() => void approve()}
          onRefresh={() => void refreshResult()}
        />
      </aside>
    </div>
  );
}

function cleanRequest(request: AppStudioUpdateRequest, newVersion: string): AppStudioUpdateRequest {
  return {
    ...request,
    appId: request.appId.trim(),
    entry: request.entry.trim(),
    name: request.name?.trim() || undefined,
    currentVersion: request.currentVersion?.trim() || undefined,
    newVersion: newVersion.trim(),
    iconPrompt: request.iconPrompt?.trim() || undefined,
    metadata: cleanEditableMetadata(request.metadata),
    iconOverride: cleanIconOverride(request.iconOverride),
  };
}

function normalizeBuildMode(value: string | null | undefined): AppStudioBuildMode | null {
  if (value === "auto" || value === "app-env" || value === "frozen-folder" || value === "existing-exe") {
    return value;
  }
  return null;
}

function SummaryRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="studio-result-row">
      <span aria-hidden="true">-</span>
      <strong>{label}</strong>
      <p>{value}</p>
    </div>
  );
}

function updateNextAction(
  result: AppStudioRunResult | null,
  lastAction: StudioAction | null,
  approvalMode: AppStudioApprovalMode,
  versionCompare: number | null,
): string {
  if (versionCompare === 1) {
    return "Fix the new version.";
  }
  if (!result) {
    return "Run Preflight, then Suggest update.";
  }
  if (!result.ok && !isWarningOnly(result)) {
    return "Review stdout/stderr and generated reports.";
  }
  if (result.enabled) {
    return "Update approved.";
  }
  if (lastAction === "suggest") {
    return "Run Apply update.";
  }
  if (lastAction === "apply") {
    if (result.executionStatus === "fail" || result.approvalAllowed === false) {
      return "Resolve fail checks before approval.";
    }
    if (approvalMode === "strict" && result.executionStatus !== "pass") {
      return "StrictApproval requires pass.";
    }
    return "Run Approve update.";
  }
  return "Review the result.";
}

function isWarningOnly(result: AppStudioRunResult): boolean {
  return result.executionStatus === "warn" && result.approvalAllowed === true;
}

function messageForResult(result: AppStudioRunResult): string {
  if (!result.ok && isWarningOnly(result)) {
    return "App Studio completed with warnings. execution_test_result.json allows approval; review logs before approving.";
  }
  return result.userMessage;
}
