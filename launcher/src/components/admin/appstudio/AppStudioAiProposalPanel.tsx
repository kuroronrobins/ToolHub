import { useEffect, useState } from "react";
import { Bot, CheckCircle2, Loader2, RefreshCw } from "lucide-react";
import { appStudioAiDiagnostics, appStudioReadAiProposal } from "../../../lib/appStudioApi";
import { generatedMetadataSuggestion } from "../../../lib/appStudioMetadata";
import {
  candidateConceptSummary,
  candidateSourceLabel,
  displayModelName,
  iconSourceLabel,
  normalizeAppStudioIconProposal,
  type NormalizedIconProposal,
} from "../../../lib/appStudioIconProposal";
import type { AppStudioAiDiagnostics, AppStudioAiIconCandidate, AppStudioAiProposal, AppStudioIconOverride, AppStudioRunResult, AppStudioSelectedIconSource } from "../../../lib/appStudioTypes";
import { IMAGE_TEST_UPDATED_EVENT, imageApiFailureGuidance, isOrganizationVerificationRequired, loadImageGenerationTestResult, type StoredImageGenerationTestResult } from "../../../lib/imageApiHealth";
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
  { key: "primaryCategory", label: "補助分類", compact: true },
  { key: "targetCategories", label: "対象カテゴリ", compact: true },
  { key: "tags", label: "特徴タグ", compact: true },
  { key: "categories", label: "互換カテゴリ" },
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
  const [localSelectedIconSource, setLocalSelectedIconSource] = useState<AppStudioSelectedIconSource>("default_icon");
  const [loadingAction, setLoadingAction] = useState<LoadingAction>(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [diagnostics, setDiagnostics] = useState<AppStudioAiDiagnostics | null>(null);
  const [imageApiHealth, setImageApiHealth] = useState<StoredImageGenerationTestResult | null>(() => loadImageGenerationTestResult());
  const loading = loadingAction !== null;

  useEffect(() => {
    void refreshDiagnostics();
  }, []);

  useEffect(() => {
    const reloadHealth = () => setImageApiHealth(loadImageGenerationTestResult());
    window.addEventListener(IMAGE_TEST_UPDATED_EVENT, reloadHealth);
    window.addEventListener("storage", reloadHealth);
    return () => {
      window.removeEventListener(IMAGE_TEST_UPDATED_EVENT, reloadHealth);
      window.removeEventListener("storage", reloadHealth);
    };
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
  const generatedMetadata = generatedMetadataSuggestion(metadata);
  const selected = selectedIconSource ?? localSelectedIconSource;
  const normalizedIcon = icon ? normalizeAppStudioIconProposal(icon, selected) : null;
  const apiCandidates = normalizedIcon?.apiCandidates ?? [];
  const primaryPreviewLabel = normalizedIcon?.primaryPreviewLabel ?? "ToolHub共通default icon";
  const metadataFields = compact ? METADATA_FIELDS.filter((field) => field.compact) : METADATA_FIELDS;
  const imageApiBlocked = imageApiHealth?.ok === false;

  function adoptPng(source: "candidate_png" | "final_png" | "ai_candidate_png" | "uploaded_png", pngDataUrl?: string | null, candidate?: AppStudioAiIconCandidate) {
    if (!pngDataUrl) {
      return;
    }
    if (source === "candidate_png" && !candidate && !apiCandidates.length) {
      setError("API生成候補がありません。画像生成の診断を確認してください。");
      return;
    }
    setLocalSelectedIconSource(source);
    onIconAdopt({ selectedIconSource: source, pngDataUrl, candidateId: candidate?.candidateId, sourcePrompt: candidate?.prompt ?? undefined });
    setMessage("PNGアイコン候補を採用しました。内容確認後、テスト登録で反映されます。");
  }

  function resetToDefaultIcon() {
    setLocalSelectedIconSource("default_icon");
    onIconAdopt({ selectedIconSource: "default_icon" });
    setMessage("ToolHub共通default iconを使用する設定に戻しました。");
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
      <ImageApiTestDiagnostics result={imageApiHealth} />
      {imageApiBlocked ? <ImageApiBlockedNotice result={imageApiHealth} /> : null}

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
              <p className="dialog-kicker">{generatedMetadata ? "メタデータ生成" : "メタデータAI未実行"}</p>
              <h4>{metadata.name || metadata.appId || (generatedMetadata ? "AI提案" : "AI提案なし")}</h4>
            </div>
            {generatedMetadata ? (
              <button
                className="secondary-button"
                type="button"
                onClick={() => onAdopt({ name: generatedMetadata.name ?? undefined, iconPrompt: generatedMetadata.iconPrompt ?? undefined })}
              >
                <CheckCircle2 size={17} aria-hidden="true" />
                表示名とPromptを採用
              </button>
            ) : (
              <span className="admin-status-pill warn">fallback非表示</span>
            )}
          </div>
          <dl className="studio-ai-fields">
            <ReportFields title="メタデータ生成状態" report={metadata.aiReport} />
            {generatedMetadata ? (
              metadataFields.map((field) => (
                <Field key={field.key} label={field.label} value={fieldValue(generatedMetadata[field.key])} />
              ))
            ) : (
              <MetadataFallbackSuppressed metadata={metadata} />
            )}
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
          <IconFunctionInterpretationPanel interpretation={icon.functionInterpretation} />
          <ImageApiSummaryPanel normalized={normalizedIcon} />
          <div className="studio-icon-candidate-section">
            <div className="admin-section-head compact">
              <div>
                <p className="dialog-kicker">AI生成候補</p>
                <h4>画像APIで生成された候補</h4>
              </div>
              <span className="admin-status-pill">{apiCandidates.length}件</span>
            </div>
            {!apiCandidates.length ? <p className="admin-muted">API画像候補は保存されていません。上の診断に表示された理由を解消してから再生成してください。</p> : null}
          <div className="studio-icon-candidate-grid">
            {apiCandidates.map((candidate) => (
              <IconCandidateCard
                key={candidate.candidateId}
                candidate={candidate}
                adopted={selected === "candidate_png" && selectedIconCandidateId === candidate.candidateId}
                onAdopt={() => adoptPng("candidate_png", candidate.pngDataUrl, candidate)}
              />
            ))}
          </div>
          </div>
          <div className="studio-icon-preview-row">
            {normalizedIcon?.candidatePngDataUrl ? <img className="studio-icon-preview primary-icon-preview" src={normalizedIcon.candidatePngDataUrl} alt={primaryPreviewLabel} /> : null}
            {normalizedIcon?.finalPngDataUrl ? <img className="studio-icon-preview" src={normalizedIcon.finalPngDataUrl} alt="ToolHub共通default icon" /> : null}
          </div>
          <div className="studio-action-row">
            <span className="admin-status-pill">採用中: {iconSourceLabel(selected)}</span>
            <button className="secondary-button" type="button" onClick={() => adoptPng("candidate_png", normalizedIcon?.candidatePngDataUrl)} disabled={!normalizedIcon?.canAdoptPrimaryPng}>
              <CheckCircle2 size={17} aria-hidden="true" />
              このPNGを採用
            </button>
            <button className="secondary-button" type="button" onClick={resetToDefaultIcon}>
              <CheckCircle2 size={17} aria-hidden="true" />
              共通アイコンに戻す
            </button>
          </div>
          <p className="admin-muted">PNGが標準アイコンです。AI候補を採用していない場合は ToolHub 共通 default icon が final_app/icon.png に使われます。</p>
          {normalizedIcon?.candidateUrl ? <p className="admin-muted">PNG URL候補: {normalizedIcon.candidateUrl}</p> : null}
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

function ImageApiBlockedNotice({ result }: { result: StoredImageGenerationTestResult }) {
  const guidance = imageApiFailureGuidance(result);
  return (
    <div className="studio-image-api-blocker" role="alert">
      <strong>画像APIテストが失敗しています。AI画像候補と再生成は利用できない状態です。</strong>
      <p>{guidance}</p>
      <p>この状態ではAI画像候補は作成されず、未採用時はToolHub共通default iconが使われます。スタイル指定の効果はAPI生成候補が1件以上ある場合だけ確認できます。</p>
    </div>
  );
}

function MetadataFallbackSuppressed({ metadata }: { metadata: AppStudioAiProposal["metadata"] }) {
  const status = metadata.aiStatus ? statusValue(metadata.aiStatus) : "未実行";
  return (
    <>
      <dt>提案状態</dt>
      <dd>
        状態: {status}。メタデータAIが完了していないため、fallback metadata はAI提案として表示していません。
        {metadata.aiFallbackReason ? ` 理由: ${metadata.aiFallbackReason}` : ""}
      </dd>
    </>
  );
}

function IconFunctionInterpretationPanel({ interpretation }: { interpretation?: AppStudioAiProposal["icon"]["functionInterpretation"] | null }) {
  if (!interpretation) {
    return null;
  }
  const primaryAction = interpretation.primaryAction ?? interpretation.primary_action;
  const inputObjects = interpretation.inputObjects ?? interpretation.input_objects ?? [];
  const outputObjects = interpretation.outputObjects ?? interpretation.output_objects ?? [];
  const actionFlow = interpretation.actionFlow ?? interpretation.action_flow;
  const compositionTemplate = interpretation.compositionTemplate ?? interpretation.composition_template;
  const avoidGeneric = interpretation.avoidGeneric ?? interpretation.avoid_generic ?? [];
  const appKind = interpretation.appKind ?? interpretation.app_kind;
  const allRows: Array<[string, string | undefined]> = [
    ["主機能", primaryAction],
    ["入力", inputObjects.join(", ")],
    ["出力", outputObjects.join(", ")],
    ["推定フロー", actionFlow],
    ["推奨構図", compositionTemplate],
    ["避ける表現", avoidGeneric.slice(0, 5).join(", ")],
  ];
  const rows = allRows.filter((row): row is [string, string] => Boolean(row[1]));
  if (!rows.length) {
    return null;
  }
  return (
    <div className="studio-icon-interpretation">
      <div>
        <p className="dialog-kicker">AIが理解した機能</p>
        <strong>{appKind || "アプリ機能の解釈"}</strong>
      </div>
      <dl>
        {rows.map(([label, value]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

function ImageApiSummaryPanel({ normalized }: { normalized: NormalizedIconProposal | null }) {
  if (!normalized) {
    return null;
  }
  const { diagnosis } = normalized;
  const apiCount = diagnosis.apiCandidateCount;
  const modelRaw = diagnosis.modelRaw;
  const model = diagnosis.modelLabel;
  const latestFailure = diagnosis.latestFailure;
  const failureClass = diagnosis.failureClass;
  const failureCategory = diagnosis.failureCategory;
  const failureMessage = diagnosis.failureMessage;
  const adminNextAction = diagnosis.adminNextAction;
  const defaultIconUsed = normalized.defaultIcon.used;
  const defaultIconReason = normalized.defaultIcon.reason;
  const organizationBlocked = isOrganizationVerificationRequired({
    model: modelRaw || model,
    errorCategory: failureClass || failureCategory,
    fallbackReason: latestFailure,
    message: failureMessage || latestFailure,
  });
  return (
    <div className={`studio-image-api-summary${apiCount > 0 ? " ok" : " warn"}`}>
      <div><span>API候補</span><strong>{apiCount}</strong></div>
      <div><span>画像モデル</span><strong>{model}</strong></div>
      <div><span>現在のアイコン</span><strong>{normalized.currentSourceLabel}</strong></div>
      {diagnosis.stylePreset ? <div><span>スタイル</span><strong>{diagnosis.stylePreset}</strong></div> : null}
      {diagnosis.revisionMode ? <div><span>再生成モード</span><strong>{diagnosis.revisionMode}</strong></div> : null}
      {diagnosis.imageQualityMode ? <div><span>生成品質設定</span><strong>{diagnosis.imageQualityMode}</strong></div> : null}
      {diagnosis.imageApiSeconds !== null ? <div><span>API秒数</span><strong>{diagnosis.imageApiSeconds.toFixed(1)}秒</strong></div> : null}
      {diagnosis.proposalReloadSeconds !== null ? <div><span>再読込</span><strong>{diagnosis.proposalReloadSeconds.toFixed(2)}秒</strong></div> : null}
      {failureCategory ? <div><span>error_category</span><strong>{failureCategory}</strong></div> : null}
      {apiCount === 0 ? (
        <div className="wide studio-icon-ai-failure">
          <strong>AI画像生成に失敗しました</strong>
          <p>理由: {failureMessage || "API画像候補が保存されませんでした。"}</p>
          <p>次アクション: {adminNextAction || imageApiFailureGuidance({ model: modelRaw || model, errorCategory: failureClass, fallbackReason: latestFailure, message: failureMessage })}</p>
          <p>現在のアイコン: ToolHub共通default icon</p>
        </div>
      ) : null}
      {failureClass ? <div><span>failure_class</span><strong>{failureClass}</strong></div> : null}
      {diagnosis.packageSecretScanStatus ? <div><span>package secret</span><strong>{secretStatusLabel(diagnosis.packageSecretScanStatus)}</strong></div> : null}
      {diagnosis.payloadSecretScanStatus ? <div><span>AI payload secret</span><strong>{secretStatusLabel(diagnosis.payloadSecretScanStatus)}</strong></div> : null}
      {diagnosis.aiSubmissionBlocked ? <div className="wide"><span>AI送信停止理由</span><strong>{diagnosis.aiSubmissionBlockReason || "secret scan によりAI送信を停止しました。"}</strong></div> : null}
      {defaultIconUsed ? <div className="wide"><span>default icon</span><strong>{defaultIconReason || "未採用時の共通アイコンを使用中です。"}</strong></div> : null}
      {latestFailure ? <div className="wide"><span>直近の失敗理由</span><strong>{latestFailure}</strong></div> : null}
      {organizationBlocked ? <div className="wide"><span>案内</span><strong>{model} は現在のOpenAI組織では利用できません。組織認証を完了するか、別のImage modelを設定してください。</strong></div> : null}
      {apiCount === 0 ? <div className="wide"><span>スタイル</span><strong>API生成候補がないため、スタイル指定の効果は検証できません。</strong></div> : null}
    </div>
  );
}

function IconCandidateCard({ candidate, adopted, onAdopt }: { candidate: AppStudioAiIconCandidate; adopted: boolean; onAdopt: () => void }) {
  const reasons = candidate.qualityReasons ?? [];
  const warnings = candidate.qualityWarnings ?? [];
  const conceptSummary = candidateConceptSummary(candidate);
  return (
    <article className={`studio-icon-candidate-card${adopted ? " selected" : ""}`}>
      <div className="studio-icon-candidate-head">
        <strong>候補 {candidate.number || candidate.candidateId}</strong>
        <span className="admin-status-pill">{candidateSourceLabel(candidate.source)}</span>
      </div>
      {candidate.pngDataUrl ? (
        <img className="studio-icon-preview primary-icon-preview" src={candidate.pngDataUrl} alt={`PNGアイコン候補 ${candidate.number}`} />
      ) : (
        <div className="studio-icon-empty">PNGなし</div>
      )}
      <div className="studio-icon-candidate-meta">
        <span>model: {displayModelName(candidate.model)}</span>
        <span>resolution: {candidate.resolution || "unknown"}</span>
        <span>status: {statusValue(candidate.status || "unknown")}</span>
        {candidate.api ? <span>api: {candidate.api}</span> : null}
        {candidate.contentType ? <span>content: {candidate.contentType}</span> : null}
        {candidate.fallbackReason ? <span>reason: {candidate.fallbackReason}</span> : null}
        {candidate.conceptId ? <span>concept: {candidate.conceptId}</span> : null}
        {adopted ? <span>採用中</span> : null}
      </div>
      {reasons.length || warnings.length || candidate.imageEvaluationNote ? (
        <details className="studio-icon-candidate-quality">
          <summary>参考情報</summary>
          <p>画像ピクセルの本格評価ではなく、Prompt・メタデータ・PNG簡易チェックに基づく参考情報です。</p>
          {reasons.length ? <p>参考理由: {reasons.slice(0, 3).join(" / ")}</p> : null}
          {warnings.length ? <p>注意: {warnings.slice(0, 4).join(" / ")}</p> : null}
          {candidate.imageEvaluationNote ? <p>{candidate.imageEvaluationNote}</p> : null}
        </details>
      ) : null}
      {conceptSummary ? <p className="admin-muted">{conceptSummary}</p> : null}
      {candidate.prompt ? (
        <details className="studio-icon-candidate-prompt">
          <summary>最終画像API Prompt</summary>
          <pre>{candidate.prompt}</pre>
        </details>
      ) : null}
      <button className="secondary-button" type="button" onClick={onAdopt} disabled={!candidate.pngDataUrl}>
        <CheckCircle2 size={17} aria-hidden="true" />
        このAI候補を採用
      </button>
    </article>
  );
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
      <StatusItem label="App Studio CLI" value={diagnostics.appStudioCliExists ? "利用可能" : "見つかりません"} />
      <StatusItem label="CLIパス" value={diagnostics.appStudioCliPath || "未確認"} />
      <StatusItem label="CLI診断" value={diagnosticMessage(diagnostics.appStudioCliMessage)} />
      <StatusItem label="診断メッセージ" value={diagnosticMessage(diagnostics.message)} />
    </div>
  );
}

function ImageApiTestDiagnostics({ result }: { result: StoredImageGenerationTestResult | null }) {
  const status = result ? (result.ok ? "成功" : "失敗") : "未確認";
  const failureClass = result?.errorCategory || "未確認";
  const checkedAt = result?.checkedAt ? formatCheckedAt(result.checkedAt) : "未確認";
  return (
    <div className="studio-ai-status-grid">
      <StatusItem label="画像APIテスト" value={status} />
      <StatusItem label="直近failure class" value={failureClass} />
      <StatusItem label="最終テスト日時" value={checkedAt} />
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
    parse_fallback_reason: "理由",
    deterministic_reason: "理由",
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
    return "API未実行（代替処理）";
  }
  if (value === "skipped") {
    return "スキップ";
  }
  if (value === "failed") {
    return "失敗";
  }
  if (value === "not_attempted") {
    return "未実行";
  }
  return value;
}

function secretStatusLabel(status: string): string {
  if (status === "passed") {
    return "問題なし";
  }
  if (status === "blocked") {
    return "ブロック";
  }
  if (status === "warning") {
    return "警告あり";
  }
  if (status === "not_run") {
    return "未実行";
  }
  if (status === "not_recorded") {
    return "記録なし";
  }
  return status;
}

function formatCheckedAt(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString("ja-JP");
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
    return "AI機能は無効です。未採用時はToolHub共通default iconで続行できます。";
  }
  return message;
}

