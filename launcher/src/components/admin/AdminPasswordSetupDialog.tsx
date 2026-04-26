import { useState } from "react";
import type { FormEvent } from "react";
import { KeyRound } from "lucide-react";
import { adminSetPassword } from "../../lib/adminApi";
import type { AdminSessionStatus } from "../../lib/adminTypes";
import { formatAdminError } from "./adminUi";

interface Props {
  onReady: (status: AdminSessionStatus) => void;
  onCancel: () => void;
}

export function AdminPasswordSetupDialog({ onReady, onCancel }: Props) {
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setBusy(true);
    try {
      const status = await adminSetPassword(password, confirmPassword);
      setPassword("");
      setConfirmPassword("");
      onReady(status);
    } catch (submitError) {
      setError(formatAdminError(submitError, "管理者パスワードを設定できませんでした。"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="admin-auth-panel" onSubmit={handleSubmit}>
      <div className="admin-auth-icon">
        <KeyRound size={24} aria-hidden="true" />
      </div>
      <div>
        <p className="dialog-kicker">初回設定</p>
        <h2>管理者パスワード設定</h2>
        <p className="admin-muted">App Studio と APIキー管理を開くための管理者パスワードを設定します。</p>
      </div>

      <label className="admin-field">
        <span>パスワード</span>
        <input
          type="password"
          value={password}
          minLength={8}
          required
          autoComplete="new-password"
          onChange={(event) => setPassword(event.target.value)}
        />
      </label>
      <label className="admin-field">
        <span>確認入力</span>
        <input
          type="password"
          value={confirmPassword}
          minLength={8}
          required
          autoComplete="new-password"
          onChange={(event) => setConfirmPassword(event.target.value)}
        />
      </label>

      {error ? <p className="admin-error" role="alert">{error}</p> : null}

      <div className="admin-form-actions">
        <button className="secondary-button" type="button" onClick={onCancel} disabled={busy}>
          閉じる
        </button>
        <button className="primary-button" type="submit" disabled={busy}>
          {busy ? "設定中" : "設定して開く"}
        </button>
      </div>
    </form>
  );
}
