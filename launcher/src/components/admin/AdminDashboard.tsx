import { useState } from "react";
import { Activity, Bot, LogOut, Package, Settings2, Wrench } from "lucide-react";
import type { AdminSessionStatus } from "../../lib/adminTypes";
import { AdminLogsPanel } from "./AdminLogsPanel";
import { AiSettingsPanel } from "./AiSettingsPanel";
import { AppStudioShell } from "./AppStudioShell";
import { UpdateManagementShell } from "./UpdateManagementShell";

type AdminSection = "appStudio" | "ai" | "updates" | "logs";

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
          <h2>ToolHub Admin</h2>
          <p className="admin-muted">App Studio と運用設定は管理者ログイン後のみ利用できます。</p>
        </div>

        <div className="admin-session-box">
          <span>セッション</span>
          <strong>{session.authenticated ? "認証済み" : "未認証"}</strong>
          {session.expiresAt ? <small>期限: {formatDate(session.expiresAt)}</small> : null}
        </div>

        <nav className="admin-nav-list" aria-label="管理者メニュー">
          <button type="button" className={active === "appStudio" ? "active" : ""} onClick={() => setActive("appStudio")}>
            <Wrench size={18} aria-hidden="true" />
            App Studio
          </button>
          <button type="button" className={active === "ai" ? "active" : ""} onClick={() => setActive("ai")}>
            <Bot size={18} aria-hidden="true" />
            AI/APIキー管理
          </button>
          <button type="button" className={active === "updates" ? "active" : ""} onClick={() => setActive("updates")}>
            <Package size={18} aria-hidden="true" />
            更新管理
          </button>
          <button type="button" className={active === "logs" ? "active" : ""} onClick={() => setActive("logs")}>
            <Activity size={18} aria-hidden="true" />
            ログ/診断
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
          <span>公開、削除、APIキー更新などの危険操作は将来再認証を必須にします。</span>
        </div>
        {active === "appStudio" ? <AppStudioShell /> : null}
        {active === "ai" ? <AiSettingsPanel /> : null}
        {active === "updates" ? <UpdateManagementShell /> : null}
        {active === "logs" ? <AdminLogsPanel /> : null}
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
