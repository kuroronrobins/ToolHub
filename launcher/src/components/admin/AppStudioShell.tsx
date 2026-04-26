import { Boxes, FileCheck2, PackagePlus, Trash2 } from "lucide-react";
import { AppStudioImportWizard } from "./appstudio/AppStudioImportWizard";

export function AppStudioShell() {
  return (
    <section className="admin-panel-section">
      <div className="admin-section-head">
        <div>
          <p className="dialog-kicker">App Studio</p>
          <h3>ToolHub App Studio</h3>
        </div>
        <span className="admin-status-pill">Shell</span>
      </div>
      <p className="admin-muted">
        CLI版 App Studio を管理者画面から実行します。今回は新規登録フローを優先実装しています。
      </p>

      <AppStudioImportWizard />

      <div className="admin-card-grid">
        <button className="admin-work-card" type="button" disabled title="上の新規登録フォームを使用してください">
          <PackagePlus size={22} aria-hidden="true" />
          <strong>新規登録</strong>
          <span>Suggest / Apply / Approve をGUIから実行できます</span>
        </button>
        <button className="admin-work-card" type="button" disabled>
          <Boxes size={22} aria-hidden="true" />
          <strong>既存アプリ更新</strong>
          <span>既存 app_id の再解析と差し替えに接続予定</span>
        </button>
        <button className="admin-work-card danger" type="button" disabled>
          <Trash2 size={22} aria-hidden="true" />
          <strong>削除/アンインストール</strong>
          <span>将来は再認証を必須にする操作</span>
        </button>
        <button className="admin-work-card" type="button" disabled>
          <FileCheck2 size={22} aria-hidden="true" />
          <strong>公開準備</strong>
          <span>App Pack と承認チェックへ接続予定</span>
        </button>
      </div>
    </section>
  );
}
