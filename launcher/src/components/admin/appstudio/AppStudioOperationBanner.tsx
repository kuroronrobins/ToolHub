import { CheckCircle2, CircleAlert, Loader2, TriangleAlert } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

export type StudioOperationKind = "idle" | "pickingFile" | "preflight" | "aiProposal" | "suggest" | "apply" | "approve" | "refresh";
export type StudioOperationStatus = "idle" | "running" | "success" | "warning" | "error";

export interface StudioOperationState {
  kind: StudioOperationKind;
  label: string;
  startedAt: number | null;
  status: StudioOperationStatus;
  message?: string;
  estimatedSeconds?: number | null;
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

const DEFAULT_ESTIMATES: Partial<Record<StudioOperationKind, number>> = {
  aiProposal: 45,
  suggest: 60,
  apply: 600,
  approve: 90,
  refresh: 5,
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
  const elapsedSeconds = useElapsedSeconds(operation.startedAt, isRunning);
  const estimateSeconds = operation.estimatedSeconds ?? DEFAULT_ESTIMATES[operation.kind] ?? null;
  const remainingSeconds = estimateSeconds == null ? null : Math.max(estimateSeconds - elapsedSeconds, 0);
  const longRunning = isRunning && ["aiProposal", "suggest", "apply", "approve"].includes(operation.kind);
  const Icon = iconForStatus(operation.status);
  const progressPercent = useMemo(() => {
    if (!isRunning || !estimateSeconds) {
      return null;
    }
    return Math.max(5, Math.min(95, Math.round((elapsedSeconds / estimateSeconds) * 100)));
  }, [elapsedSeconds, estimateSeconds, isRunning]);

  return (
    <div className={`studio-operation-banner ${operation.status} ${compact ? "compact" : ""}`.trim()} role={operation.status === "error" ? "alert" : "status"}>
      <div className="studio-operation-title">
        {isRunning ? <Loader2 className="studio-spinner" size={18} aria-hidden="true" /> : <Icon size={18} aria-hidden="true" />}
        <strong>{isRunning ? "処理中" : statusLabel(operation.status)}</strong>
      </div>
      <p>{operation.message || operation.label}</p>
      {isRunning ? (
        <span>
          現在工程: {operation.label} / 経過 {formatSeconds(elapsedSeconds)}
          {estimateSeconds ? ` / 目安 ${formatSeconds(estimateSeconds)}` : ""}
          {remainingSeconds != null ? ` / 残り約 ${formatSeconds(remainingSeconds)}` : ""}
        </span>
      ) : null}
      {progressPercent != null ? <div className="studio-operation-progress" aria-label={`進捗目安 ${progressPercent}%`} style={{ width: `${progressPercent}%` }} /> : null}
      {longRunning ? <span>初回ビルドや Playwright を含むアプリでは数分から十数分かかることがあります。表示時間は目安です。</span> : null}
    </div>
  );
}

function useElapsedSeconds(startedAt: number | null, running: boolean): number {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (!running) {
      return undefined;
    }
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [running]);
  if (!startedAt) {
    return 0;
  }
  return Math.max(0, Math.round((now - startedAt) / 1000));
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

function formatSeconds(value: number): string {
  if (value < 60) {
    return `${value}秒`;
  }
  const minutes = Math.floor(value / 60);
  const seconds = value % 60;
  return `${minutes}分${seconds}秒`;
}
