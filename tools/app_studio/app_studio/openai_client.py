from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from typing import Any


DEFAULT_IMAGE_MODEL = "gpt-image-2"


@dataclass
class OpenAIResult:
    ok: bool
    used_api: bool
    content: str
    report: str
    error: str = ""
    status: str = "fallback"
    model: str = ""
    api: str = ""
    content_type: str = "none"
    fallback_reason: str = ""
    resolution: str = ""
    error_category: str = ""
    failure_class: str = ""
    failure_message: str = ""
    admin_next_action: str = ""


@dataclass(frozen=True)
class FailureGuidance:
    failure_class: str
    message_ja: str
    next_action_ja: str


FAILURE_GUIDANCE: dict[str, FailureGuidance] = {
    "ai_disabled": FailureGuidance(
        "ai_disabled",
        "AI機能が無効のため、画像生成APIを呼び出していません。",
        "管理者画面のAI/APIキー管理でAI機能を有効にしてください。",
    ),
    "missing_api_key": FailureGuidance(
        "missing_api_key",
        "OpenAI APIキーが未登録のため、画像生成APIを実行できません。",
        "Credential Manager または環境変数 OPENAI_API_KEY にAPIキーを登録してから画像APIをテストしてください。",
    ),
    "missing_image_model": FailureGuidance(
        "missing_image_model",
        "Image model が未設定のため、画像生成APIを実行できません。",
        "AI/APIキー管理で利用可能なImage modelを設定してください。",
    ),
    "organization_not_verified": FailureGuidance(
        "organization_not_verified",
        "このImage modelの利用にはOpenAI organization verificationが必要です。",
        "OpenAI PlatformのOrganization verificationを完了するか、候補モデルの実APIテストで利用可能なImage modelへ切り替えてください。",
    ),
    "unsupported_model": FailureGuidance(
        "unsupported_model",
        "設定されたImage modelは現在のAPIキーまたはSDK設定では利用できません。",
        "AI/APIキー管理の候補モデルテストで利用可能なモデルを確認し、管理者が明示的にImage modelを変更してください。",
    ),
    "quota_or_rate_limit": FailureGuidance(
        "quota_or_rate_limit",
        "OpenAI APIのquotaまたはrate limitにより画像生成に失敗しました。",
        "OpenAI Platformで利用状況を確認し、時間を置いて再実行してください。",
    ),
    "authentication_failed": FailureGuidance(
        "authentication_failed",
        "OpenAI APIの認証に失敗しました。",
        "APIキーが有効で、対象プロジェクトまたは組織で利用可能か確認してください。",
    ),
    "secret_scan_blocked": FailureGuidance(
        "secret_scan_blocked",
        "AIへ送信するicon prompt payloadに秘密情報の可能性があるため、画像生成を停止しました。",
        "Prompt、README、メタデータからAPIキー、token、passwordなどを除去してから再生成してください。",
    ),
    "network_error": FailureGuidance(
        "network_error",
        "ネットワークまたは接続の問題により画像生成APIへ到達できませんでした。",
        "ネットワーク、プロキシ、DNS、TLS設定を確認してから再実行してください。",
    ),
    "api_error": FailureGuidance(
        "api_error",
        "画像生成APIがエラーを返しました。",
        "ai_generation_report.md の詳細を確認し、必要に応じてモデル設定やPromptを見直してください。",
    ),
    "package_missing": FailureGuidance(
        "package_missing",
        "OpenAI Python package が利用できないため、画像生成APIを呼び出せません。",
        "App Studioを実行しているPython環境にopenai packageがあるか確認してください。",
    ),
    "empty_response": FailureGuidance(
        "empty_response",
        "画像生成APIは応答しましたが、保存できる画像データまたはURLが返りませんでした。",
        "モデル設定とSDK応答形式を確認し、画像APIテストを再実行してください。",
    ),
    "unknown": FailureGuidance(
        "unknown",
        "画像生成に失敗しましたが、原因を特定できませんでした。",
        "ai_generation_report.md とApp Studioログの詳細を確認してください。",
    ),
}


def ai_enabled() -> bool:
    return os.environ.get("TOOLHUB_APP_STUDIO_AI_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"}


def get_text_model() -> str | None:
    value = os.environ.get("TOOLHUB_APP_STUDIO_TEXT_MODEL")
    if value is None:
        return None
    value = value.strip()
    if not value or value == "local-deterministic-fallback":
        return None
    return value


