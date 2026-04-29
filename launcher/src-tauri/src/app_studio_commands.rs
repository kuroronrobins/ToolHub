use crate::admin_session::AdminSessionState;
use base64::{engine::general_purpose, Engine as _};
use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};
use std::cmp::Ordering;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::time::Instant;
use tauri::State;

#[derive(Debug, Deserialize, Clone)]
#[serde(rename_all = "camelCase")]
pub struct AppStudioImportRequest {
    pub entry: String,
    pub app_id: Option<String>,
    pub name: Option<String>,
    pub version: Option<String>,
    pub build_mode: String,
    pub icon_prompt: Option<String>,
    pub metadata: Option<AppStudioEditableMetadata>,
    pub icon_override: Option<AppStudioIconOverride>,
    pub build_profile: Option<Value>,
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
    pub metadata: Option<AppStudioEditableMetadata>,
    pub icon_override: Option<AppStudioIconOverride>,
    pub build_profile: Option<Value>,
    pub create_app_env: bool,
    pub rebuild_app_env: bool,
    pub generate_lock: bool,
    pub build_frozen_folder: bool,
    pub verify_runtime: bool,
}

#[derive(Debug, Deserialize, Clone, Default)]
#[serde(rename_all = "camelCase")]
pub struct AppStudioEditableMetadata {
    pub short_description: Option<String>,
    pub description: Option<String>,
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
pub struct AppStudioResultSummary {
    pub app_id: Option<String>,
    pub output_dir: Option<String>,
    pub selected_build_mode: Option<String>,
    pub execution_status: Option<String>,
    pub approval_allowed: Option<bool>,
    pub runtime_status: Option<String>,
    pub app_pack: Option<String>,
    pub enabled: Option<bool>,
    pub version: Option<String>,
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

#[derive(Debug, Serialize, Clone, Default)]
#[serde(rename_all = "camelCase")]
pub struct AppStudioTimingPhase {
    pub phase: String,
    pub label: String,
    pub status: String,
    pub duration_seconds: Option<f64>,
}

#[derive(Debug, Serialize, Clone)]
#[serde(rename_all = "camelCase")]
pub struct AppStudioPreflightResult {
    pub ok: bool,
    pub entry_exists: bool,
    pub app_id_valid: bool,
    pub build_mode_valid: bool,
    pub python_source: String,
    pub python_path: Option<String>,
    pub runtime_python_exists: bool,
    pub warnings: Vec<String>,
    pub errors: Vec<String>,
}

#[derive(Debug, Serialize, Clone, Default)]
#[serde(rename_all = "camelCase")]
pub struct AppStudioAiMetadataSuggestion {
    pub app_id: Option<String>,
    pub name: Option<String>,
    pub short_description: Option<String>,
    pub description: Option<String>,
    pub categories: Vec<String>,
    pub keywords: Vec<String>,
    pub examples: Vec<String>,
    pub use_cases: Vec<String>,
    pub inputs: Vec<String>,
    pub outputs: Vec<String>,
    pub notes: Vec<String>,
    pub icon_prompt: Option<String>,
    pub release_notes: Vec<String>,
    pub change_summary: Option<String>,
    pub ai_report: Option<String>,
}

#[derive(Debug, Serialize, Clone, Default)]
#[serde(rename_all = "camelCase")]
pub struct AppStudioAiIconCandidateSuggestion {
    pub candidate_id: String,
    pub number: usize,
    pub source: String,
    pub prompt: Option<String>,
    pub model: Option<String>,
    pub status: Option<String>,
    pub resolution: Option<String>,
    pub fallback: bool,
    pub file_name: Option<String>,
    pub url_file_name: Option<String>,
    pub png_data_url: Option<String>,
    pub url: Option<String>,
    pub notes: Option<String>,
    pub revision_of: Option<String>,
    pub concept_id: Option<String>,
    pub concept: Option<Value>,
    pub style_family: Option<String>,
    pub scores: Option<Value>,
    pub score_total: Option<f64>,
}

#[derive(Debug, Serialize, Clone, Default)]
#[serde(rename_all = "camelCase")]
pub struct AppStudioAiIconSuggestion {
    pub prompt_initial: Option<String>,
    pub prompt_revision: Option<String>,
    pub function_interpretation: Option<Value>,
    pub candidate_svg: Option<String>,
    pub final_svg: Option<String>,
    pub fallback_svg: Option<String>,
    pub candidate_png_data_url: Option<String>,
    pub final_png_data_url: Option<String>,
    pub candidate_url: Option<String>,
    pub candidates: Vec<AppStudioAiIconCandidateSuggestion>,
    pub ai_report: Option<String>,
}

#[derive(Debug, Serialize, Clone, Default)]
#[serde(rename_all = "camelCase")]
pub struct AppStudioAiProposal {
    pub ok: bool,
    pub output_dir: Option<String>,
    pub metadata: AppStudioAiMetadataSuggestion,
    pub icon: AppStudioAiIconSuggestion,
    pub warnings: Vec<String>,
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
    pub credential_supported: bool,
    pub message: String,
}

#[derive(Debug, Clone)]
struct PythonCandidate {
    source: String,
    path: PathBuf,
}

#[derive(Debug, Clone)]
struct AiEnvPlan {
    diagnostics: AppStudioAiDiagnostics,
    api_key: Option<String>,
}

#[tauri::command]
pub fn app_studio_list_registered_apps(
    session: State<AdminSessionState>,
) -> Result<Vec<AppStudioRegisteredApp>, String> {
    session.require_authenticated()?;
    let root = crate::manifest::project_root().map_err(|error| error.to_string())?;
    Ok(list_registered_apps_from_root(&root))
}

#[tauri::command]
pub fn app_studio_preflight(
    request: AppStudioImportRequest,
    session: State<AdminSessionState>,
) -> Result<AppStudioPreflightResult, String> {
    session.require_authenticated()?;
    let root = crate::manifest::project_root().map_err(|error| error.to_string())?;
    Ok(preflight_for_request(
        &request,
        &root,
        find_python_candidate(&root),
    ))
}

#[tauri::command]
pub fn app_studio_update_preflight(
    request: AppStudioUpdateRequest,
    session: State<AdminSessionState>,
) -> Result<AppStudioPreflightResult, String> {
    session.require_authenticated()?;
    let root = crate::manifest::project_root().map_err(|error| error.to_string())?;
    Ok(preflight_for_update_request(
        &request,
        &root,
        find_python_candidate(&root),
    ))
}

#[tauri::command]
pub fn app_studio_pick_entry_file(
    session: State<AdminSessionState>,
) -> Result<Option<String>, String> {
    session.require_authenticated()?;
    pick_entry_file()
}

#[tauri::command]
pub async fn app_studio_suggest(
    request: AppStudioImportRequest,
    session: State<'_, AdminSessionState>,
) -> Result<AppStudioRunResult, String> {
    session.require_authenticated()?;
    tauri::async_runtime::spawn_blocking(move || run_import_action(request, "suggest"))
        .await
        .map_err(|_| "App Studio処理を完了できませんでした。".to_string())?
}

#[tauri::command]
pub async fn app_studio_apply(
    request: AppStudioImportRequest,
    session: State<'_, AdminSessionState>,
) -> Result<AppStudioRunResult, String> {
    session.require_authenticated()?;
    tauri::async_runtime::spawn_blocking(move || run_import_action(request, "apply"))
        .await
        .map_err(|_| "App Studio処理を完了できませんでした。".to_string())?
}

#[tauri::command]
pub async fn app_studio_update_suggest(
    request: AppStudioUpdateRequest,
    session: State<'_, AdminSessionState>,
) -> Result<AppStudioRunResult, String> {
    session.require_authenticated()?;
    tauri::async_runtime::spawn_blocking(move || run_update_action(request, "suggest"))
        .await
        .map_err(|_| "App Studio update suggest could not complete.".to_string())?
}

#[tauri::command]
pub async fn app_studio_update_apply(
    request: AppStudioUpdateRequest,
    session: State<'_, AdminSessionState>,
) -> Result<AppStudioRunResult, String> {
    session.require_authenticated()?;
    tauri::async_runtime::spawn_blocking(move || run_update_action(request, "apply"))
        .await
        .map_err(|_| "App Studio update apply could not complete.".to_string())?
}

#[tauri::command]
pub async fn app_studio_approve(
    app_id: String,
    strict: bool,
    session: State<'_, AdminSessionState>,
) -> Result<AppStudioRunResult, String> {
    session.require_authenticated()?;
    tauri::async_runtime::spawn_blocking(move || run_approve_action(app_id, strict))
        .await
        .map_err(|_| "App Studio承認処理を完了できませんでした。".to_string())?
}

#[tauri::command]
pub async fn app_studio_update_approve(
    app_id: String,
    strict: bool,
    session: State<'_, AdminSessionState>,
) -> Result<AppStudioRunResult, String> {
    session.require_authenticated()?;
    tauri::async_runtime::spawn_blocking(move || run_update_approve_action(app_id, strict))
        .await
        .map_err(|_| "App Studio update approve could not complete.".to_string())?
}

#[tauri::command]
pub fn app_studio_read_result(
    app_id: Option<String>,
    output_dir: Option<String>,
    session: State<AdminSessionState>,
) -> Result<AppStudioResultSummary, String> {
    session.require_authenticated()?;
    let root = crate::manifest::project_root().map_err(|error| error.to_string())?;
    let output_path = output_dir.as_deref().map(PathBuf::from);
    Ok(read_summary(
        &root,
        app_id.as_deref(),
        output_path.as_deref(),
    ))
}

#[tauri::command]
pub fn app_studio_read_ai_proposal(
    app_id: Option<String>,
    output_dir: Option<String>,
    session: State<AdminSessionState>,
) -> Result<AppStudioAiProposal, String> {
    session.require_authenticated()?;
    let root = crate::manifest::project_root().map_err(|error| error.to_string())?;
    let output_path = output_dir.as_deref().map(PathBuf::from).or_else(|| {
        app_id
            .as_deref()
            .and_then(|id| output_dir_from_app_yaml(&root, id))
    });
    Ok(read_ai_proposal(output_path.as_deref()))
}

#[tauri::command]
pub fn app_studio_ai_diagnostics(
    session: State<AdminSessionState>,
) -> Result<AppStudioAiDiagnostics, String> {
    session.require_authenticated()?;
    Ok(build_ai_env_plan().diagnostics)
}

#[tauri::command]
pub fn app_studio_open_output_dir(
    output_dir: String,
    session: State<AdminSessionState>,
) -> Result<(), String> {
    session.require_authenticated()?;
    let path = PathBuf::from(output_dir.trim());
    if !path.is_dir() {
        return Err("出力先フォルダが見つかりません。".to_string());
    }
    let status = if cfg!(windows) {
        Command::new("explorer").arg(&path).status()
    } else if cfg!(target_os = "macos") {
        Command::new("open").arg(&path).status()
    } else {
        Command::new("xdg-open").arg(&path).status()
    }
    .map_err(|error| format!("出力先フォルダを開けませんでした: {error}"))?;
    if status.success() {
        Ok(())
    } else {
        Err("出力先フォルダを開けませんでした。".to_string())
    }
}

fn run_update_action(
    request: AppStudioUpdateRequest,
    action: &str,
) -> Result<AppStudioRunResult, String> {
    let root = crate::manifest::project_root().map_err(|error| error.to_string())?;
    validate_update_request(&request, &root)?;
    let event = format!("update_{action}");
    append_app_studio_gui_log(
        &format!("{event} started"),
        &[
            ("app_id", request.app_id.clone()),
            (
                "current_version",
                request.current_version.clone().unwrap_or_default(),
            ),
            ("new_version", request.new_version.clone()),
            ("build_mode", request.build_mode.clone()),
        ],
    );

    let import_request = import_request_from_update(&request);
    let result = run_import_action(import_request, action);
    match result {
        Ok(mut run_result) => {
            run_result.current_version = request.current_version.clone();
            run_result.new_version = Some(request.new_version.clone());
            append_app_studio_gui_log(
                &format!("{event} finished"),
                &[
                    ("exit_code", run_result.exit_code.to_string()),
                    ("app_id", request.app_id),
                    (
                        "current_version",
                        request.current_version.unwrap_or_default(),
                    ),
                    ("new_version", request.new_version),
                    ("build_mode", request.build_mode),
                    (
                        "output_dir",
                        run_result.output_dir.clone().unwrap_or_default(),
                    ),
                ],
            );
            Ok(run_result)
        }
        Err(error) => {
            append_app_studio_gui_log(
                &format!("{event} finished"),
                &[
                    ("exit_code", "-1".to_string()),
                    ("app_id", request.app_id),
                    (
                        "current_version",
                        request.current_version.unwrap_or_default(),
                    ),
                    ("new_version", request.new_version),
                    ("build_mode", request.build_mode),
                    ("user_message", error.clone()),
                ],
            );
            Err(error)
        }
    }
}

fn run_import_action(
    mut request: AppStudioImportRequest,
    action: &str,
) -> Result<AppStudioRunResult, String> {
    let root = crate::manifest::project_root().map_err(|error| error.to_string())?;
    normalize_normal_import_request(&mut request)?;
    validate_request(&request)?;
    let python_candidate = find_python_candidate(&root).ok_or_else(python_missing_message)?;
    let python = python_candidate.path.clone();
    let script = root.join("tools").join("app_studio").join("main.py");
    if !script.is_file() {
        return Err("tools/app_studio/main.py が見つかりません。".to_string());
    }

    let metadata_override = write_metadata_override_file(&request)?;
    let metadata_override_keys = metadata_override
        .as_ref()
        .map(|(_, keys)| keys.join(","))
        .unwrap_or_default();
    let icon_override = write_icon_override_file(&request)?;
    let icon_override_source = icon_override
        .as_ref()
        .map(|(_, source)| source.clone())
        .unwrap_or_default();
    let build_profile_override = write_build_profile_override_file(&request)?;
    let build_profile_source = if build_profile_override.is_some() {
        "manual"
    } else {
        ""
    }
    .to_string();
    let ai_env = build_ai_env_plan();
    let mut cli_args: Vec<String> = vec![
        script.display().to_string(),
        "import".to_string(),
        "--entry".to_string(),
        request.entry.clone(),
        "--build-mode".to_string(),
        request.build_mode.clone(),
    ];
    if let Some(app_id) = clean_optional(&request.app_id) {
        cli_args.push("--app-id".to_string());
        cli_args.push(app_id.to_string());
    }
    if let Some(name) = clean_optional(&request.name) {
        cli_args.push("--name".to_string());
        cli_args.push(name.to_string());
    }
    if let Some(version) = clean_optional(&request.version) {
        cli_args.push("--version".to_string());
        cli_args.push(version.to_string());
    }
    if let Some(icon_prompt) = clean_optional(&request.icon_prompt) {
        cli_args.push("--icon-prompt".to_string());
        cli_args.push(icon_prompt.to_string());
    }
    if let Some((path, _)) = metadata_override.as_ref() {
        cli_args.push("--metadata-override".to_string());
        cli_args.push(path.display().to_string());
    }
    if let Some((path, _)) = icon_override.as_ref() {
        cli_args.push("--icon-override".to_string());
        cli_args.push(path.display().to_string());
    }
    if let Some(path) = build_profile_override.as_ref() {
        cli_args.push("--build-profile".to_string());
        cli_args.push(path.display().to_string());
    }
    if request.create_app_env {
        cli_args.push("--create-app-env".to_string());
    }
    if request.rebuild_app_env {
        cli_args.push("--rebuild-app-env".to_string());
    }
    if request.generate_lock {
        cli_args.push("--generate-lock".to_string());
    }
    if request.build_frozen_folder {
        cli_args.push("--build-frozen-folder".to_string());
    }
    if request.verify_runtime {
        cli_args.push("--verify-runtime".to_string());
    }
    cli_args.push(if action == "apply" {
        "--apply".to_string()
    } else {
        "--suggest".to_string()
    });
    let cli_argv = command_line_for_log(&python, &cli_args);

    append_app_studio_gui_log(
        &format!("{action} started"),
        &[
            ("app_id", request.app_id.clone().unwrap_or_default()),
            ("build_mode", request.build_mode.clone()),
            ("cli_path", script.display().to_string()),
            ("argv", cli_argv.clone()),
            ("python_source", python_candidate.source.clone()),
            ("metadata_override_keys", metadata_override_keys.clone()),
            ("icon_override_source", icon_override_source.clone()),
            ("build_profile_source", build_profile_source.clone()),
            ("ai_enabled", ai_env.diagnostics.ai_enabled.to_string()),
            ("api_key_source", ai_env.diagnostics.api_key_source.clone()),
            (
                "cli_env_ready",
                ai_env.diagnostics.cli_env_ready.to_string(),
            ),
            (
                "text_model_set",
                ai_env.diagnostics.text_model_set.to_string(),
            ),
            ("image_model", ai_env.diagnostics.image_model.clone()),
        ],
    );

    let mut command = Command::new(&python);
    for arg in &cli_args {
        command.arg(arg);
    }
    apply_ai_environment(&mut command, &ai_env);

    let process_started = Instant::now();
    let output = command
        .current_dir(&root)
        .output()
        .map_err(|_| "App Studioを起動できませんでした。".to_string())?;
    let process_wall_clock_seconds = process_started.elapsed().as_secs_f64();
    let stdout = mask_sensitive(&String::from_utf8_lossy(&output.stdout));
    let stderr = mask_sensitive(&String::from_utf8_lossy(&output.stderr));
    let exit_code = output.status.code().unwrap_or(-1);
    let output_dir = extract_output_dir(&stdout)
        .or_else(|| infer_output_dir(&request, &stdout))
        .filter(|path| path.is_dir());
    let app_id =
        extract_app_id(&stdout).or_else(|| clean_optional(&request.app_id).map(str::to_string));
    let summary = read_summary(&root, app_id.as_deref(), output_dir.as_deref());
    append_app_studio_gui_log(
        &format!("{action} finished"),
        &[
            ("exit_code", exit_code.to_string()),
            (
                "app_id",
                summary
                    .app_id
                    .clone()
                    .or(app_id.clone())
                    .unwrap_or_default(),
            ),
            ("build_mode", request.build_mode.clone()),
            ("cli_path", script.display().to_string()),
            ("argv", cli_argv),
            ("output_dir", summary.output_dir.clone().unwrap_or_default()),
            ("python_source", python_candidate.source),
            ("metadata_override_keys", metadata_override_keys),
            ("icon_override_source", icon_override_source),
            ("build_profile_source", build_profile_source),
            ("ai_enabled", ai_env.diagnostics.ai_enabled.to_string()),
            ("api_key_source", ai_env.diagnostics.api_key_source),
            (
                "cli_env_ready",
                ai_env.diagnostics.cli_env_ready.to_string(),
            ),
            (
                "user_message",
                if output.status.success() {
                    "ok".to_string()
                } else {
                    "App Studio処理に失敗しました".to_string()
                },
            ),
        ],
    );
    Ok(result_from_process(
        output.status.success(),
        exit_code,
        stdout,
        stderr,
        summary,
        Some(process_wall_clock_seconds),
        if action == "apply" {
            "Applyが完了しました。execution_test_resultを確認してください。"
        } else {
            "Suggestが完了しました。生成物を確認してください。"
        },
    ))
}

fn run_approve_action(app_id: String, strict: bool) -> Result<AppStudioRunResult, String> {
    let root = crate::manifest::project_root().map_err(|error| error.to_string())?;
    validate_app_id(&app_id)?;
    let python_candidate = find_python_candidate(&root).ok_or_else(python_missing_message)?;
    let python = python_candidate.path.clone();
    let script = root.join("tools").join("app_studio").join("main.py");
    let approval_mode = approval_mode_name(strict);
    append_app_studio_gui_log(
        "approve started",
        &[
            ("app_id", app_id.clone()),
            ("approval_mode", approval_mode.to_string()),
            ("python_source", python_candidate.source.clone()),
        ],
    );
    let process_started = Instant::now();
    let output = Command::new(&python)
        .arg(script)
        .arg("approve")
        .arg("--app-id")
        .arg(&app_id)
        .arg(approval_flag(strict))
        .current_dir(&root)
        .output()
        .map_err(|_| "App Studio承認処理を起動できませんでした。".to_string())?;
    let process_wall_clock_seconds = process_started.elapsed().as_secs_f64();
    let stdout = mask_sensitive(&String::from_utf8_lossy(&output.stdout));
    let stderr = mask_sensitive(&String::from_utf8_lossy(&output.stderr));
    let exit_code = output.status.code().unwrap_or(-1);
    let summary = read_summary(&root, Some(&app_id), None);
    append_app_studio_gui_log(
        "approve finished",
        &[
            ("exit_code", exit_code.to_string()),
            ("app_id", app_id),
            ("output_dir", summary.output_dir.clone().unwrap_or_default()),
            ("approval_mode", approval_mode.to_string()),
            ("python_source", python_candidate.source),
            (
                "user_message",
                if output.status.success() {
                    "ok".to_string()
                } else {
                    "App Studio承認処理に失敗しました".to_string()
                },
            ),
        ],
    );
    Ok(result_from_process(
        output.status.success(),
        exit_code,
        stdout,
        stderr,
        summary,
        Some(process_wall_clock_seconds),
        "承認処理が完了しました。",
    ))
}

fn run_update_approve_action(app_id: String, strict: bool) -> Result<AppStudioRunResult, String> {
    validate_app_id(&app_id)?;
    let approval_mode = approval_mode_name(strict);
    append_app_studio_gui_log(
        "update_approve started",
        &[
            ("app_id", app_id.clone()),
            ("approval_mode", approval_mode.to_string()),
        ],
    );
    let result = run_approve_action(app_id.clone(), strict);
    match result {
        Ok(run_result) => {
            append_app_studio_gui_log(
                "update_approve finished",
                &[
                    ("exit_code", run_result.exit_code.to_string()),
                    ("app_id", app_id),
                    ("approval_mode", approval_mode.to_string()),
                    (
                        "output_dir",
                        run_result.output_dir.clone().unwrap_or_default(),
                    ),
                ],
            );
            Ok(run_result)
        }
        Err(error) => {
            append_app_studio_gui_log(
                "update_approve finished",
                &[
                    ("exit_code", "-1".to_string()),
                    ("app_id", app_id),
                    ("approval_mode", approval_mode.to_string()),
                    ("user_message", error.clone()),
                ],
            );
            Err(error)
        }
    }
}

fn result_from_process(
    ok: bool,
    exit_code: i32,
    stdout: String,
    stderr: String,
    summary: AppStudioResultSummary,
    process_wall_clock_seconds: Option<f64>,
    success_message: &str,
) -> AppStudioRunResult {
    let user_message = if ok {
        success_message.to_string()
    } else if summary.apply_blocked_by_secret_scan || summary.secret_blocking_count > 0 {
        format!(
            "Secret scan blocked Apply. blocking={}, warnings={}, manual_checks={}. Review secret_scan_report.md.",
            summary.secret_blocking_count, summary.secret_warning_count, summary.secret_manual_check_count
        )
    } else if summary.execution_status.as_deref() == Some("warn")
        && summary.approval_allowed == Some(true)
    {
        "App Studio completed with warnings. execution_test_result.json allows approval; review the logs before approving.".to_string()
    } else if summary.execution_status.as_deref() == Some("pass") {
        "App Studio process returned a non-zero exit code, but execution checks passed. Review stdout/stderr before approval.".to_string()
    } else {
        "App Studio processing failed. Review stdout/stderr and generated reports.".to_string()
    };
    AppStudioRunResult {
        ok,
        exit_code,
        stdout,
        stderr,
        user_message,
        output_dir: summary.output_dir,
        app_id: summary.app_id,
        selected_build_mode: summary.selected_build_mode,
        execution_status: summary.execution_status,
        approval_allowed: summary.approval_allowed,
        runtime_status: summary.runtime_status,
        app_pack: summary.app_pack,
        enabled: summary.enabled,
        current_version: None,
        new_version: summary.version,
        metadata_override_used: summary.metadata_override_used,
        metadata_override_keys: summary.metadata_override_keys,
        icon_override_used: summary.icon_override_used,
        selected_icon_source: summary.selected_icon_source,
        exe_readiness_status: summary.exe_readiness_status,
        manual_checks: summary.manual_checks,
        secret_blocking_count: summary.secret_blocking_count,
        secret_warning_count: summary.secret_warning_count,
        secret_manual_check_count: summary.secret_manual_check_count,
        secret_scan_report: summary.secret_scan_report,
        secret_blocking_findings: summary.secret_blocking_findings,
        ai_blocked_by_secret_scan: summary.ai_blocked_by_secret_scan,
        apply_blocked_by_secret_scan: summary.apply_blocked_by_secret_scan,
        approval_blocking_warnings_count: summary.approval_blocking_warnings_count,
        non_blocking_warnings_count: summary.non_blocking_warnings_count,
        info_count: summary.info_count,
        unresolved_distribution_risks_count: summary.unresolved_distribution_risks_count,
        approval_blocking_reasons: summary.approval_blocking_reasons,
        non_blocking_warning_summaries: summary.non_blocking_warning_summaries,
        timing_report: summary.timing_report,
        timing_total_seconds: summary.timing_total_seconds.or(process_wall_clock_seconds),
        timing_estimated_total_seconds: summary.timing_estimated_total_seconds,
        timing_actual_total_seconds: summary.timing_actual_total_seconds,
        timing_prediction_error_seconds: summary.timing_prediction_error_seconds,
        timing_prediction_source: summary.timing_prediction_source,
        timing_wall_clock_total_seconds: summary.timing_wall_clock_total_seconds,
        timing_cli_measured_total_seconds: summary.timing_cli_measured_total_seconds,
        timing_unmeasured_overhead_seconds: summary.timing_unmeasured_overhead_seconds,
        timing_phases: summary.timing_phases,
        process_wall_clock_seconds,
        manifest_enabled: summary.manifest_enabled,
        approval_record_status: summary.approval_record_status,
        approval_record_path: summary.approval_record_path,
        approval_failure_summary: summary.approval_failure_summary,
        verify_release_status: summary.verify_release_status,
        verify_release_failure_summary: summary.verify_release_failure_summary,
        catalog_visible: summary.catalog_visible,
        catalog_enabled: summary.catalog_enabled,
        catalog_disabled_reason: summary.catalog_disabled_reason,
        catalog_load_error: summary.catalog_load_error,
        catalog_root: summary.catalog_root,
        app_studio_repo_root: summary.app_studio_repo_root,
    }
}

fn validate_request(request: &AppStudioImportRequest) -> Result<(), String> {
    let entry = PathBuf::from(request.entry.trim());
    if request.entry.trim().is_empty() {
        return Err("Entryファイルを指定してください。".to_string());
    }
    if !entry.is_file() {
        return Err("Entryファイルが見つかりません。".to_string());
    }
    validate_entry_path(&entry)?;
    if !["auto", "app-env", "frozen-folder", "existing-exe"].contains(&request.build_mode.as_str())
    {
        return Err("BuildModeが不正です。".to_string());
    }
    if let Some(app_id) = clean_optional(&request.app_id) {
        validate_app_id(app_id)?;
    }
    Ok(())
}

fn normalize_normal_import_request(request: &mut AppStudioImportRequest) -> Result<(), String> {
    let entry = PathBuf::from(request.entry.trim());
    if entry
        .extension()
        .and_then(|value| value.to_str())
        .map(|value| value.eq_ignore_ascii_case("exe"))
        .unwrap_or(false)
    {
        return Err("Normal App Studio registration accepts Python source only. Existing exe registration is not available in this flow.".to_string());
    }
    if request.create_app_env || request.rebuild_app_env {
        return Err("Normal App Studio registration uses an internal build_env, not runtime/app_envs options.".to_string());
    }
    request.build_mode = "frozen-folder".to_string();
    request.generate_lock = true;
    request.build_frozen_folder = true;
    request.verify_runtime = true;
    request.create_app_env = false;
    request.rebuild_app_env = false;
    Ok(())
}

fn validate_update_request(request: &AppStudioUpdateRequest, root: &Path) -> Result<(), String> {
    validate_app_id(&request.app_id)?;
    if request.new_version.trim().is_empty() {
        return Err("New version is required.".to_string());
    }
    let registered = find_registered_app(root, &request.app_id)
        .ok_or_else(|| "Target app_id is not registered.".to_string())?;
    let current_version = clean_optional(&request.current_version)
        .map(str::to_string)
        .unwrap_or(registered.version);
    if matches!(
        compare_semver(&current_version, request.new_version.trim()),
        Some(Ordering::Greater)
    ) {
        return Err("New version must not be older than current version.".to_string());
    }
    Ok(())
}

fn validate_entry_path(entry: &Path) -> Result<(), String> {
    let lower = entry.to_string_lossy().to_lowercase();
    for marker in [".env", ".pem", ".key", "credentials", "secrets", "token"] {
        if lower.contains(marker) {
            return Err("Entryファイルのパスに秘密情報らしい名前が含まれています。".to_string());
        }
    }
    Ok(())
}

fn validate_app_id(app_id: &str) -> Result<(), String> {
    let value = app_id.trim();
    if value.is_empty() || value.len() > 64 {
        return Err("AppIdは1文字以上64文字以下で指定してください。".to_string());
    }
    let mut chars = value.chars();
    let Some(first) = chars.next() else {
        return Err("AppIdを指定してください。".to_string());
    };
    if !first.is_ascii_lowercase() && !first.is_ascii_digit() {
        return Err("AppIdは英小文字または数字で開始してください。".to_string());
    }
    if !value
        .chars()
        .all(|ch| ch.is_ascii_lowercase() || ch.is_ascii_digit() || ch == '_' || ch == '-')
    {
        return Err(
            "AppIdには英小文字、数字、ハイフン、アンダースコアのみ使用できます。".to_string(),
        );
    }
    Ok(())
}

fn runtime_python_path(root: &Path) -> PathBuf {
    root.join("runtime").join("python").join(if cfg!(windows) {
        "python.exe"
    } else {
        "python"
    })
}

fn find_python_candidate(root: &Path) -> Option<PythonCandidate> {
    let embedded = runtime_python_path(root);
    if embedded.is_file() {
        return Some(PythonCandidate {
            source: "runtime".to_string(),
            path: embedded,
        });
    }
    find_on_path(if cfg!(windows) {
        "python.exe"
    } else {
        "python"
    })
    .or_else(|| find_on_path("python"))
    .map(|path| PythonCandidate {
        source: "python".to_string(),
        path,
    })
    .or_else(|| {
        find_on_path("py").map(|path| PythonCandidate {
            source: "py".to_string(),
            path,
        })
    })
}

fn find_on_path(command: &str) -> Option<PathBuf> {
    let path = std::env::var_os("PATH")?;
    for dir in std::env::split_paths(&path) {
        let candidate = dir.join(command);
        if candidate.is_file() {
            return Some(candidate);
        }
        if cfg!(windows) {
            let exe_candidate = dir.join(format!("{command}.exe"));
            if exe_candidate.is_file() {
                return Some(exe_candidate);
            }
        }
    }
    None
}

fn python_missing_message() -> String {
    "App Studioを実行するPythonが見つかりません。runtime/python/python.exeを配置するか、管理者の開発環境にpythonまたはpyを用意してください。通常ランチャー機能には影響しません。".to_string()
}

fn preflight_for_request(
    request: &AppStudioImportRequest,
    root: &Path,
    python_candidate: Option<PythonCandidate>,
) -> AppStudioPreflightResult {
    let mut warnings = Vec::new();
    let mut errors = Vec::new();

    let entry = PathBuf::from(request.entry.trim());
    let entry_exists = !request.entry.trim().is_empty() && entry.is_file();
    if request.entry.trim().is_empty() {
        errors.push("Entryファイルを指定してください。".to_string());
    } else if !entry_exists {
        errors.push("Entryファイルが見つかりません。".to_string());
    } else if let Err(error) = validate_entry_path(&entry) {
        errors.push(error);
    }
    if entry
        .extension()
        .and_then(|value| value.to_str())
        .map(|value| value.eq_ignore_ascii_case("exe"))
        .unwrap_or(false)
    {
        errors.push("Normal App Studio registration accepts Python source only. Existing exe registration is not available in this flow.".to_string());
    }

    let build_mode_valid = ["auto", "frozen-folder"].contains(&request.build_mode.as_str());
    if !build_mode_valid {
        errors.push("BuildModeが不正です。".to_string());
    }

    if request.create_app_env || request.rebuild_app_env {
        errors.push("Normal App Studio registration uses an internal build_env, not runtime/app_envs options.".to_string());
    }

    let app_id_valid = match clean_optional(&request.app_id) {
        Some(app_id) => match validate_app_id(app_id) {
            Ok(()) => true,
            Err(error) => {
                errors.push(error);
                false
            }
        },
        None => {
            warnings.push("AppIdが未入力です。CLI側の自動生成に任せます。".to_string());
            true
        }
    };

    let runtime_python_exists = runtime_python_path(root).is_file();

    let (python_source, python_path) = match python_candidate {
        Some(candidate) => (candidate.source, Some(candidate.path.display().to_string())),
        None => {
            errors.push(python_missing_message());
            ("missing".to_string(), None)
        }
    };

    AppStudioPreflightResult {
        ok: errors.is_empty(),
        entry_exists,
        app_id_valid,
        build_mode_valid,
        python_source,
        python_path,
        runtime_python_exists,
        warnings,
        errors,
    }
}

fn preflight_for_update_request(
    request: &AppStudioUpdateRequest,
    root: &Path,
    python_candidate: Option<PythonCandidate>,
) -> AppStudioPreflightResult {
    let import_request = import_request_from_update(request);
    let mut result = preflight_for_request(&import_request, root, python_candidate);
    let registered = find_registered_app(root, &request.app_id);

    if registered.is_none() {
        result
            .errors
            .push("Target app_id is not registered.".to_string());
    }
    let app_yaml = root.join("apps").join(&request.app_id).join("app.yaml");
    if !app_yaml.is_file() {
        result
            .errors
            .push("apps/<app_id>/app.yaml was not found.".to_string());
    }
    if request.new_version.trim().is_empty() {
        result.errors.push("New version is required.".to_string());
    }

    let current_version = clean_optional(&request.current_version)
        .map(str::to_string)
        .or_else(|| registered.as_ref().map(|app| app.version.clone()))
        .unwrap_or_default();
    if current_version.trim().is_empty() {
        result
            .warnings
            .push("Current version could not be read. Use manual version input.".to_string());
    } else {
        match compare_semver(&current_version, request.new_version.trim()) {
            Some(Ordering::Greater) => result.errors.push(
                "New version is older than current version. Choose a newer version.".to_string(),
            ),
            Some(Ordering::Equal) => result
                .warnings
                .push("New version is the same as current version.".to_string()),
            Some(Ordering::Less) => {}
            None => result.warnings.push(
                "Version is not simple SemVer (x.y.z). Automatic comparison is limited."
                    .to_string(),
            ),
        }
    }

    result.ok = result.errors.is_empty();
    result
}

fn read_ai_proposal(output_dir: Option<&Path>) -> AppStudioAiProposal {
    let mut proposal = AppStudioAiProposal::default();
    let Some(output_dir) = output_dir else {
        proposal
            .warnings
            .push("Output directory was not found. Run Suggest first.".to_string());
        return proposal;
    };
    proposal.output_dir = Some(output_dir.display().to_string());
    if !output_dir.is_dir() {
        proposal
            .warnings
            .push("Output directory does not exist. Run Suggest first.".to_string());
        return proposal;
    }

    let proposed_yaml = output_dir.join("proposed_app.yaml");
    if let Ok(text) = std::fs::read_to_string(&proposed_yaml) {
        if let Ok(yaml) = serde_yaml::from_str::<serde_yaml::Value>(&text) {
            proposal.metadata = metadata_from_yaml(&yaml);
        } else {
            proposal
                .warnings
                .push("proposed_app.yaml could not be parsed.".to_string());
        }
    } else {
        proposal
            .warnings
            .push("proposed_app.yaml was not found. Run Suggest first.".to_string());
    }

    let icon_work = output_dir.join("icon_work");
    proposal.icon.prompt_initial = read_text_optional(&icon_work.join("icon_prompt_initial.md"));
    proposal.icon.prompt_revision = read_text_optional(&icon_work.join("icon_prompt_revision.md"));
    proposal.icon.candidate_svg = read_text_optional(&icon_work.join("icon_candidate_1.svg"));
    proposal.icon.final_svg = read_text_optional(&icon_work.join("icon_final.svg"));
    proposal.icon.fallback_svg = read_text_optional(&icon_work.join("icon_fallback.svg"))
        .or_else(|| proposal.icon.final_svg.clone())
        .or_else(|| proposal.icon.candidate_svg.clone());
    proposal.icon.candidate_url = read_text_optional(&icon_work.join("icon_candidate_1.url.txt"));
    proposal.icon.ai_report = read_text_optional(&icon_work.join("ai_generation_report.md"));
    proposal.icon.function_interpretation = read_icon_function_interpretation(&icon_work);
    proposal.icon.candidate_png_data_url =
        read_png_data_url_optional(&icon_work.join("icon_candidate_1.png"));
    proposal.icon.final_png_data_url =
        read_png_data_url_optional(&icon_work.join("icon_final.png"));
    proposal.icon.candidates = read_icon_candidates(&icon_work);
    if proposal.icon.candidate_png_data_url.is_none() {
        proposal.icon.candidate_png_data_url = proposal
            .icon
            .candidates
            .iter()
            .find_map(|candidate| candidate.png_data_url.clone());
    }
    if proposal.icon.candidate_url.is_none() {
        proposal.icon.candidate_url = proposal
            .icon
            .candidates
            .iter()
            .find_map(|candidate| candidate.url.clone());
    }

    if proposal.metadata.icon_prompt.is_none() {
        proposal.metadata.icon_prompt = proposal
            .icon
            .prompt_revision
            .clone()
            .filter(|value| !value.trim().is_empty())
            .or_else(|| proposal.icon.prompt_initial.clone());
    }
    fill_metadata_ai_report(output_dir, &mut proposal.metadata);
    fill_release_notes(output_dir, &mut proposal.metadata);
    proposal.ok = proposal.warnings.is_empty()
        || proposal.metadata.name.is_some()
        || proposal.icon.final_png_data_url.is_some()
        || proposal.icon.candidate_png_data_url.is_some()
        || proposal.icon.fallback_svg.is_some();
    proposal
}

fn metadata_from_yaml(yaml: &serde_yaml::Value) -> AppStudioAiMetadataSuggestion {
    AppStudioAiMetadataSuggestion {
        app_id: yaml_str(yaml, &["id"]),
        name: yaml_str(yaml, &["name"]),
        short_description: yaml_str(yaml, &["display", "short_description"]),
        description: yaml_str(yaml, &["detail", "description"]),
        categories: yaml_string_list(yaml, &["display", "categories"]),
        keywords: yaml_string_list(yaml, &["search", "keywords"]),
        examples: yaml_string_list(yaml, &["search", "examples"]),
        use_cases: yaml_string_list(yaml, &["detail", "use_cases"]),
        inputs: yaml_string_list(yaml, &["detail", "inputs"]),
        outputs: yaml_string_list(yaml, &["detail", "outputs"]),
        notes: yaml_string_list(yaml, &["detail", "notes"]),
        icon_prompt: None,
        release_notes: yaml_string_list(yaml, &["release", "release_notes"]),
        change_summary: yaml_str(yaml, &["release", "change_summary"]),
        ai_report: None,
    }
}

fn fill_metadata_ai_report(output_dir: &Path, metadata: &mut AppStudioAiMetadataSuggestion) {
    let Some(json) = read_json(&output_dir.join("import_plan.json")) else {
        return;
    };
    metadata.ai_report = json
        .get("metadata_ai_report")
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(str::to_string);
}

fn fill_release_notes(output_dir: &Path, metadata: &mut AppStudioAiMetadataSuggestion) {
    let Some(json) = read_json(&output_dir.join("import_plan.json")) else {
        return;
    };
    let app_id = json.get("app_id").and_then(Value::as_str).unwrap_or("app");
    let version = json
        .get("version")
        .and_then(Value::as_str)
        .unwrap_or("unknown");
    let mode = json
        .get("selected_build_mode")
        .and_then(Value::as_str)
        .unwrap_or("unknown");
    if metadata.release_notes.is_empty() {
        metadata.release_notes = vec![
            format!("Update {app_id} to version {version}."),
            format!("Build mode: {mode}. Review execution_test_result.json before approval."),
        ];
    }
    if metadata.change_summary.is_none() {
        metadata.change_summary =
            Some(format!("Update {app_id} to version {version} with {mode}."));
    }
}

fn yaml_string_list(value: &serde_yaml::Value, path: &[&str]) -> Vec<String> {
    let mut current = value;
    for key in path {
        let serde_yaml::Value::Mapping(map) = current else {
            return Vec::new();
        };
        let Some(next) = map.get(&serde_yaml::Value::String((*key).to_string())) else {
            return Vec::new();
        };
        current = next;
    }
    match current {
        serde_yaml::Value::Sequence(items) => items
            .iter()
            .filter_map(|item| item.as_str().map(|value| value.trim().to_string()))
            .filter(|value| !value.is_empty())
            .collect(),
        serde_yaml::Value::String(value) if !value.trim().is_empty() => {
            vec![value.trim().to_string()]
        }
        _ => Vec::new(),
    }
}

fn read_text_optional(path: &Path) -> Option<String> {
    std::fs::read_to_string(path)
        .ok()
        .map(|value| value.trim().to_string())
        .filter(|value| !value.is_empty())
}

fn read_png_data_url_optional(path: &Path) -> Option<String> {
    let bytes = std::fs::read(path).ok()?;
    Some(format!(
        "data:image/png;base64,{}",
        general_purpose::STANDARD.encode(bytes)
    ))
}

fn read_icon_function_interpretation(icon_work: &Path) -> Option<Value> {
    read_json(&icon_work.join("candidate_manifest.json"))
        .and_then(|json| json.get("function_interpretation").cloned())
        .filter(|value| !value.is_null())
}

fn read_icon_candidates(icon_work: &Path) -> Vec<AppStudioAiIconCandidateSuggestion> {
    let mut candidates = Vec::new();
    if let Some(json) = read_json(&icon_work.join("candidate_manifest.json")) {
        if let Some(items) = json.get("candidates").and_then(Value::as_array) {
            for (index, item) in items.iter().enumerate() {
                let file_name = item
                    .get("file_name")
                    .and_then(Value::as_str)
                    .map(str::trim)
                    .filter(|value| !value.is_empty())
                    .map(str::to_string);
                let url_file_name = item
                    .get("url_file_name")
                    .and_then(Value::as_str)
                    .map(str::trim)
                    .filter(|value| !value.is_empty())
                    .map(str::to_string);
                let png_data_url = file_name
                    .as_deref()
                    .and_then(|name| read_png_data_url_optional(&icon_work.join(name)));
                let url = item
                    .get("url")
                    .and_then(Value::as_str)
                    .map(str::trim)
                    .filter(|value| !value.is_empty())
                    .map(str::to_string)
                    .or_else(|| {
                        url_file_name
                            .as_deref()
                            .and_then(|name| read_text_optional(&icon_work.join(name)))
                    });
                candidates.push(AppStudioAiIconCandidateSuggestion {
                    candidate_id: item
                        .get("candidate_id")
                        .or_else(|| item.get("id"))
                        .and_then(Value::as_str)
                        .map(str::to_string)
                        .unwrap_or_else(|| format!("icon_candidate_{}", index + 1)),
                    number: item
                        .get("number")
                        .and_then(Value::as_u64)
                        .map(|value| value as usize)
                        .unwrap_or(index + 1),
                    source: item
                        .get("source")
                        .and_then(Value::as_str)
                        .unwrap_or("unknown")
                        .to_string(),
                    prompt: item
                        .get("prompt")
                        .and_then(Value::as_str)
                        .map(str::to_string),
                    model: item.get("model").and_then(Value::as_str).map(str::to_string),
                    status: item
                        .get("status")
                        .and_then(Value::as_str)
                        .map(str::to_string),
                    resolution: item
                        .get("resolution")
                        .and_then(Value::as_str)
                        .map(str::to_string),
                    fallback: item
                        .get("fallback")
                        .and_then(Value::as_bool)
                        .unwrap_or(false),
                    file_name,
                    url_file_name,
                    png_data_url,
                    url,
                    notes: item.get("notes").and_then(Value::as_str).map(str::to_string),
                    revision_of: item
                        .get("revision_of")
                        .and_then(Value::as_str)
                        .map(str::to_string),
                    concept_id: item
                        .get("concept_id")
                        .and_then(Value::as_str)
                        .map(str::to_string),
                    concept: item.get("concept").cloned(),
                    style_family: item
                        .get("concept")
                        .and_then(|concept| concept.get("style_family"))
                        .and_then(Value::as_str)
                        .map(str::to_string),
                    scores: item.get("scores").cloned(),
                    score_total: item.get("score_total").and_then(Value::as_f64),
                });
            }
        }
    }
    if candidates.is_empty() {
        if let Some(png_data_url) = read_png_data_url_optional(&icon_work.join("icon_candidate_1.png")) {
            candidates.push(AppStudioAiIconCandidateSuggestion {
                candidate_id: "icon_candidate_1".to_string(),
                number: 1,
                source: "legacy".to_string(),
                prompt: read_text_optional(&icon_work.join("icon_prompt_revision.md"))
                    .or_else(|| read_text_optional(&icon_work.join("icon_prompt_initial.md"))),
                model: None,
                status: Some("legacy".to_string()),
                resolution: None,
                fallback: false,
                file_name: Some("icon_candidate_1.png".to_string()),
                url_file_name: None,
                png_data_url: Some(png_data_url),
                url: None,
                notes: Some("Legacy icon_candidate_1.png candidate.".to_string()),
                revision_of: None,
                concept_id: None,
                concept: None,
                style_family: None,
                scores: None,
                score_total: None,
            });
        } else if let Some(url) = read_text_optional(&icon_work.join("icon_candidate_1.url.txt")) {
            candidates.push(AppStudioAiIconCandidateSuggestion {
                candidate_id: "icon_candidate_1".to_string(),
                number: 1,
                source: "legacy".to_string(),
                prompt: read_text_optional(&icon_work.join("icon_prompt_revision.md"))
                    .or_else(|| read_text_optional(&icon_work.join("icon_prompt_initial.md"))),
                model: None,
                status: Some("legacy".to_string()),
                resolution: None,
                fallback: false,
                file_name: None,
                url_file_name: Some("icon_candidate_1.url.txt".to_string()),
                png_data_url: None,
                url: Some(url),
                notes: Some("Legacy icon_candidate_1.url.txt candidate.".to_string()),
                revision_of: None,
                concept_id: None,
                concept: None,
                style_family: None,
                scores: None,
                score_total: None,
            });
        }
    }
    candidates
}

fn read_summary(
    root: &Path,
    app_id: Option<&str>,
    output_dir: Option<&Path>,
) -> AppStudioResultSummary {
    let mut summary = AppStudioResultSummary::default();
    summary.app_studio_repo_root = Some(root.display().to_string());
    summary.catalog_root = Some(root.display().to_string());
    let output = output_dir
        .map(Path::to_path_buf)
        .or_else(|| app_id.and_then(|id| output_dir_from_app_yaml(root, id)));
    if let Some(path) = output {
        summary.output_dir = Some(path.display().to_string());
        read_import_plan(&path, &mut summary);
        read_execution_result(&path, &mut summary);
        read_runtime_result(&path, &mut summary);
        read_timing_result(&path, &mut summary);
        read_app_pack(&path, &mut summary);
    }
    if summary.app_id.is_none() {
        summary.app_id = app_id.map(str::to_string);
    }
    read_enabled(root, &mut summary);
    read_version(root, &mut summary);
    read_approval_record(root, &mut summary);
    read_catalog_status(root, &mut summary);
    summary
}

fn read_import_plan(output_dir: &Path, summary: &mut AppStudioResultSummary) {
    let path = output_dir.join("import_plan.json");
    let Some(json) = read_json(&path) else {
        return;
    };
    if let Some(value) = json.get("app_id").and_then(Value::as_str) {
        summary.app_id = Some(value.to_string());
    }
    if let Some(value) = json.get("selected_build_mode").and_then(Value::as_str) {
        summary.selected_build_mode = Some(value.to_string());
    }
    if let Some(value) = json.get("version").and_then(Value::as_str) {
        summary.version = Some(value.to_string());
    }
    if let Some(value) = json.get("metadata_override_used").and_then(Value::as_bool) {
        summary.metadata_override_used = value;
    }
    if let Some(items) = json.get("metadata_override_keys").and_then(Value::as_array) {
        summary.metadata_override_keys = items
            .iter()
            .filter_map(Value::as_str)
            .map(str::to_string)
            .collect();
    }
    if let Some(value) = json.get("icon_override_used").and_then(Value::as_bool) {
        summary.icon_override_used = value;
    }
    if let Some(value) = json.get("selected_icon_source").and_then(Value::as_str) {
        summary.selected_icon_source = Some(value.to_string());
    }
    if let Some(value) = json.get("exe_readiness_status").and_then(Value::as_str) {
        summary.exe_readiness_status = Some(value.to_string());
    }
    if let Some(items) = json.get("manual_checks").and_then(Value::as_array) {
        summary.manual_checks = items
            .iter()
            .filter_map(Value::as_str)
            .map(str::to_string)
            .collect();
    }
    summary.secret_blocking_count = json
        .get("blocking_secret_findings_count")
        .and_then(Value::as_u64)
        .unwrap_or(0) as usize;
    summary.secret_warning_count = json
        .get("warning_secret_findings_count")
        .and_then(Value::as_u64)
        .unwrap_or(0) as usize;
    summary.secret_manual_check_count = json
        .get("manual_check_secret_findings_count")
        .and_then(Value::as_u64)
        .unwrap_or(0) as usize;
    summary.ai_blocked_by_secret_scan = json
        .get("ai_blocked_by_secret_scan")
        .and_then(Value::as_bool)
        .unwrap_or(false);
    summary.apply_blocked_by_secret_scan = json
        .get("apply_blocked_by_secret_scan")
        .and_then(Value::as_bool)
        .unwrap_or(false);
    if let Some(value) = json.get("secret_scan_report").and_then(Value::as_str) {
        summary.secret_scan_report = Some(value.to_string());
    }
    if let Some(items) = json.get("blocking_secret_findings").and_then(Value::as_array) {
        summary.secret_blocking_findings = items
            .iter()
            .filter_map(Value::as_str)
            .map(str::to_string)
            .collect();
    }
}

fn read_execution_result(output_dir: &Path, summary: &mut AppStudioResultSummary) {
    let path = output_dir.join("execution_test_result.json");
    let Some(json) = read_json(&path) else {
        return;
    };
    if let Some(value) = json.get("overall_status").and_then(Value::as_str) {
        summary.execution_status = Some(value.to_string());
    }
    if let Some(value) = json.get("approval_allowed").and_then(Value::as_bool) {
        summary.approval_allowed = Some(value);
    }
    summary.approval_blocking_warnings_count = json
        .get("approval_blocking_warnings_count")
        .and_then(Value::as_u64)
        .unwrap_or(0) as usize;
    summary.non_blocking_warnings_count = json
        .get("non_blocking_warnings_count")
        .and_then(Value::as_u64)
        .unwrap_or(0) as usize;
    summary.info_count = json.get("info_count").and_then(Value::as_u64).unwrap_or(0) as usize;
    summary.unresolved_distribution_risks_count = json
        .get("unresolved_distribution_risks_count")
        .and_then(Value::as_u64)
        .unwrap_or(0) as usize;
    summary.approval_blocking_reasons = string_array(json.get("approval_blocking_reasons"));
    summary.non_blocking_warning_summaries = string_array(json.get("non_blocking_warning_summaries"));
}

fn read_timing_result(output_dir: &Path, summary: &mut AppStudioResultSummary) {
    let path = output_dir.join("timing_report.json");
    let Some(json) = read_json(&path) else {
        return;
    };
    summary.timing_report = Some(path.display().to_string());
    summary.timing_total_seconds = json
        .get("actual_total_seconds")
        .and_then(number_value)
        .or_else(|| json.get("wall_clock_total_seconds").and_then(number_value))
        .or_else(|| json.get("total_duration_seconds").and_then(number_value));
    summary.timing_estimated_total_seconds = json
        .get("estimated_total_seconds")
        .and_then(number_value);
    summary.timing_actual_total_seconds = json.get("actual_total_seconds").and_then(number_value);
    summary.timing_prediction_error_seconds = json.get("prediction_error_seconds").and_then(number_value);
    summary.timing_prediction_source = json
        .get("prediction_source")
        .and_then(Value::as_str)
        .map(str::to_string);
    summary.timing_wall_clock_total_seconds = json.get("wall_clock_total_seconds").and_then(number_value);
    summary.timing_cli_measured_total_seconds = json.get("cli_measured_total_seconds").and_then(number_value);
    summary.timing_unmeasured_overhead_seconds = json.get("unmeasured_overhead_seconds").and_then(number_value);
    if let Some(items) = json.get("phases").and_then(Value::as_array) {
        summary.timing_phases = items
            .iter()
            .filter_map(|item| {
                Some(AppStudioTimingPhase {
                    phase: item.get("phase")?.as_str()?.to_string(),
                    label: item
                        .get("label")
                        .and_then(Value::as_str)
                        .unwrap_or_else(|| item.get("phase").and_then(Value::as_str).unwrap_or(""))
                        .to_string(),
                    status: item
                        .get("status")
                        .and_then(Value::as_str)
                        .unwrap_or("unknown")
                        .to_string(),
                    duration_seconds: item.get("duration_seconds").and_then(Value::as_f64),
                })
            })
            .collect();
    }
}

fn number_value(value: &Value) -> Option<f64> {
    value
        .as_f64()
        .or_else(|| value.as_i64().map(|number| number as f64))
        .or_else(|| value.as_u64().map(|number| number as f64))
}

fn read_runtime_result(output_dir: &Path, summary: &mut AppStudioResultSummary) {
    let path = output_dir.join("runtime_check_result.json");
    let Some(json) = read_json(&path) else {
        return;
    };
    if let Some(value) = json.get("overall_status").and_then(Value::as_str) {
        summary.runtime_status = Some(value.to_string());
    }
}

fn string_array(value: Option<&Value>) -> Vec<String> {
    value
        .and_then(Value::as_array)
        .map(|items| {
            items
                .iter()
                .filter_map(Value::as_str)
                .map(str::to_string)
                .collect()
        })
        .unwrap_or_default()
}

fn read_app_pack(output_dir: &Path, summary: &mut AppStudioResultSummary) {
    let app_pack_dir = output_dir.join("app_pack");
    let Ok(entries) = std::fs::read_dir(app_pack_dir) else {
        return;
    };
    for entry in entries.flatten() {
        let path = entry.path();
        if path.extension().and_then(|value| value.to_str()) == Some("zip") {
            summary.app_pack = Some(path.display().to_string());
            return;
        }
    }
}

fn read_enabled(root: &Path, summary: &mut AppStudioResultSummary) {
    let Some(app_id) = summary.app_id.as_deref() else {
        return;
    };
    let Some(json) = read_json(&root.join("release").join("app_manifest.json")) else {
        return;
    };
    summary.manifest_enabled = json
        .get("apps")
        .and_then(|apps| apps.get(app_id))
        .and_then(|entry| entry.get("enabled"))
        .and_then(Value::as_bool);
    summary.enabled = summary.manifest_enabled;
}

fn read_approval_record(root: &Path, summary: &mut AppStudioResultSummary) {
    let Some(app_id) = summary.app_id.as_deref() else {
        return;
    };
    let path = root
        .join("data")
        .join("logs")
        .join("app_studio")
        .join(format!("{app_id}_approval_record.md"));
    if !path.is_file() {
        return;
    }
    summary.approval_record_path = Some(path.display().to_string());
    let Ok(text) = std::fs::read_to_string(&path) else {
        summary.approval_failure_summary = Some("approval_record.md could not be read".to_string());
        return;
    };
    summary.approval_record_status = parse_record_bullet(&text, "status");
    summary.verify_release_status = parse_record_bullet(&text, "verify_release_after");
    let failures = section_bullets(&text, "## Failures");
    if !failures.is_empty() {
        summary.approval_failure_summary = Some(failures.join(" | "));
    }
    let verify_failures = extract_json_array_preview(&text, "\"rollback_failures\"")
        .or_else(|| extract_json_array_preview(&text, "\"new_failures\""))
        .or_else(|| extract_ng_lines_preview(&text));
    summary.verify_release_failure_summary = verify_failures;
}

fn read_catalog_status(root: &Path, summary: &mut AppStudioResultSummary) {
    let Some(app_id) = summary.app_id.as_deref() else {
        return;
    };
    let app_yaml = root.join("apps").join(app_id).join("app.yaml");
    if !app_yaml.is_file() {
        summary.catalog_visible = Some(false);
        summary.catalog_enabled = Some(false);
        summary.catalog_disabled_reason = Some("app_yaml_missing".to_string());
        return;
    }
    match crate::manifest::load_apps(root) {
        Ok(apps) => {
            if let Some(app) = apps.into_iter().find(|app| app.id == app_id) {
                summary.catalog_enabled = Some(app.enabled);
                summary.catalog_visible = Some(app.enabled);
                if !app.enabled {
                    summary.catalog_disabled_reason = app
                        .disabled_reason
                        .or_else(|| Some("disabled_by_manifest_or_catalog_validation".to_string()));
                }
            } else {
                summary.catalog_visible = Some(false);
                summary.catalog_enabled = Some(false);
                summary.catalog_disabled_reason = Some("not_found_in_catalog".to_string());
            }
        }
        Err(error) => {
            summary.catalog_visible = Some(false);
            summary.catalog_enabled = Some(false);
            summary.catalog_load_error = Some(error.to_string());
            summary.catalog_disabled_reason = Some("catalog_load_error".to_string());
        }
    }
}

fn parse_record_bullet(text: &str, key: &str) -> Option<String> {
    let prefix = format!("- {key}:");
    text.lines().find_map(|line| {
        let trimmed = line.trim();
        trimmed
            .strip_prefix(&prefix)
            .map(|value| value.trim().trim_matches('`').trim().to_string())
            .filter(|value| !value.is_empty())
    })
}

fn section_bullets(text: &str, heading: &str) -> Vec<String> {
    let mut in_section = false;
    let mut items = Vec::new();
    for line in text.lines() {
        let trimmed = line.trim();
        if trimmed.starts_with("## ") {
            in_section = trimmed == heading;
            continue;
        }
        if in_section {
            if let Some(value) = trimmed.strip_prefix("- ") {
                if !value.trim().is_empty() {
                    items.push(value.trim().to_string());
                }
            }
        }
    }
    items
}

fn extract_ng_lines_preview(text: &str) -> Option<String> {
    let lines = text
        .lines()
        .filter(|line| line.contains("[NG]"))
        .map(|line| line.trim().to_string())
        .take(5)
        .collect::<Vec<_>>();
    if lines.is_empty() {
        None
    } else {
        Some(lines.join(" | "))
    }
}

fn extract_json_array_preview(text: &str, key: &str) -> Option<String> {
    let start = text.find(key)?;
    let rest = &text[start..];
    let open = rest.find('[')?;
    let close = rest[open..].find(']')?;
    let raw = &rest[open..=open + close];
    let value: Value = serde_json::from_str(raw).ok()?;
    let items = value
        .as_array()?
        .iter()
        .filter_map(Value::as_str)
        .take(5)
        .map(str::to_string)
        .collect::<Vec<_>>();
    if items.is_empty() {
        None
    } else {
        Some(items.join(" | "))
    }
}

fn read_version(root: &Path, summary: &mut AppStudioResultSummary) {
    let Some(app_id) = summary.app_id.as_deref() else {
        return;
    };
    let manifest_version =
        read_json(&root.join("release").join("app_manifest.json")).and_then(|json| {
            json.get("apps")
                .and_then(|apps| apps.get(app_id))
                .and_then(|entry| entry.get("version"))
                .and_then(Value::as_str)
                .map(str::to_string)
        });
    if let Some(version) = manifest_version {
        summary.version = Some(version);
        return;
    }
    if summary.version.is_none() {
        if let Ok(text) = std::fs::read_to_string(root.join("apps").join(app_id).join("app.yaml")) {
            if let Ok(yaml) = serde_yaml::from_str::<serde_yaml::Value>(&text) {
                if let Some(version) = yaml_str(&yaml, &["admin", "version"]) {
                    summary.version = Some(version);
                }
            }
        }
    }
}

fn list_registered_apps_from_root(root: &Path) -> Vec<AppStudioRegisteredApp> {
    let apps_dir = root.join("apps");
    let release = read_json(&root.join("release").join("app_manifest.json"));
    let mut apps = Vec::new();
    let Ok(entries) = std::fs::read_dir(apps_dir) else {
        return apps;
    };

    for entry in entries.flatten() {
        let app_dir = entry.path();
        if !app_dir.is_dir() {
            continue;
        }
        let dir_id = app_dir
            .file_name()
            .and_then(|value| value.to_str())
            .unwrap_or("unknown_app")
            .to_string();
        let app_yaml = app_dir.join("app.yaml");
        if !app_yaml.is_file() {
            continue;
        }
        let mut registered = match read_registered_app_from_yaml(&app_yaml, &dir_id) {
            Ok(app) => app,
            Err(error) => AppStudioRegisteredApp {
                app_id: dir_id.clone(),
                name: dir_id.clone(),
                enabled: false,
                warning: Some(error),
                ..AppStudioRegisteredApp::default()
            },
        };
        apply_release_manifest_data(&mut registered, release.as_ref());
        apps.push(registered);
    }
    apps.sort_by(|a, b| a.app_id.cmp(&b.app_id));
    apps
}

fn find_registered_app(root: &Path, app_id: &str) -> Option<AppStudioRegisteredApp> {
    list_registered_apps_from_root(root)
        .into_iter()
        .find(|app| app.app_id == app_id)
}

fn read_registered_app_from_yaml(
    app_yaml: &Path,
    dir_id: &str,
) -> Result<AppStudioRegisteredApp, String> {
    let text = std::fs::read_to_string(app_yaml).map_err(|error| error.to_string())?;
    let yaml: serde_yaml::Value = serde_yaml::from_str(&text).map_err(|error| error.to_string())?;
    let app_id = yaml_str(&yaml, &["id"]).unwrap_or_else(|| dir_id.to_string());
    let name = yaml_str(&yaml, &["name"]).unwrap_or_else(|| app_id.clone());
    let version = yaml_str(&yaml, &["admin", "version"]).unwrap_or_else(|| "0.1.0".to_string());
    Ok(AppStudioRegisteredApp {
        app_id,
        name,
        version,
        enabled: false,
        build_mode: yaml_str(&yaml, &["build", "build_mode"]),
        runner: yaml_str(&yaml, &["run", "runner"]),
        entry: yaml_str(&yaml, &["run", "entry"]),
        description: yaml_str(&yaml, &["display", "short_description"])
            .or_else(|| yaml_str(&yaml, &["detail", "description"])),
        warning: None,
    })
}

fn apply_release_manifest_data(app: &mut AppStudioRegisteredApp, release: Option<&Value>) {
    let Some(release) = release else {
        return;
    };
    let Some(entry) = release.get("apps").and_then(|apps| apps.get(&app.app_id)) else {
        return;
    };
    if let Some(version) = entry.get("version").and_then(Value::as_str) {
        app.version = version.to_string();
    }
    if let Some(enabled) = entry.get("enabled").and_then(Value::as_bool) {
        app.enabled = enabled;
    }
}

fn yaml_str(value: &serde_yaml::Value, path: &[&str]) -> Option<String> {
    let mut current = value;
    for key in path {
        let serde_yaml::Value::Mapping(map) = current else {
            return None;
        };
        current = map.get(&serde_yaml::Value::String((*key).to_string()))?;
    }
    current.as_str().map(|value| value.trim().to_string())
}

fn import_request_from_update(request: &AppStudioUpdateRequest) -> AppStudioImportRequest {
    AppStudioImportRequest {
        entry: request.entry.clone(),
        app_id: Some(request.app_id.clone()),
        name: request.name.clone(),
        version: Some(request.new_version.clone()),
        build_mode: request.build_mode.clone(),
        icon_prompt: request.icon_prompt.clone(),
        metadata: request.metadata.clone(),
        icon_override: request.icon_override.clone(),
        build_profile: request.build_profile.clone(),
        create_app_env: request.create_app_env,
        rebuild_app_env: request.rebuild_app_env,
        generate_lock: request.generate_lock,
        build_frozen_folder: request.build_frozen_folder,
        verify_runtime: request.verify_runtime,
    }
}

fn parse_semver(value: &str) -> Option<(u64, u64, u64)> {
    let parts = value.trim().split('.').collect::<Vec<_>>();
    if parts.len() != 3 {
        return None;
    }
    Some((
        parts[0].parse().ok()?,
        parts[1].parse().ok()?,
        parts[2].parse().ok()?,
    ))
}

fn compare_semver(current: &str, next: &str) -> Option<Ordering> {
    Some(parse_semver(current)?.cmp(&parse_semver(next)?))
}

#[cfg(test)]
fn bump_version(current: &str, mode: &str) -> Result<String, String> {
    let (major, minor, patch) =
        parse_semver(current).ok_or_else(|| "Version is not simple SemVer.".to_string())?;
    match mode {
        "patch" => Ok(format!("{major}.{minor}.{}", patch + 1)),
        "minor" => Ok(format!("{major}.{}.0", minor + 1)),
        "major" => Ok(format!("{}.0.0", major + 1)),
        _ => Err("Unsupported version bump mode.".to_string()),
    }
}

fn output_dir_from_app_yaml(root: &Path, app_id: &str) -> Option<PathBuf> {
    let app_yaml = root.join("apps").join(app_id).join("app.yaml");
    let text = std::fs::read_to_string(app_yaml).ok()?;
    for line in text.lines() {
        let trimmed = line.trim();
        if trimmed.starts_with("output_mirror:") {
            let value = trimmed
                .split_once(':')?
                .1
                .trim()
                .trim_matches('"')
                .trim_matches('\'');
            if !value.is_empty() {
                return Some(PathBuf::from(value));
            }
        }
    }
    None
}

fn read_json(path: &Path) -> Option<Value> {
    let text = std::fs::read_to_string(path).ok()?;
    serde_json::from_str(&text).ok()
}

fn extract_output_dir(stdout: &str) -> Option<PathBuf> {
    for line in stdout.lines() {
        let trimmed = line.trim();
        if let Some(value) = trimmed.strip_prefix("- output: ") {
            return Some(PathBuf::from(value.trim()));
        }
        if let Some(value) = trimmed.strip_prefix("Suggestion artifacts were saved: ") {
            return Some(PathBuf::from(value.trim()));
        }
    }
    None
}

fn extract_app_id(stdout: &str) -> Option<String> {
    for line in stdout.lines() {
        let trimmed = line.trim();
        if let Some(value) = trimmed.strip_prefix("- app_id: ") {
            return Some(value.trim().to_string());
        }
    }
    None
}

fn infer_output_dir(request: &AppStudioImportRequest, stdout: &str) -> Option<PathBuf> {
    let app_id = clean_optional(&request.app_id)
        .map(str::to_string)
        .or_else(|| extract_app_id(stdout))?;
    let entry = PathBuf::from(&request.entry);
    Some(
        entry
            .parent()?
            .join("ToolHub_AppStudio_Output")
            .join(app_id),
    )
}

fn clean_optional(value: &Option<String>) -> Option<&str> {
    value
        .as_deref()
        .map(str::trim)
        .filter(|value| !value.is_empty())
}

fn write_metadata_override_file(
    request: &AppStudioImportRequest,
) -> Result<Option<(PathBuf, Vec<String>)>, String> {
    let Some((payload, keys)) = metadata_override_payload(&request.metadata) else {
        return Ok(None);
    };
    let dir = crate::setup::user_data_root()
        .join("data")
        .join("app_studio")
        .join("metadata_overrides");
    std::fs::create_dir_all(&dir)
        .map_err(|_| "Could not create App Studio metadata override directory.".to_string())?;
    let app_stem = clean_optional(&request.app_id).unwrap_or("pending");
    let stamp = chrono::Local::now().timestamp_millis();
    let path = dir.join(format!("{}_{}.json", safe_file_stem(app_stem), stamp));
    let text = serde_json::to_string_pretty(&payload)
        .map_err(|_| "Could not serialize App Studio metadata override.".to_string())?;
    std::fs::write(&path, text)
        .map_err(|_| "Could not write App Studio metadata override file.".to_string())?;
    Ok(Some((path, keys)))
}

fn write_icon_override_file(
    request: &AppStudioImportRequest,
) -> Result<Option<(PathBuf, String)>, String> {
    let Some((payload, source)) = icon_override_payload(&request.icon_override)? else {
        return Ok(None);
    };
    let dir = crate::setup::user_data_root()
        .join("data")
        .join("app_studio")
        .join("icon_overrides");
    std::fs::create_dir_all(&dir)
        .map_err(|_| "Could not create App Studio icon override directory.".to_string())?;
    let app_stem = clean_optional(&request.app_id).unwrap_or("pending");
    let stamp = chrono::Local::now().timestamp_millis();
    let path = dir.join(format!("{}_{}.json", safe_file_stem(app_stem), stamp));
    let text = serde_json::to_string_pretty(&payload)
        .map_err(|_| "Could not serialize App Studio icon override.".to_string())?;
    std::fs::write(&path, text)
        .map_err(|_| "Could not write App Studio icon override file.".to_string())?;
    Ok(Some((path, source)))
}

fn write_build_profile_override_file(
    request: &AppStudioImportRequest,
) -> Result<Option<PathBuf>, String> {
    let Some(payload) = build_profile_payload(&request.build_profile) else {
        return Ok(None);
    };
    let dir = crate::setup::user_data_root()
        .join("data")
        .join("app_studio")
        .join("build_profile_overrides");
    std::fs::create_dir_all(&dir)
        .map_err(|_| "Could not create App Studio build profile override directory.".to_string())?;
    let app_stem = clean_optional(&request.app_id).unwrap_or("pending");
    let stamp = chrono::Local::now().timestamp_millis();
    let path = dir.join(format!("{}_{}.json", safe_file_stem(app_stem), stamp));
    let text = serde_json::to_string_pretty(&payload)
        .map_err(|_| "Could not serialize App Studio build profile override.".to_string())?;
    std::fs::write(&path, text)
        .map_err(|_| "Could not write App Studio build profile override file.".to_string())?;
    Ok(Some(path))
}

fn build_profile_payload(build_profile: &Option<Value>) -> Option<Value> {
    let value = build_profile.as_ref()?;
    match value {
        Value::Object(map) if map.is_empty() => None,
        Value::Null => None,
        _ => Some(value.clone()),
    }
}

fn icon_override_payload(
    icon_override: &Option<AppStudioIconOverride>,
) -> Result<Option<(Value, String)>, String> {
    let Some(icon_override) = icon_override.as_ref() else {
        return Ok(None);
    };
    let source = icon_override
        .selected_icon_source
        .as_deref()
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .unwrap_or("fallback_png");
    if source == "fallback_png" {
        return Ok(None);
    }
    if source != "candidate_png" && source != "final_png" {
        return Err("Icon override source is invalid.".to_string());
    }
    let png_data_url = icon_override
        .png_data_url
        .as_deref()
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .ok_or_else(|| "PNG icon data is required when adopting a PNG candidate.".to_string())?;
    if !png_data_url.starts_with("data:image/png;base64,") {
        return Err("PNG icon data must be a data:image/png;base64 URL.".to_string());
    }

    let mut map = Map::new();
    map.insert(
        "selected_icon_source".to_string(),
        Value::String(source.to_string()),
    );
    map.insert(
        "png_base64".to_string(),
        Value::String(png_data_url.to_string()),
    );
    if let Some(candidate_id) = icon_override
        .candidate_id
        .as_deref()
        .map(str::trim)
        .filter(|value| !value.is_empty())
    {
        map.insert(
            "candidate_id".to_string(),
            Value::String(candidate_id.to_string()),
        );
    }
    Ok(Some((Value::Object(map), source.to_string())))
}

fn build_ai_env_plan() -> AiEnvPlan {
    let user_data_root = crate::setup::user_data_root();
    let settings = crate::ai_settings::load_settings_at(&user_data_root)
        .unwrap_or_else(|_| crate::ai_settings::default_settings());
    let text_model = settings.text_model.trim().to_string();
    let image_model = settings.image_model.trim().to_string();
    let credential_supported = crate::secret_store::credential_manager_supported();
    let credential_key = crate::secret_store::read_openai_api_key()
        .ok()
        .flatten()
        .map(|value| value.trim().to_string())
        .filter(|value| !value.is_empty());
    let env_key = crate::secret_store::env_openai_api_key();
    let (api_key_source, api_key) = if let Some(value) = credential_key {
        ("credential".to_string(), Some(value))
    } else if let Some(value) = env_key {
        ("environment".to_string(), Some(value))
    } else {
        ("missing".to_string(), None)
    };
    let api_key_present = api_key.is_some();
    let text_model_set = !text_model.is_empty();
    let image_model_set = !image_model.is_empty();
    let cli_env_ready =
        settings.ai_enabled && api_key_present && (text_model_set || image_model_set);
    let message = if !settings.ai_enabled {
        "AI is disabled; CLI will use fallback.".to_string()
    } else if !api_key_present {
        "API key is missing; CLI will use fallback.".to_string()
    } else if !text_model_set && !image_model_set {
        "No AI models are configured; CLI will use fallback.".to_string()
    } else {
        "CLI AI environment is ready.".to_string()
    };

    AiEnvPlan {
        diagnostics: AppStudioAiDiagnostics {
            ai_enabled: settings.ai_enabled,
            api_key_source,
            api_key_present,
            text_model,
            text_model_set,
            image_model,
            image_model_set,
            cli_env_ready,
            credential_supported,
            message,
        },
        api_key,
    }
}

fn apply_ai_environment(command: &mut Command, plan: &AiEnvPlan) {
    command.env(
        "TOOLHUB_APP_STUDIO_AI_ENABLED",
        if plan.diagnostics.ai_enabled {
            "true"
        } else {
            "false"
        },
    );
    command.env(
        "TOOLHUB_APP_STUDIO_TEXT_MODEL",
        &plan.diagnostics.text_model,
    );
    command.env(
        "TOOLHUB_APP_STUDIO_IMAGE_MODEL",
        &plan.diagnostics.image_model,
    );
    command.env_remove("OPENAI_API_KEY");
    if plan.diagnostics.ai_enabled {
        if let Some(api_key) = plan.api_key.as_ref() {
            command.env("OPENAI_API_KEY", api_key);
        }
    }
}

fn metadata_override_payload(
    metadata: &Option<AppStudioEditableMetadata>,
) -> Option<(Value, Vec<String>)> {
    let metadata = metadata.as_ref()?;
    let mut map = Map::new();
    let mut keys = Vec::new();

    insert_string_override(
        &mut map,
        &mut keys,
        "short_description",
        metadata.short_description.as_deref(),
    );
    insert_string_override(
        &mut map,
        &mut keys,
        "description",
        metadata.description.as_deref(),
    );
    insert_string_override(
        &mut map,
        &mut keys,
        "change_summary",
        metadata.change_summary.as_deref(),
    );
    insert_list_override(
        &mut map,
        &mut keys,
        "categories",
        metadata.categories.as_ref(),
    );
    insert_list_override(&mut map, &mut keys, "keywords", metadata.keywords.as_ref());
    insert_list_override(&mut map, &mut keys, "examples", metadata.examples.as_ref());
    insert_list_override(
        &mut map,
        &mut keys,
        "use_cases",
        metadata.use_cases.as_ref(),
    );
    insert_list_override(&mut map, &mut keys, "inputs", metadata.inputs.as_ref());
    insert_list_override(&mut map, &mut keys, "outputs", metadata.outputs.as_ref());
    insert_list_override(&mut map, &mut keys, "notes", metadata.notes.as_ref());
    insert_list_override(
        &mut map,
        &mut keys,
        "release_notes",
        metadata.release_notes.as_ref(),
    );

    if map.is_empty() {
        None
    } else {
        Some((Value::Object(map), keys))
    }
}

fn insert_string_override(
    map: &mut Map<String, Value>,
    keys: &mut Vec<String>,
    key: &str,
    value: Option<&str>,
) {
    let Some(cleaned) = value.map(str::trim).filter(|value| !value.is_empty()) else {
        return;
    };
    map.insert(key.to_string(), Value::String(cleaned.to_string()));
    keys.push(key.to_string());
}

fn insert_list_override(
    map: &mut Map<String, Value>,
    keys: &mut Vec<String>,
    key: &str,
    value: Option<&Vec<String>>,
) {
    let Some(value) = value else {
        return;
    };
    let items: Vec<Value> = value
        .iter()
        .map(|item| item.trim())
        .filter(|item| !item.is_empty())
        .map(|item| Value::String(item.to_string()))
        .collect();
    if items.is_empty() {
        return;
    }
    map.insert(key.to_string(), Value::Array(items));
    keys.push(key.to_string());
}

fn safe_file_stem(value: &str) -> String {
    let stem: String = value
        .chars()
        .map(|character| {
            if character.is_ascii_alphanumeric() || character == '_' || character == '-' {
                character
            } else {
                '_'
            }
        })
        .collect();
    if stem.is_empty() {
        "pending".to_string()
    } else {
        stem
    }
}

fn approval_flag(strict: bool) -> &'static str {
    if strict {
        "--strict-approval"
    } else {
        "--allow-warnings"
    }
}

fn approval_mode_name(strict: bool) -> &'static str {
    if strict {
        "StrictApproval"
    } else {
        "AllowWarnings"
    }
}

