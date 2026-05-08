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

export interface AiImageGenerationTestResult {
  ok: boolean;
  message: string;
  keySource?: string | null;
  model: string;
  api: string;
  status: string;
  contentType: string;
  resolution?: string | null;
  fallbackReason?: string | null;
  error?: string | null;
  errorCategory?: string | null;
  failureClass?: string | null;
  failureMessage?: string | null;
  adminNextAction?: string | null;
}

export interface AiImageModelProbeItem {
  model: string;
  ok: boolean;
  status: string;
  contentType: string;
  fallbackReason?: string | null;
  error?: string | null;
  errorCategory?: string | null;
  failureClass?: string | null;
  failureMessage?: string | null;
  adminNextAction?: string | null;
}

export interface AiImageModelProbeResult {
  ok: boolean;
  message: string;
  items: AiImageModelProbeItem[];
}
