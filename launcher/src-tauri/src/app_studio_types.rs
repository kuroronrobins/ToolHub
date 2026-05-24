use serde::{Deserialize, Serialize};
use serde_json::Value;

#[derive(Debug, Deserialize, Clone)]
#[serde(rename_all = "camelCase")]
pub struct AppStudioImportRequest {
    pub entry: String,
    pub source_root: Option<String>,
    pub app_id: Option<String>,
    pub name: Option<String>,
    pub version: Option<String>,
    pub build_mode: String,
    pub icon_prompt: Option<String>,
    pub icon_style_preset: Option<String>,
    pub icon_style_custom: Option<String>,
    pub icon_revision_image: Option<String>,
    pub metadata: Option<AppStudioEditableMetadata>,
    pub icon_override: Option<AppStudioIconOverride>,
    pub build_profile: Option<Value>,
    #[serde(default)]
    pub show_terminal: bool,
    pub create_app_env: bool,
    pub rebuild_app_env: bool,
    pub generate_lock: bool,
    pub build_frozen_folder: bool,
    pub verify_runtime: bool,
}

#[derive(Debug, Deserialize, Clone)]
#[serde(rename_all = "camelCase")]
pub struct AppStudioUpdateRequest {
    pub app_id: String,
    pub entry: String,
    pub name: Option<String>,
    pub current_version: Option<String>,
    pub new_version: String,
    pub build_mode: String,
    pub icon_prompt: Option<String>,
    pub icon_style_preset: Option<String>,
    pub icon_style_custom: Option<String>,
    pub icon_revision_image: Option<String>,
    pub metadata: Option<AppStudioEditableMetadata>,
    pub icon_override: Option<AppStudioIconOverride>,
    pub build_profile: Option<Value>,
    #[serde(default)]
    pub show_terminal: bool,
    pub create_app_env: bool,
    pub rebuild_app_env: bool,
    pub generate_lock: bool,
    pub build_frozen_folder: bool,
    pub verify_runtime: bool,
}

#[derive(Debug, Deserialize, Clone)]
#[serde(rename_all = "camelCase")]
pub struct AppStudioIconRegenerateRequest {
    pub app_id: String,
    pub output_dir: String,
    pub base_candidate_id: Option<String>,
    pub user_revision_instruction: String,
    pub revision_mode: String,
    pub icon_style_preset: Option<String>,
    pub icon_style_custom: Option<String>,
    pub candidate_count: Option<usize>,
    pub image_quality_mode: Option<String>,
}

#[derive(Debug, Deserialize, Clone, Default)]
#[serde(rename_all = "camelCase")]
pub struct AppStudioEditableMetadata {
    pub short_description: Option<String>,
    pub description: Option<String>,
    pub primary_category: Option<String>,
    pub target_categories: Option<Vec<String>>,
    pub tags: Option<Vec<String>>,
    pub categories: Option<Vec<String>>,
    pub keywords: Option<Vec<String>>,
    pub examples: Option<Vec<String>>,
    pub use_cases: Option<Vec<String>>,
    pub inputs: Option<Vec<String>>,
    pub outputs: Option<Vec<String>>,
    pub notes: Option<Vec<String>>,
    pub release_notes: Option<Vec<String>>,
    pub change_summary: Option<String>,
}

#[derive(Debug, Deserialize, Clone, Default)]
#[serde(rename_all = "camelCase")]
pub struct AppStudioIconOverride {
    pub selected_icon_source: Option<String>,
    pub png_data_url: Option<String>,
    pub candidate_id: Option<String>,
}

#[derive(Debug, Serialize, Clone, Default)]
#[serde(rename_all = "camelCase")]
pub struct AppStudioRegisteredApp {
    pub app_id: String,
    pub name: String,
    pub version: String,
    pub enabled: bool,
    pub build_mode: Option<String>,
    pub runner: Option<String>,
    pub entry: Option<String>,
    pub description: Option<String>,
    pub warning: Option<String>,
}

#[derive(Debug, Serialize, Clone, Default)]
#[serde(rename_all = "camelCase")]
pub struct AppStudioManagedApp {
    pub app_id: String,
    pub name: String,
    pub version: Option<String>,
    pub enabled: Option<bool>,
    pub management_status: String,
    pub has_source: bool,
    pub source_dir: String,
    pub app_yaml_path: String,
    pub package_path: Option<String>,
    pub package_exists: bool,
    pub delete_plan_status: String,
    pub delete_target_count: usize,
    pub excluded_target_count: usize,
    pub warning: Option<String>,
    pub recommended_action: String,
}

