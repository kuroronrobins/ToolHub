"""Resolve API key using priority order."""
from __future__ import annotations

from typing import Iterable, Optional

from agendasnap.apikeys.base import ApiKeyProvider
from agendasnap.apikeys.embedded import EmbeddedKeyProvider
from agendasnap.apikeys.env import EnvKeyProvider
from agendasnap.apikeys.wincred import WinCredProvider

_SERVICE_DEFAULTS: dict[str, dict[str, str]] = {
    "openai": {"env_name": "OPENAI_API_KEY", "wincred_target": "AgendaSnap/OpenAI"},
    "dashscope": {"env_name": "DASHSCOPE_API_KEY", "wincred_target": "AgendaSnap/DashScope"},
    "baidu": {"env_name": "BAIDU_API_KEY", "wincred_target": "AgendaSnap/Baidu"},
    "zhipu": {"env_name": "ZHIPU_API_KEY", "wincred_target": "AgendaSnap/Zhipu"},
    "custom": {"env_name": "AGENDASNAP_API_KEY", "wincred_target": "AgendaSnap/Custom"},
}


def supported_services() -> tuple[str, ...]:
    return tuple(_SERVICE_DEFAULTS.keys())


def _defaults_for_service(service: str) -> dict[str, str]:
    key = str(service or "openai").strip().lower()
    return _SERVICE_DEFAULTS.get(key, _SERVICE_DEFAULTS["custom"])


def defaults_for_service(service: str) -> dict[str, str]:
    return dict(_defaults_for_service(service))


def default_providers(
    priority: Iterable[str],
    *,
    service: str = "openai",
    env_name: str | None = None,
    wincred_target: str | None = None,
    embedded_key: str | None = None,
):
    defaults = _defaults_for_service(service)
    resolved_env_name = str(env_name or defaults["env_name"]).strip()
    resolved_target = str(wincred_target or defaults["wincred_target"]).strip()
    mapping = {
        "env": EnvKeyProvider(env_name=resolved_env_name),
        "wincred": WinCredProvider(target_name=resolved_target),
        "embedded": EmbeddedKeyProvider(key=(embedded_key or "")),
    }
    return [mapping[name] for name in priority if name in mapping]


def resolve_api_key(
    priority: Iterable[str],
    *,
    service: str = "openai",
    env_name: str | None = None,
    wincred_target: str | None = None,
    embedded_key: str | None = None,
) -> Optional[str]:
    for provider in default_providers(
        priority,
        service=service,
        env_name=env_name,
        wincred_target=wincred_target,
        embedded_key=embedded_key,
    ):
        key = provider.get_key()
        if key:
            return key
    return None
