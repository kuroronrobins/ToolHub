export interface AdminSessionStatus {
  authenticated: boolean;
  expiresAt?: string | null;
}

export interface AiSettings {
  aiEnabled: boolean;
  textModel: string;
  imageModel: string;
  apiKeySource: string;
  updatedAt?: string | null;
}

export interface ApiKeyStatus {
  state: "registered" | "env_available" | "missing" | "credential_unavailable" | string;
  source?: string | null;
  masked?: string | null;
  credentialSupported: boolean;
  message: string;
}

export interface AiConnectionTestResult {
  ok: boolean;
  message: string;
  keySource?: string | null;
  textModelSet: boolean;
  imageModelSet: boolean;
}