def get_image_model() -> str | None:
    value = os.environ.get("TOOLHUB_APP_STUDIO_IMAGE_MODEL")
    if value is None:
        return DEFAULT_IMAGE_MODEL
    value = value.strip()
    return value or None


def text_model() -> str:
    return get_text_model() or "local-deterministic-fallback"


def image_model() -> str:
    return get_image_model() or "local-deterministic-fallback"


def has_api_key() -> bool:
    return bool(os.environ.get("OPENAI_API_KEY", "").strip())


def can_call_api(model: str | None) -> tuple[bool, str, str]:
    if not ai_enabled():
        return False, "skipped", "AI is disabled."
    if not has_api_key():
        return False, "fallback", "OPENAI_API_KEY is not set."
    if not model:
        return False, "fallback", "model is not configured."
    return True, "success", ""


def complete_json(system_prompt: str, user_prompt: str) -> OpenAIResult:
    model = get_text_model()
    allowed, status, reason = can_call_api(model)
    api = "responses.create"
    if not allowed:
        return result_with_report(False, False, "", api, status, model or "", "none", reason)
    try:
        from openai import OpenAI  # type: ignore
    except Exception as exc:
        reason = f"OpenAI package is not available: {short_error(exc)}"
        return result_with_report(False, False, "", api, "fallback", model or "", "none", reason, repr(exc))
    try:
        client = OpenAI()
        response = client.responses.create(
            model=model,
            input=f"{system_prompt}\n\n{user_prompt}",
        )
        content = extract_response_text(response)
        if not content.strip():
            reason = "Responses API returned no text."
            return result_with_report(False, True, "", api, "failed", model or "", "none", reason)
        return result_with_report(True, True, content, api, "success", model or "", "text", "")
    except Exception as exc:
        reason = f"Responses API failed: {short_error(exc)}"
        return result_with_report(False, True, "", api, "failed", model or "", "none", reason, repr(exc))


def generate_image(
    prompt: str,
    size: str = "1024x1024",
    quality: str = "medium",
    output_format: str = "png",
    model_override: str | None = None,
) -> OpenAIResult:
    model = (model_override.strip() if model_override else "") or get_image_model()
    allowed, status, reason = can_call_api(model)
    api = "images.generate"
    if not allowed:
        return result_with_report(False, False, "", api, status, model or "", "none", reason, resolution=size, error_category=error_category_from_reason(reason))
    try:
        from openai import OpenAI  # type: ignore
    except Exception as exc:
        reason = f"OpenAI package is not available: {short_error(exc)}"
        return result_with_report(False, False, "", api, "fallback", model or "", "none", reason, repr(exc), resolution=size, error_category="package_missing")

    client = OpenAI()
    params: dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "size": size,
        "output_format": output_format,
        "quality": quality,
    }
    try:
        response = client.images.generate(**params)
    except Exception as exc:
        if is_unsupported_optional_parameter(exc):
            retry_params = {key: value for key, value in params.items() if key not in {"output_format", "quality"}}
            try:
                response = client.images.generate(**retry_params)
            except Exception as retry_exc:
                reason = f"Image API failed after optional-parameter retry: {short_error(retry_exc)}"
                return result_with_report(False, True, "", api, "failed", model or "", "none", reason, repr(retry_exc), output_format="not_requested", quality="not_requested", resolution=size, error_category=classify_openai_error(retry_exc))
        else:
            reason = f"Image API failed: {short_error(exc)}"
            return result_with_report(False, True, "", api, "failed", model or "", "none", reason, repr(exc), resolution=size, error_category=classify_openai_error(exc))

    content, content_type = extract_image_content(response)
    if not content:
        reason = "Image API returned neither b64_json nor url."
        return result_with_report(False, True, "", api, "failed", model or "", "none", reason, resolution=size, error_category="empty_response")
    return result_with_report(True, True, content, api, "success", model or "", content_type, "", resolution=size)


