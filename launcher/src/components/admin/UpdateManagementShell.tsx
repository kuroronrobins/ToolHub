import { PackageCheck, RefreshCw, UploadCloud } from "lucide-react";

export function UpdateManagementShell() {
  return (
    <section className="admin-panel-section">
      <div className="admin-section-head">
        <div>
          <p className="dialog-kicker">更新管理</p>
          <h3>配布と更新の確認</h3>
        </div>
        <span className="admin-status-pill">Shell</span>
      </div>
      <div className="admin-card-grid">
        <button className="admin-work-card" type="button" disabled>
          <RefreshCw size={22} aria-hidden="true" />
          <strong>manifest確認</strong>
          <span>release/app_manifest.json の確認に接続予定</span>
        </button>
        <button className="admin-work-card" type="button" disabled>
          <PackageCheck size={22} aria-hidden="true" />
          <strong>App Pack確認</strong>
          <span>App Pack の整合性確認に接続予定</span>
        </button>
        <button className="admin-work-card danger" type="button" disabled>
          <UploadCloud size={22} aria-hidden="true" />
          <strong>publish準備</strong>
          <span>将来は再認証を必須にする操作</span>
        </button>
      </div>
    </section>
  );
}
