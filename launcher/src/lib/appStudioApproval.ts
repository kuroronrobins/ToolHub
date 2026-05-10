import type { AppStudioApprovalMode, AppStudioRunResult } from "./appStudioTypes";

type AppStudioApprovalContextAction = "suggest" | "apply" | "approve" | null;

export type AppStudioApprovalBlockingKind =
  | "none"
  | "busy"
  | "missing_result"
  | "not_apply_result"
  | "execution_fail"
  | "approval_disallowed"
  | "approval_blocking_warning"
  | "strict_blocks_warning"
  | "stale_result";

export interface AppStudioApprovalDecision {
  canApprove: boolean;
  reason: string;
  blockingKind: AppStudioApprovalBlockingKind;
  systemDecision: string;
  modeDecision: string;
}

export interface AppStudioApprovalFailureGuidance {
  reason: string;
  nextAction: string;
}

export function getAppStudioApprovalDecision(
  result: AppStudioRunResult | null,
  approvalMode: AppStudioApprovalMode,
  busy = false,
  lastAction: AppStudioApprovalContextAction = null,
): AppStudioApprovalDecision {
  if (busy) {
    return blocked("busy", "処理中のため、完了後に承認できます。", "処理中", "処理中");
  }
  if (!result?.appId) {
    return blocked("missing_result", "テスト登録の結果がまだありません。", "未判定", "承認不可");
  }
  if (result.enabled) {
    return blocked("not_apply_result", "このアプリはすでに有効化されています。", "承認済み", "承認済み");
  }
  if (isWaitingForTestRegistration(result, lastAction)) {
    return blocked(
      "approval_disallowed",
      "テスト登録と配布物検証がまだ完了していません。先に「テスト登録して配布物検証」を実行してください。",
      "テスト未実行",
      "承認不可",
    );
  }
  if (result.executionStatus === "fail") {
    const guidance = getAppStudioApprovalFailureGuidance(result);
    return blocked(
      "execution_fail",
      guidance?.reason ?? "配布物検証が失敗しています。fail check を解消してください。",
      "approval_allowed=false",
      "承認不可",
    );
  }
  if (result.approvalAllowed !== true) {
    return blocked("approval_disallowed", approvalDisallowedReason(result), "approval_allowed=false", "承認不可");
  }

  const blockingWarnings = result.approvalBlockingWarningsCount ?? 0;
  const nonBlockingWarnings = result.nonBlockingWarningsCount ?? 0;
  if (blockingWarnings > 0) {
    const reason = `配布リスクのある未解決警告が ${blockingWarnings} 件あります。`;
    return blocked("approval_blocking_warning", reason, "approval_allowed=false", "承認不可");
  }
  if (approvalMode === "strict" && nonBlockingWarnings > 0) {
    return {
      canApprove: true,
      reason: "配布リスクのない警告のみです。デフォルトの慎重モードでも承認できます。",
      blockingKind: "none",
      systemDecision: "approval_allowed=true",
      modeDecision: "strictでも承認可",
    };
  }
  if (nonBlockingWarnings > 0) {
    return {
      canApprove: true,
      reason: "配布リスクのない警告のみです。詳細を確認して問題なければ承認できます。",
      blockingKind: "none",
      systemDecision: "approval_allowed=true",
      modeDecision: "警告ありでも承認可",
    };
  }
  return {
    canApprove: true,
    reason: "配布物検証は承認可能です。",
    blockingKind: "none",
    systemDecision: "approval_allowed=true",
    modeDecision: approvalMode === "strict" ? "strictで承認可" : "承認可",
  };
}

