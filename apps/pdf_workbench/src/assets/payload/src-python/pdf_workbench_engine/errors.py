from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class EngineError(Exception):
    code: str
    message: str
    target: str | None = None
    detail: str | None = None

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "code": self.code,
            "message": self.message,
        }
        if self.target:
            payload["target"] = self.target
        if self.detail:
            payload["detail"] = self.detail
        return payload


def dependency_missing(package: str, purpose: str) -> EngineError:
    return EngineError(
        code="dependency_missing",
        message=f"{purpose}に必要なPython依存関係が見つかりません: {package}",
        detail=f"Install {package} in the Python environment used by PDF Workbench.",
    )


def user_error(message: str, code: str = "invalid_request", target: str | None = None) -> EngineError:
    return EngineError(code=code, message=message, target=target)
