import {
  CheckCircle2,
  CircleAlert,
  CircleDot,
  ClipboardCheck,
  FileCheck2,
  FolderCheck,
  Hammer,
  Loader2,
  PlayCircle,
  RefreshCw,
  Rocket,
  Save,
  ShieldCheck,
  Sparkles,
  TriangleAlert,
  UploadCloud,
} from "lucide-react";
import { listen } from "@tauri-apps/api/event";
import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import {
  appStudioPublishBuildVerify,
  appStudioPublishDryRun,
  appStudioPublishPreflight,
  appStudioPublishPrepareTarget,
  appStudioPublishRelease,
  appStudioPublishRemoteVerify,
  appStudioPublishSaveReleaseNotes,
  appStudioPublishSignInstaller,
  appStudioPublishSuggestReleaseNotes,
} from "../../../lib/appStudioApi";
import type {
  AppStudioPublishAsset,
  AppStudioPublishCheck,
  AppStudioPublishPreflightResult,
  AppStudioPublishRunResult,
  AppStudioReleaseNotesDraftResult,
  AppStudioRemoteVerificationCheck,
  AppStudioRemoteVerificationReport,
  AppStudioSaveReleaseNotesResult,
} from "../../../lib/appStudioTypes";
import { formatAdminError } from "../adminUi";

type PublishPhaseStatus = "pending" | "running" | "passed" | "failed" | "skipped";
type RecommendedActionTone = "neutral" | "success" | "warn";
type BuildVerifyStageId = "preflight" | "app_packs" | "runtime" | "tauri_build" | "installer" | "signing" | "strict_verify";

interface PublishStepItem {
  number: string;
  title: string;
  summary: string;
  status: PublishPhaseStatus;
  icon: ReactNode;
  actions?: ReactNode;
  children?: ReactNode;
}

interface RecommendedAction {
  title: string;
  message: string;
  label?: string;
  tone: RecommendedActionTone;
  onAction?: () => void;
  disabled?: boolean;
}

interface PublishProcessStep {
  id: BuildVerifyStageId;
  title: string;
  detail: string;
  status: PublishPhaseStatus;
}

interface AppStudioPublishProgressEvent {
  operation?: string;
  stage?: string;
  status?: PublishPhaseStatus;
  message?: string;
  timestamp?: string;
}

const DEFAULT_CODE_SIGN_TIMESTAMP_URL = "http://timestamp.digicert.com";
const PUBLISH_PROGRESS_EVENT = "app-studio-publish-progress";
const BUILD_VERIFY_STAGE_ORDER: BuildVerifyStageId[] = ["preflight", "app_packs", "runtime", "tauri_build", "installer", "signing", "strict_verify"];

const RECOMMENDED_RELEASE_SETTING_NOTES = [
  "署名なし installer を clean tree から build / verify して公開します。",
  "manifest の sha256 / size、checksums.sha256.txt、公開後の installer 再取得検証を標準で有効にします。",
  "公開実行、dirty tree 許可、既存 Release 上書きは、安全のため手動で有効にします。",
  "署名証明書がある場合だけ、公開時署名または現在の署名済み installer 反映を任意で有効にします。",
  "証明書 thumbprint / subject / signtool path は保存せず、空欄時は環境変数または自動検出を使います。",
];

