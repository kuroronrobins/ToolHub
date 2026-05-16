"""Responses API client (provider-aware, OpenAI-compatible)."""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Dict, Iterable, List, Optional

from agendasnap.apikeys.provider import resolve_api_key
from agendasnap.apikeys.service import api_key_missing_message


class OpenAIResponsesClient:
    def __init__(
        self,
        *,
        api_key_priority: Iterable[str],
        provider: str = "openai",
        api_key_service: str | None = None,
        base_url: str = "https://api.openai.com/v1/responses",
        timeout_seconds: float = 30.0,
    ) -> None:
        self.api_key_priority = list(api_key_priority)
        self.provider = str(provider or "openai")
        self.api_key_service = str(api_key_service or provider or "openai")
        self.base_url = str(base_url or "").strip()
        self.timeout_seconds = float(timeout_seconds)

    def request_json(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not self.base_url:
            raise RuntimeError(
                f"Responses base URL is not configured for provider='{self.provider}'. "
                "Set `base_url` in config."
            )

        api_key = resolve_api_key(
            self.api_key_priority,
            service=self.api_key_service,
        )
        if not api_key:
            raise RuntimeError(api_key_missing_message(self.api_key_service))

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.base_url,
            data=data,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                body = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore") if exc.fp else ""
            raise RuntimeError(
                f"{self.provider} API HTTP error: {exc.code} {exc.reason} {detail}"
            ) from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"{self.provider} API connection error: {exc.reason}") from exc

        try:
            return json.loads(body)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"Invalid JSON response from {self.provider} API: {body[:200]}") from exc


def extract_output_json(resp: Dict[str, Any]) -> Dict[str, Any]:
    """Extract JSON payload from Responses API output."""
    if not isinstance(resp, dict):
        raise RuntimeError("Invalid response type")

    if "output" not in resp:
        raise RuntimeError(f"Unexpected response shape: {list(resp.keys())}")

    output: List[Dict[str, Any]] = resp.get("output", [])
    for item in output:
        if item.get("type") != "message":
            continue
        content = item.get("content") or []
        for part in content:
            ptype = part.get("type")
            if ptype == "output_text" and "text" in part:
                return json.loads(part["text"])
            if ptype == "output_json" and "json" in part:
                return part["json"]

    raise RuntimeError("No parsable JSON found in Responses API output")


def extract_output_text(resp: Dict[str, Any]) -> str:
    """Extract text output from Responses API output."""
    if not isinstance(resp, dict):
        raise RuntimeError("Invalid response type")

    if "output" not in resp:
        raise RuntimeError(f"Unexpected response shape: {list(resp.keys())}")

    output: List[Dict[str, Any]] = resp.get("output", [])
    for item in output:
        if item.get("type") != "message":
            continue
        content = item.get("content") or []
        for part in content:
            ptype = part.get("type")
            if ptype == "output_text" and "text" in part:
                return str(part["text"])
            if ptype == "output_json" and "json" in part:
                return json.dumps(part["json"], ensure_ascii=False)

    raise RuntimeError("No output text found in Responses API output")
