import { useEffect, useMemo, useState } from "react";
import type { ChangeEvent } from "react";
import { ChevronRight, FileSearch, ImagePlus, Loader2, Play, RefreshCw, Rocket, ShieldCheck } from "lucide-react";
import {
  appStudioApply,
  appStudioApprove,
  appStudioPickEntryFile,
  appStudioPreflight,
  appStudioReadAiProposal,
  appStudioReadResult,
  appStudioRegenerateIcon,
  appStudioSuggest,
} from "../../../lib/appStudioApi";
import { getAppStudioApprovalDecision } from "../../../lib/appStudioApproval";
import { suggestAppIdentity } from "../../../lib/appStudioIdentity";
import {
  apiIconCandidatesForProposal,
  iconSourceLabel,
  normalizeAppStudioIconProposal,
  selectedIconCandidateForProposal,
  summaryNumberValue,
  summaryStringValue,
} from "../../../lib/appStudioIconProposal";
import { cleanEditableMetadata, cleanIconOverride, createEmptyAppStudioMetadata } from "../../../lib/appStudioMetadata";
import { IMAGE_TEST_UPDATED_EVENT, imageApiFailureGuidance, loadImageGenerationTestResult, type StoredImageGenerationTestResult } from "../../../lib/imageApiHealth";
import type {
  AppStudioAiProposal,
  AppStudioAiIconCandidate,
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
  sourceRoot: "",
  appId: "",
  name: "",
  buildMode: "frozen-folder",
  iconPrompt: "",
  iconStyleCustom: "",
  metadata: createEmptyAppStudioMetadata(),
  createAppEnv: false,
  rebuildAppEnv: false,
  generateLock: true,
  buildFrozenFolder: true,
  verifyRuntime: true,
};

type StudioAction = "suggest" | "apply" | "approve";
type IconRevisionMode = "tweak" | "refine" | "redesign" | "fresh";
type IconRegenerationSpeedMode = "speed" | "standard" | "quality";
type IconImageQualityMode = "draft" | "standard" | "high";

const ICON_REVISION_MODES: Array<{ value: IconRevisionMode; label: string; description: string }> = [
  { value: "tweak", label: "tweak", description: "前案を強く残して微修正" },
  { value: "refine", label: "refine", description: "要素を残しつつ中修正" },
  { value: "redesign", label: "redesign", description: "構図や主役を変える大修正" },
  { value: "fresh", label: "fresh", description: "前案の継承を弱めた別案" },
];

const ICON_REGENERATION_SPEED_MODES: Array<{ value: IconRegenerationSpeedMode; label: string; description: string; count: number }> = [
  { value: "speed", label: "速度優先", description: "1候補だけ生成", count: 1 },
  { value: "standard", label: "標準", description: "2候補を比較", count: 2 },
  { value: "quality", label: "品質優先", description: "3候補を比較", count: 3 },
];

const ICON_IMAGE_QUALITY_MODES: Array<{ value: IconImageQualityMode; label: string; description: string }> = [
  { value: "draft", label: "draft", description: "低めのqualityでプレビュー" },
  { value: "standard", label: "standard", description: "通常品質" },
  { value: "high", label: "high", description: "最終確認向け" },
];

