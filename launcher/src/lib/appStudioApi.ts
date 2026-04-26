import { invoke } from "@tauri-apps/api/core";
import type { AppStudioImportRequest, AppStudioResultSummary, AppStudioRunResult } from "./appStudioTypes";

export async function appStudioSuggest(request: AppStudioImportRequest): Promise<AppStudioRunResult> {
  return invoke<AppStudioRunResult>("app_studio_suggest", { request });
}

export async function appStudioApply(request: AppStudioImportRequest): Promise<AppStudioRunResult> {
  return invoke<AppStudioRunResult>("app_studio_apply", { request });
}

export async function appStudioApprove(appId: string): Promise<AppStudioRunResult> {
  return invoke<AppStudioRunResult>("app_studio_approve", { appId });
}

export async function appStudioReadResult(appId?: string, outputDir?: string): Promise<AppStudioResultSummary> {
  return invoke<AppStudioResultSummary>("app_studio_read_result", { appId, outputDir });
}
