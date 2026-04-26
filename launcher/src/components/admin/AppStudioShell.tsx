import { useState } from "react";
import { Boxes, FileCheck2, PackagePlus, Trash2 } from "lucide-react";
import { AppStudioImportWizard } from "./appstudio/AppStudioImportWizard";
import { AppStudioUpdateWizard } from "./appstudio/AppStudioUpdateWizard";

type StudioTab = "new" | "update" | "delete" | "publish";

export function AppStudioShell() {
  const [activeTab, setActiveTab] = useState<StudioTab>("new");

  return (
    <section className="admin-panel-section">
      <div className="admin-section-head">
        <div>
          <p className="dialog-kicker">App Studio</p>
          <h3>ToolHub App Studio</h3>
        </div>
        <span className="admin-status-pill">Admin only</span>
      </div>
      <p className="admin-muted">
        App Studio runs the CLI workflow from the administrator screen. New registration is available, and existing app
        update is now available as an MVP. Delete and publish workflows remain placeholders.
      </p>

      <div className="studio-tab-row" role="tablist" aria-label="App Studio sections">
        <button type="button" className={activeTab === "new" ? "active" : ""} onClick={() => setActiveTab("new")}>
          <PackagePlus size={17} aria-hidden="true" />
          New registration
        </button>
        <button type="button" className={activeTab === "update" ? "active" : ""} onClick={() => setActiveTab("update")}>
          <Boxes size={17} aria-hidden="true" />
          Existing app update
        </button>
        <button type="button" className={activeTab === "delete" ? "active" : ""} onClick={() => setActiveTab("delete")}>
          <Trash2 size={17} aria-hidden="true" />
          Delete
        </button>
        <button type="button" className={activeTab === "publish" ? "active" : ""} onClick={() => setActiveTab("publish")}>
          <FileCheck2 size={17} aria-hidden="true" />
          Publish prep
        </button>
      </div>

      {activeTab === "new" ? <AppStudioImportWizard /> : null}
      {activeTab === "update" ? <AppStudioUpdateWizard /> : null}
      {activeTab === "delete" || activeTab === "publish" ? (
        <div className="admin-card-grid">
          <button className="admin-work-card" type="button" disabled>
            <PackagePlus size={22} aria-hidden="true" />
            <strong>New registration</strong>
            <span>Use the New registration tab for Suggest / Apply / Approve.</span>
          </button>
          <button className="admin-work-card" type="button" disabled>
            <Boxes size={22} aria-hidden="true" />
            <strong>Existing app update</strong>
            <span>Use the Existing app update tab for the update MVP.</span>
          </button>
          <button className="admin-work-card danger" type="button" disabled>
            <Trash2 size={22} aria-hidden="true" />
            <strong>Delete / uninstall</strong>
            <span>Not implemented. Future dangerous operations should require re-authentication.</span>
          </button>
          <button className="admin-work-card" type="button" disabled>
            <FileCheck2 size={22} aria-hidden="true" />
            <strong>Publish prep</strong>
            <span>Not implemented. Approval and App Pack checks are available before future publishing.</span>
          </button>
        </div>
      ) : null}
    </section>
  );
}
