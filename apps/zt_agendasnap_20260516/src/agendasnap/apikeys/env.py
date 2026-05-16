"""Environment variable provider."""
import os
from typing import Optional

from agendasnap.apikeys.base import ApiKeyProvider


class EnvKeyProvider(ApiKeyProvider):
    def __init__(self, env_name: str = "OPENAI_API_KEY"):
        self.env_name = env_name

    def get_key(self) -> Optional[str]:
        return os.getenv(self.env_name)
