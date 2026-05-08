export type AppStudioBuildMode = "auto" | "app-env" | "frozen-folder" | "existing-exe";

export interface AppStudioImportRequest {
  entry: string;
  sourceRoot?: string;
  appId?: string;
  name?: string;
  version?: string;
  buildMode: AppStudioBuildMode;
  iconPrompt?: string;
  iconStylePreset?: AppStudioIconStylePreset;
  iconStyleCustom?: string;
  iconRevisionImage?: string;
  metadata?: AppStudioEditableMetadata;
  iconOverride?: AppStudioIconOverride;
  buildProfile?: AppStudioBuildProfile;
  createAppEnv: boolean;
  rebuildAppEnv: boolean;
  generateLock: boolean;
  buildFrozenFolder: boolean;
  verifyRuntime: boolean;
}

export interface AppStudioUpdateRequest {
  appId: string;
  entry: string;
  name?: string;
  currentVersion?: string;
  newVersion: string;
  buildMode: AppStudioBuildMode;
  iconPrompt?: string;
  iconStylePreset?: AppStudioIconStylePreset;
  iconStyleCustom?: string;
  iconRevisionImage?: string;
  metadata?: AppStudioEditableMetadata;
  iconOverride?: AppStudioIconOverride;
  buildProfile?: AppStudioBuildProfile;
  createAppEnv: boolean;
  rebuildAppEnv: boolean;
  generateLock: boolean;
  buildFrozenFolder: boolean;
  verifyRuntime: boolean;
}

export interface AppStudioRegisteredApp {
  appId: string;
  name: string;
  version: string;
  enabled: boolean;
  buildMode?: string | null;
  runner?: string | null;
  entry?: string | null;
  description?: string | null;
  warning?: string | null;
}

export type AppStudioManagementStatus =
  | "active"
  | "disabled_with_source"
  | "disabled_stale"
  | "enabled_missing_source"
  | "source_missing_from_manifest"
  | "invalid_manifest"
  | string;

export interface AppStudioManagedApp {
  appId: string;
  name: string;
  version?: string | null;
  enabled?: boolean | null;
  managementStatus: AppStudioManagementStatus;
  hasSource: boolean;
  sourceDir: string;
  appYamlPath: string;
  packagePath?: string | null;
  packageExists: boolean;
  deletePlanStatus: "ready" | "blocked" | string;
  deleteTargetCount: number;
  excludedTargetCount: number;
  warning?: string | null;
  recommendedAction: string;
}

export interface AppStudioDeletePlanTarget {
  category: string;
  path: string;
  normalizedPath: string;
  exists: boolean;
  deleteAllowed: boolean;
  action: string;
  comparisonKey: string;
  note: string;
}

export interface AppStudioDeletePlan {
  appId: string;
  sourceDir: string;
  appYaml: string;
  manifestEntryExists: boolean;
  manifestEnabled?: boolean | null;
  manifestVersion?: string | null;
  manifestPackage?: string | null;
  appPackPaths: string[];
  stagingPaths: string[];
  stagingCandidatePaths: string[];
  runtimeAppEnv: string;
  appStudioBackupPaths: string[];
  lifecycleBackupPaths: string[];
  externalReferences: AppStudioDeletePlanTarget[];
  userDataPaths: AppStudioDeletePlanTarget[];
  deleteTargets: AppStudioDeletePlanTarget[];
  excludedTargets: AppStudioDeletePlanTarget[];
  warnings: string[];
  blockingReasons: string[];
}

export interface AppStudioManagementActionResult {
  ok: boolean;
  message: string;
  apps: AppStudioManagedApp[];
  target?: AppStudioManagedApp | null;
}

export interface AppStudioFullDeleteRecord {
  category: string;
  action: string;
  path: string;
  normalizedPath: string;
  comparisonKey: string;
  status: string;
  note: string;
}

export interface AppStudioFullDeletePostCheckSummary {
  manifestJsonValid: boolean;
  manifestEntryPresent: boolean;
  remainingDeleteTargetCount: number;
  remainingDeleteTargets: string[];
}

export interface AppStudioFullDeleteResult {
  ok: boolean;
  message: string;
  appId: string;
  deleted: AppStudioFullDeleteRecord[];
  alreadyClean: AppStudioFullDeleteRecord[];
  skipped: AppStudioFullDeleteRecord[];
  excluded: AppStudioDeletePlanTarget[];
  failed: AppStudioFullDeleteRecord[];
  manifestEntryRemoved: boolean;
  postCheckSummary: AppStudioFullDeletePostCheckSummary;
  apps: AppStudioManagedApp[];
}

