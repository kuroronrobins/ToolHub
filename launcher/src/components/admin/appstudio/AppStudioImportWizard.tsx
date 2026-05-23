import { useEffect, useMemo, useState } from "react";
import type { ChangeEvent } from "react";
import { AlertTriangle, CheckCircle2, ChevronRight, CircleAlert, FileSearch, ImagePlus, Loader2, RefreshCw, Rocket, ShieldCheck } from "lucide-react";
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
import { getAppStudioRunResultMessage, isAppStudioWarningOnly } from "../../../lib/appStudioRunResult";
import { suggestAppIdentity } from "../../../lib/appStudioIdentity";
import {
  apiIconCandidatesForProposal,
  iconSourceLabel,
  normalizeAppStudioIconProposal,
  selectedIconCandidateForProposal,
} from "../../../lib/appStudioIconProposal";
import { cleanEditableMetadata, cleanIconOverride, createEmptyAppStudioMetadata, generatedMetadataSuggestion } from "../../../lib/appStudioMetadata";
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
import { AppStudioRunLog } from "./AppStudioRunLog";
import { AppStudioStepNav, type AppStudioImportStep } from "./AppStudioStepNav";

const INITIAL_REQUEST: AppStudioImportRequest = {
  entry: "",
  sourceRoot: "",
  appId: "",
  name: "",
  buildMode: "shared-env",
  iconPrompt: "",
  iconStyleCustom: "",
  metadata: createEmptyAppStudioMetadata(),
  showTerminal: false,
  createAppEnv: false,
  rebuildAppEnv: false,
  generateLock: true,
  buildFrozenFolder: false,
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
const MAX_ICON_PNG_BYTES = 10 * 1024 * 1024;

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
  const approvalDecision = useMemo(() => getAppStudioApprovalDecision(result, approvalMode, busy, lastAction), [approvalMode, busy, lastAction, result]);
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

  async function runPreflightAndAdvance() {
    const check = await runPreflight();
    if (check?.ok) {
      setStep("aiProposal");
      await run("suggest", "aiProposal");
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
      const resultMessage = getAppStudioRunResultMessage(freshResult, action);
      setMessage(resultMessage);
      if (!freshResult.ok && !isAppStudioWarningOnly(freshResult)) {
        setError(resultMessage);
        finishOperation("error", resultMessage);
      } else {
        finishOperation(isAppStudioWarningOnly(freshResult) ? "warning" : "success", resultMessage);
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
      const resultMessage = getAppStudioRunResultMessage(freshResult, "approve");
      setMessage(resultMessage);
      if (!freshResult.ok && !isAppStudioWarningOnly(freshResult)) {
        setError(resultMessage);
        finishOperation("error", resultMessage);
      } else {
        finishOperation(isAppStudioWarningOnly(freshResult) ? "warning" : "success", resultMessage);
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

  async function handleUploadedIconChange(event: ChangeEvent<HTMLInputElement>) {
    const input = event.currentTarget;
    const file = input.files?.[0];
    input.value = "";
    if (!file) {
      return;
    }
    setError("");
    try {
      if (!file.name.toLowerCase().endsWith(".png")) {
        throw new Error("PNGファイルを選択してください。");
      }
      if (file.size > MAX_ICON_PNG_BYTES) {
        throw new Error("PNGファイルが大きすぎます。10MB以下のファイルを選択してください。");
      }
      const header = new Uint8Array(await file.slice(0, 8).arrayBuffer());
      if (!isPngSignature(header)) {
        throw new Error("選択したファイルはPNGとして読み込めません。");
      }
      const pngDataUrl = await readFileAsDataUrl(file);
      update({
        iconOverride: {
          selectedIconSource: "uploaded_png",
          pngDataUrl,
          sourcePrompt: file.name,
        },
      });
      setMessage(`PNGアイコン「${file.name}」を採用しました。次回の登録内容作成またはテスト登録で使用します。`);
    } catch (uploadError) {
      setError(formatAdminError(uploadError, "PNGアイコンを読み込めませんでした。"));
    }
  }

  function clearUploadedIcon() {
    update({ iconOverride: undefined });
    setMessage("PNG指定を解除しました。通常のAIアイコン候補フローを使います。");
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
          approvalMode={approvalMode}
          lastAction={lastAction}
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
            <h4>登録するアプリ</h4>
            <p>アプリのメインファイルを選択し、ToolHub 上の表示名を確認します。</p>
          </div>
        </div>

        <div className="studio-entry-row">
          <label className="admin-field">
            <span>メインファイル</span>
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

        <div className="studio-policy-strip">
          <CheckCircle2 size={18} aria-hidden="true" />
          <span>通常登録は共有ランタイム方式で実行します。方式の選択は不要です。</span>
        </div>

        <label className="admin-toggle">
          <input type="checkbox" checked={Boolean(request.showTerminal)} onChange={(event) => update({ showTerminal: event.target.checked })} />
          起動時にターミナルを表示
        </label>
        <p className="admin-muted">入力待ちやコンソール操作が必要なCLIアプリで有効にします。</p>

        <AppStudioCollapsibleSection title="登録方式の詳細" summary="requirements.lock、共有ランタイム作成または再利用、起動検証を固定で実行します。">
          <AppStudioBuildOptions
            request={request}
            onChange={(next) => {
              setRequest(next);
              setPreflight(null);
            }}
          />
        </AppStudioCollapsibleSection>

        <AppStudioPreflightPanel result={preflight} busy={busy} onRun={() => void runPreflight()} showRunButton={false} />

        <div className="studio-action-row">
          <button className="secondary-button" type="button" disabled>
            戻る
          </button>
          <button className="primary-button" type="button" onClick={() => void runPreflightAndAdvance()} disabled={!canRun}>
            {operation.kind === "preflight" && busy ? <Loader2 className="studio-spinner" size={17} aria-hidden="true" /> : null}
            事前確認して次へ
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
            <h4>ランチャーに表示する内容</h4>
            <p>利用者に見える名前、説明、カテゴリ、アイコンを確認します。AI提案はこの画面に進む時に自動作成します。</p>
          </div>
        </div>

        {preflight?.ok ? (
          <div className="studio-status-banner ok">
            <CheckCircle2 size={19} aria-hidden="true" />
            <div>
              <strong>事前確認は完了しています</strong>
              <span>表示内容を確定すると、テスト登録へ進めます。</span>
            </div>
          </div>
        ) : null}

        <AppStudioLauncherPreview appId={request.appId} name={request.name} metadata={request.metadata} proposal={aiProposal} iconOverride={request.iconOverride} />

        <AppStudioMetadataEditor metadata={request.metadata} proposal={generatedMetadataSuggestion(aiProposal?.metadata)} compact onChange={(metadata) => update({ metadata })} />

        {renderIconCompactPanel()}

        <AppStudioCollapsibleSection title="AI提案の詳細" summary="必要な場合だけ開き、説明文やPNGアイコン候補を作成します。">
          {renderIconStyleControls()}
          {imageApiBlocked ? <ImageApiBlockedBanner result={imageApiHealth} /> : null}
          <AppStudioAiProposalPanel
            appId={request.appId}
            outputDir={result?.outputDir}
            result={result}
            busy={busy}
            compact
            onGenerate={() => run("suggest", "suggest")}
            onAdopt={adoptAiProposal}
            onIconAdopt={adoptIconOverride}
            selectedIconSource={request.iconOverride?.selectedIconSource}
            selectedIconCandidateId={request.iconOverride?.candidateId}
            onProposalLoaded={handleProposalLoaded}
            onLoadStart={beginProposalLoad}
            onLoadComplete={finishProposalLoad}
          />
          {aiProposal?.icon ? renderIconRevisionPanel() : null}
        </AppStudioCollapsibleSection>

        <div className="studio-action-row">
          <button className="secondary-button" type="button" onClick={() => setStep("selectEntry")}>
            戻る
          </button>
          <button className="primary-button" type="button" onClick={() => setStep("review")}>
            表示内容を確定して次へ
            <ChevronRight size={17} aria-hidden="true" />
          </button>
        </div>
      </section>
    );
  }

  function renderIconCompactPanel() {
    const uploadedIcon = request.iconOverride?.selectedIconSource === "uploaded_png" ? request.iconOverride.pngDataUrl : "";
    const adoptedIcon = request.iconOverride?.pngDataUrl;
    return (
      <section className="studio-icon-compact-panel">
        <div className="admin-section-head">
          <div>
            <p className="dialog-kicker">アイコン</p>
            <h4>ランチャー用PNG</h4>
          </div>
          <span className="admin-status-pill">採用中: {iconSourceLabel(request.iconOverride?.selectedIconSource)}</span>
        </div>
        <div className="studio-icon-compact-body">
          <div className="studio-preview-icon">
            {adoptedIcon ? <img src={adoptedIcon} alt="採用中のPNGアイコン" /> : <span>{(request.name || request.appId || "A").slice(0, 1).toUpperCase()}</span>}
          </div>
          <div>
            <p className="admin-muted">PNGを指定した場合は、その画像を icon.png として使います。AI候補は下の詳細から作成できます。</p>
            <div className="studio-action-row compact-left">
              <label className="secondary-button" title={busy ? "処理中は選択できません" : "PNGアイコンを選択します"}>
                <ImagePlus size={17} aria-hidden="true" />
                PNGを選択
                <input type="file" accept="image/png,.png" disabled={busy} onChange={(event) => void handleUploadedIconChange(event)} style={{ display: "none" }} />
              </label>
              <button className="secondary-button" type="button" onClick={clearUploadedIcon} disabled={!uploadedIcon || busy}>
                解除
              </button>
              <button className="secondary-button" type="button" onClick={() => void run("suggest", "suggest")} disabled={!canRun}>
                {operation.kind === "suggest" && busy ? <Loader2 className="studio-spinner" size={17} aria-hidden="true" /> : <RefreshCw size={17} aria-hidden="true" />}
                AIで候補を作成
              </button>
            </div>
          </div>
        </div>
        {imageApiBlocked ? <p className="admin-warning">画像APIテストが成功していないため、AI画像候補は作成できません。PNG指定または共通アイコンで進められます。</p> : null}
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
    const hasResult = Boolean(result);
    const hasBlockingIssue = Boolean(result && (!result.ok && !isAppStudioWarningOnly(result)));
    return (
      <section className="studio-step-panel">
        <div className="studio-panel-head">
          <span className="studio-step-index">3</span>
          <div>
            <h4>テスト登録</h4>
            <p>正式に有効化する前に、一時登録、起動確認、配布物検証を実行します。</p>
          </div>
        </div>

        {result ? (
          <div className={`studio-status-banner ${canApprove ? "ok" : hasBlockingIssue ? "error" : "warn"}`}>
            {canApprove ? <CheckCircle2 size={19} aria-hidden="true" /> : hasBlockingIssue ? <CircleAlert size={19} aria-hidden="true" /> : <AlertTriangle size={19} aria-hidden="true" />}
            <div>
              <strong>{canApprove ? "承認できます" : hasBlockingIssue ? "修正が必要です" : "確認が必要です"}</strong>
              <span>{canApprove ? "テスト登録と配布物検証が完了しました。内容を確認して承認へ進めます。" : approvalDecision.reason}</span>
            </div>
          </div>
        ) : (
          <div className="studio-status-banner">
            <Rocket size={19} aria-hidden="true" />
            <div>
              <strong>テスト登録はまだ実行していません</strong>
              <span>表示内容を使って、登録前の実行確認を行います。</span>
            </div>
          </div>
        )}

        {renderTestResultSummary()}

        {result?.manualChecks?.length ? (
          <div className="studio-manual-checks warning">
            <strong>手動確認が必要です</strong>
            <p>初回ログインや外部サービス連携は自動検証の対象外です。管理者が実機で確認してください。</p>
          </div>
        ) : null}

        <section className="studio-issue-guide">
          <h4>問題がある場合</h4>
          <dl>
            <div>
              <dt>起動に失敗した場合</dt>
              <dd>ログを確認してからテスト登録を再実行します。</dd>
            </div>
            <div>
              <dt>手動確認が残る場合</dt>
              <dd>確認内容をメモして承認画面で判断します。</dd>
            </div>
          </dl>
        </section>

        {renderTechnicalDetails()}

        <div className="studio-action-row">
          <button className="secondary-button" type="button" onClick={() => setStep("aiProposal")}>
            戻る
          </button>
          {hasResult ? (
            <button className="secondary-button" type="button" onClick={() => void run("apply", "apply")} disabled={!canRun}>
              {operation.kind === "apply" && busy ? <Loader2 className="studio-spinner" size={17} aria-hidden="true" /> : null}
              テスト登録を再実行
            </button>
          ) : null}
          {canApprove ? (
            <button className="primary-button" type="button" onClick={() => setStep("register")}>
              承認へ進む
              <ChevronRight size={17} aria-hidden="true" />
            </button>
          ) : (
            <button className="primary-button" type="button" onClick={() => void run("apply", "apply")} disabled={!canRun}>
              {operation.kind === "apply" && busy ? <Loader2 className="studio-spinner" size={17} aria-hidden="true" /> : <Rocket size={17} aria-hidden="true" />}
              {hasResult ? "テスト登録を実行" : "テスト登録を実行"}
            </button>
          )}
        </div>
      </section>
    );
  }

  function renderTestResultSummary() {
    const manualCheckCount = result?.manualChecks?.length ?? 0;
    return (
      <section className="studio-compact-result">
        <div className="admin-section-head">
          <div>
            <p className="dialog-kicker">結果</p>
            <h4>テスト登録の結果</h4>
          </div>
          <StatusChip tone={result ? (canApprove ? "ok" : "warn") : "idle"}>{result ? (canApprove ? "承認可能" : "確認中") : "未実行"}</StatusChip>
        </div>
        <dl>
          <ResultSummaryRow label="アプリID" value={result?.appId || request.appId || "-"} />
          <ResultSummaryRow label="表示名" value={request.name || "-"} />
          <ResultSummaryRow label="登録方式" value={buildModeLabel(result?.selectedBuildMode || request.buildMode)} />
          <ResultSummaryRow label="起動確認" value={result ? statusLabel(result.executionStatus) : "未実行"} tone={statusTone(result?.executionStatus)} />
          <ResultSummaryRow label="配布物検証" value={result ? statusLabel(result.exeReadinessStatus || result.runtimeStatus) : "未実行"} tone={statusTone(result?.exeReadinessStatus || result?.runtimeStatus)} />
          <ResultSummaryRow label="手動確認" value={manualCheckCount ? `${manualCheckCount}件` : result ? "なし" : "未実行"} tone={manualCheckCount ? "warn" : result ? "ok" : "idle"} />
        </dl>
      </section>
    );
  }

  function renderTechnicalDetails() {
    return (
      <div className="studio-detail-stack">
        <AppStudioCollapsibleSection title="技術詳細" summary="必要な場合だけ、承認判定や出力情報を確認します。">
          <dl className="studio-technical-list">
            <ResultSummaryRow label="処理結果" value={result ? (result.ok ? "成功" : "失敗") : "未実行"} tone={result ? (result.ok ? "ok" : "error") : "idle"} />
            <ResultSummaryRow label="承認判定" value={approvalDecision.reason} tone={canApprove ? "ok" : "warn"} />
            <ResultSummaryRow label="配布リスク" value={`${result?.approvalBlockingWarningsCount ?? 0}件`} tone={result?.approvalBlockingWarningsCount ? "error" : "ok"} />
            <ResultSummaryRow label="参考警告" value={`${result?.nonBlockingWarningsCount ?? 0}件`} tone={result?.nonBlockingWarningsCount ? "warn" : "ok"} />
            <ResultSummaryRow label="App Pack" value={result?.appPack || "未作成"} />
          </dl>
        </AppStudioCollapsibleSection>
        <AppStudioCollapsibleSection title="実行ログ" summary="stdout / stderr と技術ログを確認します。">
          <AppStudioRunLog busy={busy} result={result} />
        </AppStudioCollapsibleSection>
        <AppStudioCollapsibleSection title="出力フォルダ" summary="生成された確認ファイルの場所を表示します。">
          <p className="admin-muted">{result?.outputDir || "まだ出力フォルダはありません。"}</p>
        </AppStudioCollapsibleSection>
      </div>
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
    const savedRevisionInstruction = normalizedIcon?.revisionPromptInfo.userRevisionInstruction ?? "";
    const finalImageApiPrompt = latestCandidate?.prompt || normalizedIcon?.revisionPromptInfo.finalImageApiPrompt || "";
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
    const manualCheckCount = result?.manualChecks?.length ?? 0;
    return (
      <section className="studio-step-panel">
        <div className="studio-panel-head">
          <span className="studio-step-index">4</span>
          <div>
            <h4>最終確認</h4>
            <p>承認すると、このアプリが通常ランチャーに表示されます。</p>
          </div>
        </div>

        <div className={`studio-status-banner ${canApprove ? "ok" : "warn"}`}>
          {canApprove ? <ShieldCheck size={19} aria-hidden="true" /> : <AlertTriangle size={19} aria-hidden="true" />}
          <div>
            <strong>{canApprove ? "有効化の準備ができています" : "まだ承認できません"}</strong>
            <span>{canApprove ? "承認するとこのアプリが通常ランチャーに表示されます。" : approvalDecision.reason}</span>
          </div>
        </div>

        <AppStudioLauncherPreview appId={request.appId} name={request.name} metadata={request.metadata} proposal={aiProposal} iconOverride={request.iconOverride} />

        <section className="studio-approval-checklist">
          <div className="admin-section-head">
            <div>
              <p className="dialog-kicker">承認前の確認</p>
              <h4>有効化の条件</h4>
            </div>
            <StatusChip tone={canApprove ? "ok" : "warn"}>{canApprove ? "承認可能" : "要確認"}</StatusChip>
          </div>
          <dl>
            <ResultSummaryRow label="アプリ選択" value={preflight?.entryExists ? "完了" : "未確認"} tone={preflight?.entryExists ? "ok" : "warn"} />
            <ResultSummaryRow label="表示内容" value={request.name ? "確認済み" : "未入力"} tone={request.name ? "ok" : "warn"} />
            <ResultSummaryRow label="テスト登録" value={result ? statusLabel(result.executionStatus) : "未実行"} tone={statusTone(result?.executionStatus)} />
            <ResultSummaryRow label="配布物検証" value={result ? statusLabel(result.exeReadinessStatus || result.runtimeStatus) : "未実行"} tone={statusTone(result?.exeReadinessStatus || result?.runtimeStatus)} />
            <ResultSummaryRow label="手動確認" value={manualCheckCount ? `${manualCheckCount}件あり` : result ? "なし" : "未確認"} tone={manualCheckCount ? "warn" : result ? "ok" : "idle"} />
          </dl>
        </section>

        {manualCheckCount ? (
          <div className="studio-manual-checks warning">
            <strong>未確認として残ること</strong>
            <p>初回ログインや外部サービス連携は自動検証していません。必要に応じて承認後に実機確認してください。</p>
          </div>
        ) : null}

        <section className="studio-approval-effects">
          <h4>承認すると行われること</h4>
          <ul>
            <li>manifest を有効化</li>
            <li>通常ランチャーに表示</li>
            <li>承認記録を保存</li>
          </ul>
          <div className="studio-approval-condition">
            <strong>承認条件</strong>
            <span>{approvalMode === "strict" ? "配布リスクなし。手動確認メモあり。" : "配布リスク警告を許容。重大な失敗は不可。"}</span>
          </div>
        </section>

        <AppStudioCollapsibleSection title="承認条件を変更" summary="通常は慎重モードのまま承認します。必要な場合だけ変更します。">
          <fieldset className="studio-approval-mode">
            <legend>承認モード</legend>
            <label className="studio-approval-option">
              <input
                type="radio"
                name="studio-import-approval-mode"
                checked={approvalMode === "strict"}
                onChange={() => setApprovalMode("strict")}
              />
              <span>
                <strong>慎重モード</strong>
                <small>配布リスクのない参考警告や手動確認メモだけなら承認できます。</small>
              </span>
            </label>
            <label className="studio-approval-option">
              <input
                type="radio"
                name="studio-import-approval-mode"
                checked={approvalMode === "allowWarnings"}
                onChange={() => setApprovalMode("allowWarnings")}
              />
              <span>
                <strong>警告を許容</strong>
                <small>重大な失敗は承認せず、許容可能な警告だけを承認対象にします。</small>
              </span>
            </label>
          </fieldset>
        </AppStudioCollapsibleSection>

        {renderTechnicalDetails()}

        <div className="studio-action-row">
          <button className="secondary-button" type="button" onClick={() => setStep("review")}>
            テスト登録へ戻る
          </button>
          <button className="secondary-button" type="button" onClick={() => void refreshResult()} disabled={busy || !result?.appId}>
            結果を再読み込み
          </button>
          <button className="primary-button" type="button" onClick={() => void approve()} disabled={!canApprove} title={canApprove ? "承認して有効化します" : approvalDecision.reason}>
            {operation.kind === "approve" && busy ? <Loader2 className="studio-spinner" size={17} aria-hidden="true" /> : <ShieldCheck size={17} aria-hidden="true" />}
            承認して有効化
          </button>
        </div>
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

type StatusTone = "idle" | "ok" | "warn" | "error";

function StatusChip({ tone = "idle", children }: { tone?: StatusTone; children: string }) {
  return <span className={`studio-status-chip ${tone}`}>{children}</span>;
}

function ResultSummaryRow({ label, value, tone = "idle" }: { label: string; value: string; tone?: StatusTone }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>
        <StatusChip tone={tone}>{value}</StatusChip>
      </dd>
    </div>
  );
}

function buildModeLabel(mode?: string | null): string {
  if (mode === "shared-env") {
    return "共有ランタイム";
  }
  if (mode === "frozen-folder") {
    return "配布用exe";
  }
  return mode || "-";
}

function statusLabel(status?: string | null): string {
  if (status === "pass") {
    return "成功";
  }
  if (status === "warn") {
    return "要確認";
  }
  if (status === "fail") {
    return "失敗";
  }
  return status || "未実行";
}

function statusTone(status?: string | null): StatusTone {
  if (status === "pass") {
    return "ok";
  }
  if (status === "warn") {
    return "warn";
  }
  if (status === "fail") {
    return "error";
  }
  return "idle";
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

function isPngSignature(bytes: Uint8Array): boolean {
  const signature = [137, 80, 78, 71, 13, 10, 26, 10];
  return signature.every((value, index) => bytes[index] === value);
}

function readFileAsDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = typeof reader.result === "string" ? reader.result : "";
      if (result.startsWith("data:image/png;base64,")) {
        resolve(result);
      } else {
        reject(new Error("PNGデータURLを作成できませんでした。"));
      }
    };
    reader.onerror = () => reject(new Error("PNGファイルの読み込みに失敗しました。"));
    reader.readAsDataURL(file);
  });
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
    buildMode: "shared-env",
    showTerminal: Boolean(request.showTerminal),
    createAppEnv: false,
    rebuildAppEnv: false,
    generateLock: true,
    buildFrozenFolder: false,
    verifyRuntime: true,
    iconPrompt: request.iconPrompt?.trim() || undefined,
    iconStylePreset: styleInstruction ? "custom" : undefined,
    iconStyleCustom: styleInstruction || undefined,
    iconRevisionImage: request.iconRevisionImage?.startsWith("data:image/png;base64,") ? request.iconRevisionImage : undefined,
    metadata: cleanEditableMetadata(request.metadata),
    iconOverride: cleanIconOverride(request.iconOverride),
  };
}
