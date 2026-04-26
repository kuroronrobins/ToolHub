import { useState } from "react";
import { Bot, CheckCircle2, RefreshCw } from "lucide-react";
import { appStudioReadAiProposal } from "../../../lib/appStudioApi";
import type { AppStudioAiProposal, AppStudioIconOverride, AppStudioRunResult, AppStudioSelectedIconSource } from "../../../lib/appStudioTypes";
import { formatAdminError } from "../adminUi";

interface Props {
  appId?: string;
  outputDir?: string | null;
  result: AppStudioRunResult | null;
  busy: boolean;
  onGenerate: () => Promise<AppStudioRunResult | null>;
  onAdopt: (values: { name?: string; iconPrompt?: string }) => void;
  onIconAdopt: (iconOverride: AppStudioIconOverride) => void;
  selectedIconSource?: AppStudioSelectedIconSource;
  onProposalLoaded?: (proposal: AppStudioAiProposal) => void;
}

export function AppStudioAiProposalPanel({ appId, outputDir, result, busy, onGenerate, onAdopt, onIconAdopt, selectedIconSource, onProposalLoaded }: Props) {
  const [proposal, setProposal] = useState<AppStudioAiProposal | null>(null);
  const [localSelectedIconSource, setLocalSelectedIconSource] = useState<AppStudioSelectedIconSource>("fallback_png");
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function loadProposal(sourceResult: AppStudioRunResult | null = result) {
    setLoading(true);
    setError("");
    setMessage("");
    try {
      const loaded = await appStudioReadAiProposal(sourceResult?.appId ?? appId, sourceResult?.outputDir ?? outputDir ?? undefined);
      setProposal(loaded);
      onProposalLoaded?.(loaded);
      setMessage(loaded.ok ? "AI提案を読み込みました。" : "提案ファイルがまだ不足しています。Suggestを実行してください。");
    } catch (loadError) {
      setError(formatAdminError(loadError, "AI提案を読み込めませんでした。"));
    } finally {
      setLoading(false);
    }
  }

  async function generateProposal() {
    setLoading(true);
    setError("");
    setMessage("");
    try {
      const generated = await onGenerate();
      if (generated) {
        await loadProposal(generated);
      }
    } catch (generateError) {
      setError(formatAdminError(generateError, "AI提案を生成できませんでした。"));
    } finally {
      setLoading(false);
    }
  }

  const metadata = proposal?.metadata;
  const icon = proposal?.icon;
  const selected = selectedIconSource ?? localSelectedIconSource;

  function adoptPng(source: "candidate_png" | "final_png", pngDataUrl?: string | null) {
    if (!pngDataUrl) {
      return;
    }
    setLocalSelectedIconSource(source);
    onIconAdopt({ selectedIconSource: source, pngDataUrl });
    setMessage("PNG icon candidate was selected. Review it before Apply.");
  }

  function adoptFallbackPng() {
    setLocalSelectedIconSource("fallback_png");
    onIconAdopt({ selectedIconSource: "fallback_png" });
    setMessage("Fallback PNG was selected. Apply will use the local fallback icon.");
  }

  return (
    <section className="studio-step">
      <div>
        <span className="studio-step-index">AI</span>
        <h4>AI metadata and icon proposal</h4>
      </div>
      <p className="admin-muted">
        Suggestで生成される proposed_app.yaml と icon_work を読み込みます。AI提案は自動反映せず、採用ボタンを押した項目だけGUI入力へ反映します。
      </p>
      <div className="studio-action-row">
        <button className="secondary-button" type="button" onClick={() => void loadProposal()} disabled={busy || loading}>
          <RefreshCw size={17} aria-hidden="true" />
          提案を読み込み
        </button>
        <button className="secondary-button" type="button" onClick={() => void generateProposal()} disabled={busy || loading}>
          <Bot size={17} aria-hidden="true" />
          AI提案を生成
        </button>
      </div>

      {metadata ? (
        <div className="studio-ai-card">
          <div className="admin-section-head">
            <div>
              <p className="dialog-kicker">Metadata</p>
              <h4>{metadata.name || metadata.appId || "Proposed metadata"}</h4>
            </div>
            <button
              className="secondary-button"
              type="button"
              onClick={() => onAdopt({ name: metadata.name ?? undefined, iconPrompt: metadata.iconPrompt ?? undefined })}
            >
              <CheckCircle2 size={17} aria-hidden="true" />
              表示名/Prompt採用
            </button>
          </div>
          <dl className="studio-ai-fields">
            <Field label="short_description" value={metadata.shortDescription} />
            <Field label="description" value={metadata.description} />
            <Field label="categories" value={metadata.categories.join(", ")} />
            <Field label="keywords" value={metadata.keywords.join(", ")} />
            <Field label="examples" value={metadata.examples.join(" / ")} />
            <Field label="use_cases" value={metadata.useCases.join(" / ")} />
            <Field label="inputs" value={metadata.inputs.join(", ")} />
            <Field label="outputs" value={metadata.outputs.join(", ")} />
            <Field label="notes" value={metadata.notes.join(" / ")} />
            <Field label="release_notes" value={metadata.releaseNotes.join(" / ")} />
            <Field label="change_summary" value={metadata.changeSummary} />
          </dl>
        </div>
      ) : null}

      {icon ? (
        <div className="studio-ai-card">
          <div className="admin-section-head">
            <div>
              <p className="dialog-kicker">Icon</p>
              <h4>Icon candidates</h4>
            </div>
            <button className="secondary-button" type="button" onClick={() => onAdopt({ iconPrompt: icon.promptRevision || icon.promptInitial || undefined })}>
              <CheckCircle2 size={17} aria-hidden="true" />
              Prompt採用
            </button>
          </div>
          <div className="studio-icon-preview-row">
            {icon.candidatePngDataUrl ? <img className="studio-icon-preview primary-icon-preview" src={icon.candidatePngDataUrl} alt="AI PNG icon candidate" /> : null}
            {icon.finalPngDataUrl ? <img className="studio-icon-preview" src={icon.finalPngDataUrl} alt="Fallback PNG icon" /> : null}
          </div>
          <div className="studio-action-row">
            <span className="admin-status-pill">selected: {selected}</span>
            <button className="secondary-button" type="button" onClick={() => adoptPng("candidate_png", icon.candidatePngDataUrl)} disabled={!icon.candidatePngDataUrl}>
              <CheckCircle2 size={17} aria-hidden="true" />
              Use PNG candidate
            </button>
            <button className="secondary-button" type="button" onClick={() => adoptPng("final_png", icon.finalPngDataUrl)} disabled={!icon.finalPngDataUrl}>
              <CheckCircle2 size={17} aria-hidden="true" />
              Use fallback PNG
            </button>
            <button className="secondary-button" type="button" onClick={adoptFallbackPng}>
              <CheckCircle2 size={17} aria-hidden="true" />
              Clear PNG adoption
            </button>
          </div>
          <p className="admin-muted">PNG is the standard icon output. API PNG candidates are not used until you adopt one and run Apply.</p>
          {icon.candidateUrl ? <p className="admin-muted">PNG URL candidate: {icon.candidateUrl}</p> : null}
          {icon.fallbackSvg ? (
            <div className="studio-icon-fallback">
              <p className="dialog-kicker">SVG fallback</p>
              <IconSvg title="fallback svg" svg={icon.fallbackSvg} />
            </div>
          ) : null}
          <dl className="studio-ai-fields">
            <Field label="initial_prompt" value={icon.promptInitial} />
            <Field label="revision_prompt" value={icon.promptRevision} />
            <Field label="ai_report" value={icon.aiReport} />
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