export interface AppStudioRunResult {
  ok: boolean;
  exitCode: number;
  stdout: string;
  stderr: string;
  userMessage: string;
  outputDir?: string | null;
  appId?: string | null;
  selectedBuildMode?: string | null;
  executionStatus?: "pass" | "warn" | "fail" | "unknown" | string | null;
  approvalAllowed?: boolean | null;
  runtimeStatus?: "pass" | "warn" | "fail" | "unknown" | string | null;
  appPack?: string | null;
  enabled?: boolean | null;
  currentVersion?: string | null;
  newVersion?: string | null;
  metadataOverrideUsed?: boolean;
  metadataOverrideKeys?: string[];
  iconOverrideUsed?: boolean;
  selectedIconSource?: AppStudioSelectedIconSource | string | null;
  exeReadinessStatus?: "pass" | "warn" | "fail" | "unknown" | string | null;
  manualChecks?: string[];
  secretBlockingCount?: number;
  secretWarningCount?: number;
  secretManualCheckCount?: number;
  secretScanReport?: string | null;
  secretBlockingFindings?: string[];
  aiBlockedBySecretScan?: boolean;
  applyBlockedBySecretScan?: boolean;
  approvalBlockingWarningsCount?: number;
  nonBlockingWarningsCount?: number;
  infoCount?: number;
  unresolvedDistributionRisksCount?: number;
  approvalBlockingReasons?: string[];
  nonBlockingWarningSummaries?: string[];
  timingReport?: string | null;
  timingTotalSeconds?: number | null;
  timingEstimatedTotalSeconds?: number | null;
  timingActualTotalSeconds?: number | null;
  timingPredictionErrorSeconds?: number | null;
  timingPredictionSource?: string | null;
  timingWallClockTotalSeconds?: number | null;
  timingCliMeasuredTotalSeconds?: number | null;
  timingUnmeasuredOverheadSeconds?: number | null;
  timingPhases?: AppStudioTimingPhase[];
  processWallClockSeconds?: number | null;
  manifestEnabled?: boolean | null;
  approvalRecordStatus?: string | null;
  approvalRecordPath?: string | null;
  approvalFailureSummary?: string | null;
  verifyReleaseStatus?: string | null;
  verifyReleaseFailureSummary?: string | null;
  catalogVisible?: boolean | null;
  catalogEnabled?: boolean | null;
  catalogDisabledReason?: string | null;
  catalogLoadError?: string | null;
  catalogRoot?: string | null;
  appStudioRepoRoot?: string | null;
}

export interface AppStudioPreflightResult {
  ok: boolean;
  entryExists: boolean;
  appIdValid: boolean;
  buildModeValid: boolean;
  pythonSource: "runtime" | "python" | "py" | "missing" | string;
  pythonPath?: string | null;
  runtimePythonExists: boolean;
  warnings: string[];
  errors: string[];
}

export interface AppStudioResultSummary {
  appId?: string | null;
  outputDir?: string | null;
  selectedBuildMode?: string | null;
  executionStatus?: string | null;
  approvalAllowed?: boolean | null;
  runtimeStatus?: string | null;
  appPack?: string | null;
  enabled?: boolean | null;
  version?: string | null;
  metadataOverrideUsed?: boolean;
  metadataOverrideKeys?: string[];
  iconOverrideUsed?: boolean;
  selectedIconSource?: AppStudioSelectedIconSource | string | null;
  exeReadinessStatus?: "pass" | "warn" | "fail" | "unknown" | string | null;
  manualChecks?: string[];
  secretBlockingCount?: number;
  secretWarningCount?: number;
  secretManualCheckCount?: number;
  secretScanReport?: string | null;
  secretBlockingFindings?: string[];
  aiBlockedBySecretScan?: boolean;
  applyBlockedBySecretScan?: boolean;
  approvalBlockingWarningsCount?: number;
  nonBlockingWarningsCount?: number;
  infoCount?: number;
  unresolvedDistributionRisksCount?: number;
  approvalBlockingReasons?: string[];
  nonBlockingWarningSummaries?: string[];
  timingReport?: string | null;
  timingTotalSeconds?: number | null;
  timingEstimatedTotalSeconds?: number | null;
  timingActualTotalSeconds?: number | null;
  timingPredictionErrorSeconds?: number | null;
  timingPredictionSource?: string | null;
  timingWallClockTotalSeconds?: number | null;
  timingCliMeasuredTotalSeconds?: number | null;
  timingUnmeasuredOverheadSeconds?: number | null;
  timingPhases?: AppStudioTimingPhase[];
  processWallClockSeconds?: number | null;
  manifestEnabled?: boolean | null;
  approvalRecordStatus?: string | null;
  approvalRecordPath?: string | null;
  approvalFailureSummary?: string | null;
  verifyReleaseStatus?: string | null;
  verifyReleaseFailureSummary?: string | null;
  catalogVisible?: boolean | null;
  catalogEnabled?: boolean | null;
  catalogDisabledReason?: string | null;
  catalogLoadError?: string | null;
  catalogRoot?: string | null;
  appStudioRepoRoot?: string | null;
}

