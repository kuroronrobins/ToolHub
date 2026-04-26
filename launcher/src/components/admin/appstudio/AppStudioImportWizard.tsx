import { useMemo, useState } from "react";
import type { ChangeEvent } from "react";
import { FileSearch, Play, Rocket } from "lucide-react";
import { appStudioApply, appStudioApprove, appStudioReadResult, appStudioSuggest } from "../../../lib/appStudioApi";
import type { AppStudioImportRequest, AppStudioRunResult } from "../../../lib/appStudioTypes";
import { formatAdminError } from "../adminUi";
import { AppStudioBuildOptions } from "./AppStudioBuildOptions";
import { AppStudioResultPanel } from "./AppStudioResultPanel";
import { AppStudioRunLog } from "./AppStudioRunLog";

const INITIAL_REQUEST: AppStudioImportRequest = {
  entry: "",
  appId: "",
  name: "",
  buildMode: "auto",
  iconPrompt: "",
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
  const [result, setResult] = useState<AppStudioRunResult | null>(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const canRun = useMemo(() => request.entry.trim().length > 0 && !busy, [busy, request.entry]);

  function update(partial: Partial<AppStudioImportRequest>) {
    setRequest((current) => ({ ...current, ...partial }));
  }

  function handleEntryChange(event: ChangeEvent<HTMLInputElement>) {
    const entry = event.target.value;
    setRequest((current) => {
      const next: AppStudioImportRequest = { ...current, entry };
      if (!current.appId?.trim()) {
        next.appId = suggestAppId(entry);
      }
      if (!current.name?.trim()) {
        next.name = suggestName(entry);
      }
      return next;
    });
  }

  async function run(action: "suggest" | "apply") {
    setBusy(true);
    setError("");
    setMessage("");
    setLastAction(action);
    try {
      const runResult = action === "suggest" ? await appStudioSuggest(cleanRequest(request)) : await appStudioApply(cleanRequest(request));
      setResult(runResult);
      setMessage(runResult.userMessage);
      if (!runResult.ok) {
        setError(runResult.userMessage);
      }
    } catch (runError) {
      setError(formatAdminError(runError, "App Studioを実行できませんでした。"));
    } finally {
      setBusy(false);
    }
  }

  async function approve() {
    const appId = result?.appId ?? request.appId;
    if (!appId) {
      setError("承認するAppIdがありません。");
      return;
    }
    setBusy(true);
    setError("");
    setMessage("");
    setLastAction("approve");
    try {
      const approveResult = await appStudioApprove(appId);
      setResult(approveResult);
      setMessage(approveResult.userMessage);
      if (!approveResult.ok) {
        setError(approveResult.userMessage);
      }
    } catch (approveError) {
      setError(formatAdminError(approveError, "承認処理を実行できませんでした。"));
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
      const summary = await appStudioReadResult(appId || undefined, outputDir || undefined);
      setResult((current) => ({
        ok: current?.ok ?? true,
        exitCode: current?.exitCode ?? 0,
        stdout: current?.stdout ?? "",
        stderr: current?.stderr ?? "",
        userMessage: current?.userMessage ?? "結果を再読込しました。",
        outputDir: summary.outputDir,
        appId: summary.appId,
        executionStatus: summary.executionStatus,
        approvalAllowed: summary.approvalAllowed,
        runtimeStatus: summary.runtimeStatus,
        appPack: summary.appPack,
        enabled: summary.enabled,
      }));
      setMessage("結果を再読込しました。");
    } catch (refreshError) {
      setError(formatAdminError(refreshError, "結果を読み込めませんでした。"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="studio-wizard-layout">
      <section className="studio-wizard-main">
        <div className="admin-section-head">
          <div>
            <p className="dialog-kicker">新規登録</p>
            <h3>App Studio Import Wizard</h3>
          </div>
          <span className="admin-status-pill">GUI beta</span>
        </div>

        <section className="studio-step">
          <div>
            <span className="studio-step-index">1</span>
            <h4>Entry選択</h4>
          </div>
          <div className="studio-entry-row">
            <label className="admin-field">
              <span>Entryファイルパス</span>
              <input type="text" value={request.entry} placeholder="C:\\work\\mytool\\main.py" onChange={handleEntryChange} />
            </label>
            <button className="secondary-button" type="button" disabled title="ファイルダイアログは次フェーズで追加予定">
              <FileSearch size={17} aria-hidden="true" />
              参照
            </button>
          </div>
        </section>

        <section className="studio-step">
          <div>
            <span className="studio-step-index">2</span>
            <h4>基本情報</h4>
          </div>
          <div className="admin-two-column">
            <label className="admin-field">
              <span>App ID</span>
              <input type="text" value={request.appId ?? ""} placeholder="my_tool" onChange={(event) => update({ appId: event.target.value })} />
            </label>
            <label className="admin-field">
              <span>表示名</span>
              <input type="text" value={request.name ?? ""} placeholder="My Tool" onChange={(event) => update({ name: event.target.value })} />
            </label>
          </div>
        </section>

        <AppStudioBuildOptions request={request} onChange={setRequest} />

        <section className="studio-step">
          <div>
            <span className="studio-step-index">4</span>
            <h4>AI/アイコン</h4>
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

        {message ? <p className="admin-success">{message}</p> : null}
        {error ? <p className="admin-error" role="alert">{error}</p> : null}
      </section>

      <aside className="studio-wizard-side">
        <AppStudioRunLog busy={busy} result={result} />
        <AppStudioResultPanel
          result={result}
          lastAction={lastAction}
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
  };
}

function suggestAppId(entry: string): string {
  const base = basename(entry).replace(/\.[^.]+$/, "");
  return base
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9_-]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .slice(0, 64);
}

function suggestName(entry: string): string {
  const base = basename(entry).replace(/\.[^.]+$/, "");
  return base
    .split(/[_\-\s]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function basename(path: string): string {
  const normalized = path.replace(/\\/g, "/");
  return normalized.split("/").filter(Boolean).pop() ?? "";
}
