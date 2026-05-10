import { describe, expect, it } from "vitest";
import { getAppStudioApprovalDecision, getAppStudioApprovalFailureGuidance } from "./appStudioApproval";
import type { AppStudioRunResult } from "./appStudioTypes";

function result(approvalFailureSummary: string): AppStudioRunResult {
  return {
    ok: false,
    exitCode: 1,
    stdout: "",
    stderr: "",
    userMessage: "",
    appId: "demo_app",
    approvalAllowed: true,
    approvalFailureSummary,
  };
}

describe("getAppStudioApprovalFailureGuidance", () => {
  it("explains wrong-app approval failures", () => {
    const guidance = getAppStudioApprovalFailureGuidance(
      result("Execution test result app_id mismatch.; expected_app_id=demo_app; result_app_id=other_app"),
    );

    expect(guidance?.reason).toContain("別アプリ");
    expect(guidance?.nextAction).toContain("テスト登録を再実行");
  });

  it("explains stale approval failures", () => {
    const guidance = getAppStudioApprovalFailureGuidance(
      result("Runtime check result is stale.; stale_against=final_app/app.yaml is newer than runtime_check_result.json"),
    );

    expect(guidance?.reason).toContain("古い検証結果");
    expect(guidance?.nextAction).toContain("結果を再読み込み");
  });

  it("explains runtime blocking failures", () => {
    const guidance = getAppStudioApprovalFailureGuidance(
      result("Runtime check result blocks approval.; fail_checks=[fail] requirements.lock exists: Missing"),
    );

    expect(guidance?.reason).toContain("runtime 検証");
    expect(guidance?.nextAction).toContain("runtime_check_result.json");
  });

  it("explains missing source entry failures", () => {
    const guidance = getAppStudioApprovalFailureGuidance(
      result("Execution test result contains fail checks: frozen-folder build: Source entry file is missing before PyInstaller build. entry=C:\\work\\app.py"),
    );

    expect(guidance?.reason).toContain("ソースファイル");
    expect(guidance?.nextAction).toContain("選び直す");
  });

  it("uses failure guidance when execution status failed", () => {
    const decision = getAppStudioApprovalDecision(
      {
        ...result("Execution test result contains fail checks: frozen-folder build: Source entry file is missing before PyInstaller build. entry=C:\\work\\app.py"),
        executionStatus: "fail",
        approvalAllowed: false,
      },
      "strict",
    );

    expect(decision.canApprove).toBe(false);
    expect(decision.reason).toContain("ソースファイル");
  });

  it("points suggest-only results at test registration before approval", () => {
    const decision = getAppStudioApprovalDecision(
      {
        ok: true,
        exitCode: 0,
        stdout: "",
        stderr: "",
        userMessage: "",
        appId: "demo_app",
        selectedBuildMode: "frozen-folder",
        catalogVisible: false,
        catalogDisabledReason: "app_yaml_missing",
      },
      "strict",
      false,
      "suggest",
    );

    expect(decision.canApprove).toBe(false);
    expect(decision.reason).toContain("テスト登録");
    expect(decision.systemDecision).toBe("テスト未実行");
  });
});
