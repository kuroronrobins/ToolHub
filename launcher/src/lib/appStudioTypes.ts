export type AppStudioBuildMode = "auto" | "app-env" | "frozen-folder" | "existing-exe";

export interface AppStudioImportRequest {
  entry: string;
  appId?: string;
  name?: string;
  buildMode: AppStudioBuildMode;
  iconPrompt?: string;
  createAppEnv: boolean;
  rebuildAppEnv: boolean;
  generateLock: boolean;
  buildFrozenFolder: boolean;
  verifyRuntime: boolean;
}

export interface AppStudioRunResult {
  ok: boolean;
  exitCode: number;
  stdout: string;
  stderr: string;
  userMessage: string;
  outputDir?: string | null;
  appId?: string | null;
  executionStatus?: "pass" | "warn" | "fail" | "unknown" | string | null;
  approvalAllowed?: boolean | null;
  runtimeStatus?: "pass" | "warn" | "fail" | "unknown" | string | null;
  appPack?: string | null;
  enabled?: boolean | null;
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
}
