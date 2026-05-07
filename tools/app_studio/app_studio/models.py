from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


BUILD_MODES = {"auto", "app-env", "frozen-folder", "existing-exe"}
NORMAL_REGISTRATION_BUILD_MODE = "frozen-folder"
NORMAL_REGISTRATION_POLICY = "user-distribution"


@dataclass
class ImportOptions:
    entry: Path
    action: str
    app_id: str | None = None
    name: str | None = None
    build_mode: str = "auto"
    icon_prompt: str | None = None
    icon_style_preset: str | None = None
    icon_style_custom: str | None = None
    icon_revision_image_path: Path | None = None
    version: str = "0.1.0"
    create_app_env: bool = False
    rebuild_app_env: bool = False
    skip_app_env_build: bool = False
    generate_lock: bool = False
    skip_lock: bool = False
    build_frozen_folder: bool = False
    rebuild_frozen_folder: bool = False
    skip_frozen_build: bool = False
    verify_runtime: bool = False
    metadata_override_path: Path | None = None
    build_profile_path: Path | None = None


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
    status: str = ""
    detected_from: str = ""
    code_reference_file: str = ""
    detection_pattern: str = ""
    secret_scan: str = "not_scanned"

    def to_dict(self) -> dict[str, Any]:
        status = self.status or ("include" if self.include else "exclude")
        return {
            "path": str(self.path),
            "relative_path": self.relative_path,
            "size": self.size,
            "include": self.include,
            "status": status,
            "reason": self.reason,
            "category": self.category,
            "detected_from": self.detected_from,
            "code_reference_file": self.code_reference_file,
            "detection_pattern": self.detection_pattern,
            "secret_scan": self.secret_scan,
        }


@dataclass
class SourceInventory:
    records: list[FileRecord]
    local_import_files: list[Path] = field(default_factory=list)
    import_roots: list[str] = field(default_factory=list)
    manual_checks: list[dict[str, Any]] = field(default_factory=list)

    @property
    def included_files(self) -> list[Path]:
        return [record.path for record in self.records if record.include]

    def to_dict(self) -> dict[str, Any]:
        return {
            "files": [record.to_dict() for record in self.records],
            "local_import_files": [str(path) for path in self.local_import_files],
            "import_roots": self.import_roots,
            "manual_checks": self.manual_checks,
        }


@dataclass
class SecretFinding:
    path: Path
    kind: str
    severity: str
    detail: str
    included_in_package: bool = False
    included_reason: str = ""
    inventory_status: str = "unknown"
    affects_ai_submission: bool = False
    blocks_apply: bool = False
    block_reason: str = ""
    false_positive_candidate: bool = False
    recommended_action: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "kind": self.kind,
            "severity": self.severity,
            "detail": self.detail,
            "included_in_package": self.included_in_package,
            "included_reason": self.included_reason,
            "inventory_status": self.inventory_status,
            "affects_ai_submission": self.affects_ai_submission,
            "blocks_apply": self.blocks_apply,
            "block_reason": self.block_reason,
            "false_positive_candidate": self.false_positive_candidate,
            "recommended_action": self.recommended_action,
        }


