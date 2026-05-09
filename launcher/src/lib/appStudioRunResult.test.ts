import { describe, expect, it } from "vitest";
import {
  collectAppStudioRunResultWarnings,
  getAppStudioImportSidebarNextAction,
  getAppStudioRunResultMessage,
  isAppStudioWarningOnly,
  normalizeAppStudioRunResult,
} from "./appStudioRunResult";
import type { AppStudioRunResult } from "./appStudioTypes";

function result(overrides: Partial<AppStudioRunResult> = {}): AppStudioRunResult {
  return {
    ok: true,
    exitCode: 0,
    stdout: "",
    stderr: "",
    userMessage: "",
    appId: "demo_app",
    executionStatus: "pass",
    approvalAllowed: true,
    ...overrides,
  };
}

describe("normalizeAppStudioRunResult", () => {
  it("keeps wrong-app approval failures actionable", () => {
    const view = normalizeAppStudioRunResult(
      result({
        ok: false,
        approvalAllowed: false,
        approvalFailureSummary: "Execution test result app_id mismatch.; expected_app_id=demo_app; result_app_id=other_app",
      }),
      { approvalMode: "strict", lastAction: "apply" },
    );

    expect(view.canApprove).toBe(false);
    expect(view.approvalFailureGuidance?.reason).toContain("別アプリ");
    expect(view.primaryNextAction).toContain("テスト登録を再実行");
  });

  it("turns stale results into a retry test-registration next action", () => {
    const view = normalizeAppStudioRunResult(
      result({
        ok: false,
        approvalAllowed: false,
        approvalFailureSummary: "Execution test result is stale.; stale_against=final_app/app.yaml is newer than execution_test_result.json",
      }),
      { approvalMode: "strict", lastAction: "apply" },
    );

    expect(view.canApprove).toBe(false);
    expect(view.approvalFailureGuidance?.reason).toContain("古い検証結果");
    expect(view.primaryNextAction).toContain("テスト登録を再実行");
  });

  it("surfaces secret scan blocks as a report-guided next action", () => {
    const blocked = result({
      ok: false,
      approvalAllowed: false,
      applyBlockedBySecretScan: true,
      secretBlockingCount: 2,
      secretScanReport: "secret_scan_report.md",
    });
    const view = normalizeAppStudioRunResult(blocked, { approvalMode: "strict", lastAction: "apply" });

    expect(view.canApprove).toBe(false);
    expect(view.secretBlocked).toBe(true);
    expect(view.primaryNextAction).toContain("secret_scan_report.md");
    expect(collectAppStudioRunResultWarnings(blocked)).toContain("秘密情報検査で停止しています。secret_scan_report.md を確認してください。");
  });

  it("blocks approval when approval-blocking warnings remain", () => {
    const view = normalizeAppStudioRunResult(
      result({
        approvalBlockingWarningsCount: 1,
        approvalBlockingReasons: ["required_files missing"],
      }),
      { approvalMode: "strict", lastAction: "apply" },
    );

    expect(view.canApprove).toBe(false);
    expect(view.blockingReasons).toEqual(["required_files missing"]);
    expect(view.primaryNextAction).toContain("配布リスク");
  });

  it("allows non-blocking warnings and treats warning-only CLI results as completed", () => {
    const warningOnly = result({
      ok: false,
      executionStatus: "warn",
      approvalAllowed: true,
      nonBlockingWarningsCount: 1,
      nonBlockingWarningSummaries: ["manual review note"],
    });
    const view = normalizeAppStudioRunResult(warningOnly, { approvalMode: "strict", lastAction: "apply" });

    expect(view.canApprove).toBe(true);
    expect(view.warningOnly).toBe(true);
    expect(view.nonBlockingWarnings).toEqual(["manual review note"]);
    expect(isAppStudioWarningOnly(warningOnly)).toBe(true);
    expect(getAppStudioRunResultMessage(warningOnly, "apply")).toContain("警告がありますが処理は完了");
  });

  it("treats enabled results as already approved in the UI view", () => {
    const view = normalizeAppStudioRunResult(result({ enabled: true, manifestEnabled: true, catalogVisible: true }), {
      approvalMode: "strict",
      lastAction: "approve",
    });

    expect(view.statusPillLabel).toBe("有効化済み");
    expect(view.statusPillOk).toBe(true);
    expect(view.primaryNextAction).toContain("承認済み");
  });

  it("keeps missing results in a test-registration waiting state", () => {
    const view = normalizeAppStudioRunResult(null, { approvalMode: "strict" });

    expect(view.canApprove).toBe(false);
    expect(view.primaryNextAction).toContain("登録内容を作成");
    expect(
      getAppStudioImportSidebarNextAction({
        step: "register",
        hasEntry: true,
        preflightOk: false,
        result: null,
        approvalMode: "strict",
      }),
    ).toContain("事前確認");
  });

  it("keeps suggest results pointed at test registration in the sidebar", () => {
    expect(
      getAppStudioImportSidebarNextAction({
        step: "register",
        hasEntry: true,
        preflightOk: true,
        result: result({ approvalAllowed: false }),
        approvalMode: "strict",
        lastAction: "suggest",
      }),
    ).toContain("テスト登録");
  });
});
