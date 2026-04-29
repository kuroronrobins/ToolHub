import type { AppStudioApprovalMode, AppStudioRunResult } from "./appStudioTypes";

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

export function getAppStudioApprovalDecision(
  result: AppStudioRunResult | null,
  approvalMode: AppStudioApprovalMode,
  busy = false,
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
  if (result.executionStatus === "fail") {
    return blocked("execution_fail", "配布物検証が失敗しています。fail check を解消してください。", "approval_allowed=false", "承認不可");
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
  if ((result.unresolvedDistributionRisksCount ?? 0) > 0) {
    return `未解決の配布リスクが ${result.unresolvedDistributionRisksCount} 件あります。`;
  }
  if (result.applyBlockedBySecretScan || (result.secretBlockingCount ?? 0) > 0) {
    return "secret混入リスクがあります。secret_scan_report.md を確認してください。";
  }
  return "execution_test_result.json が承認不可を示しています。再度テスト登録するか、fail check を確認してください。";
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
