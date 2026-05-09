import type {
  AppStudioAiIconCandidate,
  AppStudioAiIconSuggestion,
  AppStudioAiProposal,
  AppStudioIconOverride,
  AppStudioSelectedIconSource,
} from "./appStudioTypes";

const LEGACY_FALLBACK_ICON_SOURCES = new Set(["fallback_png", "provisional_fallback_png"]);
const ADOPTABLE_ICON_SOURCES = new Set(["candidate_png", "final_png", "ai_candidate_png", "uploaded_png"]);

export interface NormalizedIconDiagnosis {
  apiCandidateCount: number;
  modelRaw: string;
  modelLabel: string;
  latestFailure: string;
  failureCategory: string;
  failureClass: string;
  failureMessage: string;
  adminNextAction: string;
  packageSecretScanStatus: string;
  payloadSecretScanStatus: string;
  aiSubmissionBlocked: boolean;
  aiSubmissionBlockReason: string;
  stylePreset: string;
  revisionMode: string;
  imageQualityMode: string;
  imageApiSeconds: number | null;
  proposalReloadSeconds: number | null;
}

export interface NormalizedDefaultIconState {
  used: boolean;
  reason: string;
  finalPngDataUrl?: string | null;
}

export interface NormalizedIconRevisionPromptInfo {
  userRevisionInstruction: string;
  finalImageApiPrompt: string;
}

export interface NormalizedIconProposal {
  currentSource: AppStudioSelectedIconSource | "unknown";
  currentSourceLabel: string;
  allCandidates: AppStudioAiIconCandidate[];
  apiCandidates: AppStudioAiIconCandidate[];
  legacyCandidates: AppStudioAiIconCandidate[];
  hiddenLegacyCount: number;
  candidatePngDataUrl?: string | null;
  finalPngDataUrl?: string | null;
  candidateUrl?: string | null;
  primaryPreviewLabel: string;
  hasAdoptableApiCandidates: boolean;
  canAdoptPrimaryPng: boolean;
  defaultIcon: NormalizedDefaultIconState;
  diagnosis: NormalizedIconDiagnosis;
  revisionPromptInfo: NormalizedIconRevisionPromptInfo;
}