export interface AppStudioTimingPhase {
  phase: string;
  label: string;
  status: string;
  durationSeconds?: number | null;
}

export interface AppStudioEditableMetadata {
  shortDescription?: string;
  description?: string;
  categories?: string[];
  keywords?: string[];
  examples?: string[];
  useCases?: string[];
  inputs?: string[];
  outputs?: string[];
  notes?: string[];
  releaseNotes?: string[];
  changeSummary?: string;
}

export interface AppStudioBuildProfileFileMapping {
  source: string;
  destination: string;
}

export interface AppStudioBuildProfile {
  paths?: string[];
  hidden_imports?: string[];
  add_data?: AppStudioBuildProfileFileMapping[];
  add_binaries?: AppStudioBuildProfileFileMapping[];
  collect_all?: string[];
  runtime_cwd?: string | null;
  environment?: Record<string, string>;
  required_files?: string[];
  manual_checks?: string[];
}

export type AppStudioSelectedIconSource = "candidate_png" | "final_png" | "fallback_png" | "default_icon" | "uploaded_png" | "ai_candidate_png";
export type AppStudioIconStylePreset = "user_prompt" | "modern" | "vivid" | "realistic" | "colored_pencil" | "watercolor" | "flat_vector" | "3d_soft" | "glassmorphism" | "clay" | "custom";

export interface AppStudioIconOverride {
  selectedIconSource: AppStudioSelectedIconSource;
  pngDataUrl?: string;
  candidateId?: string;
  sourcePrompt?: string;
}

export interface AppStudioAiMetadataSuggestion {
  appId?: string | null;
  name?: string | null;
  shortDescription?: string | null;
  description?: string | null;
  categories: string[];
  keywords: string[];
  examples: string[];
  useCases: string[];
  inputs: string[];
  outputs: string[];
  notes: string[];
  iconPrompt?: string | null;
  releaseNotes: string[];
  changeSummary?: string | null;
  aiReport?: string | null;
}

export interface AppStudioAiIconSuggestion {
  promptInitial?: string | null;
  promptRevision?: string | null;
  functionInterpretation?: AppStudioIconFunctionInterpretation | null;
  imageApiSummary?: AppStudioImageApiSummary | null;
  candidateSvg?: string | null;
  finalSvg?: string | null;
  fallbackSvg?: string | null;
  candidatePngDataUrl?: string | null;
  finalPngDataUrl?: string | null;
  candidateUrl?: string | null;
  candidates: AppStudioAiIconCandidate[];
  aiReport?: string | null;
}

export interface AppStudioAiIconCandidate {
  candidateId: string;
  number: number;
  source: string;
  prompt?: string | null;
  model?: string | null;
  status?: string | null;
  resolution?: string | null;
  fallback: boolean;
  fileName?: string | null;
  urlFileName?: string | null;
  pngDataUrl?: string | null;
  url?: string | null;
  notes?: string | null;
  revisionOf?: string | null;
  api?: string | null;
  contentType?: string | null;
  fallbackReason?: string | null;
  errorCategory?: string | null;
  conceptId?: string | null;
  concept?: AppStudioIconConcept | null;
  styleFamily?: string | null;
  scores?: AppStudioIconScores | null;
  scoreTotal?: number | null;
  scoreBasis?: string | null;
  semanticScore?: number | null;
  specificityScore?: number | null;
  smallSizeScore?: number | null;
  aestheticScore?: number | null;
  revisionFollowScore?: number | null;
  genericRiskScore?: number | null;
  qualityTotal?: number | null;
  qualityLabel?: string | null;
  qualityReasons?: string[];
  qualityWarnings?: string[];
  imageEvaluationStatus?: string | null;
  imageEvaluationNote?: string | null;
}

