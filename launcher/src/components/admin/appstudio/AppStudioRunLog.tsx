import type { AppStudioRunResult } from "../../../lib/appStudioTypes";

interface Props {
  busy: boolean;
  result: AppStudioRunResult | null;
}

export function AppStudioRunLog({ busy, result }: Props) {
  return (
    <section className="studio-side-section">
      <div className="admin-section-head">
        <div>
          <p className="dialog-kicker">実行ログ</p>
          <h4>stdout / stderr</h4>
        </div>
        <span className={`admin-status-pill ${result?.ok ? "ok" : ""}`}>{busy ? "実行中" : result ? statusText(result.ok) : "未実行"}</span>
      </div>
      {busy ? <p className="admin-muted">App Studioを実行しています。完了まで画面を閉じずに待ってください。</p> : null}
      <pre className="studio-log">{result ? joinLogs(result) : "まだ実行ログはありません。"}</pre>
    </section>
  );
}

function statusText(ok: boolean): string {
  return ok ? "成功" : "失敗";
}

function joinLogs(result: AppStudioRunResult): string {
  const parts = [
    `exitCode: ${result.exitCode}`,
    "",
    "[stdout]",
    result.stdout.trim() || "(empty)",
    "",
    "[stderr]",
    result.stderr.trim() || "(empty)",
  ];
  return parts.join("\n");
}