#[derive(Debug, Serialize, Deserialize, Clone, Default)]
#[serde(rename_all = "camelCase")]
pub struct AppStudioDeletePlanTarget {
    pub category: String,
    pub path: String,
    pub normalized_path: String,
    pub exists: bool,
    pub delete_allowed: bool,
    pub action: String,
    pub comparison_key: String,
    pub note: String,
}

#[derive(Debug, Serialize, Deserialize, Clone, Default)]
#[serde(rename_all = "camelCase")]
pub struct AppStudioDeletePlan {
    pub app_id: String,
    pub source_dir: String,
    pub app_yaml: String,
    pub manifest_entry_exists: bool,
    pub manifest_enabled: Option<bool>,
    pub manifest_version: Option<String>,
    pub manifest_package: Option<String>,
    pub app_pack_paths: Vec<String>,
    pub staging_paths: Vec<String>,
    pub staging_candidate_paths: Vec<String>,
    pub runtime_app_env: String,
    pub app_studio_backup_paths: Vec<String>,
    pub lifecycle_backup_paths: Vec<String>,
    pub external_references: Vec<AppStudioDeletePlanTarget>,
    pub user_data_paths: Vec<AppStudioDeletePlanTarget>,
    pub delete_targets: Vec<AppStudioDeletePlanTarget>,
    pub excluded_targets: Vec<AppStudioDeletePlanTarget>,
    pub warnings: Vec<String>,
    pub blocking_reasons: Vec<String>,
}

#[derive(Debug, Serialize, Clone, Default)]
#[serde(rename_all = "camelCase")]
pub struct AppStudioManagementActionResult {
    pub ok: bool,
    pub message: String,
    pub apps: Vec<AppStudioManagedApp>,
    pub target: Option<AppStudioManagedApp>,
}

#[derive(Debug, Serialize, Clone, Default)]
#[serde(rename_all = "camelCase")]
pub struct AppStudioFullDeleteRecord {
    pub category: String,
    pub action: String,
    pub path: String,
    pub normalized_path: String,
    pub comparison_key: String,
    pub status: String,
    pub note: String,
}

#[derive(Debug, Serialize, Clone, Default)]
#[serde(rename_all = "camelCase")]
pub struct AppStudioFullDeletePostCheckSummary {
    pub manifest_json_valid: bool,
    pub manifest_entry_present: bool,
    pub remaining_delete_target_count: usize,
    pub remaining_delete_targets: Vec<String>,
}

#[derive(Debug, Serialize, Clone, Default)]
#[serde(rename_all = "camelCase")]
pub struct AppStudioFullDeleteResult {
    pub ok: bool,
    pub message: String,
    pub app_id: String,
    pub deleted: Vec<AppStudioFullDeleteRecord>,
    pub already_clean: Vec<AppStudioFullDeleteRecord>,
    pub skipped: Vec<AppStudioFullDeleteRecord>,
    pub excluded: Vec<AppStudioDeletePlanTarget>,
    pub failed: Vec<AppStudioFullDeleteRecord>,
    pub manifest_entry_removed: bool,
    pub post_check_summary: AppStudioFullDeletePostCheckSummary,
    pub apps: Vec<AppStudioManagedApp>,
}

#[derive(Debug, Serialize, Clone, Default)]
#[serde(rename_all = "camelCase")]
pub struct AppStudioTimingPhase {
    pub phase: String,
    pub label: String,
    pub status: String,
    pub duration_seconds: Option<f64>,
}

#[derive(Debug, Serialize, Deserialize, Clone, Default)]
#[serde(rename_all = "camelCase")]
pub struct AppStudioAdminAlert {
    pub id: String,
    pub severity: String,
    pub title: String,
    pub summary: String,
    #[serde(alias = "why_dangerous")]
    pub why_dangerous: String,
    #[serde(alias = "admin_action")]
    pub admin_action: String,
    pub source: String,
    #[serde(alias = "check_name")]
    pub check_name: String,
}

