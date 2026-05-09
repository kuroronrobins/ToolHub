import { CheckCircle2, CircleAlert, FolderOpen, PackageCheck, ShieldCheck } from "lucide-react";
import type { ReactNode } from "react";
import { useState } from "react";
import { appStudioOpenOutputDir } from "../../../lib/appStudioApi";
import { formatAppStudioSeconds, normalizeAppStudioRunResult } from "../../../lib/appStudioRunResult";
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
  const view = normalizeAppStudioRunResult(result, { approvalMode, busy, lastAction });
  const { approvalDecision, approvalFailureGuidance, canApprove, warningOnly, secretBlocked } = view;

  async function openOutputDir() {
    if (!result?.outputDir) {
      return;
    }
    setOpenMessage("");
    setOpenError("");
    try {
      await appStudioOpenOutputDir(result.outputDir);
      setOpenMessage("Explorer で出力フォルダを開きました。");
    } catch (error) {
      setOpenError(error instanceof Error ? error.message : "出力フォルダを開けませんでした。");
    }
  }

  return (
    <section className="studio-side-section">
      <div className="admin-section-head">
        <div>
          <p className="dialog-kicker">結果</p>
          <h4>生成物と承認状態</h4>
        </div>
        <span className={`admin-status-pill ${view.statusPillOk ? "ok" : ""}`}>{view.statusPillLabel}</span>
      </div>

      {warningOnly ? (
        <p className="admin-muted">
          配布リスクのない警告のみです。詳細を確認して問題なければ、デフォルトの慎重モードでも承認できます。
        </p>
      ) : null}

      {secretBlocked ? (
        <div className="studio-manual-checks">
          <strong>秘密情報検査で停止しました</strong>
          <p>
            blocking {result?.secretBlockingCount ?? 0} 件 / warning {result?.secretWarningCount ?? 0} 件 / manual check{" "}
            {result?.secretManualCheckCount ?? 0} 件
          </p>
          {result?.secretScanReport ? <p>Report: {result.secretScanReport}</p> : null}
          {result?.secretBlockingFindings?.length ? (
            <ul>
              {result.secretBlockingFindings.slice(0, 10).map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          ) : null}
          <p>本物の秘密情報は削除し、サンプル値は placeholder として明確化してください。配布対象外のファイルは add-data に入らない状態で再実行してください。</p>
        </div>
      ) : null}

      <div className="studio-result-list">
        <ResultRow icon={<CheckCircle2 size={18} />} label="アプリID" value={result?.appId ?? "-"} />
        <ResultRow icon={<CheckCircle2 size={18} />} label="登録方式" value={result?.selectedBuildMode === "frozen-folder" ? "配布用exe" : result?.selectedBuildMode ?? "-"} />
        <ResultRow icon={<CheckCircle2 size={18} />} label="現在版" value={result?.currentVersion ?? "-"} />
        <ResultRow icon={<CheckCircle2 size={18} />} label="新しい版" value={result?.newVersion ?? "-"} />
        <ResultRow icon={<CheckCircle2 size={18} />} label="終了コード" value={result ? String(result.exitCode) : "-"} />
        <ResultRow icon={<CheckCircle2 size={18} />} label="処理結果" value={view.processResultLabel} />
        <ResultRow icon={<CheckCircle2 size={18} />} label="最後の操作" value={view.lastActionLabel} />
        <OutputDirRow value={result?.outputDir ?? ""} disabled={busy || !result?.outputDir} onOpen={() => void openOutputDir()} />
        <ResultRow icon={<CheckCircle2 size={18} />} label="メタデータ上書き" value={view.metadataOverrideLabel} />
        <ResultRow icon={<CheckCircle2 size={18} />} label="アイコン上書き" value={view.iconOverrideLabel} />
        <ResultRow icon={<CircleAlert size={18} />} label="exe化準備" value={view.exeReadinessLabel} />
        <ResultRow icon={<CircleAlert size={18} />} label="配布物検証" value={view.executionStatusLabel} />
        <ResultRow icon={<CircleAlert size={18} />} label="システム承認判定" value={approvalDecision.systemDecision} />
        <ResultRow icon={<CircleAlert size={18} />} label="現在モードの判定" value={approvalDecision.modeDecision} />
        <ResultRow icon={<CircleAlert size={18} />} label="配布リスク警告" value={String(result?.approvalBlockingWarningsCount ?? 0)} />
        <ResultRow icon={<CircleAlert size={18} />} label="参考警告" value={String(result?.nonBlockingWarningsCount ?? 0)} />
        <ResultRow icon={<CircleAlert size={18} />} label="未解決リスク" value={String(result?.unresolvedDistributionRisksCount ?? 0)} />
        <ResultRow icon={<CircleAlert size={18} />} label="runtime検証" value={view.runtimeStatusLabel} />
        <ResultRow icon={<CircleAlert size={18} />} label="秘密情報ブロック" value={String(result?.secretBlockingCount ?? 0)} />
        <ResultRow icon={<CircleAlert size={18} />} label="処理時間" value={view.timingSummary} />
        <ResultRow icon={<ShieldCheck size={18} />} label="App Studio承認記録" value={view.approvalRecordSummary} />
        <ResultRow icon={<ShieldCheck size={18} />} label="manifest enabled" value={view.manifestEnabledLabel} />
        <ResultRow icon={<ShieldCheck size={18} />} label="ホーム表示判定" value={view.catalogSummary} />
        <ResultRow icon={<ShieldCheck size={18} />} label="catalog root" value={result?.catalogRoot ?? "-"} />
        <ResultRow icon={<PackageCheck size={18} />} label="App Pack" value={view.appPackLabel} />
        <ResultRow icon={<ShieldCheck size={18} />} label="次の操作" value={view.primaryNextAction} />
      </div>

      {view.blockingReasons.length ? (
        <FindingList title="配布リスクあり" items={view.blockingReasons} />
      ) : null}
      {view.nonBlockingWarnings.length ? (
        <FindingList title="配布リスクなしの警告" items={view.nonBlockingWarnings} />
      ) : null}
      {view.manualChecks.length ? <FindingList title="手動確認メモ" items={view.manualChecks} /> : null}
      {result?.timingPhases?.length ? (
        <div className="studio-manual-checks">
          <strong>工程別時間</strong>
          <p>{view.timingDetailSummary}</p>
          <ul>
            {result.timingPhases.slice(-10).map((item, index) => (
              <li key={`${item.phase}-${index}`}>
                {item.label}: {formatAppStudioSeconds(item.durationSeconds)} ({item.status})
              </li>
            ))}
          </ul>
          {result.timingReport ? <p>Report: {result.timingReport}</p> : null}
        </div>
      ) : null}
      {approvalFailureGuidance || result?.approvalFailureSummary || result?.verifyReleaseFailureSummary || result?.catalogDisabledReason || result?.catalogLoadError ? (
        <div className="studio-manual-checks">
          <strong>承認ゲート診断</strong>
          {approvalFailureGuidance ? <p>{approvalFailureGuidance.reason}</p> : null}
          {approvalFailureGuidance ? <p>次にやること: {approvalFailureGuidance.nextAction}</p> : null}
          {result?.approvalFailureSummary ? <p>承認失敗理由: {result.approvalFailureSummary}</p> : null}
          {result?.verifyReleaseStatus ? <p>verify_release: {result.verifyReleaseStatus}</p> : null}
          {result?.verifyReleaseFailureSummary ? <p>verify_release詳細: {result.verifyReleaseFailureSummary}</p> : null}
          {result?.catalogDisabledReason ? <p>ホームに表示されない理由: {result.catalogDisabledReason}</p> : null}
          {result?.catalogLoadError ? <p>catalog読込エラー: {result.catalogLoadError}</p> : null}
          {result?.approvalRecordPath ? <p>承認記録: {result.approvalRecordPath}</p> : null}
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
            <small>配布物破損ではない警告を許容します。ただし exe欠落、required_files欠落、secret混入などのfailは承認できません。</small>
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
            <strong>配布リスクがある警告は承認しない</strong>
            <small>配布リスクのない参考警告や手動確認メモだけなら、このモードでも承認できます。</small>
          </span>
        </label>
      </fieldset>
      <div className="admin-form-actions">
        <button className="secondary-button" type="button" onClick={onRefresh} disabled={busy || !result?.appId}>
          結果を再読み込み
        </button>
        {!canApprove ? <p className="admin-error">{approvalDecision.reason}</p> : <p className="admin-success">{approvalDecision.reason}</p>}
        <button className="primary-button" type="button" onClick={onApprove} disabled={!canApprove} title={canApprove ? "承認して有効化します" : approvalDecision.reason}>
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

function FindingList({ title, items }: { title: string; items: string[] }) {
  return (
    <div className="studio-manual-checks">
      <strong>{title}</strong>
      <ul>
        {items.map((item, index) => (
          <li key={`${title}-${index}`}>{item}</li>
        ))}
      </ul>
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
        <button className="secondary-button" type="button" onClick={onOpen} disabled={disabled} title={value ? "Windows Explorer で出力先を開きます" : "出力先はまだありません"}>
          <FolderOpen size={16} aria-hidden="true" />
          フォルダを開く
        </button>
      </div>
    </div>
  );
}
