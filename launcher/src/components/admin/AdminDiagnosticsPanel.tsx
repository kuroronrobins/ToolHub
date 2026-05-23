import { Activity, ClipboardList, FolderTree, RefreshCw } from "lucide-react";

export function AdminDiagnosticsPanel() {
  return (
    <section className="admin-panel-section">
      <div className="admin-section-head">
        <div>
          <p className="dialog-kicker">診断</p>
          <h3>システム情報とログ</h3>
        </div>
        <span className="admin-status-pill">管理者専用</span>
      </div>
      <p className="admin-muted">インストール先、更新単位、管理者操作ログを確認します。</p>

      <div className="admin-info-list">
        <div>
          <FolderTree size={20} aria-hidden="true" />
          <div>
            <strong>配置方針</strong>
            <p>インストール先とユーザーデータ先を分離し、更新時にユーザーデータを保持します。</p>
          </div>
        </div>
        <div>
          <RefreshCw size={20} aria-hidden="true" />
          <div>
            <strong>更新単位</strong>
            <p>ToolHub Core、Runner、Built-in Apps、Heavy Runtimeを分けて扱います。User Dataは更新対象外です。</p>
          </div>
        </div>
        <div>
          <ClipboardList size={20} aria-hidden="true" />
          <div>
            <strong>管理者操作ログ</strong>
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

      <details className="admin-details" open>
        <summary>更新単位の内訳</summary>
        <ul className="plain-list">
          <li>ToolHub Core</li>
          <li>Runner</li>
          <li>Built-in Apps</li>
          <li>Heavy Runtime</li>
          <li>User Dataは更新対象外</li>
        </ul>
      </details>
    </section>
  );
}
