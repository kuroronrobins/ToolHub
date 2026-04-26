import { AlertTriangle, CheckCircle2, CircleAlert, Info } from "lucide-react";
import type { AppStudioPreflightResult } from "../../../lib/appStudioTypes";

interface Props {
  result: AppStudioPreflightResult | null;
  busy: boolean;
  onRun: () => void;
}

type PreflightSeverity = "pending" | "ok" | "warn" | "fix" | "fail";

interface PreflightDisplayItem {
  label: string;
  severity: PreflightSeverity;
  judgement: string;
  reason: string;
  next: string;
}

export function AppStudioPreflightPanel({ result, busy, onRun }: Props) {
  const summary = preflightSummary(result);
  const items = preflightItems(result);
  return (
    <section className="studio-step">
      <div>
        <span className="studio-step-index">P</span>
        <h4>事前確認</h4>
      </div>
      <div className="studio-preflight-head">
        <div className={`studio-preflight-summary ${summary.severity}`}>
          <strong>{summary.title}</strong>
          <span>{summary.message}</span>
        </div>
        <button className="secondary-button" type="button" onClick={onRun} disabled={busy} title={busy ? "処理中は実行できません" : "登録前の確認を実行します"}>
          事前確認を実行
        </button>
      </div>

      <div className="studio-preflight-grid">
        {items.map((item) => (
          <PreflightItem key={item.label} item={item} />
        ))}
      </div>

      <p className="admin-muted">
        Python: {result ? pythonLabel(result) : "未確認"}。通常ランチャー機能には影響しませんが、配布前の再現性確認ではruntime検証を行ってください。
      </p>

      {result?.warnings.length ? (
        <div className="studio-preflight-list warning">
          <AlertTriangle size={18} aria-hidden="true" />
          <div>
            <strong>追加の注意</strong>
            <ul>
              {result.warnings.map((item) => (
                <li key={item}>{friendlyWarning(item)}</li>
              ))}
            </ul>
          </div>
        </div>
      ) : null}
      {result?.errors.length ? (
        <div className="studio-preflight-list error">
          <CircleAlert size={18} aria-hidden="true" />
          <div>
            <strong>進行不可の理由</strong>
            <ul>
              {result.errors.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </div>
        </div>
      ) : null}
    </section>
  );
}

function PreflightItem({ item }: { item: PreflightDisplayItem }) {
  const Icon = item.severity === "ok" ? CheckCircle2 : item.severity === "warn" || item.severity === "fix" ? AlertTriangle : CircleAlert;
  return (
    <div className={`studio-preflight-item ${item.severity}`}>
      <Icon size={17} aria-hidden="true" />
      <div>
        <strong>{item.label}</strong>
        <span>{item.judgement}</span>
        <small>{item.reason}</small>
        <em>
          <Info size={13} aria-hidden="true" />
          {item.next}
        </em>
      </div>
    </div>
  );
}

function preflightSummary(result: AppStudioPreflightResult | null): { severity: PreflightSeverity; title: string; message: string } {
  if (!result) {
    return { severity: "pending", title: "未確認", message: "登録前に一度実行してください。" };
  }
  if (result.errors.length || !result.entryExists || !result.appIdValid || !result.buildModeValid) {
    return { severity: "fail", title: "進行不可", message: "修正が必要です。このまま登録処理には進めません。" };
  }
  if (!result.runtimePythonExists) {
    return {
      severity: "warn",
      title: "要注意",
      message: "開発機のPythonで続行できますが、正式配布前にはToolHub同梱runtimeで再確認が必要です。",
    };
  }
  if (result.warnings.length) {
    return { severity: "fix", title: "配布前に要確認", message: "登録作業は続行できますが、正式配布前に警告内容を確認してください。" };
  }
  return { severity: "ok", title: "問題なし", message: "このまま次へ進めます。" };
}

function preflightItems(result: AppStudioPreflightResult | null): PreflightDisplayItem[] {
  return [
    {
      label: "メインファイル",
      severity: severityFor(result?.entryExists),
      judgement: judgementFor(result?.entryExists, "問題なし", "進行不可"),
      reason: result?.entryExists === false ? "指定されたファイルが見つかりません。" : "登録対象のファイルを確認します。",
      next: result?.entryExists === false ? "パスを修正するか、参照から選び直してください。" : "問題なければ次へ進めます。",
    },
    {
      label: "アプリID",
      severity: severityFor(result?.appIdValid),
      judgement: judgementFor(result?.appIdValid, "問題なし", "進行不可"),
      reason: result?.appIdValid === false ? "使用できない形式のアプリIDです。" : "ToolHub内で使う識別子です。",
      next: result?.appIdValid === false ? "小文字英数字、ハイフン、アンダースコア中心のIDにしてください。" : "表示名とは別に管理されます。",
    },
    {
      label: "実行方式",
      severity: severityFor(result?.buildModeValid),
      judgement: judgementFor(result?.buildModeValid, "問題なし", "進行不可"),
      reason: result?.buildModeValid === false ? "指定された実行方式を扱えません。" : "選択した方式で登録処理を進めます。",
      next: result?.buildModeValid === false ? "autoまたは推奨方式を選び直してください。" : "迷う場合はautoのままで問題ありません。",
    },
    {
      label: "同梱runtime",
      severity: result ? (result.runtimePythonExists ? "ok" : "warn") : "pending",
      judgement: result ? (result.runtimePythonExists ? "問題なし" : "要注意") : "未確認",
      reason: result?.runtimePythonExists
        ? "ToolHub同梱runtimeで確認できます。"
        : "runtime/python/python.exe は未配置です。開発機のPythonで続行できます。",
      next: result?.runtimePythonExists
        ? "正式配布前のruntime検証に使えます。"
        : "正式配布前にruntimeを同梱し、runtime検証を再実行してください。",
    },
  ];
}

function severityFor(ok?: boolean): PreflightSeverity {
  if (ok === undefined) {
    return "pending";
  }
  return ok ? "ok" : "fail";
}

function judgementFor(ok: boolean | undefined, okLabel: string, failLabel: string): string {
  if (ok === undefined) {
    return "未確認";
  }
  return ok ? okLabel : failLabel;
}

function friendlyWarning(warning: string): string {
  if (warning.includes("runtime/python/python.exe") || warning.toLowerCase().includes("runtime")) {
    return "開発機のPythonで続行できますが、正式配布前にはToolHub同梱runtimeで再確認が必要です。";
  }
  return warning;
}

function pythonLabel(result: AppStudioPreflightResult): string {
  if (result.pythonSource === "missing") {
    return "なし";
  }
  const source = result.pythonSource === "runtime" ? "runtime/python/python.exe" : `開発環境fallback (${result.pythonSource})`;
  return result.pythonPath ? `${source} - ${result.pythonPath}` : source;
}
