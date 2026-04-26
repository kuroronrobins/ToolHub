from __future__ import annotations

import base64
import os
from dataclasses import dataclass


DEFAULT_IMAGE_MODEL = "gpt-image-2"


@dataclass
class OpenAIResult:
    ok: bool
    used_api: bool
    content: str
    report: str
    error: str = ""


def ai_enabled() -> bool:
    return os.environ.get("TOOLHUB_APP_STUDIO_AI_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"}


def text_model() -> str:
    return os.environ.get("TOOLHUB_APP_STUDIO_TEXT_MODEL", "local-deterministic-fallback")


def image_model() -> str:
    return os.environ.get("TOOLHUB_APP_STUDIO_IMAGE_MODEL", DEFAULT_IMAGE_MODEL)


def can_call_api() -> tuple[bool, str]:
    if not ai_enabled():
        return False, "AI is disabled. Set TOOLHUB_APP_STUDIO_AI_ENABLED=true to opt in."
    if not os.environ.get("OPENAI_API_KEY"):
        return False, "OPENAI_API_KEY is not set."
    return True, ""


def complete_json(system_prompt: str, user_prompt: str) -> OpenAIResult:
    allowed, reason = can_call_api()
    model = text_model()
    if not allowed:
        return OpenAIResult(False, False, "", f"OpenAI text generation fallback used. model={model}. reason={reason}", reason)
    if model == "local-deterministic-fallback":
        return OpenAIResult(False, False, "", "OpenAI text generation fallback used because no text model was configured.", "text model not configured")
    try:
        from openai import OpenAI  # type: ignore
    except Exception as exc:
        return OpenAIResult(False, False, "", f"OpenAI package is not available. fallback used. error={exc!r}", repr(exc))
    try:
        client = OpenAI()
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content or ""
        return OpenAIResult(True, True, content, f"OpenAI text generation succeeded. model={model}.")
    except Exception as exc:
        return OpenAIResult(False, False, "", f"OpenAI text generation failed. fallback used. model={model}. error={exc!r}", repr(exc))


def generate_image(prompt: str) -> OpenAIResult:
    allowed, reason = can_call_api()
    model = image_model()
    if not allowed:
        return OpenAIResult(False, False, "", f"OpenAI image generation fallback used. model={model}. reason={reason}", reason)
    if model == "local-deterministic-fallback":
        return OpenAIResult(False, False, "", "OpenAI image generation fallback used because no image model was configured.", "image model not configured")
    try:
        from openai import OpenAI  # type: ignore
    except Exception as exc:
        return OpenAIResult(False, False, "", f"OpenAI package is not available. fallback used. error={exc!r}", repr(exc))
    try:
        client = OpenAI()
        try:
            response = client.images.generate(model=model, prompt=prompt, size="1024x1024", response_format="b64_json")
        except TypeError:
            response = client.images.generate(model=model, prompt=prompt, size="1024x1024")
        data = response.data[0]
        b64 = getattr(data, "b64_json", None)
        if b64:
            return OpenAIResult(True, True, b64, f"OpenAI image generation succeeded. model={model}. content=b64_png")
        url = getattr(data, "url", "")
        return OpenAIResult(True, True, url or "", f"OpenAI image generation succeeded. model={model}. content=url")
    except Exception as exc:
        return OpenAIResult(False, False, "", f"OpenAI image generation failed. fallback used. model={model}. error={exc!r}", repr(exc))


def decode_base64_image(content: str) -> bytes:
    return base64.b64decode(content)
