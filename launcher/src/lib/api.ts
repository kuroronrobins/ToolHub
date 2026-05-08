import { invoke } from "@tauri-apps/api/core";
import type { LaunchResult, ToolApp } from "./types";
import type {
  UpdateDownloadRequest,
  UpdateDownloadResult,
  UpdateLaunchRequest,
  UpdateLaunchResult,
  UpdateSummary,
} from "./updateTypes";

export async function listApps(): Promise<ToolApp[]> {
  return invoke<ToolApp[]>("list_apps");
}

export async function getCategories(): Promise<string[]> {
  return invoke<string[]>("get_categories");
}

export async function launchApp(appId: string): Promise<LaunchResult> {
  return invoke<LaunchResult>("launch_app", { appId });
}

export async function getRecentLogs(appId?: string): Promise<string[]> {
  return invoke<string[]>("get_recent_logs", { appId });
}

export async function checkUpdatesMvp(): Promise<UpdateSummary> {
  return invoke<UpdateSummary>("check_updates_mvp");
}

export async function checkUpdatesRemote(): Promise<UpdateSummary> {
  return invoke<UpdateSummary>("check_updates_remote");
}

export async function downloadUpdateInstaller(request: UpdateDownloadRequest): Promise<UpdateDownloadResult> {
  return invoke<UpdateDownloadResult>("download_update_installer", { request });
}

export async function launchVerifiedUpdateInstaller(request: UpdateLaunchRequest): Promise<UpdateLaunchResult> {
  return invoke<UpdateLaunchResult>("launch_verified_update_installer", { request });
}

export async function getUpdateResultLog(): Promise<unknown | null> {
  return invoke<unknown | null>("get_update_result_log");
}