#[cfg(windows)]
fn pick_entry_file() -> Result<Option<String>, String> {
    let script = r#"
Add-Type -AssemblyName System.Windows.Forms
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$dialog = New-Object System.Windows.Forms.OpenFileDialog
$dialog.Title = 'ToolHub App Studio Entry'
$dialog.Filter = 'Python source (*.py)|*.py|All files (*.*)|*.*'
$dialog.CheckFileExists = $true
$dialog.Multiselect = $false
if ($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {
  Write-Output $dialog.FileName
}
"#;
    let output = Command::new("powershell")
        .arg("-NoProfile")
        .arg("-STA")
        .arg("-ExecutionPolicy")
        .arg("Bypass")
        .arg("-Command")
        .arg(script)
        .output()
        .map_err(|_| {
            "ファイル選択ダイアログを開けませんでした。手入力で続行してください。".to_string()
        })?;
    if !output.status.success() {
        return Err(
            "ファイル選択ダイアログでエラーが発生しました。手入力で続行してください。".to_string(),
        );
    }
    let value = String::from_utf8_lossy(&output.stdout).trim().to_string();
    if value.is_empty() {
        Ok(None)
    } else {
        Ok(Some(value))
    }
}

#[cfg(not(windows))]
fn pick_entry_file() -> Result<Option<String>, String> {
    Err("この環境ではファイル選択ダイアログを使用できません。Entryファイルパスを手入力してください。".to_string())
}

fn mask_sensitive(text: &str) -> String {
    let chars: Vec<char> = text.chars().collect();
    let mut output = String::with_capacity(text.len());
    let mut index = 0;
    while index < chars.len() {
        if chars[index] == 's'
            && chars.get(index + 1) == Some(&'k')
            && chars.get(index + 2) == Some(&'-')
        {
            let start = index;
            index += 3;
            while index < chars.len()
                && (chars[index].is_ascii_alphanumeric()
                    || chars[index] == '-'
                    || chars[index] == '_')
            {
                index += 1;
            }
            let token: String = chars[start..index].iter().collect();
            output.push_str(&crate::secret_store::mask_secret(&token));
        } else {
            output.push(chars[index]);
            index += 1;
        }
    }
    output
}

fn append_app_studio_gui_log(event: &str, attrs: &[(&str, String)]) {
    let log_dir = crate::setup::user_data_root()
        .join("data")
        .join("logs")
        .join("admin");
    if std::fs::create_dir_all(&log_dir).is_err() {
        return;
    }
    let path = log_dir.join("app_studio_gui.log");
    if let Ok(mut file) = std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(path)
    {
        use std::io::Write;
        let mut line = format!("{} {}", chrono::Local::now().to_rfc3339(), event);
        for (key, value) in attrs {
            if !value.trim().is_empty() {
                line.push(' ');
                line.push_str(key);
                line.push('=');
                line.push_str(&mask_sensitive(value));
            }
        }
        let _ = writeln!(file, "{line}");
    }
}

fn command_line_for_log(program: &Path, args: &[String]) -> String {
    let mut parts = vec![quote_log_arg(&program.display().to_string())];
    parts.extend(args.iter().map(|arg| quote_log_arg(arg)));
    parts.join(" ")
}

fn quote_log_arg(value: &str) -> String {
    if value.chars().any(|ch| ch.is_whitespace()) {
        format!("\"{}\"", value.replace('"', "\\\""))
    } else {
        value.to_string()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::{SystemTime, UNIX_EPOCH};

    fn temp_entry() -> PathBuf {
        let stamp = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let root = std::env::temp_dir().join(format!("toolhub_app_studio_gui_{stamp}"));
        std::fs::create_dir_all(&root).unwrap();
        let entry = root.join("main.py");
        std::fs::write(&entry, "print('hello')\n").unwrap();
        entry
    }

    #[test]
    fn app_studio_commands_require_admin_session() {
        let session = AdminSessionState::new();
        assert!(session.require_authenticated().is_err());
    }

    #[test]
    fn request_validation_accepts_safe_request() {
        let entry = temp_entry();
        let request = AppStudioImportRequest {
            entry: entry.display().to_string(),
            app_id: Some("my_tool".to_string()),
            name: Some("My Tool".to_string()),
            version: None,
            build_mode: "frozen-folder".to_string(),
            icon_prompt: None,
            metadata: None,
            icon_override: None,
            build_profile: None,
            create_app_env: false,
            rebuild_app_env: false,
            generate_lock: false,
            build_frozen_folder: false,
            verify_runtime: false,
        };
        assert!(validate_request(&request).is_ok());
        let _ = std::fs::remove_dir_all(entry.parent().unwrap());
    }

    #[test]
    fn app_id_validation_rejects_invalid_values() {
        assert!(validate_app_id("my_tool-1").is_ok());
        assert!(validate_app_id("BadId").is_err());
        assert!(validate_app_id("_bad").is_err());
    }

    #[test]
    fn preflight_reports_missing_python() {
        let entry = temp_entry();
        let request = AppStudioImportRequest {
            entry: entry.display().to_string(),
            app_id: Some("my_tool".to_string()),
            name: Some("My Tool".to_string()),
            version: None,
            build_mode: "app-env".to_string(),
            icon_prompt: None,
            metadata: None,
            icon_override: None,
            build_profile: None,
            create_app_env: false,
            rebuild_app_env: false,
            generate_lock: false,
            build_frozen_folder: false,
            verify_runtime: false,
        };
        let result = preflight_for_request(&request, entry.parent().unwrap(), None);
        assert!(!result.ok);
        assert_eq!(result.python_source, "missing");
        assert!(result.errors.iter().any(|item| item.contains("Python")));
        let _ = std::fs::remove_dir_all(entry.parent().unwrap());
    }

    #[test]
    fn approval_mode_maps_to_cli_flags() {
        assert_eq!(approval_flag(true), "--strict-approval");
        assert_eq!(approval_flag(false), "--allow-warnings");
        assert_eq!(approval_mode_name(true), "StrictApproval");
        assert_eq!(approval_mode_name(false), "AllowWarnings");
    }

    #[test]
    fn secret_masking_hides_openai_key() {
        let masked = mask_sensitive("key=<DUMMY_OPENAI_API_KEY> done");
        assert!(masked.contains("sk-...abcd"));
        assert!(!masked.contains("test123456"));
    }

    #[test]
    fn ai_environment_sets_cli_env_when_enabled() {
        let plan = AiEnvPlan {
            diagnostics: AppStudioAiDiagnostics {
                ai_enabled: true,
                api_key_source: "credential".to_string(),
                api_key_present: true,
                text_model: "text-model".to_string(),
                text_model_set: true,
                image_model: "gpt-image-2".to_string(),
                image_model_set: true,
                cli_env_ready: true,
                credential_supported: true,
                message: "ready".to_string(),
            },
            api_key: Some("<DUMMY_OPENAI_API_KEY>".to_string()),
        };
        let mut command = Command::new("python");

        apply_ai_environment(&mut command, &plan);

        let envs = command_envs(&command);
        assert_eq!(
            envs.get("TOOLHUB_APP_STUDIO_AI_ENABLED")
                .map(String::as_str),
            Some("true")
        );
        assert_eq!(
            envs.get("TOOLHUB_APP_STUDIO_IMAGE_MODEL")
                .map(String::as_str),
            Some("gpt-image-2")
        );
        assert_eq!(
            envs.get("OPENAI_API_KEY").map(String::as_str),
            Some("<DUMMY_OPENAI_API_KEY>")
        );
    }

    #[test]
    fn ai_environment_omits_api_key_when_disabled() {
        let plan = AiEnvPlan {
            diagnostics: AppStudioAiDiagnostics {
                ai_enabled: false,
                api_key_source: "credential".to_string(),
                api_key_present: true,
                text_model: "text-model".to_string(),
                text_model_set: true,
                image_model: "gpt-image-2".to_string(),
                image_model_set: true,
                cli_env_ready: false,
                credential_supported: true,
                message: "disabled".to_string(),
            },
            api_key: Some("<DUMMY_OPENAI_API_KEY>".to_string()),
        };
        let mut command = Command::new("python");

        apply_ai_environment(&mut command, &plan);

        let envs = command_envs(&command);
        assert_eq!(
            envs.get("TOOLHUB_APP_STUDIO_AI_ENABLED")
                .map(String::as_str),
            Some("false")
        );
        assert!(!envs.contains_key("OPENAI_API_KEY"));
    }

    #[test]
    fn metadata_override_payload_uses_only_non_empty_fields() {
        let metadata = Some(AppStudioEditableMetadata {
            short_description: Some("Short".to_string()),
            description: Some(" ".to_string()),
            categories: Some(vec!["ops".to_string(), " ".to_string()]),
            keywords: Some(vec!["tool".to_string()]),
            ..AppStudioEditableMetadata::default()
        });

        let (payload, keys) = metadata_override_payload(&metadata).unwrap();
        let object = payload.as_object().unwrap();

        assert_eq!(
            object.get("short_description").and_then(Value::as_str),
            Some("Short")
        );
        assert!(object.get("description").is_none());
        assert_eq!(keys, vec!["short_description", "categories", "keywords"]);
    }

    #[test]
    fn icon_override_payload_accepts_png_data_url_only_for_adopted_png() {
        let icon_override = Some(AppStudioIconOverride {
            selected_icon_source: Some("candidate_png".to_string()),
            png_data_url: Some("data:image/png;base64,iVBORw0KGgo=".to_string()),
            candidate_id: Some("icon_candidate_2".to_string()),
        });

        let (payload, source) = icon_override_payload(&icon_override).unwrap().unwrap();
        let object = payload.as_object().unwrap();

        assert_eq!(source, "candidate_png");
        assert_eq!(
            object.get("selected_icon_source").and_then(Value::as_str),
            Some("candidate_png")
        );
        assert!(object.get("png_base64").is_some());
        assert!(icon_override_payload(&Some(AppStudioIconOverride {
            selected_icon_source: Some("fallback_png".to_string()),
            png_data_url: None,
            candidate_id: None,
        }))
        .unwrap()
        .is_none());
    }

    #[test]
    fn update_request_preserves_metadata_override() {
        let request = AppStudioUpdateRequest {
            app_id: "sample_app".to_string(),
            entry: "C:\\work\\main.py".to_string(),
            name: Some("Sample App".to_string()),
            current_version: Some("1.0.0".to_string()),
            new_version: "1.0.1".to_string(),
            build_mode: "app-env".to_string(),
            icon_prompt: None,
            metadata: Some(AppStudioEditableMetadata {
                short_description: Some("Updated short".to_string()),
                ..AppStudioEditableMetadata::default()
            }),
            icon_override: None,
            build_profile: None,
            create_app_env: false,
            rebuild_app_env: false,
            generate_lock: false,
            build_frozen_folder: false,
            verify_runtime: false,
        };

        let import_request = import_request_from_update(&request);

        assert_eq!(
            import_request
                .metadata
                .and_then(|metadata| metadata.short_description),
            Some("Updated short".to_string())
        );
    }

    #[test]
    fn python_missing_message_is_actionable() {
        let message = python_missing_message();
        assert!(message.contains("runtime/python/python.exe"));
        assert!(message.contains("通常ランチャー機能には影響しません"));
    }

    #[test]
    fn output_dir_is_extracted_from_stdout() {
        let path = extract_output_dir(
            "ToolHub App Studio\n- output: C:\\work\\ToolHub_AppStudio_Output\\my_tool\n",
        )
        .unwrap();
        assert!(path.ends_with("my_tool"));
    }

    #[test]
    fn warning_execution_result_is_not_overstated_as_hard_failure() {
        let result = result_from_process(
            false,
            1,
            String::new(),
            String::new(),
            AppStudioResultSummary {
                app_id: Some("exe_app".to_string()),
                execution_status: Some("warn".to_string()),
                approval_allowed: Some(true),
                ..AppStudioResultSummary::default()
            },
            Some(1.0),
            "ok",
        );
        assert!(!result.ok);
        assert_eq!(result.execution_status.as_deref(), Some("warn"));
        assert_eq!(result.approval_allowed, Some(true));
        assert!(result.user_message.contains("warnings"));
    }

    #[test]
    fn read_summary_loads_execution_result_warn_and_approval() {
        let root = temp_project_root();
        let output = root
            .join("source")
            .join("ToolHub_AppStudio_Output")
            .join("exe_app");
        std::fs::create_dir_all(&output).unwrap();
        std::fs::write(
            output.join("execution_test_result.json"),
            "{\"overall_status\":\"warn\",\"approval_allowed\":true}",
        )
        .unwrap();
        std::fs::write(
            output.join("import_plan.json"),
            "{\"app_id\":\"exe_app\",\"selected_build_mode\":\"existing-exe\"}",
        )
        .unwrap();

        let summary = read_summary(&root, Some("exe_app"), Some(&output));
        assert_eq!(summary.execution_status.as_deref(), Some("warn"));
        assert_eq!(summary.approval_allowed, Some(true));
        assert_eq!(summary.selected_build_mode.as_deref(), Some("existing-exe"));
        let _ = std::fs::remove_dir_all(root);
    }

    #[test]
    fn read_summary_reports_catalog_visibility_for_enabled_app() {
        let root = temp_project_root();
        write_catalog_app(&root, "visible_app");
        write_release_manifest(&root, "visible_app", "1.0.0", true);

        let summary = read_summary(&root, Some("visible_app"), None);

        assert_eq!(summary.manifest_enabled, Some(true));
        assert_eq!(summary.catalog_visible, Some(true));
        assert_eq!(summary.catalog_enabled, Some(true));
        let _ = std::fs::remove_dir_all(root);
    }

    #[test]
    fn read_summary_reports_disabled_catalog_reason() {
        let root = temp_project_root();
        write_catalog_app(&root, "disabled_app");
        write_release_manifest(&root, "disabled_app", "1.0.0", false);

        let summary = read_summary(&root, Some("disabled_app"), None);

        assert_eq!(summary.manifest_enabled, Some(false));
        assert_eq!(summary.catalog_visible, Some(false));
        assert_eq!(summary.catalog_enabled, Some(false));
        assert!(summary.catalog_disabled_reason.is_some());
        let _ = std::fs::remove_dir_all(root);
    }

    #[test]
    fn read_summary_reports_catalog_parse_error() {
        let root = temp_project_root();
        let app_dir = root.join("apps").join("broken_app");
        std::fs::create_dir_all(&app_dir).unwrap();
        std::fs::write(app_dir.join("app.yaml"), "id: [broken\n").unwrap();
        write_release_manifest(&root, "broken_app", "1.0.0", true);

        let summary = read_summary(&root, Some("broken_app"), None);

        assert_eq!(summary.manifest_enabled, Some(true));
        assert_eq!(summary.catalog_visible, Some(false));
        assert!(summary.catalog_disabled_reason.is_some());
        let _ = std::fs::remove_dir_all(root);
    }

    #[test]
    fn read_ai_proposal_reads_metadata_and_icon_candidates() {
        let root = temp_project_root();
        let output = root.join("output");
        let icon_work = output.join("icon_work");
        std::fs::create_dir_all(&icon_work).unwrap();
        std::fs::write(
            output.join("proposed_app.yaml"),
            "id: sample\nname: Sample App\ndisplay:\n  short_description: Short\n  categories:\n    - CSV\ndetail:\n  description: Long\n  use_cases:\n    - Use\n  inputs:\n    - File\n  outputs:\n    - Report\n  notes:\n    - Note\nsearch:\n  keywords:\n    - csv\n  examples:\n    - merge csv\n",
        )
        .unwrap();
        std::fs::write(
            output.join("import_plan.json"),
            "{\"app_id\":\"sample\",\"version\":\"1.2.3\",\"selected_build_mode\":\"app-env\",\"metadata_ai_report\":\"status: success\\nmodel: text-model\"}",
        )
        .unwrap();
        std::fs::write(icon_work.join("icon_prompt_initial.md"), "simple icon").unwrap();
        std::fs::write(
            icon_work.join("icon_fallback.svg"),
            "<svg viewBox=\"0 0 64 64\"></svg>",
        )
        .unwrap();
        std::fs::write(icon_work.join("icon_final.png"), [137, 80, 78, 71]).unwrap();
        std::fs::write(icon_work.join("icon_candidate_1.png"), [137, 80, 78, 71]).unwrap();
        std::fs::write(icon_work.join("icon_candidate_2.png"), [137, 80, 78, 71]).unwrap();
        std::fs::write(
            icon_work.join("candidate_manifest.json"),
            "{\"function_interpretation\":{\"primary_action\":\"merge\",\"input_objects\":[\"pdf/document\"],\"output_objects\":[\"pdf/document\"]},\"candidates\":[{\"candidate_id\":\"icon_candidate_1\",\"number\":1,\"source\":\"api\",\"prompt\":\"p1\",\"model\":\"gpt-image-2\",\"status\":\"success\",\"resolution\":\"1024x1024\",\"fallback\":false,\"file_name\":\"icon_candidate_1.png\",\"concept_id\":\"literal_1\",\"concept\":{\"style_family\":\"modern\",\"composition\":\"pdf merge\"},\"scores\":{\"semantic_clarity\":9},\"score_total\":42},{\"candidate_id\":\"icon_candidate_2\",\"number\":2,\"source\":\"fallback\",\"prompt\":\"p2\",\"model\":\"local\",\"status\":\"fallback\",\"resolution\":\"512x512\",\"fallback\":true,\"file_name\":\"icon_candidate_2.png\"}]}",
        )
        .unwrap();

        let proposal = read_ai_proposal(Some(&output));
        assert!(proposal.ok);
        assert_eq!(proposal.metadata.name.as_deref(), Some("Sample App"));
        assert!(proposal
            .metadata
            .ai_report
            .as_deref()
            .unwrap_or_default()
            .contains("status: success"));
        assert_eq!(proposal.metadata.categories, vec!["CSV".to_string()]);
        assert!(proposal.icon.fallback_svg.is_some());
        assert!(proposal.icon.final_png_data_url.is_some());
        assert!(proposal.icon.candidate_png_data_url.is_some());
        assert_eq!(proposal.icon.candidates.len(), 2);
        assert_eq!(proposal.icon.candidates[0].candidate_id, "icon_candidate_1");
        assert_eq!(
            proposal
                .icon
                .function_interpretation
                .as_ref()
                .and_then(|value| value.get("primary_action"))
                .and_then(Value::as_str),
            Some("merge")
        );
        assert_eq!(proposal.icon.candidates[0].concept_id.as_deref(), Some("literal_1"));
        assert_eq!(proposal.icon.candidates[0].score_total, Some(42.0));
        assert!(proposal.icon.candidates[1].fallback);
        assert!(proposal
            .metadata
            .release_notes
            .iter()
            .any(|item| item.contains("1.2.3")));
        let _ = std::fs::remove_dir_all(root);
    }

    #[test]
    fn registered_app_list_survives_broken_app_yaml() {
        let root = temp_project_root();
        let broken = root.join("apps").join("broken_app");
        std::fs::create_dir_all(&broken).unwrap();
        std::fs::write(broken.join("app.yaml"), "id: [broken\n").unwrap();

        let apps = list_registered_apps_from_root(&root);
        assert_eq!(apps.len(), 1);
        assert_eq!(apps[0].app_id, "broken_app");
        assert!(apps[0].warning.is_some());
        let _ = std::fs::remove_dir_all(root);
    }

    #[test]
    fn registered_app_list_reads_manifest_version_and_enabled() {
        let root = temp_project_root();
        write_registered_app(&root, "sample_app", "1.0.0");
        write_release_manifest(&root, "sample_app", "1.2.3", true);

        let apps = list_registered_apps_from_root(&root);
        assert_eq!(apps.len(), 1);
        assert_eq!(apps[0].app_id, "sample_app");
        assert_eq!(apps[0].version, "1.2.3");
        assert!(apps[0].enabled);
        let _ = std::fs::remove_dir_all(root);
    }

    #[test]
    fn version_bump_handles_simple_semver() {
        assert_eq!(bump_version("1.2.3", "patch").unwrap(), "1.2.4");
        assert_eq!(bump_version("1.2.3", "minor").unwrap(), "1.3.0");
        assert_eq!(bump_version("1.2.3", "major").unwrap(), "2.0.0");
        assert!(bump_version("1.2", "patch").is_err());
        assert!(bump_version("", "patch").is_err());
    }

    #[test]
    fn update_preflight_rejects_older_version_and_warns_same_version() {
        let root = temp_project_root();
        write_registered_app(&root, "sample_app", "1.2.3");
        write_release_manifest(&root, "sample_app", "1.2.3", true);
        let entry = root.join("source").join("main.py");
        std::fs::create_dir_all(entry.parent().unwrap()).unwrap();
        std::fs::write(&entry, "print('hello')\n").unwrap();

        let older = AppStudioUpdateRequest {
            app_id: "sample_app".to_string(),
            entry: entry.display().to_string(),
            name: Some("Sample App".to_string()),
            current_version: Some("1.2.3".to_string()),
            new_version: "1.2.2".to_string(),
            build_mode: "frozen-folder".to_string(),
            icon_prompt: None,
            metadata: None,
            icon_override: None,
            build_profile: None,
            create_app_env: false,
            rebuild_app_env: false,
            generate_lock: false,
            build_frozen_folder: false,
            verify_runtime: false,
        };
        let candidate = Some(PythonCandidate {
            source: "python".to_string(),
            path: entry.clone(),
        });
        let result = preflight_for_update_request(&older, &root, candidate);
        assert!(!result.ok);
        assert!(result.errors.iter().any(|item| item.contains("older")));

        let same = AppStudioUpdateRequest {
            new_version: "1.2.3".to_string(),
            ..older
        };
        let candidate = Some(PythonCandidate {
            source: "python".to_string(),
            path: entry,
        });
        let result = preflight_for_update_request(&same, &root, candidate);
        assert!(result.ok);
        assert!(result.warnings.iter().any(|item| item.contains("same")));
        let _ = std::fs::remove_dir_all(root);
    }

    fn temp_project_root() -> PathBuf {
        let stamp = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let root = std::env::temp_dir().join(format!("toolhub_app_studio_project_{stamp}"));
        std::fs::create_dir_all(root.join("apps")).unwrap();
        std::fs::create_dir_all(root.join("release")).unwrap();
        root
    }

    fn command_envs(command: &Command) -> std::collections::HashMap<String, String> {
        command
            .get_envs()
            .filter_map(|(key, value)| {
                let value = value?;
                Some((
                    key.to_str()?.to_string(),
                    value.to_str().unwrap_or("").to_string(),
                ))
            })
            .collect()
    }

    fn write_registered_app(root: &Path, app_id: &str, version: &str) {
        let app_dir = root.join("apps").join(app_id);
        std::fs::create_dir_all(&app_dir).unwrap();
        std::fs::write(
            app_dir.join("app.yaml"),
            format!(
                "id: {app_id}\nname: Sample App\nrun:\n  runner: python\n  entry: main.py\nadmin:\n  version: {version}\nbuild:\n  build_mode: app-env\ndisplay:\n  short_description: Sample\n"
            ),
        )
        .unwrap();
    }

    fn write_catalog_app(root: &Path, app_id: &str) {
        let app_dir = root.join("apps").join(app_id);
        std::fs::create_dir_all(&app_dir).unwrap();
        std::fs::write(app_dir.join("icon.svg"), "<svg viewBox=\"0 0 64 64\"></svg>").unwrap();
        std::fs::write(
            app_dir.join("app.yaml"),
            format!(
                "id: {app_id}\nname: Visible App\ndisplay:\n  icon: icon.svg\n  short_description: desc\n  categories:\n    - demo\ndetail:\n  description: desc\nrun:\n  runner: cli\n  entry: main.py\n  mode: cli\nadmin:\n  version: 1.0.0\n"
            ),
        )
        .unwrap();
    }

    fn write_release_manifest(root: &Path, app_id: &str, version: &str, enabled: bool) {
        std::fs::write(
            root.join("release").join("app_manifest.json"),
            format!(
                "{{\"apps\":{{\"{app_id}\":{{\"version\":\"{version}\",\"enabled\":{enabled}}}}}}}"
            ),
        )
        .unwrap();
    }
}
