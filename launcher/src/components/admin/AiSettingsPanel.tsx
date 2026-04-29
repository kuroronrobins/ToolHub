import { useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";
import { KeyRound, PlugZap, Save, Trash2 } from "lucide-react";
import {
  aiProbeImageModels,
  aiDeleteApiKey,
  aiGetApiKeyStatus,
  aiGetSettings,
  aiSaveApiKey,
  aiSaveSettings,
  aiTestConnection,
  aiTestImageGeneration,
} from "../../lib/adminApi";
import type { AiImageGenerationTestResult, AiImageModelProbeResult, AiSettings, ApiKeyStatus } from "../../lib/adminTypes";
import { imageApiFailureGuidance, isOrganizationVerificationRequired, storeImageGenerationTestResult } from "../../lib/imageApiHealth";
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
  const [imageTest, setImageTest] = useState<AiImageGenerationTestResult | null>(null);
  const [modelProbe, setModelProbe] = useState<AiImageModelProbeResult | null>(null);
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

  async function handleImageGenerationTest() {
    setBusy(true);
    setError("");
    setMessage("");
    setImageTest(null);
    try {
      const result = await aiTestImageGeneration();
      setImageTest(result);
      storeImageGenerationTestResult(result);
      setMessage(result.ok ? `画像生成テスト成功: ${result.model}` : `画像生成テスト失敗: ${imageApiFailureGuidance(result) || result.message}`);
    } catch (testError) {
      setError(formatAdminError(testError, "画像生成テストを実行できませんでした。"));
    } finally {
      setBusy(false);
    }
  }

  async function handleProbeImageModels() {
    setBusy(true);
    setError("");
    setMessage("");
    setModelProbe(null);
    try {
      const result = await aiProbeImageModels();
      setModelProbe(result);
      const firstSuccess = result.items.find((item) => item.ok);
      if (firstSuccess) {
        setMessage(`利用可能な画像モデルを確認しました: ${firstSuccess.model}`);
      } else {
        setMessage("候補の画像モデルはいずれも実APIテストに成功しませんでした。");
      }
    } catch (probeError) {
      setError(formatAdminError(probeError, "画像モデルの実API確認を実行できませんでした。"));
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
          <button className="secondary-button" type="button" onClick={() => void handleImageGenerationTest()} disabled={busy}>
            <PlugZap size={17} aria-hidden="true" />
            画像生成テスト（実API呼び出し）
          </button>
          <button className="secondary-button" type="button" onClick={() => void handleProbeImageModels()} disabled={busy}>
            <PlugZap size={17} aria-hidden="true" />
            候補モデルを順にテスト（実API呼び出し）
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
      {imageTest ? <ImageGenerationTestResult result={imageTest} /> : null}
      {modelProbe ? (
        <ImageModelProbeResult
          result={modelProbe}
          onUseModel={(model) => {
            setSettings((current) => ({ ...current, imageModel: model }));
            setMessage(`${model} を Image model 入力欄へ反映しました。保存すると有効になります。`);
          }}
        />
      ) : null}
      {error ? <p className="admin-error" role="alert">{error}</p> : null}
    </section>
  );
}

function ImageGenerationTestResult({ result }: { result: AiImageGenerationTestResult }) {
  const guidance = imageApiFailureGuidance(result);
  return (
    <>
      {!result.ok && guidance ? <p className="admin-warning">{guidance}</p> : null}
      {isOrganizationVerificationRequired(result) ? (
        <div className="admin-api-guidance">
          <strong>{result.model || "gpt-image-2"} は現在のOpenAI組織では利用できません。</strong>
          <p>OpenAI Platformで組織認証を完了するか、別のImage modelを設定してください。認証後、反映まで最大15分程度かかる場合があります。</p>
        </div>
      ) : null}
      <div className={`admin-image-test-result ${result.ok ? "ok" : "warn"}`}>
        <div><span>ok</span><strong>{result.ok ? "true" : "false"}</strong></div>
        <div><span>model</span><strong>{result.model || "unknown"}</strong></div>
        <div><span>api</span><strong>{result.api || "unknown"}</strong></div>
        <div><span>status</span><strong>{result.status || "unknown"}</strong></div>
        <div><span>content_type</span><strong>{result.contentType || "none"}</strong></div>
        <div><span>resolution</span><strong>{result.resolution || "unknown"}</strong></div>
        {result.fallbackReason ? <div className="wide"><span>fallback_reason</span><strong>{result.fallbackReason}</strong></div> : null}
        {result.errorCategory ? <div><span>error_category</span><strong>{result.errorCategory}</strong></div> : null}
        {result.error ? <div className="wide"><span>error</span><strong>{result.error}</strong></div> : null}
        {result.ok ? <div className="wide"><span>確認済み</span><strong>{result.model}</strong></div> : null}
      </div>
    </>
  );
}

function ImageModelProbeResult({ result, onUseModel }: { result: AiImageModelProbeResult; onUseModel: (model: string) => void }) {
  return (
    <div className="admin-image-model-probe">
      <div>
        <strong>Image model 利用可能性確認</strong>
        <p>各候補に対して実際の画像生成APIを呼び出しています。実行にはOpenAI API利用料金が発生する場合があります。</p>
      </div>
      {result.items.map((item) => (
        <div key={item.model} className={`admin-image-model-probe-row ${item.ok ? "ok" : "warn"}`}>
          <div>
            <span>{item.ok ? "成功" : "失敗"}</span>
            <strong>{item.model}</strong>
          </div>
          <div>
            <span>status</span>
            <strong>{item.status || "unknown"}</strong>
          </div>
          <div>
            <span>error_category</span>
            <strong>{item.errorCategory || "none"}</strong>
          </div>
          <div className="wide">
            <span>fallback_reason</span>
            <strong>{item.fallbackReason || item.error || "none"}</strong>
          </div>
          <button className="secondary-button" type="button" onClick={() => onUseModel(item.model)} disabled={!item.ok}>
            このモデルを使用
          </button>
        </div>
      ))}
    </div>
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
