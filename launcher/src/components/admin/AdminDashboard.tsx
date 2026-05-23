import { useState } from "react";
import { Activity, Bot, Info, LogOut, Package, Settings2, Wrench } from "lucide-react";
import type { AdminSessionStatus } from "../../lib/adminTypes";
import { AdminDiagnosticsPanel } from "./AdminDiagnosticsPanel";
import { AiSettingsPanel } from "./AiSettingsPanel";
import { AppStudioShell } from "./AppStudioShell";
import { ToolHubInfoPanel } from "./ToolHubInfoPanel";
import { UpdateManagementShell } from "./UpdateManagementShell";

type AdminSection = "appStudio" | "updates" | "ai" | "diagnostics" | "info";

interface Props {
  session: AdminSessionStatus;
  onLogout: () => void;
}

export function AdminDashboard({ session, onLogout }: Props) {
  const [active, setActive] = useState<AdminSection>("appStudio");

  return (
    <div className="admin-dashboard">
      <aside className="admin-nav">
        <div>
          <p className="dialog-kicker">管理者画面</p>
          <h2>ToolHub 管理</h2>
          <p className="admin-muted">アプリ管理、配布、AI設定、診断をここに集約します。</p>
        </div>

        <div className="admin-session-box">
          <span>セッション</span>
          <strong>{session.authenticated ? "認証済み" : "未認証"}</strong>
          {session.expiresAt ? <small>期限: {formatDate(session.expiresAt)}</small> : null}
        </div>

        <nav className="admin-nav-list" aria-label="管理者メニュー">
          <button type="button" className={active === "appStudio" ? "active" : ""} onClick={() => setActive("appStudio")}>
            <Wrench size={18} aria-hidden="true" />
            アプリ管理
          </button>
          <button type="button" className={active === "updates" ? "active" : ""} onClick={() => setActive("updates")}>
            <Package size={18} aria-hidden="true" />
            配布と更新
          </button>
          <button type="button" className={active === "ai" ? "active" : ""} onClick={() => setActive("ai")}>
            <Bot size={18} aria-hidden="true" />
            AI/APIキー
          </button>
          <button type="button" className={active === "diagnostics" ? "active" : ""} onClick={() => setActive("diagnostics")}>
            <Activity size={18} aria-hidden="true" />
            診断
          </button>
          <button type="button" className={active === "info" ? "active" : ""} onClick={() => setActive("info")}>
            <Info size={18} aria-hidden="true" />
            ToolHub情報
          </button>
        </nav>

        <button className="secondary-button admin-logout-button" type="button" onClick={onLogout}>
          <LogOut size={17} aria-hidden="true" />
          ログアウト
        </button>
      </aside>

      <div className="admin-main-panel">
        <div className="admin-main-banner">
          <Settings2 size={19} aria-hidden="true" />
          <span>一般利用者の起動画面から管理・診断機能を分離し、運用操作は管理者認証後に扱います。</span>
        </div>
        {active === "appStudio" ? <AppStudioShell /> : null}
        {active === "updates" ? <UpdateManagementShell /> : null}
        {active === "ai" ? <AiSettingsPanel /> : null}
        {active === "diagnostics" ? <AdminDiagnosticsPanel /> : null}
        {active === "info" ? <ToolHubInfoPanel /> : null}
      </div>
    </div>
  );
}

function formatDate(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleString();
}
