"""Embedded API key provider (development only).

This exists for local/offline experiments. Prefer environment variables or OS keychain
providers for real usage.
"""
from __future__ import annotations

from typing import Optional

from agendasnap.apikeys.base import ApiKeyProvider


class EmbeddedKeyProvider(ApiKeyProvider):
    def __init__(self, key: str = ""):
        self.key = key

    def get_key(self) -> Optional[str]:
        return self.key or None
