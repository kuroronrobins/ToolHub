import { AlertTriangle, CheckCircle2, CircleAlert } from "lucide-react";
import type { AppStudioPreflightResult } from "../../../lib/appStudioTypes";

interface Props {
  result: AppStudioPreflightResult | null;
  busy: boolean;
  onRun: () => void;
}

export function AppStudioPreflightPanel({ result, busy, onRun }: Props) {
  return (
    <section className="studio-step">
      <div>
        <span className="studio-step-index">5</span>
        <h4>Preflight</h4>
      </div>
      <div className="studio-preflight-head">
        <span className={`admin-status-pill ${result?.ok ? "ok" : ""}`}>{result ? (result.ok ? "実行可能" : "要確認") : "未確認"}</span>
        <button className="secondary-button" type="button" onClick={onRun} disabled={busy}>
          事前確認
        </button>
      </div>
      <div className="studio-preflight-grid">
        <PreflightItem label="Entry exists" ok={result?.entryExists} />
        <PreflightItem label="AppId" ok={result?.appIdValid} />
        <PreflightItem label="BuildMode" ok={result?.buildModeValid} />
        <PreflightItem label="runtime python" ok={result?.runtimePythonExists} warnWhenFalse />
      </div>
      <p className="admin-muted">
        Python: {result ? pythonLabel(result) : "未確認"}。Pythonが見つからなくても通常ランチャー機能には影響しません。
      </p>
      {result?.warnings.length ? (
        <div className="studio-preflight-list warning">
          <AlertTriangle size={18} aria-hidden="true" />
          <ul>
            {result.warnings.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      ) : null}
      {result?.errors.length ? (
        <div className="studio-preflight-list error">
          <CircleAlert size={18} aria-hidden="true" />
          <ul>
            {result.errors.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}

function PreflightItem({ label, ok, warnWhenFalse = false }: { label: string; ok?: boolean; warnWhenFalse?: boolean }) {
  const className = ok === undefined ? "pending" : ok ? "ok" : warnWhenFalse ? "warn" : "fail";
  return (
    <div className={`studio-preflight-item ${className}`}>
      <CheckCircle2 size={17} aria-hidden="true" />
      <span>{label}</span>
    </div>
  );
}

function pythonLabel(result: AppStudioPreflightResult): string {
  if (result.pythonSource === "missing") {
    return "なし";
  }
  const source = result.pythonSource === "runtime" ? "runtime/python/python.exe" : `開発環境 fallback (${result.pythonSource})`;
  return result.pythonPath ? `${source} - ${result.pythonPath}` : source;
}
