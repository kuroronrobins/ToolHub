import { useMemo, useState } from "react";
import type { ChangeEvent } from "react";
import { FileSearch, Play, Rocket } from "lucide-react";
import {
  appStudioApply,
  appStudioApprove,
  appStudioPickEntryFile,
  appStudioPreflight,
  appStudioReadResult,
  appStudioSuggest,
} from "../../../lib/appStudioApi";
import { suggestAppIdentity } from "../../../lib/appStudioIdentity";
import { cleanEditableMetadata, cleanIconOverride, createEmptyAppStudioMetadata } from "../../../lib/appStudioMetadata";
import type { AppStudioAiProposal, AppStudioApprovalMode, AppStudioIconOverride, AppStudioImportRequest, AppStudioPreflightResult, AppStudioRunResult } from "../../../lib/appStudioTypes";
import { formatAdminError } from "../adminUi";
import { AppStudioAiProposalPanel } from "./AppStudioAiProposalPanel";
import { AppStudioBuildOptions } from "./AppStudioBuildOptions";
import { AppStudioMetadataEditor } from "./AppStudioMetadataEditor";
import { AppStudioPreflightPanel } from "./AppStudioPreflightPanel";
import { AppStudioResultPanel } from "./AppStudioResultPanel";
import { AppStudioRunLog } from "./AppStudioRunLog";

const INITIAL_REQUEST: AppStudioImportRequest = {
  entry: "",
  appId: "",
  name: "",
  buildMode: "auto",
  iconPrompt: "",
  metadata: createEmptyAppStudioMetadata(),
  createAppEnv: false,
  rebuildAppEnv: false,
  generateLock: false,
  buildFrozenFolder: false,
  verifyRuntime: false,
};

type StudioAction = "suggest" | "apply" | "approve";