export function normalizeAppStudioIconProposal(
  icon?: AppStudioAiIconSuggestion | null,
  selectedSource?: string | null,
): NormalizedIconProposal {
  const candidates = sortIconCandidates(rawCandidates(icon).map(normalizeIconCandidate));
  const apiCandidates = candidates.filter(isVisibleApiCandidate);
  const legacyCandidates = candidates.filter(isLegacyFallbackCandidate);
  const summary = icon?.imageApiSummary;
  const summaryApiCount = summaryNumberValue(summary?.apiCandidateCount ?? summary?.api_candidate_count);
  const apiCandidateCount = summaryApiCount ?? apiCandidates.length;
  const latestFailure = latestFailureReason(summary, candidates);
  const failureCategory = latestCandidateValue(candidates, "errorCategory");
  const failureClass = summaryStringValue(summary?.failureClass ?? summary?.failure_class) || failureCategory;
  const failureMessage = summaryStringValue(summary?.failureMessage ?? summary?.failure_message) || latestFailure;
  const currentSource = normalizeIconSource(selectedSource || summaryStringValue(summary?.selectedIconSource ?? summary?.selected_icon_source));
  const defaultIconUsed = Boolean(summary?.defaultIconUsed ?? summary?.default_icon_used ?? currentSource === "default_icon");
  const modelRaw =
    summaryStringValue(summary?.model) ||
    apiCandidates.find((candidate) => candidate.model && !isInternalPlaceholderModel(candidate.model))?.model ||
    "";
  const diagnosis: NormalizedIconDiagnosis = {
    apiCandidateCount,
    modelRaw,
    modelLabel: displayModelName(modelRaw),
    latestFailure,
    failureCategory,
    failureClass,
    failureMessage,
    adminNextAction: summaryStringValue(summary?.adminNextAction ?? summary?.admin_next_action),
    packageSecretScanStatus: summaryStringValue(summary?.packageSecretScanStatus ?? summary?.package_secret_scan_status),
    payloadSecretScanStatus: summaryStringValue(summary?.aiPayloadSecretScanStatus ?? summary?.ai_payload_secret_scan_status),
    aiSubmissionBlocked: Boolean(summary?.aiSubmissionBlocked ?? summary?.ai_submission_blocked),
    aiSubmissionBlockReason: summaryStringValue(summary?.aiSubmissionBlockReason ?? summary?.ai_submission_block_reason),
    stylePreset: summaryStringValue(summary?.stylePreset ?? summary?.style_preset),
    revisionMode: summaryStringValue(summary?.revisionMode ?? summary?.revision_mode),
    imageQualityMode: summaryStringValue(summary?.imageQualityMode ?? summary?.image_quality_mode),
    imageApiSeconds: summaryNumberValue(summary?.imageApiSeconds ?? summary?.image_api_seconds),
    proposalReloadSeconds: summaryNumberValue(summary?.proposalReloadSeconds ?? summary?.proposal_reload_seconds),
  };
  return {
    currentSource,
    currentSourceLabel: iconSourceLabel(currentSource),
    allCandidates: candidates,
    apiCandidates,
    legacyCandidates,
    hiddenLegacyCount: legacyCandidates.length,
    candidatePngDataUrl: icon?.candidatePngDataUrl ?? null,
    finalPngDataUrl: icon?.finalPngDataUrl ?? null,
    candidateUrl: icon?.candidateUrl ?? null,
    primaryPreviewLabel: apiCandidates.length ? "AI PNGアイコン候補" : "ToolHub共通default icon",
    hasAdoptableApiCandidates: apiCandidates.some((candidate) => Boolean(candidate.pngDataUrl)),
    canAdoptPrimaryPng: apiCandidates.length > 0 && Boolean(icon?.candidatePngDataUrl),
    defaultIcon: {
      used: defaultIconUsed,
      reason: summaryStringValue(summary?.defaultIconReason ?? summary?.default_icon_reason),
      finalPngDataUrl: icon?.finalPngDataUrl ?? null,
    },
    diagnosis,
    revisionPromptInfo: {
      userRevisionInstruction: summaryStringValue(summary?.userRevisionInstruction ?? summary?.user_revision_instruction),
      finalImageApiPrompt: summaryStringValue(summary?.finalImageApiPrompt ?? summary?.final_image_api_prompt),
    },
  };
}

export function apiIconCandidatesForProposal(proposal: AppStudioAiProposal | null): AppStudioAiIconCandidate[] {
  return normalizeAppStudioIconProposal(proposal?.icon).apiCandidates;
}

export function selectedIconCandidateForProposal(proposal: AppStudioAiProposal | null, candidateId: string): AppStudioAiIconCandidate | null {
  const candidates = apiIconCandidatesForProposal(proposal);
  return candidates.find((candidate) => candidate.candidateId === candidateId) ?? candidates[0] ?? null;
}

export function previewIconDataUrl(iconOverride?: AppStudioIconOverride, proposal?: AppStudioAiProposal | null): string | null {
  if (iconOverride?.pngDataUrl && ADOPTABLE_ICON_SOURCES.has(iconOverride.selectedIconSource)) {
    return iconOverride.pngDataUrl;
  }
  return normalizeAppStudioIconProposal(proposal?.icon, iconOverride?.selectedIconSource).defaultIcon.finalPngDataUrl ?? null;
}

export function normalizeIconSource(source?: string | null): AppStudioSelectedIconSource | "unknown" {
  const value = summaryStringValue(source);
  if (LEGACY_FALLBACK_ICON_SOURCES.has(value) || value === "" || value === "default_icon") {
    return "default_icon";
  }
  if (value === "candidate_png" || value === "final_png" || value === "ai_candidate_png" || value === "uploaded_png") {
    return value;
  }
  return "unknown";
}

export function iconSourceLabel(source?: string | null): string {
  const normalized = normalizeIconSource(source);
  if (normalized === "candidate_png" || normalized === "ai_candidate_png") {
    return "AI PNG候補";
  }
  if (normalized === "uploaded_png") {
    return "アップロードPNG";
  }
  if (normalized === "default_icon") {
    return "ToolHub共通default icon";
  }
  if (normalized === "final_png") {
    return "PNG選択済み";
  }
  return "未採用";
}

