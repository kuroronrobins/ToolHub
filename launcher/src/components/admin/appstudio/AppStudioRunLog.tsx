import type { AppStudioRunResult } from "../../../lib/appStudioTypes";

interface Props {
  busy: boolean;
  result: AppStudioRunResult | null;
}

export function AppStudioRunLog({ busy, result }: Props) {
  const warningOnly = result?.executionStatus === "warn" && result.approvalAllowed === true;
  return (
    <section className="studio-side-section">
      <div className="admin-section-head">
        <div>
          <p className="dialog-kicker">Run log</p>
          <h4>stdout / stderr</h4>
        </div>
        <span className={`admin-status-pill ${result?.ok || warningOnly ? "ok" : ""}`}>
          {busy ? "running" : result ? statusText(result) : "idle"}
        </span>
      </div>
      {busy ? <p className="admin-muted">App Studio is running. Wait for the command to finish before approving.</p> : null}
      {warningOnly ? (
        <p className="admin-muted">
          The command returned a non-zero exit code, but execution_test_result.json is warn and approval_allowed=true.
          Review the logs, then approve with AllowWarnings if acceptable.
        </p>
      ) : null}
      <pre className="studio-log">{result ? joinLogs(result) : "No run log yet."}</pre>
    </section>
  );
}

function statusText(result: AppStudioRunResult): string {
  if (result.ok) {
    return "success";
  }
  if (result.executionStatus === "warn" && result.approvalAllowed === true) {
    return "warning";
  }
  return "failed";
}

function joinLogs(result: AppStudioRunResult): string {
  const parts = [
    `exitCode: ${result.exitCode}`,
    `executionStatus: ${result.executionStatus ?? "unknown"}`,
    `approvalAllowed: ${String(result.approvalAllowed ?? "unknown")}`,
    "",
    "[stdout]",
    result.stdout.trim() || "(empty)",
    "",
    "[stderr]",
    result.stderr.trim() || "(empty)",
  ];
  return parts.join("\n");
}
