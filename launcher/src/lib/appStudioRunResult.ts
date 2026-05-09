import {
  getAppStudioApprovalDecision,
  getAppStudioApprovalFailureGuidance,
  type AppStudioApprovalDecision,
  type AppStudioApprovalFailureGuidance,
} from "./appStudioApproval";
import type { AppStudioApprovalMode, AppStudioRunResult } from "./appStudioTypes";

export type AppStudioRunAction = "suggest" | "apply" | "approve";

export interface AppStudioRunResultViewOptions {
  approvalMode: AppStudioApprovalMode;
  busy?: boolean;
  lastAction?: AppStudioRunAction | null;
}

export interface AppStudioRunResultView {
  approvalDecision: AppStudioApprovalDecision;
  approvalFailureGuidance: AppStudioApprovalFailureGuidance | null;
  canApprove: boolean;
  warningOnly: boolean;
  secretBlocked: boolean;
  statusPillLabel: string;
  statusPillOk: boolean;
  primaryNextAction: string;
  processResultLabel: string;
  lastActionLabel: string;
  metadataOverrideLabel: string;
  iconOverrideLabel: string;
  exeReadinessLabel: string;
  executionStatusLabel: string;
  runtimeStatusLabel: string;
  timingSummary: string;
  timingDetailSummary: string;
  approvalRecordSummary: string;
  catalogSummary: string;
  manifestEnabledLabel: string;
  appPackLabel: string;
  blockingReasons: string[];
  nonBlockingWarnings: string[];
  manualChecks: string[];
}

export interface AppStudioImportSidebarNextActionInput {
  step: string;
  hasEntry: boolean;
  preflightOk: boolean;
  result: AppStudioRunResult | null;
  approvalMode: AppStudioApprovalMode;
  lastAction?: AppStudioRunAction | null;
}

export interface AppStudioUpdateNextActionInput {
  result: AppStudioRunResult | null;
  lastAction: AppStudioRunAction | null;
  approvalMode: AppStudioApprovalMode;
  versionCompare: number | null;
}

export function normalizeAppStudioRunResult(
  result: AppStudioRunResult | null,
  options: AppStudioRunResultViewOptions,
): AppStudioRunResultView {
  const approvalDecision = getAppStudioApprovalDecision(result, options.approvalMode, options.busy ?? false);
  const approvalFailureGuidance = getAppStudioApprovalFailureGuidance(result);
  const canApprove = approvalDecision.canApprove;
  const warningOnly = isAppStudioWarningOnly(result);
  const secretBlocked = isAppStudioSecretBlocked(result);
  return {
    approvalDecision,
    approvalFailureGuidance,
    canApprove,
    warningOnly,
    secretBlocked,
    statusPillLabel: result?.enabled ? "有効化済み" : canApprove ? "承認可能" : "未承認",
    statusPillOk: Boolean(result?.enabled || canApprove),
    primaryNextAction: appStudioRunResultNextAction(
      result,
      options.lastAction ?? null,
      approvalFailureGuidance?.nextAction ?? approvalDecision.reason,
    ),
    processResultLabel: result ? boolLabel(result.ok) : "-",
    lastActionLabel: appStudioActionLabel(options.lastAction ?? null),
    metadataOverrideLabel: metadataOverrideText(result),
    iconOverrideLabel: iconOverrideText(result),
    exeReadinessLabel: appStudioStatusLabel(result?.exeReadinessStatus),
    executionStatusLabel: appStudioStatusLabel(result?.executionStatus),
    runtimeStatusLabel: appStudioStatusLabel(result?.runtimeStatus),
    timingSummary: timingSummary(result),
    timingDetailSummary: result ? timingDetailSummary(result) : "-",
    approvalRecordSummary: approvalRecordSummary(result),
    catalogSummary: catalogSummary(result),
    manifestEnabledLabel: triStateLabel(result?.manifestEnabled),
    appPackLabel: result?.appPack ?? "未作成",
    blockingReasons: result?.approvalBlockingReasons ?? [],
    nonBlockingWarnings: result?.nonBlockingWarningSummaries ?? [],
    manualChecks: result?.manualChecks ?? [],
  };
}