export function AppStudioPublishPanel() {
  const [result, setResult] = useState<AppStudioPublishPreflightResult | null>(null);
  const [dryRunResult, setDryRunResult] = useState<AppStudioPublishRunResult | null>(null);
  const [prepareTargetResult, setPrepareTargetResult] = useState<AppStudioPublishRunResult | null>(null);
  const [signCurrentInstallerResult, setSignCurrentInstallerResult] = useState<AppStudioPublishRunResult | null>(null);
  const [buildVerifyResult, setBuildVerifyResult] = useState<AppStudioPublishRunResult | null>(null);
  const [remoteVerifyResult, setRemoteVerifyResult] = useState<AppStudioPublishRunResult | null>(null);
  const [publishResult, setPublishResult] = useState<AppStudioPublishRunResult | null>(null);
  const [notesDraftResult, setNotesDraftResult] = useState<AppStudioReleaseNotesDraftResult | null>(null);
  const [saveNotesResult, setSaveNotesResult] = useState<AppStudioSaveReleaseNotesResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [dryRunBusy, setDryRunBusy] = useState(false);
  const [prepareTargetBusy, setPrepareTargetBusy] = useState(false);
  const [signCurrentInstallerBusy, setSignCurrentInstallerBusy] = useState(false);
  const [buildVerifyBusy, setBuildVerifyBusy] = useState(false);
  const [remoteVerifyBusy, setRemoteVerifyBusy] = useState(false);
  const [publishBusy, setPublishBusy] = useState(false);
  const [notesDraftBusy, setNotesDraftBusy] = useState(false);
  const [saveNotesBusy, setSaveNotesBusy] = useState(false);
  const [flowBusy, setFlowBusy] = useState(false);
  const [flowMessage, setFlowMessage] = useState("");
  const [buildVerifyActiveStage, setBuildVerifyActiveStage] = useState<BuildVerifyStageId | null>(null);
  const [buildVerifyStepStatuses, setBuildVerifyStepStatuses] = useState<Partial<Record<BuildVerifyStageId, PublishPhaseStatus>>>({});
  const [buildVerifyProgressMessage, setBuildVerifyProgressMessage] = useState("");
  const [downloadInstallerForVerify, setDownloadInstallerForVerify] = useState(true);
  const [confirmPublish, setConfirmPublish] = useState(false);
  const [allowDirty, setAllowDirty] = useState(false);
  const [allowExistingRelease, setAllowExistingRelease] = useState(false);
  const [updateManifestInstallerUrl, setUpdateManifestInstallerUrl] = useState(true);
  const [draft, setDraft] = useState(false);
  const [prerelease, setPrerelease] = useState(false);
  const [downloadInstallerAfterPublish, setDownloadInstallerAfterPublish] = useState(true);
  const [useCurrentInstallerForPublish, setUseCurrentInstallerForPublish] = useState(false);
  const [signInstaller, setSignInstaller] = useState(false);
  const [requireInstallerSignature, setRequireInstallerSignature] = useState(false);
  const [codeSignCertificateThumbprint, setCodeSignCertificateThumbprint] = useState("");
  const [codeSignCertificateSubject, setCodeSignCertificateSubject] = useState("");
  const [codeSignTimestampUrl, setCodeSignTimestampUrl] = useState(DEFAULT_CODE_SIGN_TIMESTAMP_URL);
  const [signToolPath, setSignToolPath] = useState("");
  const [releaseNotes, setReleaseNotes] = useState("");
  const [manifestReleaseNotesJson, setManifestReleaseNotesJson] = useState("");
  const [error, setError] = useState("");

  function applyRecommendedReleaseDefaults() {
    setDownloadInstallerForVerify(true);
    setConfirmPublish(false);
    setAllowDirty(false);
    setAllowExistingRelease(false);
    setUpdateManifestInstallerUrl(true);
    setDraft(false);
    setPrerelease(false);
    setDownloadInstallerAfterPublish(true);
    setUseCurrentInstallerForPublish(false);
    setSignInstaller(false);
    setRequireInstallerSignature(false);
    setCodeSignTimestampUrl(DEFAULT_CODE_SIGN_TIMESTAMP_URL);
  }

  useEffect(() => {
    let unlisten: (() => void) | null = null;
    let disposed = false;
    void listen<AppStudioPublishProgressEvent>(PUBLISH_PROGRESS_EVENT, (event) => {
      const payload = event.payload;
      if (payload.operation !== "build_verify") {
        return;
      }
      const stage = normalizeBuildVerifyStage(payload.stage);
      const status = normalizePhaseStatus(payload.status);
      if (stage && status === "running") {
        setBuildVerifyActiveStage(stage);
        setBuildVerifyProgressMessage(payload.message ?? "");
        setBuildVerifyStepStatuses((current) => markBuildVerifyRunning(current, stage));
        return;
      }
      if (status === "passed") {
        setBuildVerifyActiveStage(null);
        setBuildVerifyProgressMessage(payload.message ?? "release build / verify が完了しました。");
        setBuildVerifyStepStatuses((current) => markBuildVerifyComplete(current, "passed"));
        return;
      }
      if (status === "failed") {
        setBuildVerifyProgressMessage(payload.message ?? "release build / verify が失敗しました。");
        setBuildVerifyStepStatuses((current) => markBuildVerifyFailed(current));
      }
    }).then((nextUnlisten) => {
      if (disposed) {
        nextUnlisten();
      } else {
        unlisten = nextUnlisten;
      }
    });
    return () => {
      disposed = true;
      if (unlisten) {
        unlisten();
      }
    };
  }, []);

  function beginBuildVerifyProgress(message = "release build / verify を開始しています。") {
    setBuildVerifyResult(null);
    setBuildVerifyActiveStage("preflight");
    setBuildVerifyProgressMessage(message);
    setBuildVerifyStepStatuses({ preflight: "running" });
  }

  function finishBuildVerifyProgress(ok: boolean) {
    setBuildVerifyActiveStage(null);
    setBuildVerifyStepStatuses((current) => ok ? markBuildVerifyComplete(current, "passed") : markBuildVerifyFailed(current));
  }

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
      const nextResult = await appStudioPublishPrepareTarget({
        requireInstallerSignature: requireInstallerSignature || signInstaller || useCurrentInstallerForPublish,
      });
      setPrepareTargetResult(nextResult);
      setResult(nextResult.preflight);
    } catch (targetError) {
      setError(formatAdminError(targetError, "リリース対象フォルダの作成に失敗しました。"));
    } finally {
      setPrepareTargetBusy(false);
    }
  }

  async function runSignCurrentInstaller() {
    setSignCurrentInstallerBusy(true);
    setError("");
    try {
      const nextResult = await appStudioPublishSignInstaller({
        codeSignCertificateThumbprint: emptyToNull(codeSignCertificateThumbprint),
        codeSignCertificateSubject: emptyToNull(codeSignCertificateSubject),
        codeSignTimestampUrl: emptyToNull(codeSignTimestampUrl),
        signToolPath: emptyToNull(signToolPath),
      });
      setSignCurrentInstallerResult(nextResult);
      setResult(nextResult.preflight);
      if (nextResult.ok) {
        setRequireInstallerSignature(true);
        setUseCurrentInstallerForPublish(true);
        setAllowExistingRelease(true);
        setUpdateManifestInstallerUrl(true);
        setDownloadInstallerAfterPublish(true);
        setDownloadInstallerForVerify(true);
      }
    } catch (signError) {
      setError(formatAdminError(signError, "現在のNSIS installer署名に失敗しました。"));
    } finally {
      setSignCurrentInstallerBusy(false);
    }
  }

  async function runSuggestReleaseNotes() {
    setNotesDraftBusy(true);
    setError("");
    try {
      const nextResult = await appStudioPublishSuggestReleaseNotes();
      setNotesDraftResult(nextResult);
      setResult(nextResult.preflight);
      setReleaseNotes(nextResult.githubReleaseNotes);
      setManifestReleaseNotesJson(nextResult.manifestReleaseNotesJson);
    } catch (draftError) {
      setError(formatAdminError(draftError, "更新内容のAI文案作成に失敗しました。"));
    } finally {
      setNotesDraftBusy(false);
    }
  }

  async function runSaveReleaseNotes() {
    const nextNotes = manifestReleaseNotesJson.trim();
    if (!nextNotes) {
      setError("manifest に保存する release_notes JSON が空です。先にAI文案を作成するか、JSONを入力してください。");
      return;
    }
    setSaveNotesBusy(true);
    setError("");
    try {
      const nextResult = await appStudioPublishSaveReleaseNotes({ manifestReleaseNotesJson: nextNotes });
      setSaveNotesResult(nextResult);
      setResult(nextResult.preflight);
    } catch (saveError) {
      setError(formatAdminError(saveError, "release/manifest.json への更新内容保存に失敗しました。"));
    } finally {
      setSaveNotesBusy(false);
    }
  }

  async function runBuildVerify() {
    setBuildVerifyBusy(true);
    setError("");
    beginBuildVerifyProgress();
    try {
      const nextResult = await appStudioPublishBuildVerify({
        signInstaller,
        requireInstallerSignature: requireInstallerSignature || signInstaller,
        codeSignCertificateThumbprint: emptyToNull(codeSignCertificateThumbprint),
        codeSignCertificateSubject: emptyToNull(codeSignCertificateSubject),
        codeSignTimestampUrl: emptyToNull(codeSignTimestampUrl),
        signToolPath: emptyToNull(signToolPath),
      });
      setBuildVerifyResult(nextResult);
      setResult(nextResult.preflight);
      finishBuildVerifyProgress(nextResult.ok);
    } catch (buildError) {
      finishBuildVerifyProgress(false);
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
        manifestUrl: prerelease ? result?.tagManifestUrl ?? result?.updateManifestUrl ?? result?.latestManifestUrl ?? null : result?.updateManifestUrl ?? result?.latestManifestUrl ?? null,
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
    if (publishBlockReason) {
      setPublishResult(null);
      setError(publishBlockReason);
      return;
    }
    setPublishBusy(true);
    setError("");
    setPublishResult(null);
    try {
      const nextResult = await appStudioPublishRelease({
        confirmPublish,
        allowDirty,
        allowExistingRelease,
        updateManifestInstallerUrl,
        draft,
        prerelease,
        downloadInstallerForRemoteVerify: downloadInstallerAfterPublish,
        skipBuild: useCurrentInstallerForPublish && !signInstaller,
        signInstaller,
        requireInstallerSignature: requireInstallerSignature || signInstaller || useCurrentInstallerForPublish,
        codeSignCertificateThumbprint: emptyToNull(codeSignCertificateThumbprint),
        codeSignCertificateSubject: emptyToNull(codeSignCertificateSubject),
        codeSignTimestampUrl: emptyToNull(codeSignTimestampUrl),
        signToolPath: emptyToNull(signToolPath),
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

  async function runOneClickPublishFlow() {
    if (!confirmPublish) {
      setError("一括公開を実行するには「GitHub Release への公開を実行する」を有効にしてください。");
      return;
    }

    setFlowBusy(true);
    setError("");
    setFlowMessage("公開前チェックを実行しています。");
    let nextReleaseNotes = releaseNotes.trim();
    let nextManifestReleaseNotesJson = manifestReleaseNotesJson.trim();
    let buildVerifyStarted = false;
    try {
      setBusy(true);
      const preflight = await appStudioPublishPreflight();
      setResult(preflight);
      setBusy(false);
      if (!preflight.ok) {
        throw new Error("公開前チェックに失敗項目があります。内容を確認してください。");
      }
      if (preflight.dirtyFiles.length > 0 && !allowDirty) {
        throw new Error("未コミット変更があります。コミットするか、公開オプションの「dirty tree での publish を許可」を明示的に有効にしてください。");
      }

      if (!nextReleaseNotes || !nextManifestReleaseNotesJson) {
        setFlowMessage("更新内容のAI文案を作成しています。");
        setNotesDraftBusy(true);
        const draftResult = await appStudioPublishSuggestReleaseNotes();
        setNotesDraftResult(draftResult);
        setResult(draftResult.preflight);
        nextReleaseNotes = nextReleaseNotes || draftResult.githubReleaseNotes.trim();
        nextManifestReleaseNotesJson = nextManifestReleaseNotesJson || draftResult.manifestReleaseNotesJson.trim();
        setReleaseNotes(nextReleaseNotes);
        setManifestReleaseNotesJson(nextManifestReleaseNotesJson);
        setNotesDraftBusy(false);
      }

      if (!nextManifestReleaseNotesJson) {
        throw new Error("利用者向け release_notes JSON が空です。公開前に更新内容を保存してください。");
      }

      setFlowMessage("更新内容を release/manifest.json に保存しています。");
      setSaveNotesBusy(true);
      const saveResult = await appStudioPublishSaveReleaseNotes({ manifestReleaseNotesJson: nextManifestReleaseNotesJson });
      setSaveNotesResult(saveResult);
      setResult(saveResult.preflight);
      setSaveNotesBusy(false);

      if (useCurrentInstallerForPublish && !signInstaller) {
        setFlowMessage("現在の署名済み installer を使用します。release build はスキップします。");
      } else {
        setFlowMessage("release build / verify を実行しています。");
        setBuildVerifyBusy(true);
        buildVerifyStarted = true;
        beginBuildVerifyProgress("推奨フロー内で release build / verify を開始しています。");
        const buildResult = await appStudioPublishBuildVerify({
          signInstaller,
          requireInstallerSignature: requireInstallerSignature || signInstaller,
          codeSignCertificateThumbprint: emptyToNull(codeSignCertificateThumbprint),
          codeSignCertificateSubject: emptyToNull(codeSignCertificateSubject),
          codeSignTimestampUrl: emptyToNull(codeSignTimestampUrl),
          signToolPath: emptyToNull(signToolPath),
        });
        setBuildVerifyResult(buildResult);
        setResult(buildResult.preflight);
        finishBuildVerifyProgress(buildResult.ok);
        buildVerifyStarted = false;
        setBuildVerifyBusy(false);
        if (!buildResult.ok) {
          throw new Error("release build / verify に失敗しました。");
        }
      }

      setFlowMessage("リリース対象フォルダを作成しています。");
      setPrepareTargetBusy(true);
      const targetResult = await appStudioPublishPrepareTarget({
        requireInstallerSignature: requireInstallerSignature || signInstaller || useCurrentInstallerForPublish,
      });
      setPrepareTargetResult(targetResult);
      setResult(targetResult.preflight);
      setPrepareTargetBusy(false);
      if (!targetResult.ok) {
        throw new Error("リリース対象フォルダの作成に失敗しました。");
      }

      setFlowMessage("publish dry-run を実行しています。");
      setDryRunBusy(true);
      const dryRun = await appStudioPublishDryRun();
      setDryRunResult(dryRun);
      setResult(dryRun.preflight);
      setDryRunBusy(false);
      if (!dryRun.ok) {
        throw new Error("publish dry-run に失敗しました。");
      }

      setFlowMessage("GitHub Release へ公開しています。");
      setPublishBusy(true);
      const publish = await appStudioPublishRelease({
        confirmPublish,
        allowDirty,
        allowExistingRelease,
        updateManifestInstallerUrl,
        draft,
        prerelease,
        downloadInstallerForRemoteVerify: downloadInstallerAfterPublish,
        skipBuild: useCurrentInstallerForPublish && !signInstaller,
        signInstaller,
        requireInstallerSignature: requireInstallerSignature || signInstaller || useCurrentInstallerForPublish,
        codeSignCertificateThumbprint: emptyToNull(codeSignCertificateThumbprint),
        codeSignCertificateSubject: emptyToNull(codeSignCertificateSubject),
        codeSignTimestampUrl: emptyToNull(codeSignTimestampUrl),
        signToolPath: emptyToNull(signToolPath),
        releaseNotes: nextReleaseNotes || null,
      });
      setPublishResult(publish);
      setResult(publish.preflight);
      setPublishBusy(false);
      if (!publish.ok) {
        throw new Error("GitHub Release の公開に失敗しました。");
      }

      setFlowMessage("一括公開フローが完了しました。");
    } catch (flowError) {
      if (buildVerifyStarted) {
        finishBuildVerifyProgress(false);
      }
      setError(formatAdminError(flowError, "一括公開フローに失敗しました。"));
      setBusy(false);
      setNotesDraftBusy(false);
      setSaveNotesBusy(false);
      setPrepareTargetBusy(false);
      setSignCurrentInstallerBusy(false);
      setBuildVerifyBusy(false);
      setDryRunBusy(false);
      setPublishBusy(false);
    } finally {
      setFlowBusy(false);
    }
  }

  const anyBusy = busy || dryRunBusy || prepareTargetBusy || signCurrentInstallerBusy || buildVerifyBusy || remoteVerifyBusy || publishBusy || notesDraftBusy || saveNotesBusy || flowBusy;
  const hasCodeSignSelector = Boolean(codeSignCertificateThumbprint.trim() || codeSignCertificateSubject.trim());
  const uploadAssets = result?.releaseTargetAssets?.filter((asset) => asset.upload) ?? [];
  const releaseTargetReady = uploadAssets.length > 0 && uploadAssets.every((asset) => asset.targetExists);
  const notesHaveDraft = Boolean(releaseNotes.trim() || manifestReleaseNotesJson.trim() || notesDraftResult);
  const hasDirtyFiles = Boolean(result?.dirtyFiles?.length);
  const dirtyTreeAllowed = !hasDirtyFiles || allowDirty;
  const buildReady = buildVerifyResult?.ok === true || (useCurrentInstallerForPublish && signCurrentInstallerResult?.ok === true);
  const releaseNotesReady = saveNotesResult?.ok === true;
  const publishTargetReady = releaseTargetReady && dryRunResult?.ok === true;
  const publishTrustReady = !signInstaller || hasCodeSignSelector || useCurrentInstallerForPublish;
  const publishBlockReason = getPublishBlockReason({
    confirmPublish,
    preflightOk: result?.ok === true,
    releaseNotesReady,
    buildReady,
    publishTargetReady,
    hasDirtyFiles,
    allowDirty,
    publishTrustReady,
  });
  const canPublish = !anyBusy && !publishBlockReason;
  const canRunOneClickFlow = confirmPublish && dirtyTreeAllowed && !anyBusy;
  const notesStatus: PublishPhaseStatus = notesDraftBusy || saveNotesBusy ? "running" : saveNotesResult?.ok ? "passed" : "pending";
  const buildStageStatus: PublishPhaseStatus = (() => {
    if (signCurrentInstallerBusy || buildVerifyBusy) {
      return "running";
    }
    if (signCurrentInstallerResult?.ok === false || buildVerifyResult?.ok === false) {
      return "failed";
    }
    if (buildVerifyResult?.ok || (useCurrentInstallerForPublish && signCurrentInstallerResult?.ok)) {
      return "passed";
    }
    return "pending";
  })();
  const targetStageStatus: PublishPhaseStatus = (() => {
    if (prepareTargetBusy || dryRunBusy) {
      return "running";
    }
    if (prepareTargetResult?.ok === false || dryRunResult?.ok === false) {
      return "failed";
    }
    if (releaseTargetReady && dryRunResult?.ok) {
      return "passed";
    }
    return "pending";
  })();
  const remoteStageStatus: PublishPhaseStatus = (() => {
    if (remoteVerifyBusy) {
      return "running";
    }
    if (remoteVerifyResult?.ok === false) {
      return "failed";
    }
    if (remoteVerifyResult?.ok || publishResult?.report?.ok) {
      return "passed";
    }
    return "pending";
  })();
  const buildVerifyProcessSteps = buildBuildVerifyProcessSteps({
    signInstaller,
    requireInstallerSignature,
    useCurrentInstallerForPublish,
    signCurrentInstallerBusy,
    signCurrentInstallerResult,
    buildVerifyBusy,
    buildVerifyResult,
    activeStage: buildVerifyActiveStage,
    stepStatuses: buildVerifyStepStatuses,
  });
  const publishReadiness = [
    {
      label: "公開前確認",
      ok: result?.ok === true,
      message: result ? (result.ok ? "失敗なしです。" : "失敗項目があります。") : "未実行です。",
    },
    {
      label: "更新内容",
      ok: saveNotesResult?.ok === true,
      message: saveNotesResult?.ok ? "manifest に保存済みです。" : notesHaveDraft ? "保存待ちです。" : "未作成です。",
    },
    {
      label: "build / verify",
      ok: buildReady,
      message: buildVerifyResult?.ok
        ? "通過済みです。"
        : useCurrentInstallerForPublish
          ? "現在の署名済み installer を使用します。"
          : "未実行です。",
    },
    {
      label: "公開対象",
      ok: publishTargetReady,
      message: publishTargetReady ? "対象フォルダと dry-run は確認済みです。" : "対象フォルダ作成と dry-run が残っています。",
    },
    {
      label: "dirty tree",
      ok: dirtyTreeAllowed,
      message: hasDirtyFiles
        ? allowDirty
          ? "dirty tree を明示許可しています。"
          : "未コミット変更があります。"
        : result
          ? "未コミット変更はありません。"
          : "未確認です。",
    },
    {
      label: "installer信頼性",
      ok: publishTrustReady,
      message: signInstaller
        ? hasCodeSignSelector
          ? "指定証明書で署名します。"
          : "環境変数または証明書入力が必要です。"
        : useCurrentInstallerForPublish
          ? "署名済み installer を使用します。"
          : requireInstallerSignature
            ? "署名検証を必須にします。"
            : "署名なしで公開し、sha256 / size 検証で補強します。",
    },
  ];
  const recommendedAction = buildRecommendedAction({
    result,
    dryRunResult,
    buildVerifyResult,
    prepareTargetResult,
    publishResult,
    remoteVerifyResult,
    saveNotesResult,
    notesHaveDraft,
    releaseTargetReady,
    confirmPublish,
    hasDirtyFiles,
    allowDirty,
    useCurrentInstallerForPublish,
    anyBusy,
    runPreflight: () => void runPreflight(),
    runSuggestReleaseNotes: () => void runSuggestReleaseNotes(),
    runSaveReleaseNotes: () => void runSaveReleaseNotes(),
    runBuildVerify: () => void runBuildVerify(),
    runPrepareTarget: () => void runPrepareTarget(),
    runDryRun: () => void runDryRun(),
    runPublishRelease: () => void runPublishRelease(),
    runRemoteVerify: () => void runRemoteVerify(),
  });
  const releaseSteps: PublishStepItem[] = [
    {
      number: "1",
      title: "状態確認",
      summary: result ? (result.ok ? "公開前チェックは通過しています。" : "失敗項目を解消してください。") : "最初に読み取り専用チェックを実行します。",
      status: phaseFromPreflight(result, busy),
      icon: busy ? <Loader2 className="studio-spinner" size={20} aria-hidden="true" /> : <ClipboardCheck size={20} aria-hidden="true" />,
      actions: (
        <button className="secondary-button" type="button" onClick={() => void runPreflight()} disabled={anyBusy}>
          {busy ? <Loader2 className="studio-spinner" size={17} aria-hidden="true" /> : <RefreshCw size={17} aria-hidden="true" />}
          公開前確認
        </button>
      ),
      children: result ? <ReleaseSnapshot result={result} /> : null,
    },
    {
      number: "2",
      title: "更新内容",
      summary: saveNotesResult?.ok ? "利用者向け更新内容を manifest に保存済みです。" : notesHaveDraft ? "文案を確認して manifest に保存します。" : "GitHub Release本文と更新通知文を作成します。",
      status: notesStatus,
      icon: notesDraftBusy || saveNotesBusy ? <Loader2 className="studio-spinner" size={20} aria-hidden="true" /> : <Sparkles size={20} aria-hidden="true" />,
      actions: (
        <>
          <button className="secondary-button" type="button" onClick={() => void runSuggestReleaseNotes()} disabled={anyBusy}>
            {notesDraftBusy ? <Loader2 className="studio-spinner" size={17} aria-hidden="true" /> : <Sparkles size={17} aria-hidden="true" />}
            AI文案を作成
          </button>
          <button className="secondary-button" type="button" onClick={() => void runSaveReleaseNotes()} disabled={anyBusy || !manifestReleaseNotesJson.trim()}>
            {saveNotesBusy ? <Loader2 className="studio-spinner" size={17} aria-hidden="true" /> : <Save size={17} aria-hidden="true" />}
            manifestへ保存
          </button>
        </>
      ),
      children: (
        <div className="publish-notes-editor">
          <label className="admin-field">
            GitHub Release notes
            <textarea className="studio-textarea" rows={6} value={releaseNotes} disabled={anyBusy} onChange={(event) => setReleaseNotes(event.currentTarget.value)} placeholder="GitHub Release本文" />
          </label>
          <label className="admin-field">
            利用者向け release_notes JSON
            <textarea className="studio-textarea studio-json-textarea" rows={8} value={manifestReleaseNotesJson} disabled={anyBusy} onChange={(event) => setManifestReleaseNotesJson(event.currentTarget.value)} placeholder="更新通知に表示するJSON" />
          </label>
          {notesDraftResult ? (
            <p className={notesDraftResult.source === "ai" ? "admin-success" : "admin-warning"}>
              {notesDraftResult.source === "ai" ? "AI文案を作成しました。" : `AI文案は利用できませんでした。${notesDraftResult.message}`}
            </p>
          ) : null}
          {saveNotesResult?.ok ? <p className="admin-success">{saveNotesResult.message}</p> : null}
          {notesDraftResult?.aiReport ? (
            <details className="admin-details">
              <summary>AI文案生成ログ</summary>
              <pre className="studio-log">{notesDraftResult.aiReport}</pre>
            </details>
          ) : null}
        </div>
      ),
    },
    {
      number: "3",
      title: "署名 / build / verify",
      summary: useCurrentInstallerForPublish && !signInstaller ? "現在の署名済み installer を公開に使います。" : "installer、App Pack、runtime を生成して検証します。",
      status: buildStageStatus,
      icon: signCurrentInstallerBusy || buildVerifyBusy ? <Loader2 className="studio-spinner" size={20} aria-hidden="true" /> : <Hammer size={20} aria-hidden="true" />,
      actions: (
        <>
          <button className="secondary-button" type="button" onClick={() => void runBuildVerify()} disabled={anyBusy || (useCurrentInstallerForPublish && !signInstaller)}>
            {buildVerifyBusy ? <Loader2 className="studio-spinner" size={17} aria-hidden="true" /> : <Hammer size={17} aria-hidden="true" />}
            build / verify
          </button>
          <button className="secondary-button" type="button" onClick={() => void runSignCurrentInstaller()} disabled={anyBusy}>
            {signCurrentInstallerBusy ? <Loader2 className="studio-spinner" size={17} aria-hidden="true" /> : <ShieldCheck size={17} aria-hidden="true" />}
            現在のinstallerを署名
          </button>
        </>
      ),
      children: (
        <>
          <PublishProcessList steps={buildVerifyProcessSteps} />
          {buildVerifyProgressMessage ? <p className="admin-muted publish-process-message">{buildVerifyProgressMessage}</p> : null}
          <details className="publish-advanced-options">
            <summary>署名設定</summary>
            <SignatureOptions
              anyBusy={anyBusy}
              signInstaller={signInstaller}
              requireInstallerSignature={requireInstallerSignature}
              useCurrentInstallerForPublish={useCurrentInstallerForPublish}
              codeSignCertificateThumbprint={codeSignCertificateThumbprint}
              codeSignCertificateSubject={codeSignCertificateSubject}
              codeSignTimestampUrl={codeSignTimestampUrl}
              signToolPath={signToolPath}
              setSignInstaller={(checked) => {
                setSignInstaller(checked);
                if (checked) {
                  setRequireInstallerSignature(true);
                  setUseCurrentInstallerForPublish(false);
                }
              }}
              setRequireInstallerSignature={setRequireInstallerSignature}
              setUseCurrentInstallerForPublish={(checked) => {
                setUseCurrentInstallerForPublish(checked);
                if (checked) {
                  setRequireInstallerSignature(true);
                  setAllowExistingRelease(true);
                }
              }}
              setCodeSignCertificateThumbprint={setCodeSignCertificateThumbprint}
              setCodeSignCertificateSubject={setCodeSignCertificateSubject}
              setCodeSignTimestampUrl={setCodeSignTimestampUrl}
              setSignToolPath={setSignToolPath}
            />
          </details>
        </>
      ),
    },
    {
      number: "4",
      title: "公開対象確認",
      summary: releaseTargetReady && dryRunResult?.ok ? "upload 対象フォルダと dry-run は確認済みです。" : "GitHub Release に載せるファイルをまとめ、publish dry-run で確認します。",
      status: targetStageStatus,
      icon: prepareTargetBusy || dryRunBusy ? <Loader2 className="studio-spinner" size={20} aria-hidden="true" /> : <FolderCheck size={20} aria-hidden="true" />,
      actions: (
        <>
          <button className="secondary-button" type="button" onClick={() => void runPrepareTarget()} disabled={anyBusy}>
            {prepareTargetBusy ? <Loader2 className="studio-spinner" size={17} aria-hidden="true" /> : <FolderCheck size={17} aria-hidden="true" />}
            対象フォルダ作成
          </button>
          <button className="secondary-button" type="button" onClick={() => void runDryRun()} disabled={anyBusy}>
            {dryRunBusy ? <Loader2 className="studio-spinner" size={17} aria-hidden="true" /> : <PlayCircle size={17} aria-hidden="true" />}
            publish dry-run
          </button>
        </>
      ),
      children: result ? (
        <details className="publish-advanced-options">
          <summary>upload対象ファイル</summary>
          <ReleaseTargetAssets assets={result.releaseTargetAssets ?? []} />
        </details>
      ) : null,
    },
    {
      number: "5",
      title: "GitHub公開",
      summary: publishResult?.ok ? "GitHub Release 公開が完了しています。" : publishBlockReason ?? (confirmPublish ? "公開条件は揃っています。公開ボタンを実行できます。" : "公開確認を有効にすると実 publish が実行可能になります。"),
      status: phaseFromRun(publishResult, publishBusy),
      icon: publishBusy ? <Loader2 className="studio-spinner" size={20} aria-hidden="true" /> : <UploadCloud size={20} aria-hidden="true" />,
      actions: (
        <button className="primary-button publish-danger-button" type="button" onClick={() => void runPublishRelease()} disabled={!canPublish}>
          {publishBusy ? <Loader2 className="studio-spinner" size={17} aria-hidden="true" /> : <UploadCloud size={17} aria-hidden="true" />}
          GitHub publish
        </button>
      ),
      children: (
        <div className="publish-option-stack">
          <PublishReadinessChecklist items={publishReadiness} />
          {publishBlockReason ? <p className="admin-warning">{publishBlockReason}</p> : null}
          <label className="admin-toggle publish-confirm-toggle">
            <input type="checkbox" checked={confirmPublish} disabled={anyBusy} onChange={(event) => setConfirmPublish(event.currentTarget.checked)} />
            GitHub Release への公開を実行する
          </label>
          <div className="publish-mode-row">
            <label className="admin-toggle">
              <input type="checkbox" checked={draft} disabled={anyBusy} onChange={(event) => setDraft(event.currentTarget.checked)} />
              Draft
            </label>
            <label className="admin-toggle">
              <input type="checkbox" checked={prerelease} disabled={anyBusy} onChange={(event) => setPrerelease(event.currentTarget.checked)} />
              Pre-release
            </label>
            <label className="admin-toggle">
              <input type="checkbox" checked={downloadInstallerAfterPublish} disabled={anyBusy} onChange={(event) => setDownloadInstallerAfterPublish(event.currentTarget.checked)} />
              publish後にinstallerも検証
            </label>
          </div>
          <details className="publish-advanced-options">
            <summary>公開オプション</summary>
            <div className="admin-two-column">
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
                <input
                  type="checkbox"
                  checked={useCurrentInstallerForPublish}
                  disabled={anyBusy || signInstaller}
                  onChange={(event) => {
                    const checked = event.currentTarget.checked;
                    setUseCurrentInstallerForPublish(checked);
                    if (checked) {
                      setRequireInstallerSignature(true);
                      setAllowExistingRelease(true);
                    }
                  }}
                />
                現在の署名済み installer を既存 Release へ反映
              </label>
            </div>
          </details>
        </div>
      ),
    },
    {
      number: "6",
      title: "公開後確認",
      summary: remoteStageStatus === "passed" ? "公開済み manifest は確認済みです。" : "公開後の manifest、installer URL、sha256、size を確認します。",
      status: remoteStageStatus,
      icon: remoteVerifyBusy ? <Loader2 className="studio-spinner" size={20} aria-hidden="true" /> : <ShieldCheck size={20} aria-hidden="true" />,
      actions: (
        <button className="secondary-button" type="button" onClick={() => void runRemoteVerify()} disabled={anyBusy}>
          {remoteVerifyBusy ? <Loader2 className="studio-spinner" size={17} aria-hidden="true" /> : <ShieldCheck size={17} aria-hidden="true" />}
          remote verify
        </button>
      ),
      children: (
        <label className="admin-toggle">
          <input type="checkbox" checked={downloadInstallerForVerify} disabled={anyBusy} onChange={(event) => setDownloadInstallerForVerify(event.currentTarget.checked)} />
          remote verify で installer も取得して sha256 を確認する
        </label>
      ),
    },
  ];

  return (
    <section className="admin-panel-section nested-section">
      <div className="publish-command-center">
        <div className="publish-command-main">
          <p className="dialog-kicker">公開準備</p>
          <h3>Release Cockpit</h3>
          <ReleaseOrderStrip steps={releaseSteps} />
        </div>
        <RecommendedActionPanel action={recommendedAction} />
      </div>

      <div className="publish-flow-panel">
        <div className="publish-flow-copy">
          <strong>推奨フロー</strong>
          <span>
            既定は「署名なし installer を clean tree から build / verify して新しい GitHub Release へ公開」です。
            公開確認、dirty tree 許可、既存 Release 上書きだけは安全のため手動で有効にします。
          </span>
          <ul className="publish-default-list">
            {RECOMMENDED_RELEASE_SETTING_NOTES.map((note) => (
              <li key={note}>{note}</li>
            ))}
          </ul>
        </div>
        <div className="publish-flow-actions">
          <button className="secondary-button" type="button" onClick={applyRecommendedReleaseDefaults} disabled={anyBusy}>
            <RefreshCw size={17} aria-hidden="true" />
            推奨設定を再適用
          </button>
          <button className="primary-button publish-danger-button" type="button" onClick={() => void runOneClickPublishFlow()} disabled={!canRunOneClickFlow}>
            {flowBusy ? <Loader2 className="studio-spinner" size={17} aria-hidden="true" /> : <Rocket size={17} aria-hidden="true" />}
            推奨フローを実行
          </button>
        </div>
      </div>
      {flowMessage ? <p className="admin-muted publish-flow-message">{flowMessage}</p> : null}
      {error ? <p className="admin-error" role="alert">{error}</p> : null}

      <ReleaseStepList steps={releaseSteps} />

      <section className="publish-results-section">
        <div className="admin-section-head">
          <div>
            <p className="dialog-kicker">実行結果</p>
            <h3>詳細ログと検査結果</h3>
          </div>
        </div>
        {result ? <PublishSummary result={result} /> : <p className="admin-muted">公開前確認を実行すると詳細が表示されます。</p>}
        {dryRunResult ? <PublishRunSummary result={dryRunResult} title="publish dry-run result" /> : null}
        {prepareTargetResult ? <PublishRunSummary result={prepareTargetResult} title="publish target result" /> : null}
        {signCurrentInstallerResult ? <PublishRunSummary result={signCurrentInstallerResult} title="installer signing result" /> : null}
        {buildVerifyResult ? <PublishRunSummary result={buildVerifyResult} title="release build / verify result" /> : null}
        {remoteVerifyResult ? <PublishRunSummary result={remoteVerifyResult} title="remote verify result" /> : null}
        {publishResult ? <PublishRunSummary result={publishResult} title="GitHub publish result" /> : null}
      </section>
    </section>
  );
}

function buildRecommendedAction(input: {
  result: AppStudioPublishPreflightResult | null;
  dryRunResult: AppStudioPublishRunResult | null;
  buildVerifyResult: AppStudioPublishRunResult | null;
  prepareTargetResult: AppStudioPublishRunResult | null;
  publishResult: AppStudioPublishRunResult | null;
  remoteVerifyResult: AppStudioPublishRunResult | null;
  saveNotesResult: AppStudioSaveReleaseNotesResult | null;
  notesHaveDraft: boolean;
  releaseTargetReady: boolean;
  confirmPublish: boolean;
  hasDirtyFiles: boolean;
  allowDirty: boolean;
  useCurrentInstallerForPublish: boolean;
  anyBusy: boolean;
  runPreflight: () => void;
  runSuggestReleaseNotes: () => void;
  runSaveReleaseNotes: () => void;
  runBuildVerify: () => void;
  runPrepareTarget: () => void;
  runDryRun: () => void;
  runPublishRelease: () => void;
  runRemoteVerify: () => void;
}): RecommendedAction {
  const common = { disabled: input.anyBusy };
  if (!input.result) {
    return { ...common, title: "次は状態確認", message: "manifest、installer、GitHub remote を読み取り専用で確認します。", label: "公開前確認", tone: "neutral", onAction: input.runPreflight };
  }
  if (!input.result.ok) {
    return { ...common, title: "確認が必要", message: "公開前チェックの失敗項目を解消してから再確認します。", label: "再確認", tone: "warn", onAction: input.runPreflight };
  }
  if (!input.notesHaveDraft) {
    return { ...common, title: "次は更新内容", message: "GitHub Release本文と利用者向け更新通知を作成します。", label: "AI文案を作成", tone: "neutral", onAction: input.runSuggestReleaseNotes };
  }
  if (!input.saveNotesResult?.ok) {
    return { ...common, title: "次はmanifest保存", message: "利用者向け更新通知を release/manifest.json に保存します。", label: "manifestへ保存", tone: "neutral", onAction: input.runSaveReleaseNotes };
  }
  if (!input.useCurrentInstallerForPublish && !input.buildVerifyResult?.ok) {
    return { ...common, title: "次はbuild / verify", message: "installer、App Pack、runtime を生成して strict 検証します。", label: "build / verify", tone: "neutral", onAction: input.runBuildVerify };
  }
  if (!input.releaseTargetReady || input.prepareTargetResult?.ok === false) {
    return { ...common, title: "次は対象フォルダ作成", message: "GitHub Release に upload するファイルだけをまとめます。", label: "対象フォルダ作成", tone: "neutral", onAction: input.runPrepareTarget };
  }
  if (!input.dryRunResult?.ok) {
    return { ...common, title: "次はpublish dry-run", message: "公開scriptの事前判定を確認します。", label: "publish dry-run", tone: "neutral", onAction: input.runDryRun };
  }
  if (input.hasDirtyFiles && !input.allowDirty) {
    return { ...common, title: "dirty tree の判断が必要", message: "未コミット変更があるため、コミットするか、公開オプションで dirty tree publish を明示許可してください。", tone: "warn" };
  }
  if (!input.confirmPublish) {
    return { ...common, title: "公開確認が必要", message: "GitHub Release への公開を実行する確認を有効にします。", tone: "warn" };
  }
  if (!input.publishResult?.ok) {
    return { ...common, title: "次はGitHub公開", message: "tag、Release、asset upload、remote verify を実行します。", label: "GitHub publish", tone: "warn", onAction: input.runPublishRelease };
  }
  if (!input.remoteVerifyResult?.ok && !input.publishResult.report?.ok) {
    return { ...common, title: "次は公開後確認", message: "公開済み manifest と installer 情報を確認します。", label: "remote verify", tone: "neutral", onAction: input.runRemoteVerify };
  }
  return { ...common, title: "公開完了", message: "GitHub Release と公開後確認が完了しています。", tone: "success" };
}

function RecommendedActionPanel({ action }: { action: RecommendedAction }) {
  return (
    <aside className={`publish-next-action ${action.tone}`}>
      <span>次の操作</span>
      <strong>{action.title}</strong>
      <p>{action.message}</p>
      {action.label && action.onAction ? (
        <button className={action.tone === "warn" ? "primary-button publish-danger-button" : "primary-button"} type="button" onClick={action.onAction} disabled={action.disabled}>
          {action.disabled ? <Loader2 className="studio-spinner" size={17} aria-hidden="true" /> : <CheckCircle2 size={17} aria-hidden="true" />}
          {action.label}
        </button>
      ) : null}
    </aside>
  );
}

function ReleaseOrderStrip({ steps }: { steps: PublishStepItem[] }) {
  return (
    <ol className="publish-order-strip" aria-label="公開準備の順序">
      {steps.map((step) => (
        <li className={step.status} key={step.number}>
          <span>{step.number}</span>
          <strong>{step.title}</strong>
        </li>
      ))}
    </ol>
  );
}

function ReleaseStepList({ steps }: { steps: PublishStepItem[] }) {
  return (
    <div className="publish-step-list">
      {steps.map((step) => (
        <section className={`publish-step-card ${step.status}`} key={step.number}>
          <div className="publish-step-number">{step.number}</div>
          <div className="publish-step-body">
            <header className="publish-step-head">
              <div className="publish-step-title">
                {step.icon}
                <div>
                  <h4>{step.title}</h4>
                  <p>{step.summary}</p>
                </div>
              </div>
              <span>{PHASE_STATUS_LABELS[step.status]}</span>
            </header>
            {step.actions ? <div className="publish-step-actions">{step.actions}</div> : null}
            {step.children ? <div className="publish-step-content">{step.children}</div> : null}
          </div>
        </section>
      ))}
    </div>
  );
}

function PublishProcessList({ steps }: { steps: PublishProcessStep[] }) {
  return (
    <div className="publish-process-list" aria-label="署名 / build / verify の実行状況">
      {steps.map((step) => (
        <div className={`publish-process-item ${step.status}`} key={step.id}>
          <span title={PHASE_STATUS_LABELS[step.status]}>{publishProcessIcon(step.status)}</span>
          <div>
            <strong>{step.title}</strong>
            <small>{step.detail}</small>
          </div>
        </div>
      ))}
    </div>
  );
}

function publishProcessIcon(status: PublishPhaseStatus) {
  if (status === "running") {
    return <Loader2 className="studio-spinner" size={17} aria-hidden="true" />;
  }
  if (status === "passed") {
    return <CheckCircle2 size={17} aria-hidden="true" />;
  }
  if (status === "failed") {
    return <CircleAlert size={17} aria-hidden="true" />;
  }
  if (status === "skipped") {
    return <TriangleAlert size={17} aria-hidden="true" />;
  }
  return <CircleDot size={17} aria-hidden="true" />;
}

function ReleaseSnapshot({ result }: { result: AppStudioPublishPreflightResult }) {
  return (
    <div className={`publish-snapshot-grid ${result.ok ? "ok" : "warn"}`}>
      <div><span>version</span><strong>{result.version ?? "-"}</strong></div>
      <div><span>tag</span><strong>{result.tag ?? "-"}</strong></div>
      <div><span>branch</span><strong>{result.branch ?? "-"}</strong></div>
      <div><span>installer</span><strong>{result.installerExists ? "あり" : "なし"}</strong></div>
      <div><span>blockers</span><strong>{result.betaReadyBlockers}</strong></div>
      <div><span>warnings</span><strong>{result.betaReadyWarnings}</strong></div>
      <div><span>manual checks</span><strong>{result.betaReadyManualChecks}</strong></div>
      <div><span>dirty files</span><strong>{result.dirtyFiles.length}</strong></div>
    </div>
  );
}

function SignatureOptions({
  anyBusy,
  signInstaller,
  requireInstallerSignature,
  useCurrentInstallerForPublish,
  codeSignCertificateThumbprint,
  codeSignCertificateSubject,
  codeSignTimestampUrl,
  signToolPath,
  setSignInstaller,
  setRequireInstallerSignature,
  setUseCurrentInstallerForPublish,
  setCodeSignCertificateThumbprint,
  setCodeSignCertificateSubject,
  setCodeSignTimestampUrl,
  setSignToolPath,
}: {
  anyBusy: boolean;
  signInstaller: boolean;
  requireInstallerSignature: boolean;
  useCurrentInstallerForPublish: boolean;
  codeSignCertificateThumbprint: string;
  codeSignCertificateSubject: string;
  codeSignTimestampUrl: string;
  signToolPath: string;
  setSignInstaller: (checked: boolean) => void;
  setRequireInstallerSignature: (checked: boolean) => void;
  setUseCurrentInstallerForPublish: (checked: boolean) => void;
  setCodeSignCertificateThumbprint: (value: string) => void;
  setCodeSignCertificateSubject: (value: string) => void;
  setCodeSignTimestampUrl: (value: string) => void;
  setSignToolPath: (value: string) => void;
}) {
  return (
    <div className="signature-options-panel">
      <div className="signature-options-head">
        <ShieldCheck size={19} aria-hidden="true" />
        <div>
          <strong>Installer署名（任意）</strong>
          <span>個人向け Standard / Individual または OV の Authenticode 対応証明書を使えます。証明書ファイルや秘密情報は repo に保存しません。</span>
        </div>
      </div>
      <p className="signature-options-hint">
        署名なし配布の既定では build / verify と公開後の sha256 検証を必ず通します。証明書を導入した後だけ、Individual / Standard Code Signing 証明書の thumbprint を指定し、「公開時に installer を署名する」または「現在の署名済み installer を公開に使う」を有効にします。
      </p>
      <div className="admin-two-column">
        <label className="admin-toggle">
          <input type="checkbox" checked={signInstaller} disabled={anyBusy} onChange={(event) => setSignInstaller(event.currentTarget.checked)} />
          公開時に installer を署名する
        </label>
        <label className="admin-toggle">
          <input type="checkbox" checked={requireInstallerSignature || signInstaller} disabled={anyBusy || signInstaller} onChange={(event) => setRequireInstallerSignature(event.currentTarget.checked)} />
          installer 署名を検証必須にする
        </label>
        <label className="admin-toggle">
          <input type="checkbox" checked={useCurrentInstallerForPublish} disabled={anyBusy || signInstaller} onChange={(event) => setUseCurrentInstallerForPublish(event.currentTarget.checked)} />
          現在の署名済み installer を公開に使う
        </label>
      </div>
      <div className="admin-two-column">
        <label className="admin-field">
          証明書 thumbprint
          <input type="text" value={codeSignCertificateThumbprint} disabled={anyBusy} onChange={(event) => setCodeSignCertificateThumbprint(event.currentTarget.value)} placeholder="未入力なら環境変数を使用" />
        </label>
        <label className="admin-field">
          証明書 subject
          <input type="text" value={codeSignCertificateSubject} disabled={anyBusy} onChange={(event) => setCodeSignCertificateSubject(event.currentTarget.value)} placeholder="例: CN=..." />
        </label>
        <label className="admin-field">
          timestamp URL
          <input type="text" value={codeSignTimestampUrl} disabled={anyBusy} onChange={(event) => setCodeSignTimestampUrl(event.currentTarget.value)} placeholder={DEFAULT_CODE_SIGN_TIMESTAMP_URL} />
        </label>
        <label className="admin-field">
          signtool.exe path
          <input type="text" value={signToolPath} disabled={anyBusy} onChange={(event) => setSignToolPath(event.currentTarget.value)} placeholder="未入力なら自動検出" />
        </label>
      </div>
    </div>
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

const PHASE_STATUS_LABELS: Record<PublishPhaseStatus, string> = {
  pending: "未実行",
  running: "実行中",
  passed: "完了",
  failed: "失敗",
  skipped: "任意",
};

function phaseFromRun(result: AppStudioPublishRunResult | null, busy: boolean): PublishPhaseStatus {
  if (busy) {
    return "running";
  }
  if (!result) {
    return "pending";
  }
  return result.ok ? "passed" : "failed";
}

function phaseFromPreflight(result: AppStudioPublishPreflightResult | null, busy: boolean): PublishPhaseStatus {
  if (busy) {
    return "running";
  }
  if (!result) {
    return "pending";
  }
  return result.ok ? "passed" : "failed";
}

function getPublishBlockReason(input: {
  confirmPublish: boolean;
  preflightOk: boolean;
  releaseNotesReady: boolean;
  buildReady: boolean;
  publishTargetReady: boolean;
  hasDirtyFiles: boolean;
  allowDirty: boolean;
  publishTrustReady: boolean;
}): string | null {
  if (!input.confirmPublish) {
    return "GitHub Release への公開確認を有効にしてください。";
  }
  if (!input.preflightOk) {
    return "公開前確認を通過してから GitHub publish を実行してください。";
  }
  if (!input.releaseNotesReady) {
    return "更新内容を manifest に保存してから GitHub publish を実行してください。";
  }
  if (!input.buildReady) {
    return "build / verify を通過してから GitHub publish を実行してください。";
  }
  if (!input.publishTargetReady) {
    return "公開対象フォルダ作成と publish dry-run を完了してから GitHub publish を実行してください。";
  }
  if (input.hasDirtyFiles && !input.allowDirty) {
    return "未コミット変更があります。コミットするか、公開オプションの「dirty tree での publish を許可」を明示的に有効にしてください。";
  }
  if (!input.publishTrustReady) {
    return "installer 署名を有効にする場合は、証明書 thumbprint / subject か署名済み installer の利用を指定してください。";
  }
  return null;
}

function normalizeBuildVerifyStage(stage?: string): BuildVerifyStageId | null {
  if (!stage) {
    return null;
  }
  return BUILD_VERIFY_STAGE_ORDER.includes(stage as BuildVerifyStageId) ? (stage as BuildVerifyStageId) : null;
}

function normalizePhaseStatus(status?: string): PublishPhaseStatus | null {
  if (!status) {
    return null;
  }
  return ["pending", "running", "passed", "failed", "skipped"].includes(status) ? (status as PublishPhaseStatus) : null;
}

function markBuildVerifyRunning(
  current: Partial<Record<BuildVerifyStageId, PublishPhaseStatus>>,
  stage: BuildVerifyStageId,
) {
  const next = { ...current };
  const index = BUILD_VERIFY_STAGE_ORDER.indexOf(stage);
  BUILD_VERIFY_STAGE_ORDER.slice(0, index).forEach((previousStage) => {
    if (next[previousStage] !== "skipped") {
      next[previousStage] = "passed";
    }
  });
  next[stage] = "running";
  return next;
}

function markBuildVerifyComplete(
  current: Partial<Record<BuildVerifyStageId, PublishPhaseStatus>>,
  status: "passed" | "failed",
) {
  const next = { ...current };
  BUILD_VERIFY_STAGE_ORDER.forEach((stage) => {
    if (next[stage] !== "skipped") {
      next[stage] = status;
    }
  });
  return next;
}

function markBuildVerifyFailed(current: Partial<Record<BuildVerifyStageId, PublishPhaseStatus>>) {
  const next = { ...current };
  const failedStage = BUILD_VERIFY_STAGE_ORDER.find((stage) => next[stage] === "running") ?? "strict_verify";
  next[failedStage] = "failed";
  return next;
}

function buildBuildVerifyProcessSteps(input: {
  signInstaller: boolean;
  requireInstallerSignature: boolean;
  useCurrentInstallerForPublish: boolean;
  signCurrentInstallerBusy: boolean;
  signCurrentInstallerResult: AppStudioPublishRunResult | null;
  buildVerifyBusy: boolean;
  buildVerifyResult: AppStudioPublishRunResult | null;
  activeStage: BuildVerifyStageId | null;
  stepStatuses: Partial<Record<BuildVerifyStageId, PublishPhaseStatus>>;
}): PublishProcessStep[] {
  const buildSkippedForCurrentInstaller = input.useCurrentInstallerForPublish && !input.signInstaller;
  const completedStatus: PublishPhaseStatus | null = input.buildVerifyResult?.ok === true ? "passed" : input.buildVerifyResult?.ok === false ? "failed" : null;
  const statusFor = (stage: BuildVerifyStageId): PublishPhaseStatus => {
    if (stage === "signing") {
      if (input.signCurrentInstallerBusy) {
        return "running";
      }
      if (input.signCurrentInstallerResult?.ok === true) {
        return "passed";
      }
      if (input.signCurrentInstallerResult?.ok === false) {
        return "failed";
      }
      if (!input.signInstaller) {
        return "skipped";
      }
    }
    if (buildSkippedForCurrentInstaller && stage !== "signing") {
      return "skipped";
    }
    if (input.stepStatuses[stage]) {
      return input.stepStatuses[stage] ?? "pending";
    }
    if (completedStatus) {
      return stage === "signing" && !input.signInstaller ? "skipped" : completedStatus;
    }
    if (input.buildVerifyBusy && input.activeStage === stage) {
      return "running";
    }
    return "pending";
  };

  return [
    {
      id: "preflight",
      title: "環境確認",
      detail: "node / npm / cargo / rustc と release build 前提を確認します。",
      status: statusFor("preflight"),
    },
    {
      id: "app_packs",
      title: "App Pack 作成/再利用",
      detail: "変更なしの App Pack は sha256 / size 照合後に再利用します。",
      status: statusFor("app_packs"),
    },
    {
      id: "runtime",
      title: "runtime 準備",
      detail: "同梱 Python と Web automation runtime を確認します。",
      status: statusFor("runtime"),
    },
    {
      id: "tauri_build",
      title: "Tauri build",
      detail: "既存 node_modules を使い、frontend と Tauri release build を実行します。",
      status: statusFor("tauri_build"),
    },
    {
      id: "installer",
      title: "installer 作成",
      detail: "NSIS installer を収集し、manifest の sha256 / size を更新します。",
      status: statusFor("installer"),
    },
    {
      id: "signing",
      title: "installer 署名",
      detail: input.signInstaller || input.requireInstallerSignature || input.useCurrentInstallerForPublish
        ? "証明書設定が有効な場合だけ Authenticode 署名または署名検証を行います。"
        : "署名なし配布の既定です。sha256 / size と公開後検証で補強します。",
      status: statusFor("signing"),
    },
    {
      id: "strict_verify",
      title: "strict verify",
      detail: "installer、App Pack、runtime、署名条件を release gate として検証します。",
      status: statusFor("strict_verify"),
    },
  ];
}

function emptyToNull(value: string): string | null {
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
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
