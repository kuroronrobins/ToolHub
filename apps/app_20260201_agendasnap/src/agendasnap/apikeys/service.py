"""Safe API key management helpers for UI and tests."""
from __future__ import annotations

import socket
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable, Iterable

from agendasnap.apikeys.embedded import EmbeddedKeyProvider
from agendasnap.apikeys.env import EnvKeyProvider
from agendasnap.apikeys.provider import defaults_for_service, supported_services
from agendasnap.apikeys.wincred import WinCredProvider


DEFAULT_PRIORITY = ["env", "wincred", "embedded"]


@dataclass(frozen=True)
class ApiKeyStatus:
    service: str
    env_name: str
    wincred_target: str
    env_present: bool
    wincred_present: bool
    wincred_supported: bool
    effective_source: str | None
    masked_key: str | None
    status_label: str


@dataclass(frozen=True)
class ApiKeyTestResult:
    status: str
    message: str

    @property
    def ok(self) -> bool:
        return self.status == "success"


def normalize_priority(priority: Iterable[str] | None) -> list[str]:
    out = [str(item).strip().lower() for item in (priority or []) if str(item).strip()]
    return out or list(DEFAULT_PRIORITY)


def mask_api_key(key: str | None) -> str | None:
    text = str(key or "").strip()
    if not text:
        return None
    suffix = text[-4:] if len(text) >= 4 else "****"
    if len(text) <= 8:
        return f"***{suffix}"
    prefix = "sk-" if text.startswith("sk-") else text[: min(4, len(text))]
    return f"{prefix}...{suffix}"


def api_key_missing_message(service: str = "openai") -> str:
    service_label = str(service or "openai").strip() or "openai"
    env_name = defaults_for_service(service_label)["env_name"]
    return (
        f"APIキーが未登録です。設定画面 > AI利用設定 から {service_label} APIキーを登録してください。"
        f"または環境変数 {env_name} を設定してください。"
    )


class ApiKeyManager:
    def __init__(
        self,
        *,
        wincred_provider_factory: Callable[[str], WinCredProvider] | None = None,
        env_provider_factory: Callable[[str], EnvKeyProvider] | None = None,
    ) -> None:
        self._wincred_provider_factory = wincred_provider_factory or (
            lambda target: WinCredProvider(target_name=target)
        )
        self._env_provider_factory = env_provider_factory or (lambda name: EnvKeyProvider(env_name=name))

    def supported_services(self) -> tuple[str, ...]:
        return supported_services()

    def defaults_for(self, service: str) -> dict[str, str]:
        return defaults_for_service(service)

    def _env_provider(self, service: str) -> EnvKeyProvider:
        return self._env_provider_factory(self.defaults_for(service)["env_name"])

    def _wincred_provider(self, service: str) -> WinCredProvider:
        return self._wincred_provider_factory(self.defaults_for(service)["wincred_target"])

    def get_status(
        self,
        service: str = "openai",
        *,
        priority: Iterable[str] | None = None,
        embedded_key: str | None = None,
    ) -> ApiKeyStatus:
        defaults = self.defaults_for(service)
        env_provider = self._env_provider(service)
        wincred_provider = self._wincred_provider(service)
        embedded_provider = EmbeddedKeyProvider(embedded_key or "")

        env_key = env_provider.get_key()
        wincred_key = wincred_provider.get_key()
        embedded = embedded_provider.get_key()

        sources = {
            "env": env_key,
            "wincred": wincred_key,
            "embedded": embedded,
        }
        effective_source = None
        effective_key = None
        for source in normalize_priority(priority):
            key = sources.get(source)
            if key:
                effective_source = source
                effective_key = key
                break

        env_present = bool(env_key)
        wincred_present = bool(wincred_key)
        wincred_supported = bool(wincred_provider.is_supported())
        if effective_source == "env":
            status_label = "環境変数で検出 / 使用中"
        elif effective_source == "wincred":
            status_label = "Windows資格情報に登録済み / 使用中"
        elif effective_source == "embedded":
            status_label = "embedded キー使用中"
        elif env_present:
            status_label = "環境変数で検出"
        elif wincred_present:
            status_label = "Windows資格情報に登録済み"
        else:
            status_label = "未登録"

        return ApiKeyStatus(
            service=str(service or "openai").strip().lower(),
            env_name=defaults["env_name"],
            wincred_target=defaults["wincred_target"],
            env_present=env_present,
            wincred_present=wincred_present,
            wincred_supported=wincred_supported,
            effective_source=effective_source,
            masked_key=mask_api_key(effective_key),
            status_label=status_label,
        )

    def set_key(self, service: str, key: str) -> None:
        self._wincred_provider(service).set_key(key)

    def delete_key(self, service: str) -> bool:
        return self._wincred_provider(service).delete_key()

    def resolve_effective_key(
        self,
        service: str = "openai",
        *,
        priority: Iterable[str] | None = None,
        embedded_key: str | None = None,
    ) -> tuple[str | None, str | None]:
        defaults = self.defaults_for(service)
        env_key = self._env_provider_factory(defaults["env_name"]).get_key()
        wincred_key = self._wincred_provider_factory(defaults["wincred_target"]).get_key()
        embedded = EmbeddedKeyProvider(embedded_key or "").get_key()
        for source in normalize_priority(priority):
            key = {"env": env_key, "wincred": wincred_key, "embedded": embedded}.get(source)
            if key:
                return key, source
        return None, None

    def test_connection(
        self,
        service: str = "openai",
        *,
        priority: Iterable[str] | None = None,
        timeout_seconds: float = 10.0,
        opener: Callable | None = None,
    ) -> ApiKeyTestResult:
        key, _source = self.resolve_effective_key(service, priority=priority)
        if not key:
            return ApiKeyTestResult("missing", api_key_missing_message(service))

        if str(service or "openai").strip().lower() != "openai":
            return ApiKeyTestResult("unsupported", "このプロバイダーの接続テストは準備中です。")

        request = urllib.request.Request(
            "https://api.openai.com/v1/models",
            headers={"Authorization": f"Bearer {key}"},
            method="GET",
        )
        open_func = opener or urllib.request.urlopen
        try:
            with open_func(request, timeout=float(timeout_seconds)) as response:
                status = int(getattr(response, "status", 200) or 200)
                if 200 <= status < 300:
                    return ApiKeyTestResult("success", "接続テストに成功しました。")
                if status in {401, 403}:
                    return ApiKeyTestResult("auth_failed", "認証に失敗しました。APIキーを確認してください。")
                return ApiKeyTestResult("network_failed", f"接続テストに失敗しました。HTTP {status}")
        except urllib.error.HTTPError as exc:
            if exc.code in {401, 403}:
                return ApiKeyTestResult("auth_failed", "認証に失敗しました。APIキーを確認してください。")
            return ApiKeyTestResult("network_failed", f"接続テストに失敗しました。HTTP {exc.code}")
        except (TimeoutError, socket.timeout):
            return ApiKeyTestResult("timeout", "接続テストがタイムアウトしました。")
        except urllib.error.URLError as exc:
            reason = exc.reason
            if isinstance(reason, TimeoutError):
                return ApiKeyTestResult("timeout", "接続テストがタイムアウトしました。")
            return ApiKeyTestResult("network_failed", "ネットワーク接続に失敗しました。")
        except Exception:  # noqa: BLE001
            return ApiKeyTestResult("network_failed", "接続テストに失敗しました。")
