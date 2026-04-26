import { Activity, ClipboardList } from "lucide-react";

export function AdminLogsPanel() {
  return (
    <section className="admin-panel-section">
      <div className="admin-section-head">
        <div>
          <p className="dialog-kicker">ログ/診断</p>
          <h3>管理者操作ログ</h3>
        </div>
        <span className="admin-status-pill">Shell</span>
      </div>
      <div className="admin-info-list">
        <div>
          <ClipboardList size={20} aria-hidden="true" />
          <div>
            <strong>保存先</strong>
            <p>%LOCALAPPDATA%\ToolHub\data\logs\admin\admin.log</p>
          </div>
        </div>
        <div>
          <Activity size={20} aria-hidden="true" />
          <div>
            <strong>記録対象</strong>
            <p>ログイン、ログアウト、AI設定保存、APIキー登録/削除。パスワードやAPIキー全文は記録しません。</p>
          </div>
        </div>
      </div>
    </section>
  );
}
