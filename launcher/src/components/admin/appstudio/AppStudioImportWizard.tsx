import { useMemo, useState } from "react";
import type { ChangeEvent } from "react";
import { ChevronRight, FileSearch, Loader2, Play, Rocket, ShieldCheck } from "lucide-react";
import {
  appStudioApply,
  appStudioApprove,
  appStudioPickEntryFile,
  appStudioPreflight,
  appStudioReadResult,
  appStudioSuggest,
} from "../../../lib/appStudioApi";
import { BUILD_MODE_INFO, recommendBuildMode } from "../../../lib/appStudioBuildInfo";
import { suggestAppIdentity } from "../../../lib/appStudioIdentity";
import { cleanEditableMetadata, cleanIconOverride, createEmptyAppStudioMetadata } from "../../../lib/appStudioMetadata";
import type {
  AppStudioAiProposal,
  AppStudioApprovalMode,
  AppStudioIconOverride,
  AppStudioImportRequest,
  AppStudioPreflightResult,
  AppStudioRunResult,
} from "../../../lib/appStudioTypes";
import { formatAdminError } from "../adminUi";
import { AppStudioAiProposalPanel } from "./AppStudioAiProposalPanel";
import { AppStudioBuildOptions } from "./AppStudioBuildOptions";
import { AppStudioCollapsibleSection } from "./AppStudioCollapsibleSection";
import { AppStudioImportSidebar } from "./AppStudioImportSidebar";
import { AppStudioLauncherPreview } from "./AppStudioLauncherPreview";
import { AppStudioMetadataEditor } from "./AppStudioMetadataEditor";
import { AppStudioOperationBanner, IDLE_OPERATION, OPERATION_LABELS, type StudioOperationKind, type StudioOperationState, type StudioOperationStatus } from "./AppStudioOperationBanner";
import { AppStudioPreflightPanel } from "./AppStudioPreflightPanel";
import { AppStudioResultPanel } from "./AppStudioResultPanel";
import { AppStudioRunLog } from "./AppStudioRunLog";
import { AppStudioStepNav, type AppStudioImportStep } from "./AppStudioStepNav";

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
  const [step, setStep] = useState<AppStudioImportStep>("selectEntry");
  const [operation, setOperation] = useState<StudioOperationState>(IDLE_OPERATION);
  const [busy, setBusy] = useState(false);
  const [lastAction, setLastAction] = useState<StudioAction | null>(null);
  const [approvalMode, setApprovalMode] = useState<AppStudioApprovalMode>("allowWarnings");
  const [preflight, setPreflight] = useState<AppStudioPreflightResult | null>(null);
  const [result, setResult] = useState<AppStudioRunResult | null>(null);
  const [aiProposal, setAiProposal] = useState<AppStudioAiProposal | null>(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const canRun = useMemo(() => request.entry.trim().length > 0 && !busy, [busy, request.entry]);
  const recommendation = useMemo(() => recommendBuildMode(request.entry), [request.entry]);
  const canApprove = useMemo(
    () =>
      Boolean(
        result?.appId &&
          lastAction === "apply" &&
          result.executionStatus !== "fail" &&
          result.approvalAllowed !== false &&
          (approvalMode === "allowWarnings" || result.executionStatus === "pass"),
      ),
    [approvalMode, lastAction, result],
  );

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

  function beginOperation(kind: StudioOperationKind, messageText?: string) {
    setBusy(true);
    setOperation({
      kind,
      label: OPERATION_LABELS[kind],
      startedAt: Date.now(),
      status: "running",
      message: messageText,
    });
  }

  function finishOperation(status: StudioOperationStatus, messageText: string) {
    setBusy(false);
    setOperation({
      kind: "idle",
      label: OPERATION_LABELS.idle,
      startedAt: null,
      status,
      message: messageText,
    });
  }

  async function browseEntry() {
    beginOperation("pickingFile");
    setError("");
    try {
      const selected = await appStudioPickEntryFile();
      if (selected) {
        setEntry(selected);
        finishOperation("success", "ファイルを選択しました。アプリIDと表示名を確認してください。");
      } else {
        finishOperation("idle", "ファイル選択をキャンセルしました。");
      }
    } catch (browseError) {
      const fallback = "ファイル選択画面を開けませんでした。パスを手入力してください。";
      setError(formatAdminError(browseError, fallback));
      finishOperation("error", fallback);
    }
  }

  async function runPreflight(candidate: AppStudioImportRequest = request, showOperation = true): Promise<AppStudioPreflightResult | null> {
    if (showOperation) {
      beginOperation("preflight");
    }
    setError("");
    try {
      const check = await appStudioPreflight(cleanRequest(candidate));
      setPreflight(check);
      if (!check.ok) {
        const warning = "事前確認で問題が見つかりました。詳細を確認してから登録へ進んでください。";
        setError(warning);
        if (showOperation) {
          finishOperation("warning", warning);
        }
      } else if (showOperation) {
        finishOperation("success", "事前確認が完了しました。次へ進めます。");
      }
      return check;
    } catch (preflightError) {
      const fallback = "事前確認を実行できませんでした。";
      setError(formatAdminError(preflightError, fallback));
      if (showOperation) {
        finishOperation("error", fallback);
      }
      return null;
    } finally {
      if (showOperation) {
        setBusy(false);
      }
    }
  }

  async function run(action: "suggest" | "apply", operationKind: "aiProposal" | "suggest" | "apply" = action): Promise<AppStudioRunResult | null> {
    beginOperation(operationKind);
    setError("");
    setMessage("");
    setLastAction(action);
    try {
      const cleaned = cleanRequest(request);
      const check = await runPreflight(cleaned, false);
      if (!check?.ok) {
        finishOperation("warning", "事前確認で問題が見つかったため、処理を中止しました。");
        return null;
      }
      const rawResult = action === "suggest" ? await appStudioSuggest(cleaned) : await appStudioApply(cleaned);
      const freshResult = await refreshRunResult(rawResult);
      setResult(freshResult);
      const resultMessage = messageForResult(freshResult, action);
      setMessage(resultMessage);
      if (!freshResult.ok && !isWarningOnly(freshResult)) {
        setError(resultMessage);
        finishOperation("error", resultMessage);
      } else {
        finishOperation(isWarningOnly(freshResult) ? "warning" : "success", resultMessage);
        if (action === "suggest" && operationKind === "aiProposal") {
          setStep("review");
        }
      }
      return freshResult;
    } catch (runError) {
      const fallback = action === "suggest" ? "登録内容の生成に失敗しました。" : "仮登録に失敗しました。";
      setError(formatAdminError(runError, fallback));
      finishOperation("error", fallback);
      return null;
    } finally {
      setBusy(false);
    }
  }

  async function approve() {
    const appId = result?.appId ?? request.appId;
    if (!appId) {
      setError("承認にはアプリIDが必要です。");
      return;
    }
    beginOperation("approve");
    setError("");
    setMessage("");
    setLastAction("approve");
    try {
      const rawResult = await appStudioApprove(appId, approvalMode === "strict");
      const freshResult = await refreshRunResult(rawResult);
      setResult(freshResult);
      const resultMessage = messageForResult(freshResult, "approve");
      setMessage(resultMessage);
      if (!freshResult.ok && !isWarningOnly(freshResult)) {
        setError(resultMessage);
        finishOperation("error", resultMessage);
      } else {
        finishOperation(isWarningOnly(freshResult) ? "warning" : "success", resultMessage);
      }
    } catch (approveError) {
      const fallback = "承認処理に失敗しました。";
      setError(formatAdminError(approveError, fallback));
      finishOperation("error", fallback);
    } finally {
      setBusy(false);
    }
  }

  async function refreshResult() {
    if (!result?.appId && !result?.outputDir && !request.appId) {
      return;
    }
    beginOperation("refresh");
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
      const resultMessage = "結果を再読み込みしました。";
      setMessage(resultMessage);
      finishOperation("success", resultMessage);
    } catch (refreshError) {
      const fallback = "結果を再読み込みできませんでした。";
      setError(formatAdminError(refreshError, fallback));
      finishOperation("error", fallback);
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
        iconOverrideUsed: summary.iconOverrideUsed ?? runResult.iconOverrideUsed,
        selectedIconSource: summary.selectedIconSource ?? runResult.selectedIconSource,
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
    setMessage("AI提案を編集欄へ反映しました。内容を確認してから仮登録してください。");
  }

  function adoptIconOverride(iconOverride: AppStudioIconOverride) {
    update({ iconOverride });
    setMessage("PNGアイコン候補を採用しました。次回の仮登録で反映されます。");
  }

  function beginProposalLoad() {
    beginOperation("refresh", "AI提案を読み込んでいます。");
  }

  function finishProposalLoad(ok: boolean, messageText?: string) {
    finishOperation(ok ? "success" : "warning", messageText || (ok ? "AI提案を読み込みました。" : "AI提案を読み込めませんでした。"));
  }

  return (
    <div className="studio-wizard-layout studio-import-wizard">
      <section className="studio-wizard-main">
        <div className="admin-section-head">
          <div>
            <p className="dialog-kicker">新規登録</p>
            <h3>アプリ登録ウィザード</h3>
          </div>
          <span className="admin-status-pill">GUI beta</span>
        </div>

        <AppStudioStepNav currentStep={step} onStepChange={setStep} />
        <AppStudioOperationBanner operation={operation} />

        {step === "selectEntry" ? renderSelectEntry() : null}
        {step === "aiProposal" ? renderAiProposal() : null}
        {step === "review" ? renderReview() : null}
        {step === "register" ? renderRegister() : null}
      </section>

      <aside className="studio-wizard-side">
        <AppStudioImportSidebar
          step={step}
          operation={operation}
          request={request}
          preflight={preflight}
          result={result}
          aiProposal={aiProposal}
          message={message}
          error={error}
        />
      </aside>
    </div>
  );

  function renderSelectEntry() {
    return (
      <section className="studio-step-panel">
        <div className="studio-panel-head">
          <span className="studio-step-index">1</span>
          <div>
            <h4>登録するアプリを選択してください</h4>
            <p>アプリのメインファイルを選ぶと、アプリIDと表示名の候補を自動入力します。</p>
          </div>
        </div>

        <div className="studio-entry-row">
          <label className="admin-field">
            <span>アプリのメインファイル</span>
            <input type="text" value={request.entry} placeholder="C:\\work\\mytool\\main.py" onChange={handleEntryChange} />
          </label>
          <button className="secondary-button" type="button" onClick={() => void browseEntry()} disabled={busy} title={busy ? "処理中は参照できません" : "アプリのメインファイルを選択します"}>
            {busy && operation.kind === "pickingFile" ? <Loader2 className="studio-spinner" size={17} aria-hidden="true" /> : <FileSearch size={17} aria-hidden="true" />}
            参照
          </button>
        </div>

        <div className="admin-two-column">
          <label className="admin-field">
            <span>アプリID</span>
            <input type="text" value={request.appId ?? ""} placeholder="my_tool" onChange={(event) => update({ appId: event.target.value })} />
          </label>
          <label className="admin-field">
            <span>表示名</span>
            <input type="text" value={request.name ?? ""} placeholder="My Tool" onChange={(event) => update({ name: event.target.value })} />
          </label>
        </div>

        <div className="studio-build-summary">
          <strong>推奨実行方式: {recommendation.mode}</strong>
          <p>{recommendation.reason}</p>
        </div>

        <AppStudioCollapsibleSection title="詳細設定" summary="実行方式や環境作成オプションを調整できます。">
          <AppStudioBuildOptions
            request={request}
            onChange={(next) => {
              setRequest(next);
              setPreflight(null);
            }}
          />
        </AppStudioCollapsibleSection>

        <AppStudioPreflightPanel result={preflight} busy={busy} onRun={() => void runPreflight()} />

        <div className="studio-action-row">
          <button className="secondary-button" type="button" onClick={() => void runPreflight()} disabled={!canRun}>
            {operation.kind === "preflight" && busy ? <Loader2 className="studio-spinner" size={17} aria-hidden="true" /> : null}
            事前確認
          </button>
          <button className="primary-button" type="button" onClick={() => setStep("aiProposal")} disabled={!request.entry.trim()}>
            次へ
            <ChevronRight size={17} aria-hidden="true" />
          </button>
        </div>
      </section>
    );
  }

  function renderAiProposal() {
    return (
      <section className="studio-step-panel">
        <div className="studio-panel-head">
          <span className="studio-step-index">2</span>
          <div>
            <h4>AIで登録内容を作成します</h4>
            <p>管理者画面のAI設定を使い、説明文とPNGアイコン候補を作成します。採用は自動では行いません。</p>
          </div>
        </div>

        <AppStudioAiProposalPanel
          appId={request.appId}
          outputDir={result?.outputDir}
          result={result}
          busy={busy}
          compact
          onGenerate={() => run("suggest", "aiProposal")}
          onAdopt={adoptAiProposal}
          onIconAdopt={adoptIconOverride}
          selectedIconSource={request.iconOverride?.selectedIconSource}
          onProposalLoaded={setAiProposal}
          onLoadStart={beginProposalLoad}
          onLoadComplete={finishProposalLoad}
        />

        <div className="studio-action-row">
          <button className="secondary-button" type="button" onClick={() => setStep("review")}>
            AIを使わず手動入力へ進む
          </button>
          <button className="primary-button" type="button" onClick={() => setStep("review")}>
            内容確認へ
            <ChevronRight size={17} aria-hidden="true" />
          </button>
        </div>
      </section>
    );
  }

  function renderReview() {
    return (
      <section className="studio-step-panel">
        <div className="studio-panel-head">
          <span className="studio-step-index">3</span>
          <div>
            <h4>内容確認・修正</h4>
            <p>ランチャーでの見え方を確認し、AI提案を必要な項目だけ採用してください。</p>
          </div>
        </div>

        <AppStudioLauncherPreview appId={request.appId} name={request.name} metadata={request.metadata} proposal={aiProposal} iconOverride={request.iconOverride} />

        <AppStudioMetadataEditor metadata={request.metadata} proposal={aiProposal?.metadata ?? null} compact onChange={(metadata) => update({ metadata })} />

        <section className="studio-step">
          <div>
            <span className="studio-step-index">I</span>
            <h4>アイコン指示</h4>
          </div>
          <label className="admin-field">
            <span>Icon Prompt</span>
            <textarea
              className="studio-textarea"
              value={request.iconPrompt ?? ""}
              placeholder="シンプルな業務アプリ用アイコン。用途が伝わる色と形を指定してください。"
              onChange={(event) => update({ iconPrompt: event.target.value })}
            />
          </label>
          <p className="admin-muted">PNG候補はAI提案ステップで確認し、「このPNGを採用」したものだけ仮登録時に反映されます。</p>
        </section>

        <div className="studio-action-row">
          <button className="secondary-button" type="button" onClick={() => setStep("aiProposal")}>
            AI提案へ戻る
          </button>
          <button className="primary-button" type="button" onClick={() => setStep("register")}>
            登録へ進む
            <ChevronRight size={17} aria-hidden="true" />
          </button>
        </div>
      </section>
    );
  }

  function renderRegister() {
    return (
      <section className="studio-step-panel">
        <div className="studio-panel-head">
          <span className="studio-step-index">4</span>
          <div>
            <h4>仮登録・承認</h4>
            <p>登録用ファイルを生成し、仮登録と実行確認を行ってから承認します。</p>
          </div>
        </div>

        <div className="studio-build-summary">
          <strong>選択中の実行方式: {request.buildMode}</strong>
          <p>{BUILD_MODE_INFO[request.buildMode].description}</p>
        </div>

        <AppStudioCollapsibleSection title="詳細オプション" summary="requirements.lock、app_env、runtime検証を変更できます。">
          <AppStudioBuildOptions
            request={request}
            onChange={(next) => {
              setRequest(next);
              setPreflight(null);
            }}
          />
        </AppStudioCollapsibleSection>

        <AppStudioPreflightPanel result={preflight} busy={busy} onRun={() => void runPreflight()} />

        <div className="studio-action-row">
          <button className="secondary-button" type="button" onClick={() => void run("suggest", "suggest")} disabled={!canRun} title={!canRun ? "アプリのメインファイルを選択してください" : undefined}>
            {operation.kind === "suggest" && busy ? <Loader2 className="studio-spinner" size={17} aria-hidden="true" /> : <Play size={17} aria-hidden="true" />}
            登録内容を作成
          </button>
          <button className="primary-button" type="button" onClick={() => void run("apply", "apply")} disabled={!canRun} title={!canRun ? "アプリのメインファイルを選択してください" : undefined}>
            {operation.kind === "apply" && busy ? <Loader2 className="studio-spinner" size={17} aria-hidden="true" /> : <Rocket size={17} aria-hidden="true" />}
            仮登録して実行確認
          </button>
          <button className="primary-button" type="button" onClick={() => void approve()} disabled={busy || !canApprove}>
            {operation.kind === "approve" && busy ? <Loader2 className="studio-spinner" size={17} aria-hidden="true" /> : <ShieldCheck size={17} aria-hidden="true" />}
            承認して有効化
          </button>
        </div>

        <AppStudioResultPanel
          result={result}
          lastAction={lastAction}
          approvalMode={approvalMode}
          onApprovalModeChange={setApprovalMode}
          busy={busy}
          onApprove={() => void approve()}
          onRefresh={() => void refreshResult()}
        />

        <AppStudioCollapsibleSection title="実行ログ" summary="stdout / stderr と技術詳細を確認します。">
          <AppStudioRunLog busy={busy} result={result} />
        </AppStudioCollapsibleSection>
      </section>
    );
  }
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

function messageForResult(result: AppStudioRunResult, action: StudioAction): string {
  if (!result.ok && isWarningOnly(result)) {
    return "警告がありますが処理は完了しました。ログとレポートを確認してください。";
  }
  if (!result.ok) {
    return "処理に失敗しました。理由と次の操作を確認してください。";
  }
  if (action === "approve" || result.enabled) {
    return "承認して有効化しました。通常ランチャーで表示を確認してください。";
  }
  if (action === "apply") {
    return "仮登録と実行確認が完了しました。問題なければ承認してください。";
  }
  return "登録用ファイルを生成しました。内容を確認して次へ進んでください。";
}
