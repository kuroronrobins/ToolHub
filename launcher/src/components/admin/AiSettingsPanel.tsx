import { useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";
import { KeyRound, PlugZap, Save, Trash2 } from "lucide-react";
import {
  aiDeleteApiKey,
  aiGetApiKeyStatus,
  aiGetSettings,
  aiSaveApiKey,
  aiSaveSettings,
  aiTestConnection,
} from "../../lib/adminApi";
import type { AiSettings, ApiKeyStatus } from "../../lib/adminTypes";
import { formatAdminError } from "./adminUi";

const DEFAULT_SETTINGS: AiSettings = {
  aiEnabled: false,
  textModel: "",
  imageModel: "gpt-image-2",
  apiKeySource: "windows_credential_manager",
  updatedAt: null,
};

export function AiSettingsPanel() {
  const [settings, setSettings] = useState<AiSettings>(DEFAULT_SETTINGS);
  const [status, setStatus] = useState<ApiKeyStatus | null>(null);
  const [apiKey, setApiKey] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const shortKeyWarning = useMemo(() => {
    const trimmed = apiKey.trim();
    return trimmed.length > 0 && trimmed.length < 20;
  }, [apiKey]);

  async function reload() {
    setError("");
    const [loadedSettings, loadedStatus] = await Promise.all([aiGetSettings(), aiGetApiKeyStatus()]);
    setSettings(loadedSettings);
    setStatus(loadedStatus);
  }

  useEffect(() => {
    let cancelled = false;
    setBusy(true);
    Promise.all([aiGetSettings(), aiGetApiKeyStatus()])
      .then(([loadedSettings, loadedStatus]) => {
        if (!cancelled) {
          setSettings(loadedSettings);
          setStatus(loadedStatus);
        }
      })
      .catch((loadError) => {
        if (!cancelled) {
          setError(formatAdminError(loadError, "AI設定を読み込めませんでした。"));
        }
      })
      .finally(() => {
        if (!cancelled) {
          setBusy(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function handleSaveSettings(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const saved = await aiSaveSettings(settings);
      setSettings(saved);
      setMessage("AI設定を保存しました。");
    } catch (saveError) {
      setError(formatAdminError(saveError, "AI設定を保存できませんでした。"));
    } finally {
      setBusy(false);
    }
  }

  async function handleSaveApiKey() {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      await aiSaveApiKey(apiKey);
      setApiKey("");
      await reload();
      setMessage("APIキーを保存しました。");
    } catch (saveError) {
      setError(formatAdminError(saveError, "APIキーを保存できませんでした。"));
    } finally {
      setBusy(false);
    }
  }

  async function handleDeleteApiKey() {
    if (!window.confirm("登録済みOpenAI APIキーを削除しますか？")) {
      return;
    }
    setBusy(true);
    setError("");
    setMessage("");
    try {
      await aiDeleteApiKey();
      setApiKey("");
      await reload();
      setMessage("APIキーを削除しました。");
    } catch (deleteError) {
      setError(formatAdminError(deleteError, "APIキーを削除できませんでした。"));
    } finally {
      setBusy(false);
    }
  }

  async function handleTestConnection() {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const result = await aiTestConnection();
      setMessage(result.message);
    } catch (testError) {
      setError(formatAdminError(testError, "接続テストを実行できませんでした。"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="admin-panel-section">
      <div className="admin-section-head">
        <div>
          <p className="dialog-kicker">AI/APIキー管理</p>
          <h3>OpenAI設定</h3>
        </div>
        <span className={`admin-status-pill ${status?.state === "registered" || status?.state === "env_available" ? "ok" : ""}`}>
          {statusLabel(status)}
        </span>
      </div>

      <form className="admin-settings-form" onSubmit={handleSaveSettings}>
        <label className="admin-toggle">
          <input
            type="checkbox"
            checked={settings.aiEnabled}
            onChange={(event) => setSettings((current) => ({ ...current, aiEnabled: event.target.checked }))}
          />
          <span>AI機能を有効にする</span>
        </label>

        <div className="admin-two-column">
          <label className="admin-field">
            <span>Text model</span>
            <input
              type="text"
              value={settings.textModel}
              placeholder="環境に合わせて設定"
              onChange={(event) => setSettings((current) => ({ ...current, textModel: event.target.value }))}
            />
          </label>
          <label className="admin-field">
            <span>Image model</span>
            <input
              type="text"
              value={settings.imageModel}
              placeholder="gpt-image-2"
              onChange={(event) => setSettings((current) => ({ ...current, imageModel: event.target.value }))}
            />
            <small className="admin-muted">推奨: gpt-image-2 / 互換: gpt-image-1.5, gpt-image-1, gpt-image-1-mini</small>
          </label>
        </div>

        <div className="admin-form-actions">
          <button className="secondary-button" type="button" onClick={() => void handleTestConnection()} disabled={busy}>
            <PlugZap size={17} aria-hidden="true" />
            接続テスト
          </button>
          <button className="primary-button" type="submit" disabled={busy}>
            <Save size={17} aria-hidden="true" />
            保存
          </button>
        </div>
      </form>

      <div className="admin-key-box">
        <div>
          <strong>APIキー状態</strong>
          <p>{status?.message ?? "確認中です。"}</p>
          {status?.masked ? <p className="admin-masked-key">{status.masked}</p> : null}
        </div>
        <label className="admin-field">
          <span>OpenAI APIキー</span>
          <input
            type="password"
            value={apiKey}
            autoComplete="off"
            placeholder="登録時のみ入力"
            onChange={(event) => setApiKey(event.target.value)}
          />
        </label>
        {shortKeyWarning ? <p className="admin-warning">入力値が短い可能性があります。保存前に確認してください。</p> : null}
        <div className="admin-form-actions">
          <button className="secondary-button" type="button" onClick={() => void handleSaveApiKey()} disabled={busy || apiKey.trim().length === 0}>
            <KeyRound size={17} aria-hidden="true" />
            登録/更新
          </button>
          <button className="secondary-button danger-button" type="button" onClick={() => void handleDeleteApiKey()} disabled={busy}>
            <Trash2 size={17} aria-hidden="true" />
            削除
          </button>
        </div>
      </div>

      {message ? <p className="admin-success">{message}</p> : null}
      {error ? <p className="admin-error" role="alert">{error}</p> : null}
    </section>
  );
}

function statusLabel(status: ApiKeyStatus | null): string {
  if (!status) {
    return "確認中";
  }
  if (status.state === "registered") {
    return "登録済み";
  }
  if (status.state === "env_available") {
    return "環境変数";
  }
  if (status.state === "credential_unavailable") {
    return "保存不可";
  }
  return "未登録";
}
