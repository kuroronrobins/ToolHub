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
  AppStudioPublishBuildVerifyRequest,
  AppStudioPublishPreflightResult,
  AppStudioPublishPrepareTargetRequest,
  AppStudioPublishRemoteVerifyRequest,
  AppStudioPublishRequest,
  AppStudioPublishRunResult,
  AppStudioPublishSignInstallerRequest,
  AppStudioRegisteredApp,
  AppStudioReleaseNotesDraftResult,
  AppStudioResultSummary,
  AppStudioRunResult,
  AppStudioSaveReleaseNotesRequest,
  AppStudioSaveReleaseNotesResult,
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

export async function appStudioPublishPreflight(): Promise<AppStudioPublishPreflightResult> {
  return invoke<AppStudioPublishPreflightResult>("app_studio_publish_preflight");
}

export async function appStudioPublishSuggestReleaseNotes(): Promise<AppStudioReleaseNotesDraftResult> {
  return invoke<AppStudioReleaseNotesDraftResult>("app_studio_publish_suggest_release_notes");
}

export async function appStudioPublishSaveReleaseNotes(request: AppStudioSaveReleaseNotesRequest): Promise<AppStudioSaveReleaseNotesResult> {
  return invoke<AppStudioSaveReleaseNotesResult>("app_studio_publish_save_release_notes", { request });
}

export async function appStudioPublishDryRun(): Promise<AppStudioPublishRunResult> {
  return invoke<AppStudioPublishRunResult>("app_studio_publish_dry_run");
}

export async function appStudioPublishPrepareTarget(request: AppStudioPublishPrepareTargetRequest): Promise<AppStudioPublishRunResult> {
  return invoke<AppStudioPublishRunResult>("app_studio_publish_prepare_target", { request });
}

export async function appStudioPublishSignInstaller(request: AppStudioPublishSignInstallerRequest): Promise<AppStudioPublishRunResult> {
  return invoke<AppStudioPublishRunResult>("app_studio_publish_sign_installer", { request });
}

export async function appStudioPublishBuildVerify(request: AppStudioPublishBuildVerifyRequest): Promise<AppStudioPublishRunResult> {
  return invoke<AppStudioPublishRunResult>("app_studio_publish_build_verify", { request });
}

export async function appStudioPublishRemoteVerify(request: AppStudioPublishRemoteVerifyRequest): Promise<AppStudioPublishRunResult> {
  return invoke<AppStudioPublishRunResult>("app_studio_publish_remote_verify", { request });
}

export async function appStudioPublishRelease(request: AppStudioPublishRequest): Promise<AppStudioPublishRunResult> {
  return invoke<AppStudioPublishRunResult>("app_studio_publish_release", { request });
}

export async function appStudioPickEntryFile(): Promise<string | null> {
  return invoke<string | null>("app_studio_pick_entry_file");
}
