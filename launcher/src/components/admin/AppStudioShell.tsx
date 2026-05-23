import { useState } from "react";
import { Boxes, FileCheck2, PackagePlus, Trash2 } from "lucide-react";
import { AppStudioImportWizard } from "./appstudio/AppStudioImportWizard";
import { AppStudioDeleteManager } from "./appstudio/AppStudioDeleteManager";
import { AppStudioUpdateWizard } from "./appstudio/AppStudioUpdateWizard";
import { AppStudioPublishPanel } from "./appstudio/AppStudioPublishPanel";

type StudioTab = "new" | "update" | "delete" | "publish";

export function AppStudioShell() {
  const [activeTab, setActiveTab] = useState<StudioTab>("new");

  return (
    <section className="admin-panel-section">
      <div className="admin-section-head">
        <div>
          <p className="dialog-kicker">アプリ管理</p>
          <h3>アプリ登録と管理</h3>
        </div>
        <span className="admin-status-pill">管理者専用</span>
      </div>
      <p className="admin-muted">App Studioを使って、アプリ登録、既存アプリ更新、表示切り替え、削除確認、公開前確認を実行します。</p>

      <div className="studio-tab-row" role="tablist" aria-label="アプリ管理の機能">
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
      {activeTab === "publish" ? <AppStudioPublishPanel /> : null}
    </section>
  );
}