@dataclass
class SecretScanReport:
    findings: list[SecretFinding]

    @property
    def has_high(self) -> bool:
        return any(finding.severity == "high" for finding in self.findings)

    @property
    def blocks_apply(self) -> bool:
        return any(finding.blocks_apply for finding in self.findings)

    @property
    def blocks_ai_submission(self) -> bool:
        return any(finding.affects_ai_submission and finding.severity in {"high", "medium"} for finding in self.findings)

    @property
    def blocking_findings(self) -> list[SecretFinding]:
        return [finding for finding in self.findings if finding.blocks_apply]

    @property
    def warning_findings(self) -> list[SecretFinding]:
        return [finding for finding in self.findings if not finding.blocks_apply and finding.severity in {"high", "medium"} and not finding.false_positive_candidate]

    @property
    def manual_check_findings(self) -> list[SecretFinding]:
        return [finding for finding in self.findings if not finding.blocks_apply and "manual" in finding.recommended_action.lower()]

    @property
    def false_positive_candidates(self) -> list[SecretFinding]:
        return [finding for finding in self.findings if finding.false_positive_candidate]

    def to_dict(self) -> dict[str, Any]:
        return {
            "findings": [finding.to_dict() for finding in self.findings],
            "summary": {
                "total_findings": len(self.findings),
                "high_findings": sum(1 for finding in self.findings if finding.severity == "high"),
                "blocking_findings": len(self.blocking_findings),
                "warning_findings": len(self.warning_findings),
                "manual_check_findings": len(self.manual_check_findings),
                "false_positive_candidates": len(self.false_positive_candidates),
                "included_package_findings": sum(1 for finding in self.findings if finding.included_in_package),
                "excluded_findings": sum(1 for finding in self.findings if finding.inventory_status == "exclude"),
                "ai_blocking_findings": sum(1 for finding in self.findings if finding.affects_ai_submission and finding.severity in {"high", "medium"}),
            },
        }


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
class IconDesignBrief:
    app_id: str
    name: str
    entry_name: str
    purpose: str
    app_kind: str
    primary_action: str
    secondary_action: str
    input_objects: list[str]
    output_objects: list[str]
    action_flow: str
    visual_priority: list[str]
    avoid_generic: list[str]
    composition_template: str
    primary_motif: str
    secondary_motifs: list[str]
    avoid: list[str]
    palette: str
    texture: str
    small_size_rule: str
    high_resolution_rule: str
    toolhub_style_rule: str
    categories: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    use_cases: list[str] = field(default_factory=list)
    inputs: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
    source_files: list[str] = field(default_factory=list)
    dependency_signals: list[str] = field(default_factory=list)
    readme_excerpt: str = ""
    style_reference: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "app_id": self.app_id,
            "name": self.name,
            "entry_name": self.entry_name,
            "purpose": self.purpose,
            "app_kind": self.app_kind,
            "primary_action": self.primary_action,
            "secondary_action": self.secondary_action,
            "input_objects": self.input_objects,
            "output_objects": self.output_objects,
            "action_flow": self.action_flow,
            "visual_priority": self.visual_priority,
            "avoid_generic": self.avoid_generic,
            "composition_template": self.composition_template,
            "primary_motif": self.primary_motif,
            "secondary_motifs": self.secondary_motifs,
            "avoid": self.avoid,
            "palette": self.palette,
            "texture": self.texture,
            "small_size_rule": self.small_size_rule,
            "high_resolution_rule": self.high_resolution_rule,
            "toolhub_style_rule": self.toolhub_style_rule,
            "categories": self.categories,
            "keywords": self.keywords,
            "use_cases": self.use_cases,
            "inputs": self.inputs,
            "outputs": self.outputs,
            "source_files": self.source_files,
            "dependency_signals": self.dependency_signals,
            "readme_excerpt": self.readme_excerpt,
            "style_reference": self.style_reference,
        }


@dataclass
class IconConcept:
    concept_id: str
    direction: str
    concept: str
    primary_motif: str
    secondary_motif: str
    composition: str
    style_family: str
    why_specific: str
    avoid_elements: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.concept_id,
            "direction": self.direction,
            "concept": self.concept,
            "primary_motif": self.primary_motif,
            "secondary_motif": self.secondary_motif,
            "composition": self.composition,
            "style_family": self.style_family,
            "why_specific": self.why_specific,
            "avoid_elements": self.avoid_elements,
        }