#[derive(Debug, Serialize, Clone)]
#[serde(rename_all = "camelCase")]
pub struct AppStudioRunResult {
    pub ok: bool,
    pub exit_code: i32,
    pub stdout: String,
    pub stderr: String,
    pub user_message: String,
    pub output_dir: Option<String>,
    pub app_id: Option<String>,
    pub selected_build_mode: Option<String>,
    pub execution_status: Option<String>,
    pub approval_allowed: Option<bool>,
    pub runtime_status: Option<String>,
    pub app_pack: Option<String>,
    pub enabled: Option<bool>,
    pub current_version: Option<String>,
    pub new_version: Option<String>,
    pub metadata_override_used: bool,
    pub metadata_override_keys: Vec<String>,
    pub icon_override_used: bool,
    pub selected_icon_source: Option<String>,
    pub exe_readiness_status: Option<String>,
    pub manual_checks: Vec<String>,
    pub secret_blocking_count: usize,
    pub secret_warning_count: usize,
    pub secret_manual_check_count: usize,
    pub secret_scan_report: Option<String>,
    pub secret_blocking_findings: Vec<String>,
    pub ai_blocked_by_secret_scan: bool,
    pub apply_blocked_by_secret_scan: bool,
    pub approval_blocking_warnings_count: usize,
    pub non_blocking_warnings_count: usize,
    pub info_count: usize,
    pub unresolved_distribution_risks_count: usize,
    pub approval_blocking_reasons: Vec<String>,
    pub non_blocking_warning_summaries: Vec<String>,
    pub admin_alerts: Vec<AppStudioAdminAlert>,
    pub timing_report: Option<String>,
    pub timing_total_seconds: Option<f64>,
    pub timing_estimated_total_seconds: Option<f64>,
    pub timing_actual_total_seconds: Option<f64>,
    pub timing_prediction_error_seconds: Option<f64>,
    pub timing_prediction_source: Option<String>,
    pub timing_wall_clock_total_seconds: Option<f64>,
    pub timing_cli_measured_total_seconds: Option<f64>,
    pub timing_unmeasured_overhead_seconds: Option<f64>,
    pub timing_phases: Vec<AppStudioTimingPhase>,
    pub process_wall_clock_seconds: Option<f64>,
    pub manifest_enabled: Option<bool>,
    pub approval_record_status: Option<String>,
    pub approval_record_path: Option<String>,
    pub approval_failure_summary: Option<String>,
    pub verify_release_status: Option<String>,
    pub verify_release_failure_summary: Option<String>,
    pub catalog_visible: Option<bool>,
    pub catalog_enabled: Option<bool>,
    pub catalog_disabled_reason: Option<String>,
    pub catalog_load_error: Option<String>,
    pub catalog_root: Option<String>,
    pub app_studio_repo_root: Option<String>,
}

#[derive(Debug, Serialize, Clone)]
#[serde(rename_all = "camelCase")]
pub struct AppStudioPreflightResult {
    pub ok: bool,
    pub entry_exists: bool,
    pub app_id_valid: bool,
    pub build_mode_valid: bool,
    pub app_studio_cli_exists: bool,
    pub app_studio_cli_path: String,
    pub app_studio_repo_root: String,
    pub app_studio_cli_message: String,
    pub python_source: String,
    pub python_path: Option<String>,
    pub runtime_python_exists: bool,
    pub warnings: Vec<String>,
    pub errors: Vec<String>,
}

#[derive(Debug, Serialize, Clone, Default)]
#[serde(rename_all = "camelCase")]
pub struct AppStudioAiDiagnostics {
    pub ai_enabled: bool,
    pub api_key_source: String,
    pub api_key_present: bool,
    pub text_model: String,
    pub text_model_set: bool,
    pub image_model: String,
    pub image_model_set: bool,
    pub cli_env_ready: bool,
    pub app_studio_cli_exists: bool,
    pub app_studio_cli_path: String,
    pub app_studio_repo_root: String,
    pub app_studio_cli_message: String,
    pub credential_supported: bool,
    pub message: String,
}

#[derive(Debug, Serialize, Clone, Default)]
#[serde(rename_all = "camelCase")]
pub struct AppStudioPublishCheck {
    pub id: String,
    pub status: String,
    pub message: String,
}

#[derive(Debug, Serialize, Clone, Default)]
#[serde(rename_all = "camelCase")]
pub struct AppStudioPublishAsset {
    pub name: String,
    pub source_path: Option<String>,
    pub target_path: String,
    pub source_exists: bool,
    pub target_exists: bool,
    pub source_sha256: Option<String>,
    pub target_sha256: Option<String>,
    pub source_size: Option<u64>,
    pub target_size: Option<u64>,
    pub generated: bool,
    pub upload: bool,
}

