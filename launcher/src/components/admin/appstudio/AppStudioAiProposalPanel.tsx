import { useEffect, useState } from "react";
import { Bot, CheckCircle2, Loader2, RefreshCw } from "lucide-react";
import { appStudioAiDiagnostics, appStudioReadAiProposal } from "../../../lib/appStudioApi";
import type { AppStudioAiDiagnostics, AppStudioAiIconCandidate, AppStudioAiProposal, AppStudioIconOverride, AppStudioRunResult, AppStudioSelectedIconSource } from "../../../lib/appStudioTypes";
import { formatAdminError } from "../adminUi";

interface Props {
  appId?: string;
  outputDir?: string | null;
  result: AppStudioRunResult | null;
  busy: boolean;
  compact?: boolean;
  onGenerate: () => Promise<AppStudioRunResult | null>;
  onAdopt: (values: { name?: string; iconPrompt?: string }) => void;
  onIconAdopt: (iconOverride: AppStudioIconOverride) => void;
  selectedIconSource?: AppStudioSelectedIconSource;
  selectedIconCandidateId?: string;
  onProposalLoaded?: (proposal: AppStudioAiProposal) => void;
  onLoadStart?: () => void;
  onLoadComplete?: (ok: boolean, message?: string) => void;
}

const METADATA_FIELDS: Array<{ key: keyof AppStudioAiProposal["metadata"]; label: string; compact?: boolean }> = [
  { key: "shortDescription", label: "一言説明", compact: true },
  { key: "description", label: "詳細説明" },
  { key: "categories", label: "カテゴリ", compact: true },
  { key: "keywords", label: "検索キーワード", compact: true },
  { key: "examples", label: "利用例" },
  { key: "useCases", label: "用途" },
  { key: "inputs", label: "入力" },
  { key: "outputs", label: "出力" },
  { key: "notes", label: "備考" },
  { key: "releaseNotes", label: "リリースノート" },
  { key: "changeSummary", label: "変更概要" },
];

type LoadingAction = "load" | "generate" | null;

