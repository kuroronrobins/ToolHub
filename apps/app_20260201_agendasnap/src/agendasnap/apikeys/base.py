"""API key provider interface."""
from abc import ABC, abstractmethod
from typing import Optional


class ApiKeyProvider(ABC):
    @abstractmethod
    def get_key(self) -> Optional[str]:
        """Return an API key or None."""
