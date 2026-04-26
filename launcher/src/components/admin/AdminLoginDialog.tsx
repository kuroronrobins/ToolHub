import { useState } from "react";
import type { FormEvent } from "react";
import { LockKeyhole } from "lucide-react";
import { adminLogin } from "../../lib/adminApi";
import type { AdminSessionStatus } from "../../lib/adminTypes";
import { formatAdminError } from "./adminUi";

interface Props {
  onReady: (status: AdminSessionStatus) => void;
  onCancel: () => void;
}

export function AdminLoginDialog({ onReady, onCancel }: Props) {
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setBusy(true);
    try {
      const status = await adminLogin(password);
      setPassword("");
      onReady(status);
    } catch (loginError) {
      setError(formatAdminError(loginError, "管理者ログインに失敗しました。"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="admin-auth-panel" onSubmit={handleSubmit}>
      <div className="admin-auth-icon">
        <LockKeyhole size={24} aria-hidden="true" />
      </div>
      <div>
        <p className="dialog-kicker">管理者認証</p>
        <h2>管理者ログイン</h2>
        <p className="admin-muted">App Studio、AI/APIキー管理、更新管理、ログ診断を開きます。</p>
      </div>

      <label className="admin-field">
        <span>パスワード</span>
        <input
          type="password"
          value={password}
          required
          autoComplete="current-password"
          onChange={(event) => setPassword(event.target.value)}
        />
      </label>

      {error ? <p className="admin-error" role="alert">{error}</p> : null}

      <div className="admin-form-actions">
        <button className="secondary-button" type="button" onClick={onCancel} disabled={busy}>
          閉じる
        </button>
        <button className="primary-button" type="submit" disabled={busy || password.length === 0}>
          {busy ? "確認中" : "ログイン"}
        </button>
      </div>
    </form>
  );
}