def edit_image(prompt: str, image_path: str, size: str = "1024x1024", quality: str = "medium", output_format: str = "png") -> OpenAIResult:
    model = get_image_model()
    allowed, status, reason = can_call_api(model)
    api = "images.edit"
    if not allowed:
        return result_with_report(False, False, "", api, status, model or "", "none", reason, resolution=size, error_category=error_category_from_reason(reason))
    try:
        from openai import OpenAI  # type: ignore
    except Exception as exc:
        reason = f"OpenAI package is not available: {short_error(exc)}"
        return result_with_report(False, False, "", api, "fallback", model or "", "none", reason, repr(exc), resolution=size, error_category="package_missing")

    params: dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "size": size,
        "output_format": output_format,
        "quality": quality,
    }
    try:
        client = OpenAI()
        with open(image_path, "rb") as image_file:
            response = client.images.edit(image=[image_file], **params)
    except Exception as exc:
        if is_unsupported_optional_parameter(exc):
            retry_params = {key: value for key, value in params.items() if key not in {"output_format", "quality"}}
            try:
                client = OpenAI()
                with open(image_path, "rb") as image_file:
                    response = client.images.edit(image=[image_file], **retry_params)
            except Exception as retry_exc:
                reason = f"Image edit API failed after optional-parameter retry: {short_error(retry_exc)}"
                return result_with_report(False, True, "", api, "failed", model or "", "none", reason, repr(retry_exc), output_format="not_requested", quality="not_requested", resolution=size, error_category=classify_openai_error(retry_exc))
        else:
            reason = f"Image edit API failed: {short_error(exc)}"
            return result_with_report(False, True, "", api, "failed", model or "", "none", reason, repr(exc), resolution=size, error_category=classify_openai_error(exc))

    content, content_type = extract_image_content(response)
    if not content:
        reason = "Image edit API returned neither b64_json nor url."
        return result_with_report(False, True, "", api, "failed", model or "", "none", reason, resolution=size, error_category="empty_response")
    return result_with_report(True, True, content, api, "success", model or "", content_type, "", resolution=size)


def test_image_generation_connection(model_override: str | None = None) -> OpenAIResult:
    return generate_image(
        (
            "Generate a tiny ToolHub test app icon: a single teal check-shaped sparkle on a clean "
            "transparent or light background. No text, no logo, no screenshot."
        ),
        size="1024x1024",
        quality="low",
        output_format="png",
        model_override=model_override,
    )


def result_with_report(
    ok: bool,
    used_api: bool,
    content: str,
    api: str,
    status: str,
    model: str,
    content_type: str,
    fallback_reason: str,
    error: str = "",
    output_format: str = "png",
    quality: str = "medium",
    resolution: str = "",
    error_category: str = "",
) -> OpenAIResult:
    image_api = api.startswith("images.")
    failure_class = error_category or error_category_from_reason(fallback_reason)
    if ok:
        failure_class = ""
    guidance = failure_guidance(failure_class, fallback_reason)
    report = "\n".join(
        [
            f"api: {api}",
            f"status: {status}",
            f"model: {model or 'not_configured'}",
            f"ai_enabled: {str(ai_enabled()).lower()}",
            f"api_key_present: {str(has_api_key()).lower()}",
            f"used_api: {str(used_api).lower()}",
            f"content_type: {content_type}",
            f"output_format: {output_format if image_api else 'not_applicable'}",
            f"quality: {quality if image_api else 'not_applicable'}",
            f"resolution: {resolution if image_api else 'not_applicable'}",
            f"error_category: {failure_class or 'none'}",
            f"failure_class: {failure_class or 'none'}",
            f"failure_message: {guidance.message_ja if failure_class else 'none'}",
            f"admin_next_action: {guidance.next_action_ja if failure_class else 'none'}",
            f"fallback_reason: {mask_sensitive(fallback_reason) if fallback_reason else 'none'}",
        ]
    )
    return OpenAIResult(
        ok,
        used_api,
        content,
        report,
        mask_sensitive(error),
        status,
        model,
        api,
        content_type,
        fallback_reason,
        resolution,
        failure_class,
        failure_class,
        guidance.message_ja if failure_class else "",
        guidance.next_action_ja if failure_class else "",
    )


def extract_response_text(response: Any) -> str:
    output_text = getattr(response, "output_text", None)
    if isinstance(output_text, str) and output_text.strip():
        return output_text
    return extract_text_recursive(getattr(response, "output", None)).strip()


