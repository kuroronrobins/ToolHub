import type { AppStudioRunResult } from "../../../lib/appStudioTypes";
import { isAppStudioWarningOnly } from "../../../lib/appStudioRunResult";

interface Props {
  busy: boolean;
  result: AppStudioRunResult | null;
}

export function AppStudioRunLog({ busy, result }: Props) {
  const warningOnly = isAppStudioWarningOnly(result);
  const referenceOnly = warningOnly && !(result?.adminAlerts?.length ?? 0);
  return (
    <section className="studio-side-section studio-run-log-section">
      <div className="admin-section-head">
        <div>
          <p className="dialog-kicker">実行ログ</p>
          <h4>stdout / stderr</h4>
        </div>
        <span className={`admin-status-pill ${result?.ok || warningOnly ? "ok" : ""}`}>
          {busy ? "実行中" : result ? statusText(result) : "未実行"}
        </span>
      </div>
      {busy ? <p className="admin-muted">App Studioを実行しています。完了するまで承認はできません。</p> : null}
      {referenceOnly ? (
        <p className="admin-muted">
          管理者対応が必要なアラートはありません。内部検証に参考情報だけが残っています。
        </p>
      ) : null}
      <pre className="studio-log">{result ? joinLogs(result) : "実行ログはまだありません。"}</pre>
    </section>
  );
}

function statusText(result: AppStudioRunResult): string {
  if (result.ok) {
    return "成功";
  }
  if (isAppStudioWarningOnly(result)) {
    return "参考情報";
  }
  return "失敗";
}

function joinLogs(result: AppStudioRunResult): string {
  const parts = [
    `exitCode: ${result.exitCode}`,
    `executionStatus: ${result.executionStatus ?? "unknown"}`,
    `approvalAllowed: ${String(result.approvalAllowed ?? "unknown")}`,
    `approvalBlockingWarnings: ${String(result.approvalBlockingWarningsCount ?? 0)}`,
    `adminAlerts: ${String(result.adminAlerts?.length ?? 0)}`,
    `timingTotalSeconds: ${String(result.timingTotalSeconds ?? "unknown")}`,
    `timingEstimatedTotalSeconds: ${String(result.timingEstimatedTotalSeconds ?? "unknown")}`,
    `timingPredictionErrorSeconds: ${String(result.timingPredictionErrorSeconds ?? "unknown")}`,
    `timingUnmeasuredOverheadSeconds: ${String(result.timingUnmeasuredOverheadSeconds ?? "unknown")}`,
    `processWallClockSeconds: ${String(result.processWallClockSeconds ?? "unknown")}`,
    `manifestEnabled: ${String(result.manifestEnabled ?? "unknown")}`,
    `approvalRecordStatus: ${result.approvalRecordStatus ?? "unknown"}`,
    `verifyReleaseStatus: ${result.verifyReleaseStatus ?? "unknown"}`,
    `catalogVisible: ${String(result.catalogVisible ?? "unknown")}`,
    `catalogDisabledReason: ${result.catalogDisabledReason ?? "none"}`,
    "",
    "[stdout]",
    result.stdout.trim() || "(empty)",
    "",
    "[stderr]",
    result.stderr.trim() || "(empty)",
  ];
  return parts.join("\n");
}
