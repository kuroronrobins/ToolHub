import { invoke } from "@tauri-apps/api/core";
import type {
  AppStudioImportRequest,
  AppStudioIconRegenerateRequest,
  AppStudioDeletePlan,
  AppStudioFullDeleteResult,
  AppStudioManagedApp,
  AppStudioManagementActionResult,
  AppStudioAiProposal,
  AppStudioAiDiagnostics,
  AppStudioPreflightResult,
  AppStudioRegisteredApp,
  AppStudioResultSummary,
  AppStudioRunResult,
  AppStudioUpdateRequest,
} from "./appStudioTypes";

export async function appStudioListRegisteredApps(): Promise<AppStudioRegisteredApp[]> {
  return invoke<AppStudioRegisteredApp[]>("app_studio_list_registered_apps");
}

export async function appStudioManagementListApps(): Promise<AppStudioManagedApp[]> {
  return invoke<AppStudioManagedApp[]>("app_studio_management_list_apps");
}

export async function appStudioManagementSetEnabled(appId: string, enabled: boolean): Promise<AppStudioManagementActionResult> {
  return invoke<AppStudioManagementActionResult>("app_studio_management_set_enabled", { appId, enabled });
}

export async function appStudioDeletePlan(appId: string): Promise<AppStudioDeletePlan> {
  return invoke<AppStudioDeletePlan>("app_studio_delete_plan", { appId });
}

export async function appStudioFullDeleteApply(
  appId: string,
  planSnapshot?: AppStudioDeletePlan | null,
): Promise<AppStudioFullDeleteResult> {
  return invoke<AppStudioFullDeleteResult>("app_studio_full_delete_apply", { appId, planSnapshot });
}

export async function appStudioSuggest(request: AppStudioImportRequest): Promise<AppStudioRunResult> {
  return invoke<AppStudioRunResult>("app_studio_suggest", { request });
}

export async function appStudioApply(request: AppStudioImportRequest): Promise<AppStudioRunResult> {
  return invoke<AppStudioRunResult>("app_studio_apply", { request });
}

export async function appStudioUpdateSuggest(request: AppStudioUpdateRequest): Promise<AppStudioRunResult> {
  return invoke<AppStudioRunResult>("app_studio_update_suggest", { request });
}

export async function appStudioUpdateApply(request: AppStudioUpdateRequest): Promise<AppStudioRunResult> {
  return invoke<AppStudioRunResult>("app_studio_update_apply", { request });
}

export async function appStudioApprove(appId: string, strict: boolean): Promise<AppStudioRunResult> {
  return invoke<AppStudioRunResult>("app_studio_approve", { appId, strict });
}

export async function appStudioUpdateApprove(appId: string, strict: boolean): Promise<AppStudioRunResult> {
  return invoke<AppStudioRunResult>("app_studio_update_approve", { appId, strict });
}

export async function appStudioReadResult(appId?: string, outputDir?: string): Promise<AppStudioResultSummary> {
  return invoke<AppStudioResultSummary>("app_studio_read_result", { appId, outputDir });
}

export async function appStudioReadAiProposal(appId?: string, outputDir?: string): Promise<AppStudioAiProposal> {
  return invoke<AppStudioAiProposal>("app_studio_read_ai_proposal", { appId, outputDir });
}

export async function appStudioRegenerateIcon(request: AppStudioIconRegenerateRequest): Promise<AppStudioAiProposal> {
  return invoke<AppStudioAiProposal>("app_studio_regenerate_icon", { request });
}

export async function appStudioAiDiagnostics(): Promise<AppStudioAiDiagnostics> {
  return invoke<AppStudioAiDiagnostics>("app_studio_ai_diagnostics");
}

export async function appStudioOpenOutputDir(outputDir: string): Promise<void> {
  return invoke<void>("app_studio_open_output_dir", { outputDir });
}

export async function appStudioPreflight(request: AppStudioImportRequest): Promise<AppStudioPreflightResult> {
  return invoke<AppStudioPreflightResult>("app_studio_preflight", { request });
}

export async function appStudioUpdatePreflight(request: AppStudioUpdateRequest): Promise<AppStudioPreflightResult> {
  return invoke<AppStudioPreflightResult>("app_studio_update_preflight", { request });
}

export async function appStudioPickEntryFile(): Promise<string | null> {
  return invoke<string | null>("app_studio_pick_entry_file");
}