def extract_text_recursive(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        if isinstance(value.get("text"), str):
            return value["text"]
        if isinstance(value.get("value"), str):
            return value["value"]
        return "\n".join(extract_text_recursive(item) for item in value.values()).strip()
    if isinstance(value, (list, tuple)):
        return "\n".join(extract_text_recursive(item) for item in value).strip()
    for attr in ("text", "value", "content"):
        if hasattr(value, attr):
            text = extract_text_recursive(getattr(value, attr))
            if text:
                return text
    return ""


def extract_image_content(response: Any) -> tuple[str, str]:
    data_items = getattr(response, "data", None) or []
    if not data_items:
        return "", "none"
    first = data_items[0]
    b64 = getattr(first, "b64_json", None)
    if isinstance(b64, str) and b64.strip():
        return b64.strip(), "b64_png"
    url = getattr(first, "url", None)
    if isinstance(url, str) and url.strip():
        return url.strip(), "url"
    if isinstance(first, dict):
        b64 = first.get("b64_json")
        if isinstance(b64, str) and b64.strip():
            return b64.strip(), "b64_png"
        url = first.get("url")
        if isinstance(url, str) and url.strip():
            return url.strip(), "url"
    return "", "none"


def is_unsupported_optional_parameter(exc: Exception) -> bool:
    text = short_error(exc).lower()
    return any(fragment in text for fragment in ["unknown parameter", "unsupported parameter", "unexpected keyword", "unexpected parameter"])


def classify_openai_error(exc: Exception) -> str:
    return error_category_from_reason(short_error(exc))


def error_category_from_reason(reason: str) -> str:
    text = reason.lower()
    if (
        "organization must be verified" in text
        or "verify organization" in text
        or "verified organization" in text
        or "organization verification" in text
    ):
        return "organization_not_verified"
    if "not set" in text:
        return "missing_api_key"
    if "not configured" in text:
        return "missing_image_model"
    if "disabled" in text:
        return "ai_disabled"
    if "secret scan" in text or "secret" in text and "blocked" in text:
        return "secret_scan_blocked"
    if "package is not available" in text:
        return "package_missing"
    if (
        "api_key" in text
        or "authentication" in text
        or "unauthorized" in text
        or "invalid api key" in text
        or "401" in text
    ):
        return "authentication_failed"
    if "quota" in text or "insufficient_quota" in text or "rate limit" in text or "429" in text:
        return "quota_or_rate_limit"
    if any(fragment in text for fragment in ["timeout", "timed out", "connection", "network", "dns", "proxy", "ssl"]):
        return "network_error"
    if "model" in text and ("not" in text or "unsupported" in text or "does not exist" in text):
        return "unsupported_model"
    if "unsupported parameter" in text or "unknown parameter" in text or "unexpected parameter" in text:
        return "api_error"
    if "neither b64_json nor url" in text or "returned no" in text:
        return "empty_response"
    return "api_error" if text else "unknown"


def normalize_failure_class(value: str | None) -> str:
    normalized = (value or "").strip().lower()
    aliases = {
        "none": "",
        "model_not_configured": "missing_image_model",
        "organization_verification_required": "organization_not_verified",
        "authentication": "authentication_failed",
        "quota": "quota_or_rate_limit",
        "rate_limit": "quota_or_rate_limit",
        "unsupported_parameter": "api_error",
    }
    normalized = aliases.get(normalized, normalized)
    if normalized in FAILURE_GUIDANCE:
        return normalized
    return "unknown" if normalized else ""


def failure_guidance(failure_class: str | None, fallback_reason: str = "") -> FailureGuidance:
    normalized = normalize_failure_class(failure_class) or error_category_from_reason(fallback_reason)
    normalized = normalize_failure_class(normalized) or "unknown"
    return FAILURE_GUIDANCE.get(normalized, FAILURE_GUIDANCE["unknown"])


def short_error(error: Exception) -> str:
    text = str(error) or repr(error)
    text = mask_sensitive(text).replace("\r", " ").replace("\n", " ")
    return text[:300]


def mask_sensitive(text: str) -> str:
    chars = list(text)
    output: list[str] = []
    index = 0
    while index < len(chars):
        if chars[index:index + 3] == ["s", "k", "-"]:
            start = index
            index += 3
            while index < len(chars) and (chars[index].isalnum() or chars[index] in {"-", "_"}):
                index += 1
            token = "".join(chars[start:index])
            suffix = token[-4:] if len(token) > 4 else "****"
            output.append(f"sk-...{suffix}")
        else:
            output.append(chars[index])
            index += 1
    return "".join(output)


def decode_base64_image(content: str) -> bytes:
    if content.startswith("data:image/png;base64,"):
        content = content.split(",", 1)[1]
    return base64.b64decode(content)
