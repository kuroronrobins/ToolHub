import { useEffect, useState } from "react";
import { ShieldCheck, X } from "lucide-react";
import { adminIsPasswordSet, adminLogout, adminSessionStatus } from "../../lib/adminApi";
import type { AdminSessionStatus } from "../../lib/adminTypes";
import { AdminDashboard } from "./AdminDashboard";
import { AdminLoginDialog } from "./AdminLoginDialog";
import { AdminPasswordSetupDialog } from "./AdminPasswordSetupDialog";
import { formatAdminError } from "./adminUi";

type AdminEntryView = "loading" | "setup" | "login" | "dashboard";

interface Props {
  open: boolean;
  onClose: () => void;
}

export function AdminEntryDialog({ open, onClose }: Props) {
  const [view, setView] = useState<AdminEntryView>("loading");
  const [session, setSession] = useState<AdminSessionStatus>({ authenticated: false });
  const [error, setError] = useState("");

  useEffect(() => {
    if (!open) {
      setView("loading");
      setError("");
      return;
    }

    let cancelled = false;
    setView("loading");
    setError("");
    Promise.all([adminIsPasswordSet(), adminSessionStatus()])
      .then(([passwordSet, status]) => {
        if (cancelled) {
          return;
        }
        setSession(status);
        if (status.authenticated) {
          setView("dashboard");
        } else {
          setView(passwordSet ? "login" : "setup");
        }
      })
      .catch((loadError) => {
        if (!cancelled) {
          setError(formatAdminError(loadError, "管理者画面を開けませんでした。"));
          setView("login");
        }
      });

    return () => {
      cancelled = true;
    };
  }, [open]);

  if (!open) {
    return null;
  }

  async function handleLogout() {
    setError("");
    try {
      await adminLogout();
      setSession({ authenticated: false });
      setView("login");
    } catch (logoutError) {
      setError(formatAdminError(logoutError, "ログアウトできませんでした。"));
    }
  }

  function handleReady(status: AdminSessionStatus) {
    setSession(status);
    setView("dashboard");
  }

  return (
    <div className="dialog-backdrop" role="presentation" onMouseDown={onClose}>
      <section
        className="dialog-panel admin-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="admin-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <header className="dialog-header">
          <div className="admin-dialog-title">
            <ShieldCheck size={21} aria-hidden="true" />
            <div>
              <p className="dialog-kicker">管理者</p>
              <h2 id="admin-title">管理者画面</h2>
            </div>
          </div>
          <button className="icon-button" type="button" onClick={onClose} title="閉じる">
            <X size={20} aria-hidden="true" />
          </button>
        </header>

        <div className="admin-dialog-body">
          {view === "loading" ? <div className="loading-state">管理者設定を確認しています。</div> : null}
          {view === "setup" ? <AdminPasswordSetupDialog onReady={handleReady} onCancel={onClose} /> : null}
          {view === "login" ? <AdminLoginDialog onReady={handleReady} onCancel={onClose} /> : null}
          {view === "dashboard" ? <AdminDashboard session={session} onLogout={() => void handleLogout()} /> : null}
          {error ? <p className="admin-error" role="alert">{error}</p> : null}
        </div>
      </section>
    </div>
  );
}
