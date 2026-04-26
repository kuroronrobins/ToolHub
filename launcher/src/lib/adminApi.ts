import { invoke } from "@tauri-apps/api/core";
import type { AdminSessionStatus, AiConnectionTestResult, AiSettings, ApiKeyStatus } from "./adminTypes";

export async function adminIsPasswordSet(): Promise<boolean> {
  return invoke<boolean>("admin_is_password_set");
}

export async function adminSetPassword(password: string, confirmPassword: string): Promise<AdminSessionStatus> {
  return invoke<AdminSessionStatus>("admin_set_password", { password, confirmPassword });
}

export async function adminLogin(password: string): Promise<AdminSessionStatus> {
  return invoke<AdminSessionStatus>("admin_login", { password });
}

export async function adminLogout(): Promise<void> {
  return invoke<void>("admin_logout");
}

export async function adminSessionStatus(): Promise<AdminSessionStatus> {
  return invoke<AdminSessionStatus>("admin_session_status");
}

export async function aiGetSettings(): Promise<AiSettings> {
  return invoke<AiSettings>("ai_get_settings");
}

export async function aiSaveSettings(settings: AiSettings): Promise<AiSettings> {
  return invoke<AiSettings>("ai_save_settings", { settings });
}

export async function aiGetApiKeyStatus(): Promise<ApiKeyStatus> {
  return invoke<ApiKeyStatus>("ai_get_api_key_status");
}

export async function aiSaveApiKey(apiKey: string): Promise<void> {
  return invoke<void>("ai_save_api_key", { apiKey });
}

export async function aiDeleteApiKey(): Promise<void> {
  return invoke<void>("ai_delete_api_key");
}

export async function aiTestConnection(): Promise<AiConnectionTestResult> {
  return invoke<AiConnectionTestResult>("ai_test_connection");
}
