import { AlertCircle, CheckCircle2, Loader2, X } from "lucide-react";
import type { LaunchEvent, RunStatus, ToolApp } from "../lib/types";

interface Props {
  app: ToolApp | null;
  status: RunStatus;
  message: string;
  events: LaunchEvent[];
  onClose: () => void;
}

export function LaunchProgressDialog({ app, status, message, events, onClose }: Props) {
  if (!app || status === "idle") {
    return null;
  }

  const canClose = status !== "running";
  const lastProgress = [...events].reverse().find((event) => typeof event.progress === "number")?.progress;

  return (
    <div className="dialog-backdrop" role="presentation">
      <section className="dialog-panel compact" role="dialog" aria-modal="true" aria-labelledby="launch-title">
        <header className="dialog-header">
          <div>
            <p className="dialog-kicker">起動状態</p>
            <h2 id="launch-title">{app.name}</h2>
          </div>
          {canClose ? (
            <button className="icon-button" type="button" onClick={onClose} title="閉じる">
              <X size={20} aria-hidden="true" />
            </button>
          ) : null}
        </header>

        <div className={`launch-status ${status}`}>
          {status === "running" ? <Loader2 className="spin" size={28} aria-hidden="true" /> : null}
          {status === "success" ? <CheckCircle2 size={30} aria-hidden="true" /> : null}
          {status === "error" ? <AlertCircle size={30} aria-hidden="true" /> : null}
          <p>{message}</p>
        </div>

        {typeof lastProgress === "number" ? (
          <div className="progress-track" aria-label="進捗">
            <span style={{ width: `${Math.max(0, Math.min(100, lastProgress))}%` }} />
          </div>
        ) : null}

        {events.length > 0 ? (
          <ul className="event-list" aria-label="実行メッセージ">
            {events.slice(-5).map((event, index) => (
              <li key={`${event.type}-${index}`}>{event.message}</li>
            ))}
          </ul>
        ) : null}
      </section>
    </div>
  );
}