export interface AppStudioImageApiSummary {
  apiCandidateCount?: number;
  api_candidate_count?: number;
  fallbackCandidateCount?: number;
  fallback_candidate_count?: number;
  imageApiSuccess?: boolean;
  image_api_success?: boolean;
  latestImageApiFailure?: string;
  latest_image_api_failure?: string;
  failureClass?: string;
  failure_class?: string;
  failureMessage?: string;
  failure_message?: string;
  adminNextAction?: string;
  admin_next_action?: string;
  fallbackCreatedReason?: string;
  fallback_created_reason?: string;
  fallbackCandidateCountDeprecated?: boolean;
  fallback_candidate_count_deprecated?: boolean;
  fallbackCreatedReasonDeprecated?: boolean;
  fallback_created_reason_deprecated?: boolean;
  selectedIconSource?: string;
  selected_icon_source?: string;
  defaultIconUsed?: boolean;
  default_icon_used?: boolean;
  defaultIconReason?: string;
  default_icon_reason?: string;
  iconStatus?: string;
  icon_status?: string;
  packageSecretScanStatus?: string;
  package_secret_scan_status?: string;
  packageSecretScanFindings?: number;
  package_secret_scan_findings?: number;
  packageAiSubmissionBlocked?: boolean;
  package_ai_submission_blocked?: boolean;
  packageAiSubmissionBlockReason?: string;
  package_ai_submission_block_reason?: string;
  aiPayloadSecretScanStatus?: string;
  ai_payload_secret_scan_status?: string;
  aiSubmissionBlocked?: boolean;
  ai_submission_blocked?: boolean;
  aiSubmissionBlockReason?: string;
  ai_submission_block_reason?: string;
  model?: string;
  stylePreset?: string;
  style_preset?: string;
  scoreBasis?: string;
  score_basis?: string;
  imageEvaluationStatus?: string;
  image_evaluation_status?: string;
  imageEvaluationNote?: string;
  image_evaluation_note?: string;
  recommendedCandidateId?: string;
  recommended_candidate_id?: string;
  recommendedQualityLabel?: string;
  recommended_quality_label?: string;
  recommendedQualityTotal?: number;
  recommended_quality_total?: number;
  qualityLabelCounts?: Record<string, number>;
  quality_label_counts?: Record<string, number>;
  revisionMode?: string;
  revision_mode?: string;
  imageQualityMode?: string;
  image_quality_mode?: string;
  userRevisionInstruction?: string;
  user_revision_instruction?: string;
  finalImageApiPrompt?: string;
  final_image_api_prompt?: string;
  imageApiSeconds?: number;
  image_api_seconds?: number;
  proposalReloadSeconds?: number;
  proposal_reload_seconds?: number;
  regenerationTiming?: Record<string, number>;
  regeneration_timing?: Record<string, number>;
}

export interface AppStudioIconFunctionInterpretation {
  appKind?: string;
  app_kind?: string;
  primaryAction?: string;
  primary_action?: string;
  secondaryAction?: string;
  secondary_action?: string;
  inputObjects?: string[];
  input_objects?: string[];
  outputObjects?: string[];
  output_objects?: string[];
  actionFlow?: string;
  action_flow?: string;
  visualPriority?: string[];
  visual_priority?: string[];
  avoidGeneric?: string[];
  avoid_generic?: string[];
  compositionTemplate?: string;
  composition_template?: string;
  primaryMotif?: string;
  primary_motif?: string;
  secondaryMotifs?: string[];
  secondary_motifs?: string[];
}

export interface AppStudioIconConcept {
  id?: string;
  direction?: string;
  concept?: string;
  primaryMotif?: string;
  primary_motif?: string;
  secondaryMotif?: string;
  secondary_motif?: string;
  composition?: string;
  styleFamily?: string;
  style_family?: string;
  whySpecific?: string;
  why_specific?: string;
  avoidElements?: string[];
  avoid_elements?: string[];
}

export interface AppStudioIconScores {
  semanticClarity?: number;
  specificity?: number;
  smallSizeLegibility?: number;
  aesthetics?: number;
  diversity?: number;
  [key: string]: number | undefined;
}

export interface AppStudioAiProposal {
  ok: boolean;
  outputDir?: string | null;
  metadata: AppStudioAiMetadataSuggestion;
  icon: AppStudioAiIconSuggestion;
  warnings: string[];
}

export interface AppStudioIconRegenerateRequest {
  appId: string;
  outputDir: string;
  baseCandidateId?: string | null;
  userRevisionInstruction: string;
  revisionMode: "tweak" | "refine" | "redesign" | "fresh" | string;
  iconStylePreset?: AppStudioIconStylePreset | string | null;
  iconStyleCustom?: string | null;
  candidateCount?: number | null;
  imageQualityMode?: "draft" | "standard" | "high" | string | null;
}

export interface AppStudioAiDiagnostics {
  aiEnabled: boolean;
  apiKeySource: "credential" | "environment" | "missing" | string;
  apiKeyPresent: boolean;
  textModel: string;
  textModelSet: boolean;
  imageModel: string;
  imageModelSet: boolean;
  cliEnvReady: boolean;
  credentialSupported: boolean;
  message: string;
}

export type AppStudioApprovalMode = "allowWarnings" | "strict";
export type AppStudioVersionBumpMode = "patch" | "minor" | "major" | "manual";
