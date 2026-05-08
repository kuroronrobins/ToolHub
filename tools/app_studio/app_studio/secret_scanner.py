from __future__ import annotations

import fnmatch
import os
import re
from pathlib import Path
from typing import Any

from .models import FileRecord, SecretFinding, SecretScanReport, SourceInventory


BLOCKED_NAME_PATTERNS = [".env", ".env.*", "*.key", "*.pem"]
BLOCKED_EXACT_NAMES = {
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
WARNING_PATTERNS = ["*.log", "*.wav", "*.mp3", "*.m4a"]
LARGE_FILE_BYTES = 25 * 1024 * 1024
TEXT_SCAN_LIMIT = 1024 * 1024
SKIP_DIRS = {
    ".git",
    ".hg",
    ".mypy_cache",
    ".pytest_cache",
    ".svn",
    ".venv",
    "build",
    "dist",
    "env",
    "node_modules",
    "output",
    "outputs",
    "release",
    "result",
    "results",
    "runtime",
    "target",
    "toolhub_appstudio_output",
    "venv",
    "work",
    "works",
    "__pycache__",
    ".pytest_tmp",
}
EXCLUDED_SENSITIVE_DIRS = {".auth"}
WARNING_DIRS = {"logs", "log", "screenshots", "sessions", "tmp", "temp"}
PLACEHOLDER_VALUES = {
    "",
    "-",
    "dummy",
    "example",
    "placeholder",
    "sample",
    "test",
    "todo",
    "none",
    "null",
    "your-key",
    "your_key",
    "your-api-key",
    "your_api_key",
    "your-token",
    "your_token",
    "<your key>",
    "<your-key>",
    "<api key>",
    "<api-key>",
    "<token>",
    "<password>",
    "xxxx",
    "xxxxx",
    "****",
    "********",
}

ASSIGNMENT_RE = re.compile(
    r"(?im)^\s*(?:export\s+)?(?P<name>openai_api_key|api[_-]?key|token|password|secret|client[_-]?secret|credentials?)\s*[:=]\s*(?P<value>[^\r\n#]*)"
)
OPENAI_ENV_RE = re.compile(r"\bOPENAI_API_KEY\b", re.IGNORECASE)
PRIVATE_KEY_RE = re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----")
JWT_RE = re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")
OPENAI_KEY_RE = re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")
LONG_RANDOM_RE = re.compile(r"\b[A-Za-z0-9_/-]{32,}\b")


def scan_secrets(source_root: Path, inventory: SourceInventory | None = None) -> SecretScanReport:
    findings: list[SecretFinding] = []
    inventory_by_path = inventory_map(inventory)
    scan_files = iter_inventory_scan_files(inventory) if inventory else iter_scan_files(source_root)
    for path in scan_files:
        if not path.is_file() or should_skip(path, source_root):
            continue
        lower_parts = {part.lower() for part in path.relative_to(source_root).parts}
        name = path.name.lower()

        if lower_parts & EXCLUDED_SENSITIVE_DIRS:
            findings.append(
                enrich_finding(
                    path,
                    source_root,
                    inventory_by_path,
                    kind="excluded-sensitive-directory",
                    severity="medium",
                    detail="Sensitive auth/session directory is excluded from packaging and must not be bundled.",
                    recommended_action="manual_check: keep this directory outside source packages and do not add it to build_profile.add_data.",
                )
            )
            continue
        if lower_parts & WARNING_DIRS:
            findings.append(
                enrich_finding(
                    path,
                    source_root,
                    inventory_by_path,
                    kind="excluded-runtime-user-data",
                    severity="medium",
                    detail="Runtime output, logs, screenshots, sessions, or temp files are excluded from packaging.",
                    recommended_action="manual_check: confirm runtime output is not referenced by code or add_data.",
                )
            )

        for pattern in BLOCKED_NAME_PATTERNS:
            if fnmatch.fnmatch(name, pattern.lower()):
                findings.append(
                    enrich_finding(
                        path,
                        source_root,
                        inventory_by_path,
                        kind="unsafe-filename",
                        severity="high",
                        detail=f"Unsafe credential filename pattern matched: {pattern}",
                        recommended_action="Remove this file from the app source or replace it with a documented placeholder outside the package.",
                    )
                )
                break
        if name in BLOCKED_EXACT_NAMES:
            findings.append(
                enrich_finding(
                    path,
                    source_root,
                    inventory_by_path,
                    kind="credential-state-file",
                    severity="high",
                    detail=f"Credential, cookie, session, token, or storage-state filename matched: {name}",
                    recommended_action="Move real credential/session state outside the app source. Do not package authenticated state.",
                )
            )

        if any(fnmatch.fnmatch(name, pattern.lower()) for pattern in WARNING_PATTERNS):
            findings.append(
                enrich_finding(
                    path,
                    source_root,
                    inventory_by_path,
                    kind="personal-or-binary-data",
                    severity="medium",
                    detail="Log or recording-like file should not be bundled.",
                    recommended_action="manual_check: keep logs and recordings outside the source package.",
                )
            )
        size = path.stat().st_size
        if size >= LARGE_FILE_BYTES:
            findings.append(
                enrich_finding(
                    path,
                    source_root,
                    inventory_by_path,
                    kind="large-file",
                    severity="medium",
                    detail=f"Large file warning: {size} bytes.",
                    recommended_action="manual_check: confirm this large file is required at runtime before packaging.",
                )
            )
        if size <= TEXT_SCAN_LIMIT and is_probably_text(path):
            text = path.read_text(encoding="utf-8", errors="replace")
            findings.extend(content_findings(path, source_root, inventory_by_path, text))

    report = SecretScanReport(deduplicate_findings(findings))
    apply_secret_summary_to_inventory(report, inventory_by_path)
    return report


def iter_inventory_scan_files(inventory: SourceInventory | None) -> list[Path]:
    if not inventory:
        return []
    files: list[Path] = []
    for record in inventory.records:
        status = record.status or ("include" if record.include else "exclude")
        if record.include or status in {"blocked", "manual_check"} or record.secret_scan != "not_scanned":
            files.append(record.path)
    return sorted(files, key=lambda path: path.as_posix().lower())


def iter_scan_files(source_root: Path) -> list[Path]:
    files: list[Path] = []
    for root, dirnames, filenames in os.walk(source_root):
        dirnames[:] = [
            dirname
            for dirname in dirnames
            if dirname.lower() not in SKIP_DIRS and not dirname.lower().startswith("pytest-cache-files-")
        ]
        current = Path(root)
        files.extend(current / filename for filename in filenames)
    return sorted(files, key=lambda path: path.as_posix().lower())


def inventory_map(inventory: SourceInventory | None) -> dict[Path, FileRecord]:
    if not inventory:
        return {}
    return {record.path.resolve(): record for record in inventory.records}


def content_findings(path: Path, source_root: Path, inventory_by_path: dict[Path, FileRecord], text: str) -> list[SecretFinding]:
    findings: list[SecretFinding] = []
    if PRIVATE_KEY_RE.search(text):
        findings.append(
            enrich_finding(
                path,
                source_root,
                inventory_by_path,
                kind="private-key-content",
                severity="high",
                detail="Private key block was detected in file content.",
                recommended_action="Remove the private key and load credentials from a user-controlled location.",
            )
        )
    if OPENAI_KEY_RE.search(text):
        findings.append(
            enrich_finding(
                path,
                source_root,
                inventory_by_path,
                kind="secret-value",
                severity="high",
                detail="OpenAI-style API key value was detected.",
                recommended_action="Revoke/remove the key and replace it with environment or credential-store loading.",
            )
        )
    if JWT_RE.search(text):
        findings.append(
            enrich_finding(
                path,
                source_root,
                inventory_by_path,
                kind="secret-value",
                severity="high",
                detail="JWT-like token value was detected.",
                recommended_action="Remove runtime tokens or authenticated session state from the source package.",
            )
        )

    assignment_count = 0
    for match in ASSIGNMENT_RE.finditer(text):
        assignment_count += 1
        name = match.group("name")
        raw_value = match.group("value")
        value = clean_secret_value(raw_value)
        if is_placeholder_value(value):
            findings.append(
                enrich_finding(
                    path,
                    source_root,
                    inventory_by_path,
                    kind="placeholder-secret-reference",
                    severity="medium",
                    detail=f"{name} is assigned a placeholder or empty value.",
                    false_positive_candidate=True,
                    recommended_action="No immediate Apply block. Keep placeholders obvious, e.g. <your key>, and load real values at runtime.",
                )
            )
        elif looks_like_real_secret(value):
            findings.append(
                enrich_finding(
                    path,
                    source_root,
                    inventory_by_path,
                    kind="secret-value",
                    severity="high",
                    detail=f"{name} appears to contain a real secret value.",
                    recommended_action="Remove or rotate the value. Use environment variables or a credential store instead.",
                )
            )
        else:
            findings.append(
                enrich_finding(
                    path,
                    source_root,
                    inventory_by_path,
                    kind="manual-check-secret-assignment",
                    severity="medium",
                    detail=f"{name} has a non-empty value that is not clearly a placeholder.",
                    recommended_action="manual_check: verify this value is not a real credential before distribution.",
                )
            )

    if assignment_count == 0 and OPENAI_ENV_RE.search(text):
        findings.append(
            enrich_finding(
                path,
                source_root,
                inventory_by_path,
                kind="env-var-reference",
                severity="medium",
                detail="OPENAI_API_KEY is referenced as an environment variable name, but no key value was detected.",
                false_positive_candidate=True,
                recommended_action="No immediate Apply block. Documentation-only references are acceptable; AI generation may fall back.",
            )
        )
    return findings


def enrich_finding(
    path: Path,
    source_root: Path,
    inventory_by_path: dict[Path, FileRecord],
    *,
    kind: str,
    severity: str,
    detail: str,
    false_positive_candidate: bool = False,
    recommended_action: str = "",
) -> SecretFinding:
    record = inventory_by_path.get(path.resolve())
    inventory_status = record.status if record else "unknown"
    included = bool(record.include) if record else False
    included_reason = record.reason if record else ""
    affects_ai = affects_ai_submission(path, source_root, record)
    blocks, block_reason = apply_block_decision(kind, severity, included, inventory_status, false_positive_candidate)
    if not recommended_action:
        recommended_action = default_recommended_action(blocks, inventory_status, false_positive_candidate)
    return SecretFinding(
        path=path.resolve(),
        kind=kind,
        severity=severity,
        detail=detail,
        included_in_package=included,
        included_reason=included_reason,
        inventory_status=inventory_status,
        affects_ai_submission=affects_ai,
        blocks_apply=blocks,
        block_reason=block_reason,
        false_positive_candidate=false_positive_candidate,
        recommended_action=recommended_action,
    )


def apply_block_decision(kind: str, severity: str, included: bool, inventory_status: str, false_positive_candidate: bool) -> tuple[bool, str]:
    if false_positive_candidate:
        return False, "placeholder or documentation-only reference"
    if inventory_status == "blocked":
        return True, "file_inventory marks this file as blocked"
    if severity != "high":
        return False, "not a high severity finding"
    if included:
        return True, "high severity finding is included in the package"
    if inventory_status in {"manual_check", "unknown"}:
        return True, "high severity finding is not proven to be excluded from package or AI input"
    if kind in {"unsafe-filename", "credential-state-file", "private-key-content"} and inventory_status != "exclude":
        return True, "credential-like file is not safely excluded"
    return False, "file_inventory excludes this file from the package"


def affects_ai_submission(path: Path, source_root: Path, record: FileRecord | None) -> bool:
    try:
        relative = path.relative_to(source_root)
    except ValueError:
        relative = path
    lower_name = path.name.lower()
    lower_parts = {part.lower() for part in relative.parts}
    if lower_name in {"readme.md", "readme.txt"}:
        return True
    if "docs" in lower_parts and path.suffix.lower() in {".md", ".txt"}:
        return True
    if record and record.include and path.suffix.lower() in {".md", ".txt", ".py", ".json", ".yaml", ".yml", ".toml", ".ini"}:
        return True
    return False


def default_recommended_action(blocks: bool, inventory_status: str, false_positive_candidate: bool) -> str:
    if blocks:
        return "Remove the secret, move it outside the source package, or replace it with a safe placeholder."
    if false_positive_candidate:
        return "Keep the placeholder/documentation wording clear; no Apply block is required."
    if inventory_status == "exclude":
        return "manual_check: confirm the excluded file is not referenced by build_profile.add_data."
    return "manual_check: review this finding before approval."


def clean_secret_value(raw_value: str) -> str:
    value = raw_value.strip().strip(",")
    if value.startswith(("'", '"')) and value.endswith(("'", '"')) and len(value) >= 2:
        value = value[1:-1]
    return value.strip()


def is_placeholder_value(value: str) -> bool:
    normalized = value.strip().strip("\"'").lower()
    if normalized in PLACEHOLDER_VALUES:
        return True
    if not normalized:
        return True
    if normalized.startswith("<") and normalized.endswith(">"):
        return True
    if set(normalized) <= {"*", "x", "X", "_", "-"}:
        return True
    return any(marker in normalized for marker in ["your key", "your-key", "dummy", "example", "placeholder", "sample"])


def looks_like_real_secret(value: str) -> bool:
    if not value or is_placeholder_value(value):
        return False
    if OPENAI_KEY_RE.search(value) or JWT_RE.search(value):
        return True
    if len(value) < 20 or any(ch.isspace() for ch in value):
        return False
    if value.startswith(("http://", "https://", "file://")):
        return False
    if LONG_RANDOM_RE.fullmatch(value):
        has_alpha = any(ch.isalpha() for ch in value)
        has_digit = any(ch.isdigit() for ch in value)
        return has_alpha and has_digit
    return False


def deduplicate_findings(findings: list[SecretFinding]) -> list[SecretFinding]:
    result: list[SecretFinding] = []
    seen: set[tuple[str, str, str, str]] = set()
    for finding in findings:
        key = (str(finding.path).lower(), finding.kind, finding.severity, finding.detail)
        if key in seen:
            continue
        seen.add(key)
        result.append(finding)
    return result


def apply_secret_summary_to_inventory(report: SecretScanReport, inventory_by_path: dict[Path, FileRecord]) -> None:
    by_path: dict[Path, list[SecretFinding]] = {}
    for finding in report.findings:
        by_path.setdefault(finding.path.resolve(), []).append(finding)
    for path, findings in by_path.items():
        record = inventory_by_path.get(path)
        if not record:
            continue
        if any(finding.blocks_apply for finding in findings):
            record.secret_scan = "blocked"
        elif any(finding.severity == "high" for finding in findings):
            record.secret_scan = "manual_check"
        elif any(finding.false_positive_candidate for finding in findings):
            record.secret_scan = "false_positive_candidate"
        else:
            record.secret_scan = "warning"


def should_skip(path: Path, source_root: Path) -> bool:
    parts = {part.lower() for part in path.relative_to(source_root).parts}
    if parts & SKIP_DIRS:
        return True
    return any(part.startswith("pytest-cache-files-") for part in parts)


def is_probably_text(path: Path) -> bool:
    try:
        sample = path.read_bytes()[:4096]
    except OSError:
        return False
    return b"\x00" not in sample


def secret_report_markdown(report: SecretScanReport, source_root: Path) -> str:
    summary = report.to_dict()["summary"]
    lines = [
        "# Secret Scan Report",
        "",
        "## Summary",
        "",
        f"- total findings: {summary['total_findings']}",
        f"- blocking findings: {summary['blocking_findings']}",
        f"- warning findings: {summary['warning_findings']}",
        f"- manual check findings: {summary['manual_check_findings']}",
        f"- false positive candidates: {summary['false_positive_candidates']}",
        f"- included package findings: {summary['included_package_findings']}",
        f"- excluded findings: {summary['excluded_findings']}",
        f"- AI submission blocked: {str(report.blocks_ai_submission).lower()}",
        f"- Apply blocked: {str(report.blocks_apply).lower()}",
        "",
        "Secret scan remains enabled. Apply is blocked only when a finding can affect the packaged app, AI submission safety, or cannot be proven excluded.",
        "",
    ]
    if not report.findings:
        lines.append("No secret-like files or values were detected.")
        return "\n".join(lines) + "\n"

    append_finding_section(lines, "Blocking Findings", report.blocking_findings, source_root)
    append_finding_section(lines, "Warnings / Manual Checks", [item for item in report.findings if not item.blocks_apply and not item.false_positive_candidate and item.inventory_status != "exclude"], source_root)
    append_finding_section(lines, "Excluded from Package", [item for item in report.findings if item.inventory_status == "exclude"], source_root)
    append_finding_section(lines, "False Positive Candidates", report.false_positive_candidates, source_root)

    lines.extend(
        [
            "## Recommended Actions",
            "",
            "- Remove real secrets from source files and load them from environment variables or a credential store at runtime.",
            "- Keep placeholders explicit, for example `<your key>` or `dummy`, when documenting configuration.",
            "- Keep logs, sessions, screenshots, `.auth`, storage state, cookies, and temp files outside packaged inputs.",
            "- If a warning is intentionally excluded, confirm it is not referenced by build_profile.add_data.",
            "",
        ]
    )
    return "\n".join(lines) + "\n"


def append_finding_section(lines: list[str], title: str, findings: list[SecretFinding], source_root: Path) -> None:
    lines.extend([f"## {title}", ""])
    if not findings:
        lines.extend(["none", ""])
        return
    lines.append("| Severity | Kind | Path | Inventory | Included | Blocks Apply | Detail | Reason | Action |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for finding in findings:
        lines.append(
            "| "
            + " | ".join(
                [
                    finding.severity,
                    finding.kind,
                    relative_path(finding.path, source_root),
                    finding.inventory_status,
                    str(finding.included_in_package).lower(),
                    str(finding.blocks_apply).lower(),
                    clean_table_text(finding.detail),
                    clean_table_text(finding.block_reason or "-"),
                    clean_table_text(finding.recommended_action or "-"),
                ]
            )
            + " |"
        )
    lines.append("")


def relative_path(path: Path, source_root: Path) -> str:
    try:
        return path.relative_to(source_root).as_posix()
    except ValueError:
        return str(path)


def clean_table_text(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\r", " ").replace("\n", " ")
