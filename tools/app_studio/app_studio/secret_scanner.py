from __future__ import annotations

import fnmatch
import re
from pathlib import Path

from .models import SecretFinding, SecretScanReport


HIGH_NAME_PATTERNS = [
    ".env",
    "*.key",
    "*.pem",
    "*token*",
    "*secret*",
    "*password*",
    "*api_key*",
    "*credentials*",
    "*client_secret*",
    "*storage_state*",
    "*cookie*",
    "*session*",
]
HIGH_CONTENT_PATTERNS = [
    re.compile(r"OPENAI_API_KEY", re.IGNORECASE),
    re.compile(r"api[_-]?key", re.IGNORECASE),
    re.compile(r"client[_-]?secret", re.IGNORECASE),
    re.compile(r"password\s*=", re.IGNORECASE),
    re.compile(r"secret\s*=", re.IGNORECASE),
    re.compile(r"token\s*=", re.IGNORECASE),
    re.compile(r"credentials", re.IGNORECASE),
]
WARNING_PATTERNS = ["*.log", "*.wav", "*.mp3", "*.m4a"]
LARGE_FILE_BYTES = 25 * 1024 * 1024
SKIP_DIRS = {".git", ".venv", "venv", "env", "__pycache__", "node_modules", "toolhub_appstudio_output"}
EXCLUDED_SENSITIVE_DIRS = {".auth"}
WARNING_DIRS = {"logs", "log", "screenshots", "tmp", "temp"}


def scan_secrets(source_root: Path) -> SecretScanReport:
    findings: list[SecretFinding] = []
    for path in sorted(source_root.rglob("*")):
        if not path.is_file() or should_skip(path, source_root):
            continue
        lower_parts = {part.lower() for part in path.relative_to(source_root).parts}
        if lower_parts & EXCLUDED_SENSITIVE_DIRS:
            findings.append(SecretFinding(path.resolve(), "excluded-sensitive-directory", "medium", "Sensitive auth/session directory is excluded from packaging and must not be bundled."))
            continue
        if lower_parts & WARNING_DIRS:
            findings.append(SecretFinding(path.resolve(), "excluded-runtime-user-data", "medium", "Runtime output, logs, screenshots, or temp files are excluded from packaging."))
            continue
        name = path.name
        lower_name = name.lower()
        for pattern in HIGH_NAME_PATTERNS:
            if fnmatch.fnmatch(lower_name, pattern.lower()):
                findings.append(SecretFinding(path.resolve(), "filename", "high", f"Sensitive filename pattern matched: {pattern}"))
                break
        if any(fnmatch.fnmatch(lower_name, pattern.lower()) for pattern in WARNING_PATTERNS):
            findings.append(SecretFinding(path.resolve(), "personal-or-binary-data", "medium", "Log or recording-like file should not be bundled."))
        size = path.stat().st_size
        if size >= LARGE_FILE_BYTES:
            findings.append(SecretFinding(path.resolve(), "large-file", "medium", f"Large file warning: {size} bytes."))
        if size <= 1024 * 1024 and is_probably_text(path):
            text = path.read_text(encoding="utf-8", errors="replace")
            for pattern in HIGH_CONTENT_PATTERNS:
                if pattern.search(text):
                    findings.append(SecretFinding(path.resolve(), "content", "high", f"Sensitive content pattern matched: {pattern.pattern}"))
                    break
    return SecretScanReport(findings)


def should_skip(path: Path, source_root: Path) -> bool:
    parts = {part.lower() for part in path.relative_to(source_root).parts}
    return bool(parts & SKIP_DIRS)


def is_probably_text(path: Path) -> bool:
    try:
        sample = path.read_bytes()[:4096]
    except OSError:
        return False
    return b"\x00" not in sample


def secret_report_markdown(report: SecretScanReport, source_root: Path) -> str:
    lines = ["# Secret Scan Report", ""]
    if not report.findings:
        lines.append("No secret-like files or patterns were detected.")
        return "\n".join(lines) + "\n"

    lines.append("The following findings require human review before registration.")
    lines.append("")
    lines.append("| Severity | Kind | Path | Detail |")
    lines.append("| --- | --- | --- | --- |")
    for finding in report.findings:
        try:
            relative = finding.path.relative_to(source_root)
        except ValueError:
            relative = finding.path
        lines.append(f"| {finding.severity} | {finding.kind} | {relative} | {finding.detail} |")
    lines.append("")
    if report.has_high:
        lines.append("High severity findings block Apply by default.")
    return "\n".join(lines) + "\n"
