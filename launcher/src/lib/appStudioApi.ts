import { invoke } from "@tauri-apps/api/core";
import type { AppStudioImportRequest, AppStudioPreflightResult, AppStudioResultSummary, AppStudioRunResult } from "./appStudioTypes";

export async function appStudioSuggest(request: AppStudioImportRequest): Promise<AppStudioRunResult> {
  return invoke<AppStudioRunResult>("app_studio_suggest", { request });
}

export async function appStudioApply(request: AppStudioImportRequest): Promise<AppStudioRunResult> {
  return invoke<AppStudioRunResult>("app_studio_apply", { request });
}

export async function appStudioApprove(appId: string, strict: boolean): Promise<AppStudioRunResult> {
  return invoke<AppStudioRunResult>("app_studio_approve", { appId, strict });
}

export async function appStudioReadResult(appId?: string, outputDir?: string): Promise<AppStudioResultSummary> {
  return invoke<AppStudioResultSummary>("app_studio_read_result", { appId, outputDir });
}

export async function appStudioPreflight(request: AppStudioImportRequest): Promise<AppStudioPreflightResult> {
  return invoke<AppStudioPreflightResult>("app_studio_preflight", { request });
}

export async function appStudioPickEntryFile(): Promise<string | null> {
  return invoke<string | null>("app_studio_pick_entry_file");
}