function approvalDisallowedReason(result: AppStudioRunResult): string {
  const guidance = getAppStudioApprovalFailureGuidance(result);
  if (guidance) {
    return guidance.reason;
  }
  if ((result.unresolvedDistributionRisksCount ?? 0) > 0) {
    return `未解決の配布リスクが ${result.unresolvedDistributionRisksCount} 件あります。`;
  }
  if (result.applyBlockedBySecretScan || (result.secretBlockingCount ?? 0) > 0) {
    return "secret混入リスクがあります。secret_scan_report.md を確認してください。";
  }
  return "execution_test_result.json が承認不可を示しています。再度テスト登録するか、fail check を確認してください。";
}

function isWaitingForTestRegistration(result: AppStudioRunResult, lastAction: AppStudioApprovalContextAction): boolean {
  if (result.executionStatus || result.approvalAllowed === true || result.enabled) {
    return false;
  }
  if (lastAction === "suggest") {
    return true;
  }
  return Boolean(
    result.appId &&
      !result.appPack &&
      result.manifestEnabled !== true &&
      (result.catalogDisabledReason === "app_yaml_missing" || result.catalogVisible === false),
  );
}

export function getAppStudioApprovalFailureGuidance(result: AppStudioRunResult | null): AppStudioApprovalFailureGuidance | null {
  const summary = result?.approvalFailureSummary?.trim();
  if (!summary) {
    return null;
  }
  const lower = summary.toLowerCase();
  const retryApply = "App Studio のテスト登録を再実行し、結果を再読み込みしてから承認してください。";
  if (lower.includes("app_id mismatch")) {
    return {
      reason: `承認ゲートが別アプリの検証結果を検出しました。${compactSummary(summary)}`,
      nextAction: retryApply,
    };
  }
  if (lower.includes("output_dir mismatch")) {
    return {
      reason: `承認ゲートが別の出力フォルダの検証結果を検出しました。${compactSummary(summary)}`,
      nextAction: "現在の出力先で App Studio のテスト登録を再実行し、結果を再読み込みしてから承認してください。",
    };
  }
  if (lower.includes(" is stale") || lower.includes("stale_against=")) {
    return {
      reason: `承認ゲートが古い検証結果を検出しました。${compactSummary(summary)}`,
      nextAction: retryApply,
    };
  }
  if (lower.includes("runtime check result blocks approval") || lower.includes("runtime check result contains approval-blocking warnings")) {
    return {
      reason: `runtime 検証が承認を止めています。${compactSummary(summary)}`,
      nextAction: "runtime_check_result.json の fail または配布リスク警告を解消し、テスト登録を再実行してください。",
    };
  }
  if (
    lower.includes("source entry file is missing") ||
    lower.includes("source root directory is missing") ||
    lower.includes("pyinstaller_input_path_missing") ||
    lower.includes("winerror 2")
  ) {
    return {
      reason: `アプリのソースファイルが見つからないため、配布用exeを作成できません。${compactSummary(summary)}`,
      nextAction: "アプリ選択で現在存在する entry/app.py を選び直すか、移動したソースフォルダを元の場所に戻してからテスト登録を再実行してください。",
    };
  }
  if (lower.includes("execution test result does not allow approval") || lower.includes("execution test result contains fail checks") || lower.includes("overall_status=fail")) {
    return {
      reason: `execution 検証が承認を止めています。${compactSummary(summary)}`,
      nextAction: "execution_test_result.json の fail check を解消し、テスト登録を再実行してください。",
    };
  }
  return {
    reason: `承認ゲートで停止しました。${compactSummary(summary)}`,
    nextAction: "approval_record.md の Failures を確認し、必要なら診断スクリプトを実行してください。",
  };
}

function compactSummary(value: string): string {
  const first = value.split("|")[0]?.trim() || value;
  return first.length > 220 ? `${first.slice(0, 220)}...` : first;
}

function blocked(
  blockingKind: AppStudioApprovalBlockingKind,
  reason: string,
  systemDecision: string,
  modeDecision: string,
): AppStudioApprovalDecision {
  return {
    canApprove: false,
    reason,
    blockingKind,
    systemDecision,
    modeDecision,
  };
}
