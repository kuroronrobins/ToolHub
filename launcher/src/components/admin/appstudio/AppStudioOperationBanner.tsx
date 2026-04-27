import { CheckCircle2, CircleAlert, Loader2, TriangleAlert } from "lucide-react";

export type StudioOperationKind = "idle" | "pickingFile" | "preflight" | "aiProposal" | "suggest" | "apply" | "approve" | "refresh";
export type StudioOperationStatus = "idle" | "running" | "success" | "warning" | "error";

export interface StudioOperationState {
  kind: StudioOperationKind;
  label: string;
  startedAt: number | null;
  status: StudioOperationStatus;
  message?: string;
}

export const OPERATION_LABELS: Record<StudioOperationKind, string> = {
  idle: "待機中",
  pickingFile: "ファイル選択画面を開いています",
  preflight: "事前確認を実行しています",
  aiProposal: "AI提案を生成しています",
  suggest: "登録内容を作成しています",
  apply: "テスト登録と配布物検証を実行しています",
  approve: "承認して有効化しています",
  refresh: "結果を再読み込みしています",
};

export const IDLE_OPERATION: StudioOperationState = {
  kind: "idle",
  label: OPERATION_LABELS.idle,
  startedAt: null,
  status: "idle",
};

interface Props {
  operation: StudioOperationState;
  compact?: boolean;
}

export function AppStudioOperationBanner({ operation, compact = false }: Props) {
  const isRunning = operation.status === "running";
  const longRunning = isRunning && ["aiProposal", "suggest", "apply", "approve"].includes(operation.kind);
  const Icon = iconForStatus(operation.status);
  return (
    <div className={`studio-operation-banner ${operation.status} ${compact ? "compact" : ""}`.trim()} role={operation.status === "error" ? "alert" : "status"}>
      <div className="studio-operation-title">
        {isRunning ? <Loader2 className="studio-spinner" size={18} aria-hidden="true" /> : <Icon size={18} aria-hidden="true" />}
        <strong>{isRunning ? "処理中" : statusLabel(operation.status)}</strong>
      </div>
      <p>{operation.message || operation.label}</p>
      {longRunning ? <span>数十秒かかる場合があります。画面を閉じずにお待ちください。</span> : null}
    </div>
  );
}

function iconForStatus(status: StudioOperationStatus) {
  if (status === "success") {
    return CheckCircle2;
  }
  if (status === "warning") {
    return TriangleAlert;
  }
  if (status === "error") {
    return CircleAlert;
  }
  return CheckCircle2;
}

function statusLabel(status: StudioOperationStatus): string {
  if (status === "success") {
    return "完了";
  }
  if (status === "warning") {
    return "警告あり";
  }
  if (status === "error") {
    return "失敗";
  }
  return "状態";
}
