import type { AppStudioAiProposal, AppStudioImportRequest, AppStudioPreflightResult, AppStudioRunResult } from "../../../lib/appStudioTypes";
import { AppStudioOperationBanner, type StudioOperationState } from "./AppStudioOperationBanner";
import { type AppStudioImportStep, importStepLabel } from "./AppStudioStepNav";

interface Props {
  step: AppStudioImportStep;
  operation: StudioOperationState;
  request: AppStudioImportRequest;
  preflight: AppStudioPreflightResult | null;
  result: AppStudioRunResult | null;
  aiProposal: AppStudioAiProposal | null;
  message: string;
  error: string;
}

export function AppStudioImportSidebar({ step, operation, request, preflight, result, aiProposal, message, error }: Props) {
  const warnings = collectWarnings(preflight, result, aiProposal);
  return (
    <section className="studio-side-section studio-import-sidebar">
      <div className="admin-section-head">
        <div>
          <p className="dialog-kicker">現在の状態</p>
          <h4>{importStepLabel(step)}</h4>
        </div>
        <span className={`admin-status-pill ${result?.enabled ? "ok" : ""}`}>{result?.enabled ? "承認済み" : "未承認"}</span>
      </div>

      <AppStudioOperationBanner operation={operation} compact />

      <div className="studio-next-action">
        <strong>次にやること</strong>
        <p>{nextAction(step, request, preflight, result)}</p>
      </div>

      {message ? <p className="admin-success">{message}</p> : null}
      {error ? <p className="admin-error" role="alert">{error}</p> : null}

      <dl className="studio-sidebar-status">
        <div>
          <dt>アプリID</dt>
          <dd>{request.appId || result?.appId || "-"}</dd>
        </div>
        <div>
          <dt>バージョン</dt>
          <dd>{request.version || result?.newVersion || result?.currentVersion || "-"}</dd>
        </div>
        <div>
          <dt>実行方式</dt>
          <dd>{result?.selectedBuildMode || request.buildMode}</dd>
        </div>
        <div>
          <dt>事前確認</dt>
          <dd>{preflight ? (preflight.ok ? "OK" : "要確認") : "未実行"}</dd>
        </div>
        <div>
          <dt>メタデータ生成</dt>
          <dd>{reportStatus(aiProposal?.metadata.aiReport)}</dd>
        </div>
        <div>
          <dt>画像生成</dt>
          <dd>{reportStatus(aiProposal?.icon.aiReport)}</dd>
        </div>
        <div>
          <dt>承認状態</dt>
          <dd>{result?.enabled ? "有効化済み" : "未承認"}</dd>
        </div>
      </dl>

      {warnings.length ? (
        <div className="studio-sidebar-warnings">
          <strong>警告</strong>
          <ul>
            {warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}

function nextAction(
  step: AppStudioImportStep,
  request: AppStudioImportRequest,
  preflight: AppStudioPreflightResult | null,
  result: AppStudioRunResult | null,
): string {
  if (step === "selectEntry") {
    return request.entry ? "アプリIDと表示名を確認し、必要なら事前確認を実行してから次へ進んでください。" : "登録するアプリのメインファイルを選択してください。";
  }
  if (step === "aiProposal") {
    return "AI提案を作成するか、AIを使わず手動入力へ進んでください。";
  }
  if (step === "review") {
    return "説明文、カテゴリ、アイコンを確認し、問題なければ登録へ進んでください。";
  }
  if (!result) {
    return preflight?.ok ? "登録内容を作成し、続けて仮登録と実行確認を行ってください。" : "まず事前確認を実行してください。";
  }
  if (result.enabled) {
    return "承認済みです。通常ランチャーで表示と起動を確認してください。";
  }
  if (result.executionStatus === "fail" || result.approvalAllowed === false) {
    return "実行確認の失敗を解消してから承認してください。";
  }
  return "仮登録結果を確認し、問題なければ承認して有効化してください。";
}

function collectWarnings(preflight: AppStudioPreflightResult | null, result: AppStudioRunResult | null, aiProposal: AppStudioAiProposal | null): string[] {
  const warnings = new Set<string>();
  preflight?.warnings.forEach((warning) => warnings.add(warning));
  aiProposal?.warnings.forEach((warning) => warnings.add(warning));
  if (result?.executionStatus === "warn") {
    warnings.add("実行確認が警告扱いです。ログとレポートを確認してください。");
  }
  if (reportStatus(aiProposal?.icon.aiReport) === "フォールバック") {
    warnings.add("画像生成はフォールバックPNGを使用しています。");
  }
  return Array.from(warnings);
}

function reportStatus(report?: string | null): string {
  if (!report) {
    return "未実行";
  }
  const line = report.split(/\r?\n/).find((item) => item.trim().startsWith("status:"));
  const value = line?.slice("status:".length).trim();
  if (value === "success") {
    return "成功";
  }
  if (value === "fallback") {
    return "フォールバック";
  }
  if (value === "skipped") {
    return "スキップ";
  }
  if (value === "failed") {
    return "失敗";
  }
  return value || "未実行";
}
