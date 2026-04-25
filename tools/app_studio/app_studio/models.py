from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


BUILD_MODES = {"auto", "app-env", "frozen-folder", "existing-exe"}


@dataclass
class ImportOptions:
    entry: Path
    action: str
    app_id: str | None = None
    name: str | None = None
    build_mode: str = "auto"
    icon_prompt: str | None = None
    version: str = "0.1.0"


@dataclass
class StudioContext:
    repo_root: Path
    entry: Path
    source_root: Path
    app_id: str
    name: str
    output_dir: Path
    requested_build_mode: str
    build_mode: str
    version: str = "0.1.0"

    @property
    def entry_relative(self) -> Path:
        return self.entry.relative_to(self.source_root)


@dataclass
class FileRecord:
    path: Path
    relative_path: str
    size: int
    include: bool
    reason: str
    category: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "relative_path": self.relative_path,
            "size": self.size,
            "include": self.include,
            "reason": self.reason,
            "category": self.category,
        }


@dataclass
class SourceInventory:
    records: list[FileRecord]
    local_import_files: list[Path] = field(default_factory=list)
    import_roots: list[str] = field(default_factory=list)

    @property
    def included_files(self) -> list[Path]:
        return [record.path for record in self.records if record.include]

    def to_dict(self) -> dict[str, Any]:
        return {
            "files": [record.to_dict() for record in self.records],
            "local_import_files": [str(path) for path in self.local_import_files],
            "import_roots": self.import_roots,
        }


@dataclass
class SecretFinding:
    path: Path
    kind: str
    severity: str
    detail: str

    def to_dict(self) -> dict[str, str]:
        return {
            "path": str(self.path),
            "kind": self.kind,
            "severity": self.severity,
            "detail": self.detail,
        }


@dataclass
class SecretScanReport:
    findings: list[SecretFinding]

    @property
    def has_high(self) -> bool:
        return any(finding.severity == "high" for finding in self.findings)

    def to_dict(self) -> dict[str, Any]:
        return {"findings": [finding.to_dict() for finding in self.findings]}


@dataclass
class DependencyReport:
    source: str
    requirements: list[str]
    import_roots: list[str]
    third_party_candidates: list[str]
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "requirements": self.requirements,
            "import_roots": self.import_roots,
            "third_party_candidates": self.third_party_candidates,
            "notes": self.notes,
        }


@dataclass
class BuildPlan:
    mode: str
    runner: str
    entry: str
    required_runtime: str | None
    reasons: list[str]
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "runner": self.runner,
            "entry": self.entry,
            "required_runtime": self.required_runtime,
            "reasons": self.reasons,
            "warnings": self.warnings,
        }


@dataclass
class GeneratedArtifacts:
    metadata: dict[str, Any]
    app_yaml: str
    readme: str
    requirements: str
    icon_prompt_initial: str
    icon_prompt_revision: str
    icon_svg: str
    build_plan_md: str
    import_plan: dict[str, Any]