export function getAppStudioImportSidebarNextAction(input: AppStudioImportSidebarNextActionInput): string {
  if (input.step === "selectEntry") {
    return input.hasEntry ? "アプリIDと表示名を確認し、必要なら事前確認を実行してから次へ進んでください。" : "登録するアプリのメインファイルを選択してください。";
  }
  if (input.step === "aiProposal") {
    return "保存済み提案を読むか、AIで新しく提案を作成してください。";
  }
  if (input.step === "review") {
    return "説明文、カテゴリ、アイコンを確認し、必要ならAIアイコンを再生成してください。";
  }
  if (!input.result) {
    return input.preflightOk ? "登録内容を作成し、続けてテスト登録と配布物検証を行ってください。" : "まず事前確認を実行してください。";
  }
  return normalizeAppStudioRunResult(input.result, {
    approvalMode: input.approvalMode,
    lastAction: input.lastAction ?? null,
  }).primaryNextAction;
}

export function collectAppStudioRunResultWarnings(result: AppStudioRunResult | null): string[] {
  const warnings = new Set<string>();
  if (result?.executionStatus === "warn") {
    warnings.add("配布物検証が警告扱いです。ログとレポートを確認してください。");
  }
  if (isAppStudioSecretBlocked(result)) {
    warnings.add("秘密情報検査で停止しています。secret_scan_report.md を確認してください。");
  }
  const guidance = getAppStudioApprovalFailureGuidance(result);
  if (guidance) {
    warnings.add(guidance.reason);
  }
  return Array.from(warnings);
}

