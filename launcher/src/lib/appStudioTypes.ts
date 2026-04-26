export type AppStudioBuildMode = "auto" | "app-env" | "frozen-folder" | "existing-exe";

export interface AppStudioImportRequest {
  entry: string;
  appId?: string;
  name?: string;
  version?: string;
  buildMode: AppStudioBuildMode;
  iconPrompt?: string;
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
}

export type AppStudioApprovalMode = "allowWarnings" | "strict";
export type AppStudioVersionBumpMode = "patch" | "minor" | "major" | "manual";