@dataclass
class IconCandidateAsset:
    candidate_id: str
    number: int
    source: str
    prompt: str
    model: str
    status: str
    resolution: str
    is_fallback: bool
    png: bytes | None = None
    url: str = ""
    file_name: str = ""
    url_file_name: str = ""
    notes: str = ""
    revision_of: str = ""
    api: str = ""
    content_type: str = ""
    fallback_reason: str = ""
    error_category: str = ""
    concept_id: str = ""
    concept: dict[str, Any] = field(default_factory=dict)
    scores: dict[str, float] = field(default_factory=dict)
    score_total: float = 0.0
    score_basis: str = "prompt_concept_only"
    semantic_score: float = 0.0
    specificity_score: float = 0.0
    small_size_score: float = 0.0
    aesthetic_score: float = 0.0
    revision_follow_score: float = 0.0
    generic_risk_score: float = 0.0
    quality_total: float = 0.0
    quality_label: str = ""
    quality_reasons: list[str] = field(default_factory=list)
    quality_warnings: list[str] = field(default_factory=list)
    image_evaluation_status: str = "not_run"
    image_evaluation_note: str = "Image pixels were not inspected by this rule-based score."

    def manifest_entry(self) -> dict[str, Any]:
        semantic_score = self.semantic_score or float(self.scores.get("semantic_clarity") or 0.0)
        specificity_score = self.specificity_score or float(self.scores.get("specificity") or 0.0)
        small_size_score = self.small_size_score or float(self.scores.get("small_size_legibility") or 0.0)
        aesthetic_score = self.aesthetic_score or float(self.scores.get("aesthetics") or 0.0)
        revision_follow_score = self.revision_follow_score or 0.0
        generic_risk_score = self.generic_risk_score or 0.0
        quality_total = self.quality_total or _quality_total(
            semantic_score,
            specificity_score,
            small_size_score,
            aesthetic_score,
            revision_follow_score,
            generic_risk_score,
        )
        quality_label = self.quality_label or _quality_label(quality_total)
        return {
            "candidate_id": self.candidate_id,
            "number": self.number,
            "source": self.source,
            "prompt": self.prompt,
            "model": self.model,
            "status": self.status,
            "resolution": self.resolution,
            "fallback": self.is_fallback,
            "file_name": self.file_name,
            "url_file_name": self.url_file_name,
            "url": self.url,
            "notes": self.notes,
            "revision_of": self.revision_of,
            "api": self.api,
            "content_type": self.content_type,
            "fallback_reason": self.fallback_reason,
            "error_category": self.error_category,
            "concept_id": self.concept_id,
            "concept": self.concept,
            "scores": self.scores,
            "score_total": self.score_total,
            "score_basis": self.score_basis,
            "semantic_score": round(semantic_score, 2),
            "specificity_score": round(specificity_score, 2),
            "small_size_score": round(small_size_score, 2),
            "aesthetic_score": round(aesthetic_score, 2),
            "revision_follow_score": round(revision_follow_score, 2),
            "generic_risk_score": round(generic_risk_score, 2),
            "quality_total": round(quality_total, 2),
            "quality_label": quality_label,
            "quality_reasons": self.quality_reasons,
            "quality_warnings": self.quality_warnings,
            "image_evaluation_status": self.image_evaluation_status,
            "image_evaluation_note": self.image_evaluation_note,
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
    icon_ai_report: str = ""
    icon_final_png: bytes | None = None
    icon_candidate_png: bytes | None = None
    icon_candidate_url: str = ""
    icon_candidates: list[IconCandidateAsset] = field(default_factory=list)
    icon_design_brief: dict[str, Any] = field(default_factory=dict)
    build_profile: dict[str, Any] | None = None
    exe_readiness: dict[str, Any] | None = None


@dataclass
class RuntimeCheck:
    name: str
    status: str
    detail: str
    approval_category: str = ""
    approval_blocking: bool = False
    resolved: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "detail": self.detail,
            "approval_category": approval_category_for_check(self.status, self.approval_category),
            "approval_blocking": self.approval_blocking or self.status == "fail",
            "resolved": self.resolved,
        }