#[derive(Debug, Serialize, Clone, Default)]
#[serde(rename_all = "camelCase")]
pub struct AppStudioPublishPreflightResult {
    pub ok: bool,
    pub generated_at: String,
    pub repo_root: String,
    pub release_dir: String,
    pub release_target_dir: String,
    pub release_target_manifest_path: String,
    pub branch: Option<String>,
    pub remote_name: String,
    pub remote_url: Option<String>,
    pub github_owner: Option<String>,
    pub github_repo: Option<String>,
    pub version: Option<String>,
    pub tag: Option<String>,
    pub release_url: Option<String>,
    pub latest_manifest_url: Option<String>,
    pub tag_manifest_url: Option<String>,
    pub update_manifest_url: Option<String>,
    pub manifest_path: String,
    pub app_manifest_path: String,
    pub installer_file: Option<String>,
    pub installer_path: Option<String>,
    pub installer_exists: bool,
    pub installer_sha256: Option<String>,
    pub manifest_installer_sha256: Option<String>,
    pub installer_size: Option<u64>,
    pub manifest_installer_size: Option<u64>,
    pub release_target_assets: Vec<AppStudioPublishAsset>,
    pub dirty_files: Vec<String>,
    pub dirty_release_files: Vec<String>,
    pub dirty_runtime_data_files: Vec<String>,
    pub dirty_source_files: Vec<String>,
    pub dirty_other_files: Vec<String>,
    pub readiness_summary: Option<Value>,
    pub beta_ready_blockers: usize,
    pub beta_ready_warnings: usize,
    pub beta_ready_manual_checks: usize,
    pub beta_ready_future_formal_only: usize,
    pub checks: Vec<AppStudioPublishCheck>,
}

#[derive(Debug, Serialize, Clone, Default)]
#[serde(rename_all = "camelCase")]
pub struct AppStudioPublishRunResult {
    pub ok: bool,
    pub exit_code: i32,
    pub stdout: String,
    pub stderr: String,
    pub command_line: String,
    pub started_at: String,
    pub finished_at: String,
    pub process_wall_clock_seconds: f64,
    pub user_message: String,
    pub report: Option<Value>,
    pub preflight: AppStudioPublishPreflightResult,
}

#[derive(Debug, Serialize, Clone, Default)]
#[serde(rename_all = "camelCase")]
pub struct AppStudioReleaseNotesDraftResult {
    pub ok: bool,
    pub source: String,
    pub message: String,
    pub github_release_notes: String,
    pub manifest_release_notes_json: String,
    pub ai_report: Option<String>,
    pub preflight: AppStudioPublishPreflightResult,
}

#[derive(Debug, Deserialize, Clone, Default)]
#[serde(rename_all = "camelCase")]
pub struct AppStudioSaveReleaseNotesRequest {
    pub manifest_release_notes_json: String,
}

#[derive(Debug, Serialize, Clone, Default)]
#[serde(rename_all = "camelCase")]
pub struct AppStudioSaveReleaseNotesResult {
    pub ok: bool,
    pub message: String,
    pub manifest_path: String,
    pub preflight: AppStudioPublishPreflightResult,
}

#[derive(Debug, Deserialize, Clone, Default)]
#[serde(rename_all = "camelCase")]
pub struct AppStudioPublishRemoteVerifyRequest {
    pub manifest_url: Option<String>,
    pub expected_version: Option<String>,
    pub download_installer: bool,
}

#[derive(Debug, Deserialize, Clone, Default)]
#[serde(rename_all = "camelCase")]
pub struct AppStudioPublishPrepareTargetRequest {
    pub require_installer_signature: bool,
}

#[derive(Debug, Deserialize, Clone, Default)]
#[serde(rename_all = "camelCase")]
pub struct AppStudioPublishBuildVerifyRequest {
    pub sign_installer: bool,
    pub require_installer_signature: bool,
    pub code_sign_certificate_thumbprint: Option<String>,
    pub code_sign_certificate_subject: Option<String>,
    pub code_sign_timestamp_url: Option<String>,
    pub sign_tool_path: Option<String>,
}

