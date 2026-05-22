import type { AppStudioAiProposal, AppStudioApprovalMode, AppStudioImportRequest, AppStudioPreflightResult, AppStudioRunResult } from "../../../lib/appStudioTypes";
import { generatedMetadataSuggestion } from "../../../lib/appStudioMetadata";
import { normalizeAppStudioIconProposal, previewIconDataUrl } from "../../../lib/appStudioIconProposal";
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
  const iconDataUrl = previewIconDataUrl(request.iconOverride, aiProposal);
  const generatedMetadata = generatedMetadataSuggestion(aiProposal?.metadata);
  const appName = request.name?.trim() || generatedMetadata?.name || request.appId || "表示名未設定";
  const shortDescription = request.metadata?.shortDescription?.trim() || generatedMetadata?.shortDescription || "説明文は表示内容画面で確認します。";
  const statusLabel = result?.enabled ? "承認済み" : result && approvalMode && !error ? "承認待ち" : sidebarStatusLabel(step, preflight, result);
  return (
    <section className="studio-side-section studio-import-sidebar">
      <div className="admin-section-head">
        <div>
          <p className="dialog-kicker">現在の状態</p>
          <h4>{importStepLabel(step)}</h4>
        </div>
        <span className={`admin-status-pill ${result?.enabled ? "ok" : ""}`}>{statusLabel}</span>
      </div>

      <AppStudioOperationBanner operation={operation} compact />

      <div className="studio-sidebar-preview">
        <div className="studio-sidebar-preview-icon" aria-hidden="true">
          {iconDataUrl ? <img src={iconDataUrl} alt="" /> : <span>{appName.slice(0, 1).toUpperCase()}</span>}
        </div>
        <div>
          <strong>{appName}</strong>
          <p>{shortDescription}</p>
        </div>
      </div>

      <div className="studio-next-action">
        <strong>次にやること</strong>
        <p>{nextAction}</p>
      </div>

      {message ? <p className="admin-success">{message}</p> : null}
      {error ? <p className="admin-error" role="alert">{error}</p> : null}

      <dl className="studio-sidebar-status">
        <div>
          <dt>アプリ選択</dt>
          <dd>{request.entry ? "入力中" : "未入力"}</dd>
        </div>
        <div>
          <dt>事前確認</dt>
          <dd>{preflightStatus(preflight)}</dd>
        </div>
        <div>
          <dt>表示内容</dt>
          <dd>{request.name ? "確認中" : "未確認"}</dd>
        </div>
        <div>
          <dt>テスト登録</dt>
          <dd>{result ? testStatus(result) : "未実行"}</dd>
        </div>
        <div>
          <dt>承認</dt>
          <dd>{result?.enabled ? "有効化済み" : "未承認"}</dd>
        </div>
      </dl>

      {warnings.length ? (
        <div className="studio-sidebar-warnings">
          <strong>注意 {warnings.length}件</strong>
          <ul>
            {warnings.slice(0, 2).map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}

function sidebarStatusLabel(step: AppStudioImportStep, preflight: AppStudioPreflightResult | null, result: AppStudioRunResult | null): string {
  if (result?.enabled) {
    return "承認済み";
  }
  if (result) {
    return "承認待ち";
  }
  if (step === "selectEntry" && !preflight) {
    return "未確認";
  }
  if (step === "aiProposal") {
    return "表示確認中";
  }
  if (step === "review") {
    return "テスト前";
  }
  if (step === "register") {
    return "最終確認";
  }
  return "進行中";
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

function testStatus(result: AppStudioRunResult): string {
  if (result.executionStatus === "pass") {
    return "成功";
  }
  if (result.executionStatus === "warn") {
    return "要確認";
  }
  if (result.executionStatus === "fail" || !result.ok) {
    return "失敗";
  }
  return result.executionStatus || "確認中";
}

function friendlyWarning(warning: string): string {
  if (warning.includes("runtime/python/python.exe") || warning.toLowerCase().includes("runtime")) {
    return "通常新規登録では内部build_envで配布用exeを作成します。";
  }
  return warning;
}