export function getAppStudioRunResultMessage(result: AppStudioRunResult, action: AppStudioRunAction): string {
  if (!result.ok && isAppStudioWarningOnly(result)) {
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

export function getAppStudioUpdateNextAction(input: AppStudioUpdateNextActionInput): string {
  if (input.versionCompare === 1) {
    return "新しいバージョンが現在版より古いです。Version Bump を見直してください。";
  }
  if (!input.result) {
    return "Preflight 後に更新内容を作成してください。";
  }
  const view = normalizeAppStudioRunResult(input.result, {
    approvalMode: input.approvalMode,
    lastAction: input.lastAction,
  });
  if (!input.result.ok && !view.warningOnly) {
    return view.approvalFailureGuidance?.nextAction ?? view.approvalDecision.reason;
  }
  if (input.result.enabled) {
    return "更新は承認済みです。通常ランチャーで表示と起動を確認してください。";
  }
  if (input.lastAction === "suggest") {
    return "Apply update でテスト更新と配布物検証を実行してください。";
  }
  if (input.lastAction === "apply") {
    return view.canApprove ? "テスト更新結果を確認し、問題なければ承認して有効化してください。" : view.primaryNextAction;
  }
  return view.primaryNextAction;
}

export function getAppStudioUpdateRunResultMessage(result: AppStudioRunResult, action: AppStudioRunAction): string {
  if (!result.ok && isAppStudioWarningOnly(result)) {
    return "警告がありますが更新処理は完了しました。ログとレポートを確認してください。";
  }
  if (!result.ok) {
    return "更新処理に失敗しました。理由と次の操作を確認してください。";
  }
  if (action === "approve") {
    if (result.manifestEnabled === true && result.catalogVisible === true) {
      return "更新を承認して有効化しました。ホームの更新後にアプリ一覧へ反映されます。";
    }
    if (result.manifestEnabled === true) {
      return `更新承認は完了しましたが、ホーム表示の確認が未完了です。理由: ${result.catalogDisabledReason || result.catalogLoadError || "catalog_visible=false"}`;
    }
    return `更新承認は完了していません。理由: ${result.approvalFailureSummary || result.verifyReleaseFailureSummary || "manifest enabled=false"}`;
  }
  if (result.enabled) {
    return "更新を承認して有効化しました。通常ランチャーで表示を確認してください。";
  }
  if (action === "apply") {
    return "テスト更新と配布物検証が完了しました。問題なければ承認してください。";
  }
  return "更新内容を作成しました。内容を確認して次へ進んでください。";
}

export function isAppStudioWarningOnly(result: AppStudioRunResult | null | undefined): boolean {
  return result?.executionStatus === "warn" && result.approvalAllowed === true;
}

export function isAppStudioSecretBlocked(result: AppStudioRunResult | null | undefined): boolean {
  return Boolean(result?.applyBlockedBySecretScan || (result?.secretBlockingCount ?? 0) > 0);
}

export function appStudioStatusLabel(status?: string | null): string {
  if (status === "pass") {
    return "問題なし";
  }
  if (status === "warn") {
    return "警告あり";
  }
  if (status === "fail") {
    return "失敗";
  }
  return status || "未確認";
}

export function appStudioActionLabel(action: AppStudioRunAction | null): string {
  if (action === "suggest") {
    return "登録内容作成";
  }
  if (action === "apply") {
    return "テスト登録";
  }
  if (action === "approve") {
    return "承認";
  }
  return "-";
}

export function formatAppStudioSeconds(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) {
    return "-";
  }
  if (value < 60) {
    return `${value.toFixed(1)}秒`;
  }
  const minutes = Math.floor(value / 60);
  const seconds = Math.round(value % 60);
  return `${minutes}分${seconds}秒`;
}

function appStudioRunResultNextAction(
  result: AppStudioRunResult | null,
  lastAction: AppStudioRunAction | null,
  decisionReason: string,
): string {
  if (!result) {
    return "事前確認後、登録内容を作成してください。";
  }
  if (result.enabled) {
    return "承認済みです。通常ランチャーで表示と起動を確認してください。";
  }
  if (lastAction === "suggest") {
    return "テスト登録して配布物検証を実行してください。";
  }
  return decisionReason;
}

function boolLabel(value: boolean): string {
  return value ? "成功" : "失敗";
}

function metadataOverrideText(result: AppStudioRunResult | null): string {
  if (!result?.metadataOverrideUsed) {
    return "未使用";
  }
  return result.metadataOverrideKeys?.length ? result.metadataOverrideKeys.join(", ") : "使用";
}

function iconOverrideText(result: AppStudioRunResult | null): string {
  if (!result?.iconOverrideUsed) {
    return result?.selectedIconSource ?? "未使用";
  }
  return result.selectedIconSource ?? "使用";
}

function timingSummary(result: AppStudioRunResult | null): string {
  if (!result?.timingTotalSeconds) {
    return "-";
  }
  const estimate = result.timingEstimatedTotalSeconds ? ` / 目安 ${formatAppStudioSeconds(result.timingEstimatedTotalSeconds)}` : "";
  return `${formatAppStudioSeconds(result.timingTotalSeconds)}${estimate}`;
}

function timingDetailSummary(result: AppStudioRunResult): string {
  const actual = result.timingActualTotalSeconds ?? result.timingWallClockTotalSeconds ?? result.timingTotalSeconds;
  const estimate = result.timingEstimatedTotalSeconds;
  const error = result.timingPredictionErrorSeconds;
  const cli = result.timingCliMeasuredTotalSeconds;
  const overhead = result.timingUnmeasuredOverheadSeconds;
  const process = result.processWallClockSeconds;
  const parts = [
    `実績: ${formatAppStudioSeconds(actual)}`,
    estimate != null ? `予測: ${formatAppStudioSeconds(estimate)}` : "",
    error != null ? `差分: ${formatSignedSeconds(error)}` : "",
    process != null ? `Tauri子プロセス: ${formatAppStudioSeconds(process)}` : "",
    cli != null ? `工程計: ${formatAppStudioSeconds(cli)}` : "",
    overhead != null ? `未計測/待機: ${formatAppStudioSeconds(overhead)}` : "",
    result.timingPredictionSource ? `予測根拠: ${result.timingPredictionSource}` : "",
  ].filter(Boolean);
  return parts.join(" / ") || "-";
}

function approvalRecordSummary(result: AppStudioRunResult | null): string {
  if (!result) {
    return "-";
  }
  const status = result.approvalRecordStatus ?? "missing";
  const verify = result.verifyReleaseStatus ? ` / verify_release=${result.verifyReleaseStatus}` : "";
  return `${status}${verify}`;
}

function catalogSummary(result: AppStudioRunResult | null): string {
  if (!result) {
    return "-";
  }
  if (result.catalogVisible === true) {
    return "ホーム表示対象です";
  }
  if (result.catalogVisible === false) {
    return result.catalogDisabledReason || result.catalogLoadError || "ホーム表示対象ではありません";
  }
  return "未確認";
}

function triStateLabel(value: boolean | null | undefined): string {
  if (value === true) {
    return "true";
  }
  if (value === false) {
    return "false";
  }
  return "unknown";
}

function formatSignedSeconds(value: number): string {
  const sign = value > 0 ? "+" : "";
  return `${sign}${formatAppStudioSeconds(Math.abs(value))}`;
}