#[derive(Debug, Deserialize, Clone, Default)]
#[serde(rename_all = "camelCase")]
pub struct AppStudioPublishSignInstallerRequest {
    pub code_sign_certificate_thumbprint: Option<String>,
    pub code_sign_certificate_subject: Option<String>,
    pub code_sign_timestamp_url: Option<String>,
    pub sign_tool_path: Option<String>,
}

#[derive(Debug, Deserialize, Clone, Default)]
#[serde(rename_all = "camelCase")]
pub struct AppStudioPublishRequest {
    pub confirm_publish: bool,
    pub allow_dirty: bool,
    pub allow_existing_release: bool,
    pub update_manifest_installer_url: bool,
    pub draft: bool,
    pub prerelease: bool,
    pub download_installer_for_remote_verify: bool,
    pub skip_build: bool,
    pub sign_installer: bool,
    pub require_installer_signature: bool,
    pub code_sign_certificate_thumbprint: Option<String>,
    pub code_sign_certificate_subject: Option<String>,
    pub code_sign_timestamp_url: Option<String>,
    pub sign_tool_path: Option<String>,
    pub release_notes: Option<String>,
}

#[cfg(test)]
mod tests {
    use super::{
        AppStudioAdminAlert, AppStudioIconOverride, AppStudioImportRequest, AppStudioRunResult,
        AppStudioTimingPhase,
    };
    use serde_json::{json, Value};

    #[test]
    fn import_request_deserializes_existing_camel_case_shape() {
        let request: AppStudioImportRequest = serde_json::from_value(json!({
            "entry": "C:/apps/demo/main.py",
            "sourceRoot": "C:/apps/demo",
            "appId": "demo_app",
            "name": "Demo App",
            "version": "0.1.0",
            "buildMode": "shared-env",
            "iconPrompt": "blue document",
            "iconStylePreset": "modern",
            "iconStyleCustom": null,
            "iconRevisionImage": null,
            "metadata": {
                "shortDescription": "Short",
                "releaseNotes": ["Initial"]
            },
            "iconOverride": null,
            "buildProfile": {"hidden_imports": ["demo"]},
            "createAppEnv": false,
            "rebuildAppEnv": false,
            "generateLock": true,
            "buildFrozenFolder": false,
            "verifyRuntime": true
        }))
        .expect("camelCase import request should deserialize");

        assert_eq!(request.source_root.as_deref(), Some("C:/apps/demo"));
        assert_eq!(request.app_id.as_deref(), Some("demo_app"));
        assert_eq!(request.icon_style_preset.as_deref(), Some("modern"));
        assert_eq!(
            request
                .metadata
                .as_ref()
                .and_then(|metadata| metadata.short_description.as_deref()),
            Some("Short")
        );
        assert!(request.generate_lock);
        assert!(!request.build_frozen_folder);
        assert!(!request.show_terminal);

        let terminal_request: AppStudioImportRequest = serde_json::from_value(json!({
            "entry": "C:/apps/demo/main.py",
            "buildMode": "shared-env",
            "showTerminal": true,
            "createAppEnv": false,
            "rebuildAppEnv": false,
            "generateLock": true,
            "buildFrozenFolder": false,
            "verifyRuntime": true
        }))
        .expect("terminal flag should deserialize");
        assert!(terminal_request.show_terminal);
    }

    #[test]
    fn icon_override_deserializes_existing_camel_case_shape() {
        let icon: AppStudioIconOverride = serde_json::from_value(json!({
            "selectedIconSource": "ai_candidate_png",
            "pngDataUrl": "data:image/png;base64,AAAA",
            "candidateId": "icon_candidate_1"
        }))
        .expect("camelCase icon override should deserialize");

        assert_eq!(
            icon.selected_icon_source.as_deref(),
            Some("ai_candidate_png")
        );
        assert_eq!(
            icon.png_data_url.as_deref(),
            Some("data:image/png;base64,AAAA")
        );
        assert_eq!(icon.candidate_id.as_deref(), Some("icon_candidate_1"));
    }

