import { CheckCircle2, CircleAlert, FolderOpen, PackageCheck, ShieldCheck } from "lucide-react";
import type { ReactNode } from "react";
import { useState } from "react";
import { appStudioOpenOutputDir } from "../../../lib/appStudioApi";
import type { AppStudioApprovalMode, AppStudioRunResult } from "../../../lib/appStudioTypes";

interface Props {
  result: AppStudioRunResult | null;
  lastAction: "suggest" | "apply" | "approve" | null;
  approvalMode: AppStudioApprovalMode;
  onApprovalModeChange: (mode: AppStudioApprovalMode) => void;
  busy: boolean;
  onApprove: () => void;
  onRefresh: () => void;
}

export function AppStudioResultPanel({ result, lastAction, approvalMode, onApprovalModeChange, busy, onApprove, onRefresh }: Props) {
  const [openMessage, setOpenMessage] = useState("");
  const [openError, setOpenError] = useState("");
  const warningOnly = Boolean(result && !result.ok && result.executionStatus === "warn" && result.approvalAllowed === true);
  const canApprove = Boolean(
    result?.appId &&
      lastAction === "apply" &&
      result.executionStatus !== "fail" &&
      result.approvalAllowed !== false &&
      (approvalMode === "allowWarnings" || result.executionStatus === "pass"),
  );
  const nextAction = nextActionText(result, lastAction, approvalMode);

  async function openOutputDir() {
    if (!result?.outputDir) {
      return;
    }
    setOpenMessage("");
    setOpenError("");
    try {
      await appStudioOpenOutputDir(result.outputDir);
      setOpenMessage("Explorerで出力先を開きました。");
    } catch (error) {
      setOpenError(error instanceof Error ? error.message : "出力先を開けませんでした。");
    }
  }

  return (
    <section className="studio-side-section">
      <div className="admin-section-head">
        <div>
          <p className="dialog-kicker">結果</p>
          <h4>生成物と承認状態</h4>
        </div>
        <span className={`admin-status-pill ${result?.enabled || warningOnly ? "ok" : ""}`}>
          {result?.enabled ? "有効化済み" : warningOnly ? "警告 / 承認可" : "未承認"}
        </span>
      </div>

      {warningOnly ? (
        <p className="admin-muted">
          CLIの終了コードは0以外ですが、実行確認結果は「警告」かつ承認可能です。ログを確認してから承認してください。
        </p>
      ) : null}

      {result?.selectedBuildMode === "existing-exe" ? (
        <p className="admin-muted">
          existing-exe は既存の実行ファイルと関連ファイルを使います。dry execution が警告でスキップされる場合があります。
        </p>
      ) : null}

      <div className="studio-result-list">
        <ResultRow icon={<CheckCircle2 size={18} />} label="アプリID" value={result?.appId ?? "-"} />
        <ResultRow icon={<CheckCircle2 size={18} />} label="実行方式" value={result?.selectedBuildMode ?? "-"} />
        <ResultRow icon={<CheckCircle2 size={18} />} label="現在版" value={result?.currentVersion ?? "-"} />
        <ResultRow icon={<CheckCircle2 size={18} />} label="新しい版" value={result?.newVersion ?? "-"} />
        <ResultRow icon={<CheckCircle2 size={18} />} label="終了コード" value={result ? String(result.exitCode) : "-"} />
        <ResultRow icon={<CheckCircle2 size={18} />} label="処理結果" value={result ? boolLabel(result.ok) : "-"} />
        <ResultRow icon={<CheckCircle2 size={18} />} label="最後の操作" value={actionLabel(lastAction)} />
        <OutputDirRow value={result?.outputDir ?? ""} disabled={busy || !result?.outputDir} onOpen={() => void openOutputDir()} />
        <ResultRow icon={<CheckCircle2 size={18} />} label="メタデータ上書き" value={metadataOverrideText(result)} />
        <ResultRow icon={<CheckCircle2 size={18} />} label="アイコン上書き" value={iconOverrideText(result)} />
        <ResultRow icon={<CircleAlert size={18} />} label="exe化準備" value={executionLabel(result?.exeReadinessStatus)} />
        <ResultRow icon={<CircleAlert size={18} />} label="実行確認" value={executionLabel(result?.executionStatus)} />
        <ResultRow icon={<CircleAlert size={18} />} label="承認可否" value={formatBool(result?.approvalAllowed)} />
        <ResultRow icon={<CircleAlert size={18} />} label="実行環境" value={executionLabel(result?.runtimeStatus)} />
        <ResultRow icon={<PackageCheck size={18} />} label="App Pack" value={result?.appPack ?? "未作成"} />
        <ResultRow icon={<ShieldCheck size={18} />} label="次の操作" value={nextAction} />
      </div>

      {result?.manualChecks?.length ? (
        <div className="studio-manual-checks">
          <strong>手動確認</strong>
          <ul>
            {result.manualChecks.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      ) : null}

      {openMessage ? <p className="admin-success">{openMessage}</p> : null}
      {openError ? <p className="admin-error">{openError}</p> : null}

      <fieldset className="studio-approval-mode">
        <legend>承認モード</legend>
        <label className="studio-approval-option">
          <input
            type="radio"
            name="studio-approval-mode"
            checked={approvalMode === "allowWarnings"}
            onChange={() => onApprovalModeChange("allowWarnings")}
          />
          <span>
            <strong>警告ありでも承認可能</strong>
            <small>重大な失敗がなければ承認できます。軽微な警告を許容する運用向けです。</small>
          </span>
        </label>
        <label className="studio-approval-option">
          <input
            type="radio"
            name="studio-approval-mode"
            checked={approvalMode === "strict"}
            onChange={() => onApprovalModeChange("strict")}
          />
          <span>
            <strong>警告があれば承認しない</strong>
            <small>警告を含めて問題ゼロの場合のみ承認できます。慎重運用向けです。</small>
          </span>
        </label>
      </fieldset>
      <div className="admin-form-actions">
        <button className="secondary-button" type="button" onClick={onRefresh} disabled={busy || !result?.appId}>
          結果を再読み込み
        </button>
        <button className="primary-button" type="button" onClick={onApprove} disabled={busy || !canApprove}>
          <ShieldCheck size={17} aria-hidden="true" />
          承認して有効化
        </button>
      </div>
    </section>
  );
}

function ResultRow({ icon, label, value }: { icon: ReactNode; label: string; value: string }) {
  return (
    <div className="studio-result-row">
      <span aria-hidden="true">{icon}</span>
      <strong>{label}</strong>
      <p>{value}</p>
    </div>
  );
}

function OutputDirRow({ value, disabled, onOpen }: { value: string; disabled: boolean; onOpen: () => void }) {
  return (
    <div className="studio-result-row output-dir-row">
      <span aria-hidden="true">
        <FolderOpen size={18} />
      </span>
      <strong>出力先</strong>
      <div>
        <p>{value || "-"}</p>
        <button className="secondary-button" type="button" onClick={onOpen} disabled={disabled} title={value ? "Windows Explorerで出力先を開きます" : "出力先はまだありません"}>
          <FolderOpen size={16} aria-hidden="true" />
          フォルダを開く
        </button>
      </div>
    </div>
  );
}

function formatBool(value: boolean | null | undefined): string {
  if (value === true) {
    return "承認できます";
  }
  if (value === false) {
    return "承認できません";
  }
  return "未確認";
}

function boolLabel(value: boolean): string {
  return value ? "成功" : "失敗";
}

function actionLabel(action: "suggest" | "apply" | "approve" | null): string {
  if (action === "suggest") {
    return "登録内容を作成";
  }
  if (action === "apply") {
    return "テスト登録";
  }
  if (action === "approve") {
    return "承認";
  }
  return "-";
}

function metadataOverrideText(result: AppStudioRunResult | null): string {
  if (!result?.metadataOverrideUsed) {
    return "未使用";
  }
  return result.metadataOverrideKeys?.length ? result.metadataOverrideKeys.join(", ") : "使用";
}

function iconOverrideText(result: AppStudioRunResult | null): string {
  if (!result?.iconOverrideUsed) {
    return result?.selectedIconSource ?? "未使用";
  }
  return result.selectedIconSource ?? "使用";
}

function executionLabel(status?: string | null): string {
  if (status === "pass") {
    return "問題なし";
  }
  if (status === "warn") {
    return "警告";
  }
  if (status === "fail") {
    return "失敗";
  }
  return status || "未確認";
}

function nextActionText(
  result: AppStudioRunResult | null,
  lastAction: "suggest" | "apply" | "approve" | null,
  approvalMode: AppStudioApprovalMode,
): string {
  if (!result) {
    return "事前確認後、登録内容を作成してください。";
  }
  const warningOnly = result.executionStatus === "warn" && result.approvalAllowed === true;
  if (!result.ok && !warningOnly) {
    return "ログと生成レポートを確認してください。";
  }
  if (result.enabled) {
    return "承認済みです。";
  }
  if (lastAction === "suggest") {
    return "テスト登録して起動確認してください。";
  }
  if (lastAction === "apply") {
    if (result.executionStatus === "fail" || result.approvalAllowed === false) {
      return "失敗チェックを解消してください。";
    }
    if (approvalMode === "strict" && result.executionStatus !== "pass") {
      return "慎重運用では警告なしのpassが必要です。";
    }
    return "承認できます。";
  }
  return "結果を確認してください。";
}