export function AppStudioImportWizard() {
  const [request, setRequest] = useState<AppStudioImportRequest>(INITIAL_REQUEST);
  const [step, setStep] = useState<AppStudioImportStep>("selectEntry");
  const [operation, setOperation] = useState<StudioOperationState>(IDLE_OPERATION);
  const [busy, setBusy] = useState(false);
  const [lastAction, setLastAction] = useState<StudioAction | null>(null);
  const [approvalMode, setApprovalMode] = useState<AppStudioApprovalMode>("strict");
  const [preflight, setPreflight] = useState<AppStudioPreflightResult | null>(null);
  const [result, setResult] = useState<AppStudioRunResult | null>(null);
  const [aiProposal, setAiProposal] = useState<AppStudioAiProposal | null>(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [iconRevisionPrompt, setIconRevisionPrompt] = useState("");
  const [iconRevisionMode, setIconRevisionMode] = useState<IconRevisionMode>("refine");
  const [iconRegenerationSpeedMode, setIconRegenerationSpeedMode] = useState<IconRegenerationSpeedMode>("speed");
  const [iconImageQualityMode, setIconImageQualityMode] = useState<IconImageQualityMode>("standard");
  const [revisionBaseCandidateId, setRevisionBaseCandidateId] = useState("");
  const [lastRevisionBase, setLastRevisionBase] = useState<AppStudioAiIconCandidate | null>(null);
  const [imageApiHealth, setImageApiHealth] = useState<StoredImageGenerationTestResult | null>(() => loadImageGenerationTestResult());

  const canRun = useMemo(() => request.entry.trim().length > 0 && !busy, [busy, request.entry]);
  const imageApiBlocked = imageApiHealth?.ok === false;
  const recommendation = useMemo(
    () => ({
      mode: "frozen-folder",
      reason: "通常ユーザー向け配布として、Pythonソースからfrozen-folder exeを作成して登録します。",
    }),
    [],
  );
  const approvalDecision = useMemo(() => getAppStudioApprovalDecision(result, approvalMode, busy), [approvalMode, busy, result]);
  const canApprove = approvalDecision.canApprove;

  useEffect(() => {
    const reloadHealth = () => setImageApiHealth(loadImageGenerationTestResult());
    window.addEventListener(IMAGE_TEST_UPDATED_EVENT, reloadHealth);
    window.addEventListener("storage", reloadHealth);
    return () => {
      window.removeEventListener(IMAGE_TEST_UPDATED_EVENT, reloadHealth);
      window.removeEventListener("storage", reloadHealth);
    };
  }, []);

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
      estimatedSeconds: estimateOperationSeconds(kind, result),
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
      estimatedSeconds: null,
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
        finishOperation("success", "事前確認が完了しました。このまま次へ進めます。");
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

  async function run(
    action: "suggest" | "apply",
    operationKind: "aiProposal" | "suggest" | "apply" = action,
    requestOverride: AppStudioImportRequest = request,
  ): Promise<AppStudioRunResult | null> {
    beginOperation(operationKind);
    setError("");
    setMessage("");
    setLastAction(action);
    try {
      const cleaned = cleanRequest(requestOverride);
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
      const fallback = action === "suggest" ? "登録内容の作成に失敗しました。" : "テスト登録と配布物検証に失敗しました。";
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
        exeReadinessStatus: summary.exeReadinessStatus ?? runResult.exeReadinessStatus,
        manualChecks: summary.manualChecks ?? runResult.manualChecks,
        secretBlockingCount: summary.secretBlockingCount ?? runResult.secretBlockingCount,
        secretWarningCount: summary.secretWarningCount ?? runResult.secretWarningCount,
        secretManualCheckCount: summary.secretManualCheckCount ?? runResult.secretManualCheckCount,
        secretScanReport: summary.secretScanReport ?? runResult.secretScanReport,
        secretBlockingFindings: summary.secretBlockingFindings ?? runResult.secretBlockingFindings,
        aiBlockedBySecretScan: summary.aiBlockedBySecretScan ?? runResult.aiBlockedBySecretScan,
        applyBlockedBySecretScan: summary.applyBlockedBySecretScan ?? runResult.applyBlockedBySecretScan,
        approvalBlockingWarningsCount: summary.approvalBlockingWarningsCount ?? runResult.approvalBlockingWarningsCount,
        nonBlockingWarningsCount: summary.nonBlockingWarningsCount ?? runResult.nonBlockingWarningsCount,
        infoCount: summary.infoCount ?? runResult.infoCount,
        unresolvedDistributionRisksCount: summary.unresolvedDistributionRisksCount ?? runResult.unresolvedDistributionRisksCount,
        approvalBlockingReasons: summary.approvalBlockingReasons ?? runResult.approvalBlockingReasons,
        nonBlockingWarningSummaries: summary.nonBlockingWarningSummaries ?? runResult.nonBlockingWarningSummaries,
        timingReport: summary.timingReport ?? runResult.timingReport,
        timingTotalSeconds: summary.timingTotalSeconds ?? runResult.timingTotalSeconds,
        timingEstimatedTotalSeconds: summary.timingEstimatedTotalSeconds ?? runResult.timingEstimatedTotalSeconds,
        timingActualTotalSeconds: summary.timingActualTotalSeconds ?? runResult.timingActualTotalSeconds,
        timingPredictionErrorSeconds: summary.timingPredictionErrorSeconds ?? runResult.timingPredictionErrorSeconds,
        timingPredictionSource: summary.timingPredictionSource ?? runResult.timingPredictionSource,
        timingWallClockTotalSeconds: summary.timingWallClockTotalSeconds ?? runResult.timingWallClockTotalSeconds,
        timingCliMeasuredTotalSeconds: summary.timingCliMeasuredTotalSeconds ?? runResult.timingCliMeasuredTotalSeconds,
        timingUnmeasuredOverheadSeconds: summary.timingUnmeasuredOverheadSeconds ?? runResult.timingUnmeasuredOverheadSeconds,
        timingPhases: summary.timingPhases ?? runResult.timingPhases,
        manifestEnabled: summary.manifestEnabled ?? runResult.manifestEnabled,
        approvalRecordStatus: summary.approvalRecordStatus ?? runResult.approvalRecordStatus,
        approvalRecordPath: summary.approvalRecordPath ?? runResult.approvalRecordPath,
        approvalFailureSummary: summary.approvalFailureSummary ?? runResult.approvalFailureSummary,
        verifyReleaseStatus: summary.verifyReleaseStatus ?? runResult.verifyReleaseStatus,
        verifyReleaseFailureSummary: summary.verifyReleaseFailureSummary ?? runResult.verifyReleaseFailureSummary,
        catalogVisible: summary.catalogVisible ?? runResult.catalogVisible,
        catalogEnabled: summary.catalogEnabled ?? runResult.catalogEnabled,
        catalogDisabledReason: summary.catalogDisabledReason ?? runResult.catalogDisabledReason,
        catalogLoadError: summary.catalogLoadError ?? runResult.catalogLoadError,
        catalogRoot: summary.catalogRoot ?? runResult.catalogRoot,
        appStudioRepoRoot: summary.appStudioRepoRoot ?? runResult.appStudioRepoRoot,
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
    setMessage("AI提案を編集欄へ反映しました。内容を確認してからテスト登録してください。");
  }

  function adoptIconOverride(iconOverride: AppStudioIconOverride) {
    update({ iconOverride });
    setMessage("PNGアイコン候補を採用しました。次回のテスト登録で反映されます。");
  }

  function beginProposalLoad() {
    beginOperation("refresh", "保存済みAI提案を読み込んでいます。");
  }

  function finishProposalLoad(ok: boolean, messageText?: string) {
    finishOperation(ok ? "success" : "warning", messageText || (ok ? "保存済みAI提案を読み込みました。" : "保存済みAI提案を読み込めませんでした。"));
  }

  function handleProposalLoaded(proposal: AppStudioAiProposal) {
    setAiProposal(proposal);
    const candidates = apiIconCandidatesForProposal(proposal);
    if (!revisionBaseCandidateId || !candidates.some((candidate) => candidate.candidateId === revisionBaseCandidateId)) {
      setRevisionBaseCandidateId(candidates[0]?.candidateId ?? "");
    }
  }

  async function regenerateIconProposal() {
    if (imageApiBlocked) {
      setError(`画像APIテストが失敗しているため、AI画像の再生成は実行できません。${imageApiFailureGuidance(imageApiHealth)}`);
      return;
    }
    const revision = iconRevisionPrompt.trim();
    if (!revision) {
      setError("アイコンの修正指示を入力してください。");
      return;
    }
    const baseCandidate = selectedIconCandidateForProposal(aiProposal, revisionBaseCandidateId);
    setLastRevisionBase(baseCandidate);
    const outputDir = aiProposal?.outputDir ?? result?.outputDir;
    const appId = result?.appId ?? aiProposal?.metadata.appId ?? request.appId;
    if (!outputDir || !appId) {
      setError("保存済み提案の出力先が見つかりません。先にAI提案を生成または読み込みしてください。");
      return;
    }
    const speed = ICON_REGENERATION_SPEED_MODES.find((mode) => mode.value === iconRegenerationSpeedMode) ?? ICON_REGENERATION_SPEED_MODES[0];
    const styleInstruction = request.iconStyleCustom?.trim();
    beginOperation("aiProposal", "アイコン画像だけを軽量再生成しています。");
    setError("");
    setMessage("");
    try {
      await appStudioRegenerateIcon({
        appId,
        outputDir,
        baseCandidateId: baseCandidate?.candidateId ?? revisionBaseCandidateId,
        userRevisionInstruction: revision,
        revisionMode: iconRevisionMode,
        iconStylePreset: styleInstruction ? "custom" : undefined,
        iconStyleCustom: styleInstruction || undefined,
        candidateCount: speed.count,
        imageQualityMode: iconImageQualityMode,
      });
      beginOperation("refresh", "再生成したアイコン候補を読み込んでいます。");
      const loaded = await appStudioReadAiProposal(appId, outputDir);
      handleProposalLoaded(loaded);
      update({ iconPrompt: buildIconRevisionContext(baseCandidate, request.iconOverride, revision, iconRevisionMode) });
      const apiSeconds = imageApiSeconds(loaded);
      finishOperation(loaded.ok ? "success" : "warning", loaded.ok ? `アイコン候補を再生成して読み込みました。画像API: ${apiSeconds}` : "再生成後の提案ファイルを読み込めませんでした。");
    } catch (regenerateError) {
      const fallback = "アイコン候補を再生成できませんでした。";
      setError(formatAdminError(regenerateError, fallback));
      finishOperation("error", fallback);
    } finally {
      setBusy(false);
    }
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

        <label className="admin-field">
          <span>ソース範囲</span>
          <input type="text" value={request.sourceRoot ?? ""} placeholder="未入力ならメインファイルのフォルダ" onChange={(event) => update({ sourceRoot: event.target.value })} />
        </label>

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
          <strong>登録方式: 配布用exe固定</strong>
          <p>{recommendation.reason}</p>
        </div>

        <AppStudioCollapsibleSection title="実行予定" summary="requirements.lock、build_env、frozen-folder build、配布物検証を固定で実行します。">
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
            事前確認を実行
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

        {renderIconStyleControls()}
        {imageApiBlocked ? <ImageApiBlockedBanner result={imageApiHealth} /> : null}

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
          selectedIconCandidateId={request.iconOverride?.candidateId}
          onProposalLoaded={handleProposalLoaded}
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

  function renderIconStyleControls() {
    return (
      <section className="studio-icon-style-panel">
        <div>
          <p className="dialog-kicker">Icon style</p>
          <h4>スタイルは文章で指定</h4>
        </div>
        <p className="admin-muted">
          プリセットは使わず、アイコンPromptまたは下の補足にスタイルを文章で書いてください。ここに書いた内容はユーザー指示として扱い、別スタイルで上書きしません。
        </p>
        <label className="admin-field">
          <span>スタイル補足</span>
          <input
            type="text"
            value={request.iconStyleCustom ?? ""}
            placeholder="例: iPhoneのLiquid Glass風。赤いPDFエンブレムを中心に、半透明で柔らかい反射、変形していく動き。"
            onChange={(event) => update({ iconStyleCustom: event.target.value, iconStylePreset: event.target.value.trim() ? "custom" : undefined })}
          />
        </label>
        {imageApiBlocked ? <p className="admin-warning">画像APIテストが成功していないため、スタイル補足の効果確認はAPI画像候補が生成された場合に限られます。</p> : null}
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

        {renderIconRevisionPanel()}

        <AppStudioMetadataEditor metadata={request.metadata} proposal={aiProposal?.metadata ?? null} compact onChange={(metadata) => update({ metadata })} />

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

  function renderIconRevisionPanel() {
    const normalizedIcon = aiProposal?.icon ? normalizeAppStudioIconProposal(aiProposal.icon, request.iconOverride?.selectedIconSource) : null;
    const revisionCandidates = normalizedIcon?.apiCandidates ?? [];
    const baseCandidate = selectedIconCandidateForProposal(aiProposal, revisionBaseCandidateId);
    const latestCandidate = revisionCandidates[0] ?? null;
    const baseIcon = lastRevisionBase?.pngDataUrl ?? baseCandidate?.pngDataUrl ?? null;
    const latestIcon = latestCandidate?.pngDataUrl ?? null;
    const adoptedIcon = request.iconOverride?.pngDataUrl ?? null;
    const imageSummary = aiProposal?.icon.imageApiSummary;
    const savedRevisionInstruction = summaryStringValue(imageSummary?.userRevisionInstruction ?? imageSummary?.user_revision_instruction);
    const finalImageApiPrompt = latestCandidate?.prompt || summaryStringValue(imageSummary?.finalImageApiPrompt ?? imageSummary?.final_image_api_prompt);
    const intermediatePrompt = aiProposal?.icon.promptRevision || request.iconPrompt || "";
    return (
      <section className="studio-icon-revision-panel">
        <div className="admin-section-head">
          <div>
            <p className="dialog-kicker">アイコン再生成</p>
            <h4>AIアイコンを修正する</h4>
          </div>
          <span className="admin-status-pill">採用中: {iconSourceLabel(request.iconOverride?.selectedIconSource)}</span>
        </div>
        {imageApiBlocked ? <ImageApiBlockedBanner result={imageApiHealth} /> : null}
        <div className="studio-icon-revision-modes" role="group" aria-label="icon revision mode">
          {ICON_REVISION_MODES.map((mode) => (
            <button
              key={mode.value}
              className={`studio-segment-button${iconRevisionMode === mode.value ? " selected" : ""}`}
              type="button"
              onClick={() => setIconRevisionMode(mode.value)}
              title={mode.description}
            >
              <strong>{mode.label}</strong>
              <span>{mode.description}</span>
            </button>
          ))}
        </div>
        <div className="studio-icon-revision-modes" role="group" aria-label="icon regeneration candidate count">
          {ICON_REGENERATION_SPEED_MODES.map((mode) => (
            <button
              key={mode.value}
              className={`studio-segment-button${iconRegenerationSpeedMode === mode.value ? " selected" : ""}`}
              type="button"
              onClick={() => setIconRegenerationSpeedMode(mode.value)}
              title={mode.description}
            >
              <strong>{mode.label}</strong>
              <span>{mode.description}</span>
            </button>
          ))}
        </div>
        <div className="studio-icon-revision-modes" role="group" aria-label="icon image quality mode">
          {ICON_IMAGE_QUALITY_MODES.map((mode) => (
            <button
              key={mode.value}
              className={`studio-segment-button${iconImageQualityMode === mode.value ? " selected" : ""}`}
              type="button"
              onClick={() => setIconImageQualityMode(mode.value)}
              title={mode.description}
            >
              <strong>{mode.label}</strong>
              <span>{mode.description}</span>
            </button>
          ))}
        </div>
        <label className="admin-field">
          <span>修正元の候補</span>
          <select value={revisionBaseCandidateId} onChange={(event) => setRevisionBaseCandidateId(event.target.value)}>
            {revisionCandidates.map((candidate) => (
              <option key={candidate.candidateId} value={candidate.candidateId}>
                候補 {candidate.number}: API生成 / {candidate.resolution || "unknown"}
              </option>
            ))}
          </select>
        </label>
        <div className="studio-icon-compare">
          <div>
            <span>修正元候補</span>
            {baseIcon ? <img className="studio-icon-preview" src={baseIcon} alt="修正元のPNGアイコン候補" /> : <div className="studio-icon-empty">候補なし</div>}
          </div>
          <div>
            <span>現在採用中</span>
            {adoptedIcon ? <img className="studio-icon-preview" src={adoptedIcon} alt="現在採用中のPNGアイコン" /> : <div className="studio-icon-empty">未採用</div>}
          </div>
          <div>
            <span>最新候補</span>
            {latestIcon ? <img className="studio-icon-preview primary-icon-preview" src={latestIcon} alt="最新のPNGアイコン候補" /> : <div className="studio-icon-empty">候補なし</div>}
          </div>
        </div>
        <label className="admin-field">
          <span>修正指示</span>
          <textarea
            className="studio-textarea"
            value={iconRevisionPrompt}
            placeholder="例: もっとシンプルで小サイズでも見やすく。帳票・登録の意味が伝わる落ち着いた緑系にしたい。"
            onChange={(event) => setIconRevisionPrompt(event.target.value)}
          />
        </label>
        <div className="studio-prompt-summary">
          <div>
            <strong>初回Prompt</strong>
            <p>{aiProposal?.icon.promptInitial || "まだ生成されていません。"}</p>
          </div>
          <div>
            <strong>ユーザー修正指示</strong>
            <p>{iconRevisionPrompt || savedRevisionInstruction || "修正指示を入力すると次回生成に使われます。"}</p>
          </div>
          <div>
            <strong>AI/中間Prompt</strong>
            <p>{intermediatePrompt || "まだ生成されていません。"}</p>
          </div>
          <div>
            <strong>最終画像API Prompt</strong>
            <p>{finalImageApiPrompt || "再生成後、実際に画像APIへ渡したPromptを表示します。"}</p>
          </div>
        </div>
        <div className="studio-action-row">
          <button className="secondary-button" type="button" onClick={() => update({ iconPrompt: iconRevisionPrompt })} disabled={!iconRevisionPrompt.trim()}>
            <ImagePlus size={17} aria-hidden="true" />
            指示を保存
          </button>
          <button className="primary-button" type="button" onClick={() => void regenerateIconProposal()} disabled={busy || !iconRevisionPrompt.trim() || imageApiBlocked}>
            {operation.kind === "aiProposal" && busy ? <Loader2 className="studio-spinner" size={17} aria-hidden="true" /> : <RefreshCw size={17} aria-hidden="true" />}
            この内容で再生成
          </button>
        </div>
        <p className="admin-muted">再生成はAI APIを呼び、最新の提案ファイルとPNG候補を作り直します。採用は自動では行いません。</p>
      </section>
    );
  }

  function renderRegister() {
    return (
      <section className="studio-step-panel">
        <div className="studio-panel-head">
          <span className="studio-step-index">4</span>
          <div>
            <h4>登録・承認</h4>
            <p>作成、テスト、本登録の3段階で進めます。正式に有効化されるのは承認後です。</p>
          </div>
        </div>

        <div className="studio-build-summary">
          <strong>配布用exeを作成して登録します</strong>
          <p>Pythonソースを解析し、内部build_envでPyInstaller frozen-folderを作成してから配布物を検証します。</p>
        </div>

        <AppStudioCollapsibleSection title="実行予定" summary="固定ポリシーを確認できます。通常新規登録では旧オプションを変更できません。">
          <AppStudioBuildOptions
            request={request}
            onChange={(next) => {
              setRequest(next);
              setPreflight(null);
            }}
          />
        </AppStudioCollapsibleSection>

        <AppStudioPreflightPanel result={preflight} busy={busy} onRun={() => void runPreflight()} />

        <div className="studio-register-action-grid">
          <button className="studio-register-action" type="button" onClick={() => void run("suggest", "suggest")} disabled={!canRun} title={!canRun ? "アプリのメインファイルを選択してください" : undefined}>
            {operation.kind === "suggest" && busy ? <Loader2 className="studio-spinner" size={18} aria-hidden="true" /> : <Play size={18} aria-hidden="true" />}
            <span>
              <strong>{operation.kind === "suggest" && busy ? "登録内容を作成しています..." : "登録内容を作成"}</strong>
              <small>設定ファイルや出力物を作成します。まだToolHubへ有効化しません。</small>
            </span>
          </button>
          <button className="studio-register-action primary" type="button" onClick={() => void run("apply", "apply")} disabled={!canRun} title={!canRun ? "アプリのメインファイルを選択してください" : undefined}>
            {operation.kind === "apply" && busy ? <Loader2 className="studio-spinner" size={18} aria-hidden="true" /> : <Rocket size={18} aria-hidden="true" />}
            <span>
              <strong>{operation.kind === "apply" && busy ? "配布物検証を実行しています..." : "テスト登録して配布物検証"}</strong>
              <small>一時的に登録し、exeと同梱ファイルが揃っているか確認します。</small>
            </span>
          </button>
          <button className="studio-register-action primary" type="button" onClick={() => void approve()} disabled={!canApprove} title={canApprove ? "承認して有効化します" : approvalDecision.reason}>
            {operation.kind === "approve" && busy ? <Loader2 className="studio-spinner" size={18} aria-hidden="true" /> : <ShieldCheck size={18} aria-hidden="true" />}
            <span>
              <strong>{operation.kind === "approve" && busy ? "承認して有効化しています..." : "承認して有効化"}</strong>
              <small>このアプリを正式に利用可能な状態にします。</small>
            </span>
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

function ImageApiBlockedBanner({ result }: { result: StoredImageGenerationTestResult | null }) {
  if (!result || result.ok) {
    return null;
  }
  return (
    <div className="studio-image-api-blocker" role="alert">
      <strong>画像APIテストが失敗しています。AI画像候補と再生成はブロック中です。</strong>
      <p>{imageApiFailureGuidance(result)}</p>
      <p>AI画像候補は作成されません。候補未採用時はToolHub共通default iconが使用されます。メタデータ編集と手動入力は継続できます。</p>
    </div>
  );
}

function buildIconRevisionContext(
  baseCandidate: AppStudioAiIconCandidate | null,
  iconOverride: AppStudioIconOverride | undefined,
  userInstruction: string,
  mode: IconRevisionMode,
): string {
  const adopted = iconOverride?.candidateId && baseCandidate?.candidateId === iconOverride.candidateId ? "adopted" : "not_adopted";
  const strength = revisionModeStrength(mode);
  const previousPromptPolicy =
    mode === "fresh"
      ? "Use the previous prompt only as a weak negative/reference; create a different concept."
      : mode === "redesign"
        ? "Do not strongly inherit the previous prompt; change composition, main motif, or color."
        : mode === "tweak"
          ? "Strongly preserve the previous candidate while applying a small targeted change."
          : "Preserve the useful idea, but visibly improve the composition or motif.";
  return [
    "USER ICON REQUEST - PRIMARY SOURCE OF TRUTH:",
    userInstruction,
    "",
    "Icon revision context - secondary",
    `revision_mode: ${mode}`,
    `change_strength: ${strength.change}`,
    `previous_candidate_id: ${baseCandidate?.candidateId || "unknown"}`,
    "previous_prompt: omitted from the saved UI request so it cannot override the user's instruction",
    `previous_status: ${baseCandidate?.status || "unknown"}`,
    `previous_source: ${baseCandidate?.source || "unknown"}`,
    `previous_resolution: ${baseCandidate?.resolution || "unknown"}`,
    `previous_adoption_state: ${adopted}`,
    `preserve_elements: ${strength.preserve}`,
    `change_elements: ${strength.change}`,
    "avoid_elements: only when not requested by the user: generic abstract shapes, document-only, gear-only, check-only, nodes-only, initial-letter-only, tiny text, crowded UI screenshots",
    `previous_prompt_policy: ${previousPromptPolicy}`,
    mode === "redesign"
      ? "divergence_requirement: must change the main motif or composition; color-only changes are insufficient."
      : mode === "fresh"
        ? "divergence_requirement: create a substantially different concept family, composition, primary motif, and color focus."
        : "divergence_requirement: the regenerated concept must visibly change at least one of composition, primary motif, or color focus from the previous candidate.",
    "priority_rule: the user request above overrides generated app metadata, previous prompts, style presets, and candidate concepts.",
    "image_edit_api: pass the selected previous PNG as an input image when available",
  ].join("\n");
}

function revisionModeStrength(mode: IconRevisionMode): { preserve: string; change: string } {
  if (mode === "tweak") {
    return {
      preserve: "primary motif, action flow, color family, ToolHub consistency, small-size readability",
      change: "one focused detail requested by the user",
    };
  }
  if (mode === "redesign") {
    return {
      preserve: "app function and input/output meaning only",
      change: "composition, main silhouette, material treatment, and at least one color accent",
    };
  }
  if (mode === "fresh") {
    return {
      preserve: "only the app function, input objects, output objects, and generic avoid rules",
      change: "new concept family, new composition, new primary motif, new color focus",
    };
  }
  return {
    preserve: "best app-specific idea, readable action flow, ToolHub quality",
    change: "composition clarity, motif specificity, and visual polish",
  };
}

function imageApiSeconds(proposal: AppStudioAiProposal): string {
  const seconds = normalizeAppStudioIconProposal(proposal.icon).diagnosis.imageApiSeconds;
  return seconds === null ? "未記録" : `${seconds.toFixed(1)}秒`;
}

function estimateOperationSeconds(kind: StudioOperationKind, result: AppStudioRunResult | null): number | null {
  if (kind === "apply") {
    return result?.timingTotalSeconds ?? result?.timingEstimatedTotalSeconds ?? 600;
  }
  if (kind === "suggest" || kind === "aiProposal") {
    return 60;
  }
  if (kind === "approve") {
    return 90;
  }
  if (kind === "refresh" || kind === "preflight") {
    return 5;
  }
  return null;
}

function cleanRequest(request: AppStudioImportRequest): AppStudioImportRequest {
  const styleInstruction = request.iconStyleCustom?.trim();
  return {
    ...request,
    entry: request.entry.trim(),
    sourceRoot: request.sourceRoot?.trim() || undefined,
    appId: request.appId?.trim() || undefined,
    name: request.name?.trim() || undefined,
    buildMode: "frozen-folder",
    createAppEnv: false,
    rebuildAppEnv: false,
    generateLock: true,
    buildFrozenFolder: true,
    verifyRuntime: true,
    iconPrompt: request.iconPrompt?.trim() || undefined,
    iconStylePreset: styleInstruction ? "custom" : undefined,
    iconStyleCustom: styleInstruction || undefined,
    iconRevisionImage: request.iconRevisionImage?.startsWith("data:image/png;base64,") ? request.iconRevisionImage : undefined,
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
  if (action === "approve") {
    if (result.manifestEnabled === true && result.catalogVisible === true) {
      return "承認して有効化しました。ホームの更新後にアプリ一覧へ表示されます。";
    }
    if (result.manifestEnabled === true) {
      return `承認は完了しましたが、ホーム表示の確認が未完了です。理由: ${result.catalogDisabledReason || result.catalogLoadError || "catalog_visible=false"}`;
    }
    return `承認は完了していません。理由: ${result.approvalFailureSummary || result.verifyReleaseFailureSummary || "manifest enabled=false"}`;
  }
  if (result.enabled) {
    return "承認して有効化しました。通常ランチャーで表示を確認してください。";
  }
  if (action === "apply") {
    return "テスト登録と配布物検証が完了しました。問題なければ承認してください。";
  }
  return "登録内容を作成しました。内容を確認して次へ進んでください。";
}