    #[test]
    fn run_result_serializes_existing_camel_case_shape() {
        let result = AppStudioRunResult {
            ok: true,
            exit_code: 0,
            stdout: "ok".to_string(),
            stderr: String::new(),
            user_message: "done".to_string(),
            output_dir: Some("C:/out".to_string()),
            app_id: Some("demo_app".to_string()),
            selected_build_mode: Some("shared-env".to_string()),
            execution_status: Some("warn".to_string()),
            approval_allowed: Some(true),
            runtime_status: Some("warn".to_string()),
            app_pack: Some("release/app_packs/demo_app-0.1.0.zip".to_string()),
            enabled: Some(false),
            current_version: None,
            new_version: None,
            metadata_override_used: false,
            metadata_override_keys: vec![],
            icon_override_used: false,
            selected_icon_source: Some("default_icon".to_string()),
            exe_readiness_status: Some("ready".to_string()),
            manual_checks: vec![],
            secret_blocking_count: 0,
            secret_warning_count: 0,
            secret_manual_check_count: 0,
            secret_scan_report: Some("secret_scan_report.md".to_string()),
            secret_blocking_findings: vec![],
            ai_blocked_by_secret_scan: false,
            apply_blocked_by_secret_scan: false,
            approval_blocking_warnings_count: 0,
            non_blocking_warnings_count: 1,
            info_count: 3,
            unresolved_distribution_risks_count: 0,
            approval_blocking_reasons: vec![],
            non_blocking_warning_summaries: vec!["manual check".to_string()],
            admin_alerts: vec![AppStudioAdminAlert {
                id: "registration.failed".to_string(),
                severity: "critical".to_string(),
                title: "登録検証に失敗しました".to_string(),
                summary: "summary".to_string(),
                why_dangerous: "risk".to_string(),
                admin_action: "fix".to_string(),
                source: "source".to_string(),
                check_name: "check".to_string(),
            }],
            timing_report: Some("timing_report.json".to_string()),
            timing_total_seconds: Some(1.0),
            timing_estimated_total_seconds: Some(2.0),
            timing_actual_total_seconds: Some(1.5),
            timing_prediction_error_seconds: Some(-0.5),
            timing_prediction_source: Some("test".to_string()),
            timing_wall_clock_total_seconds: Some(1.2),
            timing_cli_measured_total_seconds: Some(1.1),
            timing_unmeasured_overhead_seconds: Some(0.1),
            timing_phases: vec![AppStudioTimingPhase {
                phase: "build".to_string(),
                label: "Build".to_string(),
                status: "ok".to_string(),
                duration_seconds: Some(1.25),
            }],
            process_wall_clock_seconds: Some(1.3),
            manifest_enabled: Some(false),
            approval_record_status: Some("not_approved".to_string()),
            approval_record_path: Some("approval_record.md".to_string()),
            approval_failure_summary: None,
            verify_release_status: Some("ok".to_string()),
            verify_release_failure_summary: None,
            catalog_visible: Some(false),
            catalog_enabled: Some(false),
            catalog_disabled_reason: Some("enabled=false".to_string()),
            catalog_load_error: None,
            catalog_root: Some("C:/repo".to_string()),
            app_studio_repo_root: Some("C:/repo".to_string()),
        };

        let value = serde_json::to_value(result).expect("run result should serialize");
        assert_eq!(value["exitCode"], Value::from(0));
        assert_eq!(value["selectedBuildMode"], Value::from("shared-env"));
        assert_eq!(value["approvalAllowed"], Value::from(true));
        assert_eq!(value["approvalBlockingWarningsCount"], Value::from(0));
        assert_eq!(value["adminAlerts"].as_array().map(Vec::len), Some(1));
        assert_eq!(value["adminAlerts"][0]["whyDangerous"], Value::from("risk"));
        assert_eq!(value["timingPhases"].as_array().map(Vec::len), Some(1));
        assert_eq!(
            value["timingPhases"][0]["durationSeconds"],
            Value::from(1.25)
        );
        assert!(value.get("selected_build_mode").is_none());
        assert!(value["timingPhases"][0].get("duration_seconds").is_none());
    }

    #[test]
    fn timing_phase_serializes_existing_camel_case_shape() {
        let phase = AppStudioTimingPhase {
            phase: "runtime_check".to_string(),
            label: "Runtime check".to_string(),
            status: "warn".to_string(),
            duration_seconds: Some(3.5),
        };

        let value = serde_json::to_value(phase).expect("timing phase should serialize");
        assert_eq!(value["phase"], Value::from("runtime_check"));
        assert_eq!(value["label"], Value::from("Runtime check"));
        assert_eq!(value["status"], Value::from("warn"));
        assert_eq!(value["durationSeconds"], Value::from(3.5));
        assert!(value.get("duration_seconds").is_none());
    }
}
