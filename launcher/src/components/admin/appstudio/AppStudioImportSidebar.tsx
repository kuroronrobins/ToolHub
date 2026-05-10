import type { AppStudioAiProposal, AppStudioApprovalMode, AppStudioImportRequest, AppStudioPreflightResult, AppStudioRunResult } from "../../../lib/appStudioTypes";
import { normalizeAppStudioIconProposal } from "../../../lib/appStudioIconProposal";
import { collectAppStudioRunResultWarnings, getAppStudioImportSidebarNextAction, type AppStudioRunAction } from "../../../lib/appStudioRunResult";
import { AppStudioOperationBanner, type StudioOperationState } from "./AppStudioOperationBanner";
import { type AppStudioImportStep, importStepLabel } from "./AppStudioStepNav";

interface Props {
  step: AppStudioImportStep;
  operation: StudioOperationState;
  request: AppStudioImportRequest;
  preflight: AppStudioPreflightResult | null;
  result: AppStudioRunResult | null;
  aiProposal: AppStudioAiProposal | null;
  approvalMode: AppStudioApprovalMode;
  lastAction: AppStudioRunAction | null;
  message: string;
  error: string;
}

export function AppStudioImportSidebar({ step, operation, request, preflight, result, aiProposal, approvalMode, lastAction, message, error }: Props) {
  const warnings = collectWarnings(preflight, result, aiProposal);
  const nextAction = getAppStudioImportSidebarNextAction({
    step,
    hasEntry: Boolean(request.entry),
    preflightOk: preflight?.ok === true,
    result,
    approvalMode,
    lastAction,
  });
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
        <p>{nextAction}</p>
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
          <dt>登録方式</dt>
          <dd>{buildModeLabel(result?.selectedBuildMode || request.buildMode)}</dd>
        </div>
        <div>
          <dt>事前確認</dt>
          <dd>{preflightStatus(preflight)}</dd>
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
          <strong>直近の注意</strong>
          <ul>
            {warnings.slice(0, 4).map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}

function collectWarnings(preflight: AppStudioPreflightResult | null, result: AppStudioRunResult | null, aiProposal: AppStudioAiProposal | null): string[] {
  const warnings = new Set<string>();
  preflight?.warnings.forEach((warning) => warnings.add(friendlyWarning(warning)));
  aiProposal?.warnings.forEach((warning) => warnings.add(warning));
  collectAppStudioRunResultWarnings(result).forEach((warning) => warnings.add(warning));
  const normalizedIcon = aiProposal?.icon ? normalizeAppStudioIconProposal(aiProposal.icon) : null;
  if (normalizedIcon && normalizedIcon.diagnosis.apiCandidateCount === 0 && normalizedIcon.defaultIcon.used) {
    warnings.add("AI画像候補は保存されていません。未採用時のToolHub共通default iconを使用しています。");
  }
  return Array.from(warnings);
}

function preflightStatus(preflight: AppStudioPreflightResult | null): string {
  if (!preflight) {
    return "未実行";
  }
  if (!preflight.entryExists || !preflight.appIdValid || !preflight.buildModeValid || !preflight.appStudioCliExists || preflight.errors.length) {
    return "進行不可";
  }
  if (preflight.warnings.length) {
    return "要注意";
  }
  return "問題なし";
}

function buildModeLabel(mode?: string | null): string {
  if (mode === "shared-env") {
    return "共有ランタイム";
  }
  if (mode === "frozen-folder") {
    return "配布用exe";
  }
  return mode || "-";
}

function friendlyWarning(warning: string): string {
  if (warning.includes("runtime/python/python.exe") || warning.toLowerCase().includes("runtime")) {
    return "通常新規登録では内部build_envで配布用exeを作成します。";
  }
  return warning;
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
    return "API未実行（代替処理）";
  }
  if (value === "skipped") {
    return "スキップ";
  }
  if (value === "failed") {
    return "失敗";
  }
  return value || "未実行";
}
