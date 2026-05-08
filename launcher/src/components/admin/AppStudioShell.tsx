import { useState } from "react";
import { Boxes, FileCheck2, PackagePlus, Trash2 } from "lucide-react";
import { AppStudioImportWizard } from "./appstudio/AppStudioImportWizard";
import { AppStudioDeleteManager } from "./appstudio/AppStudioDeleteManager";
import { AppStudioUpdateWizard } from "./appstudio/AppStudioUpdateWizard";

type StudioTab = "new" | "update" | "delete" | "publish";

export function AppStudioShell() {
  const [activeTab, setActiveTab] = useState<StudioTab>("new");

  return (
    <section className="admin-panel-section">
      <div className="admin-section-head">
        <div>
          <p className="dialog-kicker">アプリスタジオ</p>
          <h3>ToolHub アプリスタジオ</h3>
        </div>
        <span className="admin-status-pill">管理者専用</span>
      </div>
      <p className="admin-muted">
        管理者画面からアプリ登録、既存アプリ更新、表示切り替え、削除確認を実行します。公開準備は今後の拡張用です。
      </p>

      <div className="studio-tab-row" role="tablist" aria-label="アプリスタジオの機能">
        <button type="button" className={activeTab === "new" ? "active" : ""} onClick={() => setActiveTab("new")}>
          <PackagePlus size={17} aria-hidden="true" />
          新規登録
        </button>
        <button type="button" className={activeTab === "update" ? "active" : ""} onClick={() => setActiveTab("update")}>
          <Boxes size={17} aria-hidden="true" />
          既存アプリ更新
        </button>
        <button type="button" className={activeTab === "delete" ? "active" : ""} onClick={() => setActiveTab("delete")}>
          <Trash2 size={17} aria-hidden="true" />
          削除管理
        </button>
        <button type="button" className={activeTab === "publish" ? "active" : ""} onClick={() => setActiveTab("publish")}>
          <FileCheck2 size={17} aria-hidden="true" />
          公開準備
        </button>
      </div>

      {activeTab === "new" ? <AppStudioImportWizard /> : null}
      {activeTab === "update" ? <AppStudioUpdateWizard /> : null}
      {activeTab === "delete" ? <AppStudioDeleteManager /> : null}
      {activeTab === "publish" ? (
        <div className="admin-card-grid">
          <button className="admin-work-card" type="button" disabled>
            <PackagePlus size={22} aria-hidden="true" />
            <strong>新規登録</strong>
            <span>新しいアプリの提案、適用、承認を行います。</span>
          </button>
          <button className="admin-work-card" type="button" disabled>
            <Boxes size={22} aria-hidden="true" />
            <strong>既存アプリ更新</strong>
            <span>登録済みアプリの更新ワークフローを実行します。</span>
          </button>
          <button className="admin-work-card" type="button" disabled>
            <FileCheck2 size={22} aria-hidden="true" />
            <strong>公開準備</strong>
            <span>未実装です。将来の公開前チェック用に配置しています。</span>
          </button>
        </div>
      ) : null}
    </section>
  );
}