export function AppStudioImportWizard() {
  const [request, setRequest] = useState<AppStudioImportRequest>(INITIAL_REQUEST);
  const [busy, setBusy] = useState(false);
  const [lastAction, setLastAction] = useState<StudioAction | null>(null);
  const [approvalMode, setApprovalMode] = useState<AppStudioApprovalMode>("allowWarnings");
  const [preflight, setPreflight] = useState<AppStudioPreflightResult | null>(null);
  const [result, setResult] = useState<AppStudioRunResult | null>(null);
  const [aiProposal, setAiProposal] = useState<AppStudioAiProposal | null>(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const canRun = useMemo(() => request.entry.trim().length > 0 && !busy, [busy, request.entry]);

  function update(partial: Partial<AppStudioImportRequest>) {
    setRequest((current) => ({ ...current, ...partial }));
    setPreflight(null);
  }

  function handleEntryChange(event: ChangeEvent<HTMLInputElement>) {
    setEntry(event.target.value);
  }

  function setEntry(entry: string) {
    setRequest((current) => {
      const suggestion = suggestAppIdentity(entry);
      const next: AppStudioImportRequest = { ...current, entry };
      if (!current.appId?.trim()) {
        next.appId = suggestion.appId;
      }
      if (!current.name?.trim()) {
        next.name = suggestion.name;
      }
      return next;
    });
    setPreflight(null);
  }

  async function browseEntry() {
    setError("");
    try {
      const selected = await appStudioPickEntryFile();
      if (selected) {
        setEntry(selected);
      }
    } catch (browseError) {
      setError(formatAdminError(browseError, "Entry file dialog could not be opened. Use manual path input."));
    }
  }

  async function runPreflight(candidate: AppStudioImportRequest = request): Promise<AppStudioPreflightResult | null> {
    setError("");
    try {
      const check = await appStudioPreflight(cleanRequest(candidate));
      setPreflight(check);
      if (!check.ok) {
        setError("Preflight reported errors. Review the details before running App Studio.");
      }
      return check;
    } catch (preflightError) {
      setError(formatAdminError(preflightError, "Preflight could not run."));
      return null;
    }
  }

  async function run(action: "suggest" | "apply"): Promise<AppStudioRunResult | null> {
    setBusy(true);
    setError("");
    setMessage("");
    setLastAction(action);
    try {
      const cleaned = cleanRequest(request);
      const check = await runPreflight(cleaned);
      if (!check?.ok) {
        return null;
      }
      const rawResult = action === "suggest" ? await appStudioSuggest(cleaned) : await appStudioApply(cleaned);
      const freshResult = await refreshRunResult(rawResult);
      setResult(freshResult);
      setMessage(messageForResult(freshResult));
      if (!freshResult.ok && !isWarningOnly(freshResult)) {
        setError(freshResult.userMessage);
      }
      return freshResult;
    } catch (runError) {
      setError(formatAdminError(runError, "App Studio could not run."));
      return null;
    } finally {
      setBusy(false);
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
      const rawResult = await appStudioApprove(appId, approvalMode === "strict");
      const freshResult = await refreshRunResult(rawResult);
      setResult(freshResult);
      setMessage(messageForResult(freshResult));
      if (!freshResult.ok && !isWarningOnly(freshResult)) {
        setError(freshResult.userMessage);
      }
    } catch (approveError) {
      setError(formatAdminError(approveError, "Approval could not run."));
    } finally {
      setBusy(false);
    }
  }

  async function refreshResult() {
    if (!result?.appId && !result?.outputDir && !request.appId) {
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
          appId: request.appId,
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
        newVersion: summary.version ?? runResult.newVersion,
        metadataOverrideUsed: summary.metadataOverrideUsed ?? runResult.metadataOverrideUsed,
        metadataOverrideKeys: summary.metadataOverrideKeys ?? runResult.metadataOverrideKeys,
      };
    } catch {
      return runResult;
    }
  }

  function adoptAiProposal(values: { name?: string; iconPrompt?: string }) {
    update({
      name: values.name ?? request.name,
      iconPrompt: values.iconPrompt ?? request.iconPrompt,
    });
    setMessage("AI proposal was copied into the editable fields. Review before Apply.");
  }

  function adoptIconOverride(iconOverride: AppStudioIconOverride) {
    update({ iconOverride });
    setMessage("PNG icon candidate was selected. It will be used on the next Apply.");
  }

  return (
    <div className="studio-wizard-layout">
      <section className="studio-wizard-main">
        <div className="admin-section-head">
          <div>
            <p className="dialog-kicker">New registration</p>
            <h3>App Studio Import Wizard</h3>
          </div>
          <span className="admin-status-pill">GUI beta</span>
        </div>

        <section className="studio-step">
          <div>
            <span className="studio-step-index">1</span>
            <h4>Entry</h4>
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

        <section className="studio-step">
          <div>
            <span className="studio-step-index">2</span>
            <h4>Basic info</h4>
          </div>
          <div className="admin-two-column">
            <label className="admin-field">
              <span>App ID</span>
              <input type="text" value={request.appId ?? ""} placeholder="my_tool" onChange={(event) => update({ appId: event.target.value })} />
            </label>
            <label className="admin-field">
              <span>Name</span>
              <input type="text" value={request.name ?? ""} placeholder="My Tool" onChange={(event) => update({ name: event.target.value })} />
            </label>
          </div>
        </section>

        <AppStudioMetadataEditor metadata={request.metadata} proposal={aiProposal?.metadata ?? null} onChange={(metadata) => update({ metadata })} />

        <AppStudioBuildOptions
          request={request}
          onChange={(next) => {
            setRequest(next);
            setPreflight(null);
          }}
        />

        <section className="studio-step">
          <div>
            <span className="studio-step-index">4</span>
            <h4>Icon prompt</h4>
          </div>
          <label className="admin-field">
            <span>Icon Prompt</span>
            <textarea
              className="studio-textarea"
              value={request.iconPrompt ?? ""}
              placeholder="シンプルな業務アプリアイコン。用途を短く指定してください。"
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
          <button className="secondary-button" type="button" onClick={() => void run("suggest")} disabled={!canRun}>
            <Play size={17} aria-hidden="true" />
            Suggest
          </button>
          <button className="primary-button" type="button" onClick={() => void run("apply")} disabled={!canRun}>
            <Rocket size={17} aria-hidden="true" />
            Apply
          </button>
        </div>

        {message ? <p className={result && !result.ok && isWarningOnly(result) ? "admin-muted" : "admin-success"}>{message}</p> : null}
        {error ? <p className="admin-error" role="alert">{error}</p> : null}
      </section>

      <aside className="studio-wizard-side">
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

function cleanRequest(request: AppStudioImportRequest): AppStudioImportRequest {
  return {
    ...request,
    entry: request.entry.trim(),
    appId: request.appId?.trim() || undefined,
    name: request.name?.trim() || undefined,
    iconPrompt: request.iconPrompt?.trim() || undefined,
    metadata: cleanEditableMetadata(request.metadata),
    iconOverride: cleanIconOverride(request.iconOverride),
  };
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
