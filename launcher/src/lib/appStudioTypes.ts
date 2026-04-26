export type AppStudioBuildMode = "auto" | "app-env" | "frozen-folder" | "existing-exe";

export interface AppStudioImportRequest {
  entry: string;
  appId?: string;
  name?: string;
  version?: string;
  buildMode: AppStudioBuildMode;
  iconPrompt?: string;
  metadata?: AppStudioEditableMetadata;
  iconOverride?: AppStudioIconOverride;
  createAppEnv: boolean;
  rebuildAppEnv: boolean;
  generateLock: boolean;
  buildFrozenFolder: boolean;
  verifyRuntime: boolean;
}

export interface AppStudioUpdateRequest {
  appId: string;
  entry: string;
  name?: string;
  currentVersion?: string;
  newVersion: string;
  buildMode: AppStudioBuildMode;
  iconPrompt?: string;
  metadata?: AppStudioEditableMetadata;
  iconOverride?: AppStudioIconOverride;
  createAppEnv: boolean;
  rebuildAppEnv: boolean;
  generateLock: boolean;
  buildFrozenFolder: boolean;
  verifyRuntime: boolean;
}

export interface AppStudioRegisteredApp {
  appId: string;
  name: string;
  version: string;
  enabled: boolean;
  buildMode?: string | null;
  runner?: string | null;
  entry?: string | null;
  description?: string | null;
  warning?: string | null;
}

export interface AppStudioRunResult {
  ok: boolean;
  exitCode: number;
  stdout: string;
  stderr: string;
  userMessage: string;
  outputDir?: string | null;
  appId?: string | null;
  selectedBuildMode?: string | null;
  executionStatus?: "pass" | "warn" | "fail" | "unknown" | string | null;
  approvalAllowed?: boolean | null;
  runtimeStatus?: "pass" | "warn" | "fail" | "unknown" | string | null;
  appPack?: string | null;
  enabled?: boolean | null;
  currentVersion?: string | null;
  newVersion?: string | null;
  metadataOverrideUsed?: boolean;
  metadataOverrideKeys?: string[];
  iconOverrideUsed?: boolean;
  selectedIconSource?: AppStudioSelectedIconSource | string | null;
}

export interface AppStudioPreflightResult {
  ok: boolean;
  entryExists: boolean;
  appIdValid: boolean;
  buildModeValid: boolean;
  pythonSource: "runtime" | "python" | "py" | "missing" | string;
  pythonPath?: string | null;
  runtimePythonExists: boolean;
  warnings: string[];
  errors: string[];
}

export interface AppStudioResultSummary {
  appId?: string | null;
  outputDir?: string | null;
  selectedBuildMode?: string | null;
  executionStatus?: string | null;
  approvalAllowed?: boolean | null;
  runtimeStatus?: string | null;
  appPack?: string | null;
  enabled?: boolean | null;
  version?: string | null;
  metadataOverrideUsed?: boolean;
  metadataOverrideKeys?: string[];
  iconOverrideUsed?: boolean;
  selectedIconSource?: AppStudioSelectedIconSource | string | null;
}

export interface AppStudioEditableMetadata {
  shortDescription?: string;
  description?: string;
  categories?: string[];
  keywords?: string[];
  examples?: string[];
  useCases?: string[];
  inputs?: string[];
  outputs?: string[];
  notes?: string[];
  releaseNotes?: string[];
  changeSummary?: string;
}

export type AppStudioSelectedIconSource = "candidate_png" | "final_png" | "fallback_png";

export interface AppStudioIconOverride {
  selectedIconSource: AppStudioSelectedIconSource;
  pngDataUrl?: string;
}

export interface AppStudioAiMetadataSuggestion {
  appId?: string | null;
  name?: string | null;
  shortDescription?: string | null;
  description?: string | null;
  categories: string[];
  keywords: string[];
  examples: string[];
  useCases: string[];
  inputs: string[];
  outputs: string[];
  notes: string[];
  iconPrompt?: string | null;
  releaseNotes: string[];
  changeSummary?: string | null;
}

export interface AppStudioAiIconSuggestion {
  promptInitial?: string | null;
  promptRevision?: string | null;
  candidateSvg?: string | null;
  finalSvg?: string | null;
  fallbackSvg?: string | null;
  candidatePngDataUrl?: string | null;
  finalPngDataUrl?: string | null;
  candidateUrl?: string | null;
  aiReport?: string | null;
}

export interface AppStudioAiProposal {
  ok: boolean;
  outputDir?: string | null;
  metadata: AppStudioAiMetadataSuggestion;
  icon: AppStudioAiIconSuggestion;
  warnings: string[];
}

export type AppStudioApprovalMode = "allowWarnings" | "strict";
export type AppStudioVersionBumpMode = "patch" | "minor" | "major" | "manual";