export function candidateSourceLabel(source?: string | null): string {
  const value = summaryStringValue(source);
  if (value === "api_generate") {
    return "API";
  }
  if (value === "api_edit") {
    return "API edit";
  }
  if (value === "legacy") {
    return "旧互換候補";
  }
  if (value.includes("fallback")) {
    return "旧互換候補";
  }
  if (value === "api") {
    return "API生成";
  }
  return value || "unknown";
}

export function candidateConceptSummary(candidate: AppStudioAiIconCandidate): string {
  const concept = candidate.concept as Record<string, unknown> | null | undefined;
  if (!concept) {
    return "";
  }
  const direction = summaryStringValue(concept.direction) || candidate.conceptId || "";
  const composition = summaryStringValue(concept.composition);
  const whySpecific = summaryStringValue(concept.why_specific) || summaryStringValue(concept.whySpecific);
  return [direction, composition, whySpecific].filter(Boolean).join(" / ");
}

export function summaryStringValue(value: unknown): string {
  return typeof value === "string" ? value : "";
}

export function summaryNumberValue(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

export function isInternalPlaceholderModel(value?: string | null): boolean {
  return value === "local-deterministic-fallback" || value === "deterministic-text-prompt-fallback" || value === "image-model-not-configured";
}

export function displayModelName(value?: string | null): string {
  if (!value || isInternalPlaceholderModel(value)) {
    return "未設定";
  }
  return value;
}

function rawCandidates(icon?: AppStudioAiIconSuggestion | null): AppStudioAiIconCandidate[] {
  if (!icon) {
    return [];
  }
  if (Array.isArray(icon.candidates) && icon.candidates.length) {
    return icon.candidates;
  }
  if (icon.candidatePngDataUrl || icon.candidateUrl) {
    return [
      {
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
      },
    ];
  }
  return [];
}

function normalizeIconCandidate(candidate: AppStudioAiIconCandidate): AppStudioAiIconCandidate {
  const source = summaryStringValue(candidate.source);
  const legacyFallback = source.includes("fallback") || candidate.fallback;
  return {
    ...candidate,
    fallback: legacyFallback,
    scoreBasis: normalizeScoreBasis(candidate.scoreBasis),
    imageEvaluationStatus: normalizeImageEvaluationStatus(candidate.imageEvaluationStatus),
  };
}

function sortIconCandidates(candidates: AppStudioAiIconCandidate[]): AppStudioAiIconCandidate[] {
  return [...candidates].sort((left, right) => {
    if (left.fallback !== right.fallback) {
      return left.fallback ? 1 : -1;
    }
    return (left.number || 0) - (right.number || 0);
  });
}

function isVisibleApiCandidate(candidate: AppStudioAiIconCandidate): boolean {
  return !isLegacyFallbackCandidate(candidate) && Boolean(candidate.source?.startsWith("api") || candidate.source === "legacy");
}

function isLegacyFallbackCandidate(candidate: AppStudioAiIconCandidate): boolean {
  return Boolean(candidate.fallback || candidate.source?.includes("fallback"));
}

function normalizeScoreBasis(value?: string | null): string | null | undefined {
  if (value === "prompt_concept_only") {
    return "rule_based_prompt_and_manifest";
  }
  return value;
}

function normalizeImageEvaluationStatus(value?: string | null): string | null | undefined {
  if (value === "fallback_rule_based") {
    return "deterministic_png_check";
  }
  return value;
}

function latestFailureReason(summary: AppStudioAiIconSuggestion["imageApiSummary"] | undefined | null, candidates: AppStudioAiIconCandidate[]): string {
  const summaryFailure = summaryStringValue(summary?.latestImageApiFailure ?? summary?.latest_image_api_failure);
  if (summaryFailure) {
    return summaryFailure;
  }
  const reasons = candidates.map((candidate) => candidate.fallbackReason || "").filter(Boolean);
  return reasons[reasons.length - 1] || "";
}

function latestCandidateValue(candidates: AppStudioAiIconCandidate[], key: keyof AppStudioAiIconCandidate): string {
  const values = candidates.map((candidate) => summaryStringValue(candidate[key])).filter(Boolean);
  return values[values.length - 1] || "";
}
