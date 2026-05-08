import type { AiImageGenerationTestResult } from "./adminTypes";

export const IMAGE_TEST_STORAGE_KEY = "toolhub.appStudio.imageGenerationTest";
export const IMAGE_TEST_UPDATED_EVENT = "toolhub-appstudio-image-test-updated";

export type StoredImageGenerationTestResult = AiImageGenerationTestResult & {
  checkedAt?: string;
};

export function loadImageGenerationTestResult(): StoredImageGenerationTestResult | null {
  if (typeof window === "undefined") {
    return null;
  }
  try {
    const raw = window.localStorage.getItem(IMAGE_TEST_STORAGE_KEY);
    return raw ? (JSON.parse(raw) as StoredImageGenerationTestResult) : null;
  } catch {
    return null;
  }
}

export function storeImageGenerationTestResult(result: AiImageGenerationTestResult) {
  if (typeof window === "undefined") {
    return;
  }
  const stored: StoredImageGenerationTestResult = { ...result, checkedAt: new Date().toISOString() };
  window.localStorage.setItem(IMAGE_TEST_STORAGE_KEY, JSON.stringify(stored));
  window.dispatchEvent(new Event(IMAGE_TEST_UPDATED_EVENT));
}

export function isOrganizationVerificationRequired(result?: Pick<AiImageGenerationTestResult, "model" | "errorCategory" | "fallbackReason" | "message"> | null): boolean {
  if (!result) {
    return false;
  }
  const text = `${result.errorCategory || ""}\n${result.fallbackReason || ""}\n${result.message || ""}`.toLowerCase();
  return (
    text.includes("organization_not_verified") ||
    text.includes("organization_verification_required") ||
    text.includes("organization must be verified") ||
    text.includes("verify organization")
  );
}

export function imageApiFailureGuidance(result?: Pick<AiImageGenerationTestResult, "model" | "errorCategory" | "fallbackReason" | "message"> | null): string {
  if (!result) {
    return "";
  }
  const model = result.model || "Image model";
  const category = result.errorCategory || "";
  if (isOrganizationVerificationRequired(result)) {
    return `${model} は現在のOpenAI組織では利用できません。OpenAI PlatformでOrganization verificationを完了するか、別のImage modelを設定してください。認証後、反映まで最大15分程度かかる場合があります。`;
  }
  if (category === "missing_api_key") {
    return "OPENAI_API_KEY が未登録のため、画像APIを実行できません。APIキーを登録してから画像生成テストを実行してください。";
  }
  if (category === "missing_image_model" || category === "model_not_configured") {
    return "Image model が未設定のため、画像APIを実行できません。利用可能な画像モデルを設定してください。";
  }
  if (category === "package_missing") {
    return "OpenAI Python package が利用できないため、画像APIを実行できません。App Studio のPython環境を確認してください。";
  }
  if (category === "quota_or_rate_limit" || category === "quota" || category === "rate_limit") {
    return "OpenAI API の quota または rate limit により画像生成に失敗しています。利用状況を確認してから再実行してください。";
  }
  if (category === "authentication_failed" || category === "authentication") {
    return "OpenAI APIの認証に失敗しています。APIキーが有効で、対象プロジェクトまたは組織で利用可能か確認してください。";
  }
  if (category === "secret_scan_blocked") {
    return "AIへ送信するicon prompt payloadに秘密情報の可能性があるため、画像生成を停止しました。PromptやメタデータからAPIキー、token、passwordなどを除去してください。";
  }
  if (category === "network_error") {
    return "ネットワークまたは接続の問題により画像APIへ到達できません。ネットワーク、プロキシ、DNS、TLS設定を確認してください。";
  }
  if (category === "unsupported_model") {
    return `${model} は現在のAPIキーまたはSDK設定では利用できません。候補モデルの実APIテストで使えるモデルを確認してください。`;
  }
  if (category === "unsupported_parameter") {
    return "画像APIのパラメータがこのモデルでは受け付けられていません。モデルまたはSDKバージョンを確認してください。";
  }
  return "画像APIテストが失敗しているため、AI画像候補は生成できません。詳細を確認してから再実行してください。";
}