export function AppStudioAiProposalPanel({
  appId,
  outputDir,
  result,
  busy,
  compact = false,
  onGenerate,
  onAdopt,
  onIconAdopt,
  selectedIconSource,
  selectedIconCandidateId,
  onProposalLoaded,
  onLoadStart,
  onLoadComplete,
}: Props) {
  const [proposal, setProposal] = useState<AppStudioAiProposal | null>(null);
  const [localSelectedIconSource, setLocalSelectedIconSource] = useState<AppStudioSelectedIconSource>("fallback_png");
  const [loadingAction, setLoadingAction] = useState<LoadingAction>(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [diagnostics, setDiagnostics] = useState<AppStudioAiDiagnostics | null>(null);
  const loading = loadingAction !== null;

  useEffect(() => {
    void refreshDiagnostics();
  }, []);

  async function refreshDiagnostics() {
    try {
      setDiagnostics(await appStudioAiDiagnostics());
    } catch {
      setDiagnostics(null);
    }
  }

  async function loadProposal(sourceResult: AppStudioRunResult | null = result) {
    setLoadingAction("load");
    setError("");
    setMessage("");
    onLoadStart?.();
    try {
      await refreshDiagnostics();
      const loaded = await appStudioReadAiProposal(sourceResult?.appId ?? appId, sourceResult?.outputDir ?? outputDir ?? undefined);
      setProposal(loaded);
      onProposalLoaded?.(loaded);
      const loadedMessage = loaded.ok ? "保存済み提案を読み込みました。" : "提案ファイルがまだ不足しています。先にAIで新しく提案を作成してください。";
      setMessage(loadedMessage);
      onLoadComplete?.(loaded.ok, loadedMessage);
    } catch (loadError) {
      const fallback = "保存済み提案を読み込めませんでした。";
      setError(formatAdminError(loadError, fallback));
      onLoadComplete?.(false, fallback);
    } finally {
      setLoadingAction(null);
    }
  }

  async function generateProposal() {
    setLoadingAction("generate");
    setError("");
    setMessage("");
    try {
      await refreshDiagnostics();
      const generated = await onGenerate();
      if (generated) {
        await loadProposal(generated);
      }
    } catch (generateError) {
      setError(formatAdminError(generateError, "AIで新しく提案を作成できませんでした。"));
    } finally {
      setLoadingAction(null);
    }
  }

  const metadata = proposal?.metadata;
  const icon = proposal?.icon;
  const selected = selectedIconSource ?? localSelectedIconSource;
  const iconCandidates = icon ? normalizedIconCandidates(icon) : [];
  const metadataFields = compact ? METADATA_FIELDS.filter((field) => field.compact) : METADATA_FIELDS;

  function adoptPng(source: "candidate_png" | "final_png", pngDataUrl?: string | null, candidate?: AppStudioAiIconCandidate) {
    if (!pngDataUrl) {
      return;
    }
    setLocalSelectedIconSource(source);
    onIconAdopt({ selectedIconSource: source, pngDataUrl, candidateId: candidate?.candidateId, sourcePrompt: candidate?.prompt ?? undefined });
    setMessage("PNGアイコン候補を採用しました。内容確認後、テスト登録で反映されます。");
  }

  function adoptFallbackPng() {
    setLocalSelectedIconSource("fallback_png");
    onIconAdopt({ selectedIconSource: "fallback_png" });
    setMessage("フォールバックPNGを使用する設定にしました。");
  }

  return (
    <section className="studio-step">
      <div>
        <span className="studio-step-index">AI</span>
        <h4>AI提案</h4>
      </div>
      <p className="admin-muted">
        説明文、カテゴリ、PNGアイコン候補を作成します。AI提案は自動確定されず、採用ボタンを押した項目だけ編集欄に反映されます。
      </p>
      {diagnostics ? <DiagnosticsPanel diagnostics={diagnostics} /> : null}

      <div className="studio-ai-actions">
        <button className="studio-ai-action-card" type="button" onClick={() => void loadProposal()} disabled={busy || loading}>
          {loadingAction === "load" ? <Loader2 className="studio-spinner" size={18} aria-hidden="true" /> : <RefreshCw size={18} aria-hidden="true" />}
          <span>
            <strong>{loadingAction === "load" ? "保存済み提案を読み込み中..." : "保存済み提案を読み込む"}</strong>
            <small>前回生成済みの提案ファイルを表示します。APIは呼びません。</small>
            <em>既存提案を使う操作です。</em>
          </span>
        </button>
        <button className="studio-ai-action-card primary" type="button" onClick={() => void generateProposal()} disabled={busy || loading}>
          {loadingAction === "generate" ? <Loader2 className="studio-spinner" size={18} aria-hidden="true" /> : <Bot size={18} aria-hidden="true" />}
          <span>
            <strong>{loadingAction === "generate" ? "AI提案を生成しています..." : "AIで新しく提案を作成"}</strong>
            <small>AIに依頼して説明文・カテゴリ・アイコン候補を新規生成します。</small>
            <em>APIを呼ぶ操作です。数十秒かかる場合があります。</em>
          </span>
        </button>
      </div>

      {metadata ? (
        <div className="studio-ai-card">
          <div className="admin-section-head">
            <div>
              <p className="dialog-kicker">メタデータ生成</p>
              <h4>{metadata.name || metadata.appId || "AI提案"}</h4>
            </div>
            <button
              className="secondary-button"
              type="button"
              onClick={() => onAdopt({ name: metadata.name ?? undefined, iconPrompt: metadata.iconPrompt ?? undefined })}
            >
              <CheckCircle2 size={17} aria-hidden="true" />
              表示名とPromptを採用
            </button>
          </div>
          <dl className="studio-ai-fields">
            <ReportFields title="メタデータ生成状態" report={metadata.aiReport} />
            {metadataFields.map((field) => (
              <Field key={field.key} label={field.label} value={fieldValue(metadata[field.key])} />
            ))}
          </dl>
        </div>
      ) : null}

      {icon ? (
        <div className="studio-ai-card">
          <div className="admin-section-head">
            <div>
              <p className="dialog-kicker">アイコン生成</p>
              <h4>PNG候補</h4>
            </div>
            <button className="secondary-button" type="button" onClick={() => onAdopt({ iconPrompt: icon.promptRevision || icon.promptInitial || undefined })}>
              <CheckCircle2 size={17} aria-hidden="true" />
              Promptを採用
            </button>
          </div>
          <div className="studio-icon-candidate-grid">
            {iconCandidates.map((candidate) => (
              <IconCandidateCard
                key={candidate.candidateId}
                candidate={candidate}
                adopted={selectedIconSource === "candidate_png" && selectedIconCandidateId === candidate.candidateId}
                onAdopt={() => adoptPng("candidate_png", candidate.pngDataUrl, candidate)}
              />
            ))}
          </div>
          <div className="studio-icon-preview-row">
            {icon.candidatePngDataUrl ? <img className="studio-icon-preview primary-icon-preview" src={icon.candidatePngDataUrl} alt="AI PNGアイコン候補" /> : null}
            {icon.finalPngDataUrl ? <img className="studio-icon-preview" src={icon.finalPngDataUrl} alt="フォールバックPNGアイコン" /> : null}
          </div>
          <div className="studio-action-row">
            <span className="admin-status-pill">採用中: {selectedIconLabel(selected)}</span>
            <button className="secondary-button" type="button" onClick={() => adoptPng("candidate_png", icon.candidatePngDataUrl)} disabled={!icon.candidatePngDataUrl}>
              <CheckCircle2 size={17} aria-hidden="true" />
              このPNGを採用
            </button>
            <button className="secondary-button" type="button" onClick={() => adoptPng("final_png", icon.finalPngDataUrl)} disabled={!icon.finalPngDataUrl}>
              <CheckCircle2 size={17} aria-hidden="true" />
              フォールバックPNGを使用
            </button>
            <button className="secondary-button" type="button" onClick={adoptFallbackPng}>
              <CheckCircle2 size={17} aria-hidden="true" />
              アイコン採用を解除
            </button>
          </div>
          <p className="admin-muted">PNGが標準アイコンです。採用前のPNG候補は final_app/icon.png には反映されません。</p>
          {icon.candidateUrl ? <p className="admin-muted">PNG URL候補: {icon.candidateUrl}</p> : null}
          {icon.fallbackSvg ? (
            <div className="studio-icon-fallback">
              <p className="dialog-kicker">SVG fallback</p>
              <IconSvg title="fallback svg" svg={icon.fallbackSvg} />
            </div>
          ) : null}
          <dl className="studio-ai-fields">
            <ReportFields title="画像生成状態" report={icon.aiReport} />
            {!compact ? <Field label="初回Prompt" value={icon.promptInitial} /> : null}
            {!compact ? <Field label="修正Prompt" value={icon.promptRevision} /> : null}
          </dl>
        </div>
      ) : null}

      {proposal?.warnings.length ? (
        <ul className="studio-ai-warning">
          {proposal.warnings.map((warning) => (
            <li key={warning}>{warning}</li>
          ))}
        </ul>
      ) : null}
      {message ? <p className="admin-success">{message}</p> : null}
      {error ? <p className="admin-error" role="alert">{error}</p> : null}
    </section>
  );
}

function IconCandidateCard({ candidate, adopted, onAdopt }: { candidate: AppStudioAiIconCandidate; adopted: boolean; onAdopt: () => void }) {
  return (
    <article className={`studio-icon-candidate-card${adopted ? " selected" : ""}`}>
      <div className="studio-icon-candidate-head">
        <strong>候補 {candidate.number || candidate.candidateId}</strong>
        <span className={candidate.fallback ? "admin-status-pill warn" : "admin-status-pill"}>{candidate.fallback ? "fallback" : sourceLabel(candidate.source)}</span>
      </div>
      {candidate.pngDataUrl ? (
        <img className="studio-icon-preview primary-icon-preview" src={candidate.pngDataUrl} alt={`PNGアイコン候補 ${candidate.number}`} />
      ) : (
        <div className="studio-icon-empty">PNGなし</div>
      )}
      <div className="studio-icon-candidate-meta">
        <span>model: {candidate.model || "unknown"}</span>
        <span>resolution: {candidate.resolution || "unknown"}</span>
        <span>status: {statusValue(candidate.status || "unknown")}</span>
        {adopted ? <span>採用中</span> : null}
      </div>
      <button className="secondary-button" type="button" onClick={onAdopt} disabled={!candidate.pngDataUrl}>
        <CheckCircle2 size={17} aria-hidden="true" />
        このPNGを採用
      </button>
    </article>
  );
}

function normalizedIconCandidates(icon: AppStudioAiProposal["icon"]): AppStudioAiIconCandidate[] {
  if (Array.isArray(icon.candidates) && icon.candidates.length) {
    return icon.candidates;
  }
  const candidates: AppStudioAiIconCandidate[] = [];
  if (icon.candidatePngDataUrl || icon.candidateUrl) {
    candidates.push({
      candidateId: "icon_candidate_1",
      number: 1,
      source: "legacy",
      prompt: icon.promptRevision || icon.promptInitial,
      model: "unknown",
      status: "legacy",
      resolution: "unknown",
      fallback: false,
      pngDataUrl: icon.candidatePngDataUrl,
      url: icon.candidateUrl,
    });
  }
  return candidates;
}

function sourceLabel(source?: string | null): string {
  if (!source) {
    return "unknown";
  }
  if (source.includes("fallback")) {
    return "fallback";
  }
  if (source === "api") {
    return "API生成";
  }
  return source;
}

function Field({ label, value }: { label: string; value?: string | null }) {
  if (!value) {
    return null;
  }
  return (
    <>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </>
  );
}

function DiagnosticsPanel({ diagnostics }: { diagnostics: AppStudioAiDiagnostics }) {
  return (
    <div className="studio-ai-status-grid">
      <StatusItem label="AI機能" value={diagnostics.aiEnabled ? "有効" : "無効"} />
      <StatusItem label="APIキー取得元" value={apiKeyLabel(diagnostics)} />
      <StatusItem label="テキストモデル" value={diagnostics.textModel || "未設定"} />
      <StatusItem label="画像モデル" value={diagnostics.imageModel || "未設定"} />
      <StatusItem label="CLI環境" value={diagnostics.cliEnvReady ? "AI利用の準備ができています" : "AI利用の準備が未完了です"} />
      <StatusItem label="診断メッセージ" value={diagnosticMessage(diagnostics.message)} />
    </div>
  );
}

function StatusItem({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function ReportFields({ title, report }: { title: string; report?: string | null }) {
  const summary = reportSummary(report);
  if (!summary.length) {
    return null;
  }
  return (
    <>
      <dt>{title}</dt>
      <dd>
        <div className="studio-ai-report-summary">
          {summary.map(([key, value]) => (
            <span key={key}>
              <strong>{key}</strong>: {value}
            </span>
          ))}
        </div>
      </dd>
    </>
  );
}

function fieldValue(value: unknown): string {
  if (Array.isArray(value)) {
    return value.filter(Boolean).join(" / ");
  }
  if (typeof value === "string") {
    return value;
  }
  return "";
}

function reportSummary(report?: string | null): Array<[string, string]> {
  if (!report) {
    return [];
  }
  const labels: Record<string, string> = {
    api: "API",
    status: "状態",
    model: "モデル",
    parse_status: "JSON解析",
    content_type: "形式",
    saved_candidate: "保存候補",
    fallback_reason: "理由",
  };
  const lines = report.split(/\r?\n/);
  return Object.keys(labels)
    .map((key): [string, string] | null => {
      const prefix = `${key}:`;
      const line = lines.find((item) => item.trim().startsWith(prefix));
      const value = line?.slice(prefix.length).trim();
      return value ? [labels[key], statusValue(value)] : null;
    })
    .filter((item): item is [string, string] => Boolean(item));
}

function statusValue(value: string): string {
  if (value === "success") {
    return "成功";
  }
  if (value === "fallback") {
    return "フォールバック";
  }
  if (value === "skipped") {
    return "スキップ";
  }
  if (value === "failed") {
    return "失敗";
  }
  return value;
}

function apiKeyLabel(diagnostics: AppStudioAiDiagnostics): string {
  if (!diagnostics.apiKeyPresent) {
    return "未設定";
  }
  if (diagnostics.apiKeySource === "credential") {
    return "Credential Manager";
  }
  if (diagnostics.apiKeySource === "environment") {
    return "環境変数";
  }
  return "設定済み";
}

function diagnosticMessage(message: string): string {
  if (!message) {
    return "診断メッセージはありません。";
  }
  if (message.includes("ready")) {
    return "CLI環境はAI利用の準備ができています。";
  }
  if (message.includes("missing") || message.includes("not configured")) {
    return "AI利用に必要な設定が不足しています。";
  }
  if (message.includes("disabled")) {
    return "AI機能は無効です。フォールバックで続行できます。";
  }
  return message;
}

function selectedIconLabel(source: AppStudioSelectedIconSource | string): string {
  if (source === "candidate_png") {
    return "AI PNG候補";
  }
  if (source === "final_png") {
    return "フォールバックPNG";
  }
  return "未採用";
}

function IconSvg({ title, svg }: { title: string; svg: string }) {
  const safeSvg = sanitizeSvg(svg);
  if (!safeSvg) {
    return null;
  }
  return <div className="studio-icon-preview" title={title} dangerouslySetInnerHTML={{ __html: safeSvg }} />;
}

function sanitizeSvg(svg: string): string {
  const trimmed = svg.trim();
  if (!trimmed.startsWith("<svg") || !trimmed.includes("</svg>")) {
    return "";
  }
  return trimmed
    .replace(/<script[\s\S]*?<\/script>/gi, "")
    .replace(/\son[a-z]+\s*=\s*"[^"]*"/gi, "")
    .replace(/\son[a-z]+\s*=\s*'[^']*'/gi, "");
}