@dataclass
class RuntimeCheckResult:
    app_id: str
    overall_status: str
    checks: list[RuntimeCheck]
    evidence: dict[str, Any] = field(default_factory=dict)
    approval_blocking_warnings_count: int = 0
    non_blocking_warnings_count: int = 0
    info_count: int = 0
    unresolved_distribution_risks_count: int = 0
    approval_blocking_reasons: list[str] = field(default_factory=list)
    non_blocking_warning_summaries: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "app_id": self.app_id,
            "overall_status": self.overall_status,
            "checks": [check.to_dict() for check in self.checks],
            "evidence": self.evidence,
            "approval_blocking_warnings_count": self.approval_blocking_warnings_count,
            "non_blocking_warnings_count": self.non_blocking_warnings_count,
            "info_count": self.info_count,
            "unresolved_distribution_risks_count": self.unresolved_distribution_risks_count,
            "approval_blocking_reasons": self.approval_blocking_reasons,
            "non_blocking_warning_summaries": self.non_blocking_warning_summaries,
        }


@dataclass
class AppEnvBuildResult:
    ok: bool
    skipped: bool
    app_env_path: Path
    python_path: Path | None
    python_source: str
    report: str
    error: str = ""


@dataclass
class LockGenerationResult:
    ok: bool
    skipped: bool
    lock_path: Path
    source: str
    report: str
    error: str = ""


@dataclass
class FrozenBuildResult:
    ok: bool
    skipped: bool
    exe_path: Path | None
    report: str
    command: list[str] = field(default_factory=list)
    error: str = ""


@dataclass
class ExecutionCheck:
    name: str
    status: str
    detail: str
    approval_category: str = ""
    approval_blocking: bool = False
    resolved: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "detail": self.detail,
            "approval_category": approval_category_for_check(self.status, self.approval_category),
            "approval_blocking": self.approval_blocking or self.status == "fail",
            "resolved": self.resolved,
        }


@dataclass
class ExecutionTestResult:
    app_id: str
    generated_at: str
    overall_status: str
    approval_allowed: bool
    checks: list[ExecutionCheck]
    evidence: dict[str, Any] = field(default_factory=dict)
    approval_blocking_warnings_count: int = 0
    non_blocking_warnings_count: int = 0
    info_count: int = 0
    unresolved_distribution_risks_count: int = 0
    approval_blocking_reasons: list[str] = field(default_factory=list)
    non_blocking_warning_summaries: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "app_id": self.app_id,
            "generated_at": self.generated_at,
            "overall_status": self.overall_status,
            "approval_allowed": self.approval_allowed,
            "checks": [check.to_dict() for check in self.checks],
            "evidence": self.evidence,
            "approval_blocking_warnings_count": self.approval_blocking_warnings_count,
            "non_blocking_warnings_count": self.non_blocking_warnings_count,
            "info_count": self.info_count,
            "unresolved_distribution_risks_count": self.unresolved_distribution_risks_count,
            "approval_blocking_reasons": self.approval_blocking_reasons,
            "non_blocking_warning_summaries": self.non_blocking_warning_summaries,
        }


def approval_category_for_check(status: str, explicit: str = "") -> str:
    if explicit:
        return explicit
    if status == "fail":
        return "fail"
    if status == "warn":
        return "non_blocking_warning"
    return "info"


def _quality_total(
    semantic_score: float,
    specificity_score: float,
    small_size_score: float,
    aesthetic_score: float,
    revision_follow_score: float,
    generic_risk_score: float,
) -> float:
    positive = semantic_score + specificity_score + small_size_score + aesthetic_score + revision_follow_score
    generic_penalty_balance = max(0.0, 10.0 - generic_risk_score)
    return max(0.0, min(100.0, ((positive + generic_penalty_balance) / 60.0) * 100.0))


def _quality_label(total: float) -> str:
    if total >= 82:
        return "excellent"
    if total >= 68:
        return "good"
    if total >= 52:
        return "usable"
    return "weak"
