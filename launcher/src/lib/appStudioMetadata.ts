import type { AppStudioAiMetadataSuggestion, AppStudioEditableMetadata, AppStudioIconOverride } from "./appStudioTypes";

export const EMPTY_APP_STUDIO_METADATA: AppStudioEditableMetadata = {
  shortDescription: "",
  description: "",
  categories: [],
  keywords: [],
  examples: [],
  useCases: [],
  inputs: [],
  outputs: [],
  notes: [],
  releaseNotes: [],
  changeSummary: "",
};

export function createEmptyAppStudioMetadata(): AppStudioEditableMetadata {
  return {
    shortDescription: "",
    description: "",
    categories: [],
    keywords: [],
    examples: [],
    useCases: [],
    inputs: [],
    outputs: [],
    notes: [],
    releaseNotes: [],
    changeSummary: "",
  };
}

export function metadataFromSuggestion(suggestion: AppStudioAiMetadataSuggestion): AppStudioEditableMetadata {
  return cleanEditableMetadata({
    shortDescription: suggestion.shortDescription ?? "",
    description: suggestion.description ?? "",
    categories: suggestion.categories,
    keywords: suggestion.keywords,
    examples: suggestion.examples,
    useCases: suggestion.useCases,
    inputs: suggestion.inputs,
    outputs: suggestion.outputs,
    notes: suggestion.notes,
    releaseNotes: suggestion.releaseNotes,
    changeSummary: suggestion.changeSummary ?? "",
  }) ?? createEmptyAppStudioMetadata();
}

export function cleanEditableMetadata(metadata?: AppStudioEditableMetadata): AppStudioEditableMetadata | undefined {
  if (!metadata) {
    return undefined;
  }
  const cleaned: AppStudioEditableMetadata = {
    shortDescription: cleanString(metadata.shortDescription),
    description: cleanString(metadata.description),
    categories: cleanList(metadata.categories),
    keywords: cleanList(metadata.keywords),
    examples: cleanList(metadata.examples),
    useCases: cleanList(metadata.useCases),
    inputs: cleanList(metadata.inputs),
    outputs: cleanList(metadata.outputs),
    notes: cleanList(metadata.notes),
    releaseNotes: cleanList(metadata.releaseNotes),
    changeSummary: cleanString(metadata.changeSummary),
  };
  return hasEditableMetadata(cleaned) ? cleaned : undefined;
}

export function hasEditableMetadata(metadata?: AppStudioEditableMetadata): boolean {
  if (!metadata) {
    return false;
  }
  return Boolean(
    cleanString(metadata.shortDescription) ||
      cleanString(metadata.description) ||
      cleanString(metadata.changeSummary) ||
      cleanList(metadata.categories).length ||
      cleanList(metadata.keywords).length ||
      cleanList(metadata.examples).length ||
      cleanList(metadata.useCases).length ||
      cleanList(metadata.inputs).length ||
      cleanList(metadata.outputs).length ||
      cleanList(metadata.notes).length ||
      cleanList(metadata.releaseNotes).length,
  );
}

export function splitMetadataText(value: string): string[] {
  const seen = new Set<string>();
  const items: string[] = [];
  for (const raw of value.split(/[\n,]/)) {
    const item = raw.trim();
    if (!item || seen.has(item)) {
      continue;
    }
    seen.add(item);
    items.push(item);
  }
  return items;
}

export function joinMetadataList(value?: string[]): string {
  return cleanList(value).join("\n");
}

export function cleanList(value?: string[]): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  const seen = new Set<string>();
  const cleaned: string[] = [];
  for (const item of value) {
    const text = String(item).trim();
    if (!text || seen.has(text)) {
      continue;
    }
    seen.add(text);
    cleaned.push(text);
  }
  return cleaned;
}

export function cleanString(value?: string | null): string {
  return String(value ?? "").trim();
}

export function cleanIconOverride(iconOverride?: AppStudioIconOverride): AppStudioIconOverride | undefined {
  if (!iconOverride || iconOverride.selectedIconSource === "fallback_png" || iconOverride.selectedIconSource === "default_icon") {
    return undefined;
  }
  if (
    iconOverride.selectedIconSource !== "candidate_png" &&
    iconOverride.selectedIconSource !== "final_png" &&
    iconOverride.selectedIconSource !== "ai_candidate_png" &&
    iconOverride.selectedIconSource !== "uploaded_png"
  ) {
    return undefined;
  }
  const pngDataUrl = cleanString(iconOverride.pngDataUrl);
  if (!pngDataUrl.startsWith("data:image/png;base64,")) {
    return undefined;
  }
  return {
    selectedIconSource: iconOverride.selectedIconSource,
    pngDataUrl,
    candidateId: cleanString(iconOverride.candidateId) || undefined,
    sourcePrompt: cleanString(iconOverride.sourcePrompt) || undefined,
  };
}
