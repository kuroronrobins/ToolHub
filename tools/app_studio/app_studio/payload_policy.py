from __future__ import annotations

import fnmatch
from pathlib import Path


GENERATED_DIR_NAMES = {
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".cache",
}
BUILD_OUTPUT_DIR_NAMES = {
    "ToolHub_AppStudio_Output",
    "be",
    "bt",
    "build",
    "build_env",
    "dist",
    "env",
    "venv",
    ".venv",
}
GENERATED_FILE_PATTERNS = {
    "*.pyc",
    "*.pyo",
    "*.pyd.tmp",
    "*.tmp",
    "*.spec",
}

FORBIDDEN_DIRS = {
    ".auth",
    ".git",
    "log",
    "logs",
    "node_modules",
    "screenshots",
    "temp",
    "tmp",
    *GENERATED_DIR_NAMES,
    *BUILD_OUTPUT_DIR_NAMES,
}
FORBIDDEN_PATTERNS = {
    ".env",
    ".env.*",
    "*.key",
    "*.log",
    "*.pem",
    "*.pyc",
    "*.pyo",
    "*.tmp",
}
FORBIDDEN_EXACT_NAMES = {
    "auth_state.json",
    "client_secret.json",
    "client-secrets.json",
    "client_secrets.json",
    "cookie.json",
    "cookies.json",
    "credential.json",
    "credentials.json",
    "session.json",
    "sessions.json",
    "storage_state.json",
    "token.json",
    "tokens.json",
}
FORBIDDEN_CONFIG_SUFFIXES = {".json", ".yaml", ".yml", ".toml", ".ini", ".txt"}
FORBIDDEN_CONFIG_MARKERS = {
    "api_key",
    "apikey",
    "auth_state",
    "client_secret",
    "credential",
    "credentials",
    "password",
    "passwd",
    "secret",
    "storage_state",
}
FORBIDDEN_AUTH_MARKERS = {"cookie", "session", "token"}


def should_exclude_payload_path(relative: Path) -> tuple[bool, str]:
    parts = normalized_parts(relative)
    if not parts:
        return False, ""

    for part in parts:
        if part in lower_set(GENERATED_DIR_NAMES):
            return True, f"generated directory: {part}"
        if part in lower_set(BUILD_OUTPUT_DIR_NAMES):
            return True, f"build output directory: {part}"

    name = parts[-1]
    if any(fnmatch.fnmatch(name, pattern.lower()) for pattern in GENERATED_FILE_PATTERNS):
        return True, f"generated file: {name}"
    return False, ""


def is_forbidden_packaged_payload(relative: Path, is_file: bool = True) -> tuple[bool, str]:
    parts = normalized_parts(relative)
    if not parts:
        return False, ""

    for part in parts:
        if part in lower_set(FORBIDDEN_DIRS):
            return True, f"forbidden directory: {part}"

    if not is_file:
        return False, ""

    name = parts[-1]
    if is_allowed_runtime_certificate(parts, name):
        return False, ""
    if any(fnmatch.fnmatch(name, pattern.lower()) for pattern in FORBIDDEN_PATTERNS):
        return True, f"forbidden file pattern: {name}"
    if name in FORBIDDEN_EXACT_NAMES:
        return True, f"forbidden exact file: {name}"
    if name.startswith(".env"):
        return True, f"forbidden environment file: {name}"

    suffix = Path(name).suffix.lower()
    stem = Path(name).stem.lower()
    if suffix in FORBIDDEN_CONFIG_SUFFIXES:
        if any(marker in stem for marker in FORBIDDEN_CONFIG_MARKERS):
            return True, f"forbidden credential config: {name}"
        if any(marker in stem for marker in FORBIDDEN_AUTH_MARKERS):
            return True, f"forbidden auth config: {name}"
    return False, ""


def is_allowed_runtime_certificate(relative_parts: list[str], name: str) -> bool:
    return name == "cacert.pem" and "certifi" in relative_parts


def normalized_parts(path: Path) -> list[str]:
    return [part.lower() for part in path.parts if part not in {"", "."}]


def lower_set(values: set[str]) -> set[str]:
    return {value.lower() for value in values}
