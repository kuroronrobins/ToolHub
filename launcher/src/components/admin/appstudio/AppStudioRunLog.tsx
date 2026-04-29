import type { AppStudioRunResult } from "../../../lib/appStudioTypes";

interface Props {
  busy: boolean;
  result: AppStudioRunResult | null;
}

export function AppStudioRunLog({ busy, result }: Props) {
  const warningOnly = result?.executionStatus === "warn" && result.approvalAllowed === true;
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
      {warningOnly ? (
        <p className="admin-muted">
          CLIの終了コードが0以外でも、execution_test_result.json が warn かつ approval_allowed=true の場合があります。配布リスクのない警告だけなら慎重モードでも承認できます。
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
  if (result.executionStatus === "warn" && result.approvalAllowed === true) {
    return "警告";
  }
  return "失敗";
}

function joinLogs(result: AppStudioRunResult): string {
  const parts = [
    `exitCode: ${result.exitCode}`,
    `executionStatus: ${result.executionStatus ?? "unknown"}`,
    `approvalAllowed: ${String(result.approvalAllowed ?? "unknown")}`,
    `approvalBlockingWarnings: ${String(result.approvalBlockingWarningsCount ?? 0)}`,
    `nonBlockingWarnings: ${String(result.nonBlockingWarningsCount ?? 0)}`,
    `timingTotalSeconds: ${String(result.timingTotalSeconds ?? "unknown")}`,
    "",
    "[stdout]",
    result.stdout.trim() || "(empty)",
    "",
    "[stderr]",
    result.stderr.trim() || "(empty)",
  ];
  return parts.join("\n");
}
