import { X } from "lucide-react";
import type { UpdateItem, UpdateSummary } from "../lib/updateTypes";

const UNSUPPORTED_ACTION_LABELS: Record<string, string> = {
  download: "ダウンロード",
  extract: "展開",
  replace: "置換",
  backup: "バックアップ",
  rollback: "ロールバック",
  signature_verification: "署名検証",
};

const CONFIG_SOURCE_LABELS: Record<string, string> = {
  user: "ユーザー設定",
  default: "default設定",
  missing: "未確認",
};

interface Props {
  summary: UpdateSummary | null;
  onClose: () => void;
}

function VersionRow({ item }: { item: UpdateItem }) {
  return (
    <div className="version-row">
      <span>{item.label}</span>
      <strong>
        {item.currentVersion} -&gt; {item.nextVersion}
      </strong>
    </div>
  );
}

export function UpdateSummaryDialog({ summary, onClose }: Props) {
  if (!summary) {
    return null;
  }

  return (
    <div className="dialog-backdrop" role="presentation" onMouseDown={onClose}>
      <section className="dialog-panel compact" role="dialog" aria-modal="true" aria-labelledby="update-title" onMouseDown={(event) => event.stopPropagation()}>
        <header className="dialog-header">
          <div>
            <p className="dialog-kicker">更新</p>
            <h2 id="update-title">{summary.title}</h2>
          </div>
          <button className="icon-button" type="button" onClick={onClose} title="閉じる">
            <X size={20} aria-hidden="true" />
          </button>
        </header>

        <section className="detail-section">
          <h3>内容</h3>
          <p>{summary.message}</p>
          <div className="version-list">
            <div className="version-row">
              <span>現在のToolHub</span>
              <strong>{summary.currentVersion ?? "-"}</strong>
            </div>
            <div className="version-row">
              <span>配布元のバージョン</span>
              <strong>{summary.remoteManifestVersion ?? summary.localManifestVersion ?? "未確認"}</strong>
            </div>
          </div>
        </section>

        <details className="admin-details">
          <summary>管理者向け詳細</summary>
          <div className="version-list">
            {summary.core ? <VersionRow item={summary.core} /> : null}
            {summary.runner ? <VersionRow item={summary.runner} /> : null}
            {summary.apps.map((item) => (
              <VersionRow key={item.label} item={item} />
            ))}
            {summary.runtimeUpdate ? <div className="version-row"><span>Web自動化用ランタイム</span><strong>更新あり</strong></div> : null}
            {!summary.core && !summary.runner && !summary.apps.length && !summary.runtimeUpdate ? (
              <div className="version-row"><span>更新候補</span><strong>なし</strong></div>
            ) : null}
            <div className="version-row"><span>設定種別</span><strong>{summary.configSource ? CONFIG_SOURCE_LABELS[summary.configSource] ?? summary.configSource : "-"}</strong></div>
            <div className="version-row"><span>設定ファイル</span><strong>{summary.configPath ?? "-"}</strong></div>
            <div className="version-row"><span>remote manifest</span><strong>{summary.remoteManifestUrl ?? "-"}</strong></div>
            <div className="version-row"><span>installer</span><strong>{summary.installerUrl ?? "-"}</strong></div>
            <div className="version-row"><span>installer sha256</span><strong>{summary.installerSha256 ?? "-"}</strong></div>
            <div className="version-row"><span>manifest</span><strong>{summary.localManifestPath ?? "-"}</strong></div>
            <div className="version-row"><span>app manifest</span><strong>{summary.appManifestPath ?? "-"}</strong></div>
          </div>
          {summary.notes?.length ? (
            <ul className="update-note-list">
              {summary.notes.map((note) => (
                <li key={note}>{note}</li>
              ))}
            </ul>
          ) : null}
          {summary.unsupportedActions?.length ? (
            <p className="admin-muted">未実装: {summary.unsupportedActions.map((action) => UNSUPPORTED_ACTION_LABELS[action] ?? action).join("、")}</p>
          ) : null}
        </details>
      </section>
    </div>
  );
}

