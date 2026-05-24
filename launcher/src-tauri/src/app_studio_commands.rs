use crate::admin_session::AdminSessionState;
use crate::app_studio_ai_proposal_reader::{read_ai_proposal, AppStudioAiProposal};
use crate::app_studio_cli::{resolve_app_studio_script, AppStudioCliStatus};
#[cfg(test)]
use crate::app_studio_cli_args::approval_flag;
use crate::app_studio_cli_args::{
    approval_mode_name, build_approve_cli_args, build_icon_regenerate_cli_args,
    build_image_test_cli_args, build_import_cli_args, import_request_from_update,
    normalize_normal_import_request, AppStudioCliAction, AppStudioIconRegenerateCliOptions,
    AppStudioImportCliOverrides,
};
use crate::app_studio_delete_plan::build_delete_plan;
#[cfg(test)]
use crate::app_studio_delete_plan::normalize_plan_path;
use crate::app_studio_full_delete::full_delete_apply;
#[cfg(test)]
use crate::app_studio_full_delete::validate_full_delete_plan;
use crate::app_studio_management::{
    find_registered_app, list_managed_apps_from_root, list_registered_apps_from_root,
    management_set_enabled,
};
use crate::app_studio_overrides::{
    write_build_profile_override_file, write_icon_override_file, write_icon_revision_image_file,
    write_metadata_override_file,
};
use crate::app_studio_preflight::{
    build_import_preflight_result, find_python_candidate, python_missing_message, validate_app_id,
    validate_entry_path, validate_source_root_path, PythonCandidate,
};
use crate::app_studio_process::{
    append_app_studio_gui_log, command_line_for_log, mask_sensitive, redact_cli_arg_value,
    result_from_process,
};
use crate::app_studio_result_reader::AppStudioResultSummary;
use crate::app_studio_result_reader::{output_dir_from_app_yaml, read_summary};
#[cfg(test)]
use crate::app_studio_types::AppStudioDeletePlanTarget;
#[cfg(test)]
use crate::app_studio_types::AppStudioEditableMetadata;
use crate::app_studio_types::{
    AppStudioAiDiagnostics, AppStudioDeletePlan, AppStudioFullDeleteResult,
    AppStudioIconRegenerateRequest, AppStudioImportRequest, AppStudioManagedApp,
    AppStudioManagementActionResult, AppStudioPreflightResult, AppStudioPublishAsset,
    AppStudioPublishCheck, AppStudioPublishPreflightResult, AppStudioPublishRemoteVerifyRequest,
    AppStudioPublishRequest, AppStudioPublishRunResult, AppStudioRegisteredApp, AppStudioRunResult,
    AppStudioUpdateRequest,
};
use chrono::Utc;
use serde_json::{Map, Value};
use sha2::{Digest, Sha256};
use std::cmp::Ordering;
use std::fs;
use std::io::Read;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::time::Instant;
use tauri::State;

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
pub fn app_studio_management_list_apps(
    session: State<AdminSessionState>,
) -> Result<Vec<AppStudioManagedApp>, String> {
    session.require_authenticated()?;
    let root = crate::manifest::project_root().map_err(|error| error.to_string())?;
    Ok(list_managed_apps_from_root(&root))
}

#[tauri::command]
pub fn app_studio_management_set_enabled(
    app_id: String,
    enabled: bool,
    session: State<AdminSessionState>,
) -> Result<AppStudioManagementActionResult, String> {
    session.require_authenticated()?;
    let root = crate::manifest::project_root().map_err(|error| error.to_string())?;
    management_set_enabled(&root, &app_id, enabled)
}

#[tauri::command]
pub fn app_studio_delete_plan(
    app_id: String,
    session: State<AdminSessionState>,
) -> Result<AppStudioDeletePlan, String> {
    session.require_authenticated()?;
    let root = crate::manifest::project_root().map_err(|error| error.to_string())?;
    build_delete_plan(&root, &app_id)
}

#[tauri::command]
pub fn app_studio_full_delete_apply(
    app_id: String,
    plan_snapshot: Option<AppStudioDeletePlan>,
    session: State<AdminSessionState>,
) -> Result<AppStudioFullDeleteResult, String> {
    session.require_authenticated()?;
    let root = crate::manifest::project_root().map_err(|error| error.to_string())?;
    full_delete_apply(&root, &app_id, plan_snapshot.as_ref())
}

#[tauri::command]
pub fn app_studio_preflight(
    request: AppStudioImportRequest,
    session: State<AdminSessionState>,
) -> Result<AppStudioPreflightResult, String> {
    session.require_authenticated()?;
    let root = crate::manifest::project_root().map_err(|error| error.to_string())?;
    Ok(build_import_preflight_result(
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
pub fn app_studio_publish_preflight(
    session: State<AdminSessionState>,
) -> Result<AppStudioPublishPreflightResult, String> {
    session.require_authenticated()?;
    let root = crate::manifest::project_root().map_err(|error| error.to_string())?;
    Ok(build_publish_preflight(&root))
}

#[tauri::command]
pub async fn app_studio_publish_dry_run(
    session: State<'_, AdminSessionState>,
) -> Result<AppStudioPublishRunResult, String> {
    session.require_authenticated()?;
    tauri::async_runtime::spawn_blocking(run_publish_dry_run)
        .await
        .map_err(|_| "GitHub Release dry-run could not complete.".to_string())?
}

#[tauri::command]
pub async fn app_studio_publish_prepare_target(
    session: State<'_, AdminSessionState>,
) -> Result<AppStudioPublishRunResult, String> {
    session.require_authenticated()?;
    tauri::async_runtime::spawn_blocking(run_publish_prepare_target)
        .await
        .map_err(|_| "GitHub Release target preparation could not complete.".to_string())?
}

#[tauri::command]
pub async fn app_studio_publish_build_verify(
    session: State<'_, AdminSessionState>,
) -> Result<AppStudioPublishRunResult, String> {
    session.require_authenticated()?;
    tauri::async_runtime::spawn_blocking(run_publish_build_verify)
        .await
        .map_err(|_| "Release build/verify could not complete.".to_string())?
}

#[tauri::command]
pub async fn app_studio_publish_remote_verify(
    request: AppStudioPublishRemoteVerifyRequest,
    session: State<'_, AdminSessionState>,
) -> Result<AppStudioPublishRunResult, String> {
    session.require_authenticated()?;
    tauri::async_runtime::spawn_blocking(move || run_publish_remote_verify(request))
        .await
        .map_err(|_| "GitHub Release remote verification could not complete.".to_string())?
}

#[tauri::command]
pub async fn app_studio_publish_release(
    request: AppStudioPublishRequest,
    session: State<'_, AdminSessionState>,
) -> Result<AppStudioPublishRunResult, String> {
    session.require_authenticated()?;
    tauri::async_runtime::spawn_blocking(move || run_publish_release(request))
        .await
        .map_err(|_| "GitHub Release publish could not complete.".to_string())?
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
pub async fn app_studio_regenerate_icon(
    request: AppStudioIconRegenerateRequest,
    session: State<'_, AdminSessionState>,
) -> Result<AppStudioAiProposal, String> {
    session.require_authenticated()?;
    tauri::async_runtime::spawn_blocking(move || run_icon_regenerate_action(request))
        .await
        .map_err(|_| "App Studio icon regeneration could not complete.".to_string())?
}

#[tauri::command]
pub fn app_studio_ai_diagnostics(
    session: State<AdminSessionState>,
) -> Result<AppStudioAiDiagnostics, String> {
    session.require_authenticated()?;
    let mut diagnostics = build_ai_env_plan().diagnostics;
    match crate::manifest::project_root() {
        Ok(root) => {
            let status = crate::app_studio_cli::app_studio_cli_status(&root);
            apply_cli_status_to_diagnostics(&mut diagnostics, status);
        }
        Err(error) => {
            diagnostics.app_studio_cli_exists = false;
            diagnostics.app_studio_cli_message =
                format!("ToolHub root を解決できませんでした: {error}");
        }
    }
    Ok(diagnostics)
}

fn apply_cli_status_to_diagnostics(
    diagnostics: &mut AppStudioAiDiagnostics,
    status: AppStudioCliStatus,
) {
    diagnostics.app_studio_cli_exists = status.cli_exists;
    diagnostics.app_studio_cli_path = status.cli_path;
    diagnostics.app_studio_repo_root = status.repo_root;
    diagnostics.app_studio_cli_message = status.message;
}

fn resolve_app_studio_script_for_action(root: &Path, action: &str) -> Result<PathBuf, String> {
    match resolve_app_studio_script(root) {
        Ok(script) => Ok(script),
        Err(status) => {
            log_app_studio_cli_missing(action, &status);
            Err(status.message)
        }
    }
}

fn log_app_studio_cli_missing(action: &str, status: &AppStudioCliStatus) {
    append_app_studio_gui_log(
        &format!("{action} blocked"),
        &[
            ("reason", "app_studio_cli_missing".to_string()),
            ("repo_root", status.repo_root.clone()),
            ("cli_path", status.cli_path.clone()),
            ("tools_dir_exists", status.tools_dir_exists.to_string()),
            (
                "app_studio_dir_exists",
                status.app_studio_dir_exists.to_string(),
            ),
            ("user_message", status.message.clone()),
        ],
    );
}

pub(crate) fn run_image_generation_test(
) -> Result<crate::ai_settings::AiImageGenerationTestResult, String> {
    run_image_generation_test_for_model(None)
}

pub(crate) fn run_image_model_probe() -> Result<crate::ai_settings::AiImageModelProbeResult, String>
{
    const CANDIDATE_MODELS: [&str; 4] = [
        "gpt-image-2",
        "gpt-image-1.5",
        "gpt-image-1",
        "gpt-image-1-mini",
    ];
    let mut items = Vec::new();
    for model in CANDIDATE_MODELS {
        match run_image_generation_test_for_model(Some(model)) {
            Ok(result) => items.push(crate::ai_settings::AiImageModelProbeItem {
                model: result.model,
                ok: result.ok,
                status: result.status,
                content_type: result.content_type,
                fallback_reason: result.fallback_reason,
                error: result.error,
                error_category: result.error_category,
                failure_class: result.failure_class,
                failure_message: result.failure_message,
                admin_next_action: result.admin_next_action,
            }),
            Err(error) => items.push(crate::ai_settings::AiImageModelProbeItem {
                model: model.to_string(),
                ok: false,
                status: "failed".to_string(),
                content_type: "none".to_string(),
                fallback_reason: Some(error),
                error: None,
                error_category: Some("probe_error".to_string()),
                failure_class: Some("unknown".to_string()),
                failure_message: None,
                admin_next_action: None,
            }),
        }
    }
    let ok = items.iter().any(|item| item.ok);
    let message = if ok {
        "At least one image model passed the real API test.".to_string()
    } else {
        "No candidate image model passed the real API test.".to_string()
    };
    Ok(crate::ai_settings::AiImageModelProbeResult { ok, message, items })
}

fn run_image_generation_test_for_model(
    model_override: Option<&str>,
) -> Result<crate::ai_settings::AiImageGenerationTestResult, String> {
    let root = crate::manifest::project_root().map_err(|error| error.to_string())?;
    let python_candidate = find_python_candidate(&root).ok_or_else(python_missing_message)?;
    let script = resolve_app_studio_script_for_action(&root, "image-test")?;
    let ai_env = build_ai_env_plan();
    let cli_args = build_image_test_cli_args(&script, model_override);
    let mut command = Command::new(&python_candidate.path);
    for arg in &cli_args {
        command.arg(arg);
    }
    command.current_dir(&root);
    apply_ai_environment(&mut command, &ai_env);
    let output = command
        .output()
        .map_err(|error| format!("Image generation test could not start: {error}"))?;
    let stdout = mask_sensitive(&String::from_utf8_lossy(&output.stdout));
    let stderr = mask_sensitive(&String::from_utf8_lossy(&output.stderr));
    let parsed: Value = serde_json::from_str(stdout.trim()).unwrap_or_else(|_| {
        let mut map = Map::new();
        map.insert("ok".to_string(), Value::Bool(false));
        map.insert(
            "message".to_string(),
            Value::String(if stderr.trim().is_empty() {
                "Image API test did not return JSON.".to_string()
            } else {
                stderr.trim().to_string()
            }),
        );
        Value::Object(map)
    });
    Ok(crate::ai_settings::AiImageGenerationTestResult {
        ok: parsed.get("ok").and_then(Value::as_bool).unwrap_or(false),
        message: parsed
            .get("message")
            .and_then(Value::as_str)
            .unwrap_or("Image API test failed.")
            .to_string(),
        key_source: Some(ai_env.diagnostics.api_key_source.clone()),
        model: parsed
            .get("model")
            .and_then(Value::as_str)
            .unwrap_or(&ai_env.diagnostics.image_model)
            .to_string(),
        api: parsed
            .get("api")
            .and_then(Value::as_str)
            .unwrap_or("images.generate")
            .to_string(),
        status: parsed
            .get("status")
            .and_then(Value::as_str)
            .unwrap_or(if output.status.success() {
                "success"
            } else {
                "failed"
            })
            .to_string(),
        content_type: parsed
            .get("content_type")
            .and_then(Value::as_str)
            .unwrap_or("none")
            .to_string(),
        resolution: parsed
            .get("resolution")
            .and_then(Value::as_str)
            .map(str::to_string),
        fallback_reason: parsed
            .get("fallback_reason")
            .and_then(Value::as_str)
            .map(str::to_string)
            .filter(|value| !value.is_empty()),
        error: parsed
            .get("error")
            .and_then(Value::as_str)
            .map(str::to_string)
            .filter(|value| !value.is_empty()),
        error_category: parsed
            .get("error_category")
            .and_then(Value::as_str)
            .map(str::to_string)
            .filter(|value| !value.is_empty()),
        failure_class: parsed
            .get("failure_class")
            .and_then(Value::as_str)
            .or_else(|| parsed.get("error_category").and_then(Value::as_str))
            .map(str::to_string)
            .filter(|value| !value.is_empty()),
        failure_message: parsed
            .get("failure_message")
            .and_then(Value::as_str)
            .map(str::to_string)
            .filter(|value| !value.is_empty()),
        admin_next_action: parsed
            .get("admin_next_action")
            .and_then(Value::as_str)
            .map(str::to_string)
            .filter(|value| !value.is_empty()),
    })
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

fn run_icon_regenerate_action(
    request: AppStudioIconRegenerateRequest,
) -> Result<AppStudioAiProposal, String> {
    let root = crate::manifest::project_root().map_err(|error| error.to_string())?;
    let app_id = request.app_id.trim().to_string();
    validate_app_id(&app_id)?;
    let output_path = PathBuf::from(request.output_dir.trim());
    if !output_path.is_dir() {
        return Err(
            "App Studioの出力フォルダが見つかりません。先にSuggestを実行してください。".to_string(),
        );
    }
    let instruction = request.user_revision_instruction.trim().to_string();
    if instruction.is_empty() {
        return Err("アイコンの修正指示を入力してください。".to_string());
    }
    let candidate_count = request.candidate_count.unwrap_or(1).clamp(1, 6);
    let revision_mode = match request.revision_mode.trim() {
        "tweak" | "refine" | "redesign" | "fresh" => request.revision_mode.trim().to_string(),
        _ => "refine".to_string(),
    };
    let image_quality_mode = match request
        .image_quality_mode
        .as_deref()
        .unwrap_or("standard")
        .trim()
    {
        "draft" | "standard" | "high" => request
            .image_quality_mode
            .as_deref()
            .unwrap_or("standard")
            .trim()
            .to_string(),
        _ => "standard".to_string(),
    };
    let python_candidate = find_python_candidate(&root).ok_or_else(python_missing_message)?;
    let python = python_candidate.path.clone();
    let script = resolve_app_studio_script_for_action(&root, "icon-regenerate")?;
    let ai_env = build_ai_env_plan();
    let cli_args = build_icon_regenerate_cli_args(
        &script,
        AppStudioIconRegenerateCliOptions {
            app_id: &app_id,
            output_dir: &output_path,
            user_revision_instruction: &instruction,
            revision_mode: &revision_mode,
            candidate_count,
            image_quality_mode: &image_quality_mode,
            base_candidate_id: clean_optional(&request.base_candidate_id),
            icon_style_preset: clean_optional(&request.icon_style_preset),
            icon_style_custom: clean_optional(&request.icon_style_custom),
        },
    );
    let cli_argv = command_line_for_log(
        &python,
        &redact_cli_arg_value(&cli_args, "--user-revision-instruction"),
    );
    append_app_studio_gui_log(
        "icon-regenerate started",
        &[
            ("app_id", app_id.clone()),
            ("output_dir", output_path.display().to_string()),
            (
                "base_candidate_id",
                request.base_candidate_id.unwrap_or_default(),
            ),
            ("revision_mode", revision_mode.clone()),
            ("candidate_count", candidate_count.to_string()),
            ("image_quality_mode", image_quality_mode.clone()),
            ("cli_path", script.display().to_string()),
            ("argv", cli_argv.clone()),
            ("python_source", python_candidate.source.clone()),
            ("ai_enabled", ai_env.diagnostics.ai_enabled.to_string()),
            ("api_key_source", ai_env.diagnostics.api_key_source.clone()),
            ("image_model", ai_env.diagnostics.image_model.clone()),
        ],
    );

    let mut command = Command::new(&python);
    for arg in &cli_args {
        command.arg(arg);
    }
    apply_ai_environment(&mut command, &ai_env);
    let output = command
        .current_dir(&root)
        .output()
        .map_err(|_| "App Studioのアイコン再生成を起動できませんでした。".to_string())?;
    let stdout = mask_sensitive(&String::from_utf8_lossy(&output.stdout));
    let stderr = mask_sensitive(&String::from_utf8_lossy(&output.stderr));
    let exit_code = output.status.code().unwrap_or(-1);
    append_app_studio_gui_log(
        "icon-regenerate finished",
        &[
            ("exit_code", exit_code.to_string()),
            ("app_id", app_id),
            ("output_dir", output_path.display().to_string()),
            ("revision_mode", revision_mode),
            ("candidate_count", candidate_count.to_string()),
            ("image_quality_mode", image_quality_mode),
            ("argv", cli_argv),
            ("python_source", python_candidate.source),
            (
                "user_message",
                if output.status.success() {
                    "ok".to_string()
                } else {
                    "App Studioのアイコン再生成に失敗しました。".to_string()
                },
            ),
        ],
    );
    if !output.status.success() {
        let detail = if !stderr.trim().is_empty() {
            stderr
        } else if !stdout.trim().is_empty() {
            stdout
        } else {
            format!("exit_code={exit_code}")
        };
        return Err(format!("アイコン再生成に失敗しました: {detail}"));
    }
    let reload_started = Instant::now();
    let mut proposal = read_ai_proposal(Some(&output_path));
    let proposal_reload_seconds = reload_started.elapsed().as_secs_f64();
    record_icon_proposal_reload_timing(&output_path, proposal_reload_seconds);
    if let Some(Value::Object(summary)) = proposal.icon.image_api_summary.as_mut() {
        summary.insert(
            "proposal_reload_seconds".to_string(),
            Value::from(proposal_reload_seconds),
        );
    }
    Ok(proposal)
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
    let script = resolve_app_studio_script_for_action(&root, action)?;

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
    let icon_revision_image = write_icon_revision_image_file(&request)?;
    let build_profile_override = write_build_profile_override_file(&request)?;
    let build_profile_source = if build_profile_override.is_some() {
        "manual"
    } else {
        ""
    }
    .to_string();
    let ai_env = build_ai_env_plan();
    let cli_args = build_import_cli_args(
        &script,
        &request,
        AppStudioCliAction::from_action_name(action),
        AppStudioImportCliOverrides {
            metadata_override: metadata_override.as_ref().map(|(path, _)| path.as_path()),
            icon_override: icon_override.as_ref().map(|(path, _)| path.as_path()),
            build_profile: build_profile_override.as_deref(),
            icon_revision_image: icon_revision_image.as_deref(),
        },
    );
    let cli_argv = command_line_for_log(&python, &cli_args);

    append_app_studio_gui_log(
        &format!("{action} started"),
        &[
            ("app_id", request.app_id.clone().unwrap_or_default()),
            (
                "source_root",
                request.source_root.clone().unwrap_or_default(),
            ),
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

fn build_publish_preflight(root: &Path) -> AppStudioPublishPreflightResult {
    let release_dir = root.join("release");
    let manifest_path = release_dir.join("manifest.json");
    let app_manifest_path = release_dir.join("app_manifest.json");
    let remote_name = "origin".to_string();
    let mut checks = Vec::new();
    let manifest = read_json_value(&manifest_path);
    let readiness = run_release_readiness_json(root);
    let readiness_summary = readiness
        .as_ref()
        .and_then(|value| value.get("summary").cloned());

    let version = manifest
        .as_ref()
        .and_then(|value| json_path_string(value, &["toolhub", "version"]));
    let tag = version.as_ref().map(|version| format!("v{version}"));
    let installer_file = manifest
        .as_ref()
        .and_then(|value| json_path_string(value, &["toolhub", "installer", "file"]));
    let manifest_installer_sha256 = manifest
        .as_ref()
        .and_then(|value| json_path_string(value, &["toolhub", "installer", "sha256"]));
    let manifest_installer_size = manifest
        .as_ref()
        .and_then(|value| json_path_u64(value, &["toolhub", "installer", "size"]));
    let installer_path = installer_file
        .as_ref()
        .map(|file| release_dir.join("dist_installer").join(file));
    let installer_exists = installer_path
        .as_ref()
        .map(|path| path.is_file())
        .unwrap_or(false);
    let installer_sha256 = installer_path
        .as_ref()
        .filter(|path| path.is_file())
        .and_then(|path| sha256_file(path).ok());
    let installer_size = installer_path
        .as_ref()
        .filter(|path| path.is_file())
        .and_then(|path| fs::metadata(path).ok())
        .map(|metadata| metadata.len());

    let remote_url = git_output(root, &["remote", "get-url", &remote_name]);
    let (github_owner, github_repo) = remote_url
        .as_deref()
        .and_then(parse_github_remote)
        .map(|(owner, repo)| (Some(owner), Some(repo)))
        .unwrap_or((None, None));
    let release_url = match (&github_owner, &github_repo, &tag) {
        (Some(owner), Some(repo), Some(tag)) => Some(format!(
            "https://github.com/{owner}/{repo}/releases/tag/{tag}"
        )),
        _ => None,
    };
    let latest_manifest_url = match (&github_owner, &github_repo) {
        (Some(owner), Some(repo)) => Some(format!(
            "https://github.com/{owner}/{repo}/releases/latest/download/manifest.json"
        )),
        _ => None,
    };
    let tag_manifest_url = match (&github_owner, &github_repo, &tag) {
        (Some(owner), Some(repo), Some(tag)) => Some(format!(
            "https://github.com/{owner}/{repo}/releases/download/{tag}/manifest.json"
        )),
        _ => None,
    };
    let update_manifest_url =
        read_update_manifest_url(&root.join("config.default").join("launcher.yaml"));
    let dirty_files = git_lines(root, &["status", "--short"]);
    let dirty_groups = classify_dirty_files(&dirty_files);
    let branch = git_output(root, &["rev-parse", "--abbrev-ref", "HEAD"]);
    let release_target_dir = planned_release_target_dir(root, tag.as_deref());
    let release_target_manifest_path = release_target_dir.join("release_target_manifest.json");
    let release_target_assets = build_release_target_asset_plan(
        &manifest_path,
        &app_manifest_path,
        installer_path.as_deref(),
        installer_file.as_deref(),
        &release_target_dir,
    );

    push_check(
        &mut checks,
        "manifest_json",
        if manifest.is_some() { "pass" } else { "fail" },
        if manifest.is_some() {
            "release/manifest.json is readable."
        } else {
            "release/manifest.json is missing or invalid."
        },
    );
    push_check(
        &mut checks,
        "app_manifest_json",
        if read_json_value(&app_manifest_path).is_some() {
            "pass"
        } else {
            "fail"
        },
        if app_manifest_path.is_file() {
            "release/app_manifest.json is present."
        } else {
            "release/app_manifest.json is missing."
        },
    );
    push_check(
        &mut checks,
        "installer_artifact",
        if installer_exists { "pass" } else { "fail" },
        if installer_exists {
            "Installer artifact exists."
        } else {
            "Installer artifact is missing."
        },
    );
    let sha_status = if manifest_installer_sha256.is_some()
        && installer_sha256.is_some()
        && manifest_installer_sha256 == installer_sha256
    {
        "pass"
    } else {
        "fail"
    };
    push_check(
        &mut checks,
        "installer_sha256",
        sha_status,
        if sha_status == "pass" {
            "Installer sha256 matches release manifest."
        } else {
            "Installer sha256 is missing or does not match release manifest."
        },
    );
    let size_status = if manifest_installer_size.is_some()
        && installer_size.is_some()
        && manifest_installer_size == installer_size
    {
        "pass"
    } else {
        "warning"
    };
    push_check(
        &mut checks,
        "installer_size",
        size_status,
        if size_status == "pass" {
            "Installer size matches release manifest."
        } else {
            "Installer size is missing or does not match release manifest."
        },
    );
    push_check(
        &mut checks,
        "github_remote",
        if github_owner.is_some() && github_repo.is_some() {
            "pass"
        } else {
            "warning"
        },
        if github_owner.is_some() && github_repo.is_some() {
            "GitHub origin remote was detected."
        } else {
            "GitHub origin remote could not be parsed."
        },
    );
    push_check(
        &mut checks,
        "working_tree",
        if dirty_files.is_empty() {
            "pass"
        } else {
            "warning"
        },
        if dirty_files.is_empty() {
            "Working tree is clean."
        } else {
            "Working tree has uncommitted changes; publish script will require -AllowDirty."
        },
    );
    push_check(
        &mut checks,
        "dirty_release_scope",
        if dirty_groups.release_files.is_empty() {
            "pass"
        } else {
            "warning"
        },
        if dirty_groups.release_files.is_empty() {
            "No release/publish boundary files are dirty."
        } else {
            "Release or publish boundary files are dirty. Confirm these are intended before publishing."
        },
    );
    push_check(
        &mut checks,
        "dirty_runtime_data_scope",
        if dirty_groups.runtime_data_files.is_empty() {
            "pass"
        } else {
            "warning"
        },
        if dirty_groups.runtime_data_files.is_empty() {
            "No runtime/data state files are dirty."
        } else {
            "Runtime or user-state paths are dirty. Review carefully before using -AllowDirty."
        },
    );
    push_check(
        &mut checks,
        "update_manifest_url",
        if update_manifest_url.is_some() {
            "pass"
        } else {
            "warning"
        },
        if update_manifest_url.is_some() {
            "Default update manifest URL is configured."
        } else {
            "Default update manifest URL is not configured."
        },
    );
    let release_target_ready = release_target_assets
        .iter()
        .filter(|asset| asset.upload)
        .all(|asset| asset.target_exists);
    push_check(
        &mut checks,
        "release_target_folder",
        if release_target_dir.is_dir() {
            "pass"
        } else {
            "warning"
        },
        if release_target_dir.is_dir() {
            "GitHub Release target folder exists."
        } else {
            "GitHub Release target folder has not been prepared yet."
        },
    );
    push_check(
        &mut checks,
        "release_target_assets",
        if release_target_ready {
            "pass"
        } else {
            "warning"
        },
        if release_target_ready {
            "All planned GitHub Release upload assets exist in the target folder."
        } else {
            "Prepare the release target folder before publish so the exact upload assets can be reviewed."
        },
    );

    let beta_ready_blockers = readiness_count(&readiness, &["summary", "beta_ready_blockers"]);
    let beta_ready_warnings = readiness_count(&readiness, &["summary", "beta_ready_warnings"]);
    let beta_ready_manual_checks =
        readiness_count(&readiness, &["summary", "beta_ready_manual_checks"]);
    let beta_ready_future_formal_only =
        readiness_count(&readiness, &["summary", "beta_ready_future_formal_only"]);
    push_check(
        &mut checks,
        "beta_ready_blockers",
        if beta_ready_blockers == 0 {
            "pass"
        } else {
            "fail"
        },
        if beta_ready_blockers == 0 {
            "No beta_ready blockers were reported."
        } else {
            "beta_ready blockers remain."
        },
    );

    let ok = checks.iter().all(|check| check.status != "fail");

    AppStudioPublishPreflightResult {
        ok,
        generated_at: Utc::now().to_rfc3339(),
        repo_root: root.display().to_string(),
        release_dir: release_dir.display().to_string(),
        release_target_dir: release_target_dir.display().to_string(),
        release_target_manifest_path: release_target_manifest_path.display().to_string(),
        branch,
        remote_name,
        remote_url,
        github_owner,
        github_repo,
        version,
        tag,
        release_url,
        latest_manifest_url,
        tag_manifest_url,
        update_manifest_url,
        manifest_path: manifest_path.display().to_string(),
        app_manifest_path: app_manifest_path.display().to_string(),
        installer_file,
        installer_path: installer_path.map(|path| path.display().to_string()),
        installer_exists,
        installer_sha256,
        manifest_installer_sha256,
        installer_size,
        manifest_installer_size,
        release_target_assets,
        dirty_files,
        dirty_release_files: dirty_groups.release_files,
        dirty_runtime_data_files: dirty_groups.runtime_data_files,
        dirty_source_files: dirty_groups.source_files,
        dirty_other_files: dirty_groups.other_files,
        readiness_summary,
        beta_ready_blockers,
        beta_ready_warnings,
        beta_ready_manual_checks,
        beta_ready_future_formal_only,
        checks,
    }
}

fn run_publish_dry_run() -> Result<AppStudioPublishRunResult, String> {
    let root = crate::manifest::project_root().map_err(|error| error.to_string())?;
    let script = root.join("scripts").join("publish_github_release.ps1");
    if !script.is_file() {
        return Err(format!(
            "GitHub Release publish script is missing: {}",
            script.display()
        ));
    }

    let args = vec![
        "-NoProfile".to_string(),
        "-ExecutionPolicy".to_string(),
        "Bypass".to_string(),
        "-File".to_string(),
        script.display().to_string(),
        "-DryRun".to_string(),
        "-SkipBuild".to_string(),
        "-SkipVerify".to_string(),
        "-SkipTag".to_string(),
        "-SkipRemoteVerify".to_string(),
        "-AllowDirty".to_string(),
    ];
    let command_line = command_line_for_log(Path::new("powershell"), &args);
    append_app_studio_gui_log(
        "publish_dry_run started",
        &[("command", command_line.clone())],
    );

    let started_at = Utc::now().to_rfc3339();
    let started = Instant::now();
    let output = Command::new("powershell")
        .args(&args)
        .current_dir(&root)
        .output()
        .map_err(|error| format!("GitHub Release dry-run could not start: {error}"))?;
    let process_wall_clock_seconds = started.elapsed().as_secs_f64();
    let finished_at = Utc::now().to_rfc3339();
    let exit_code = output.status.code().unwrap_or(-1);
    let stdout = mask_sensitive(&String::from_utf8_lossy(&output.stdout));
    let stderr = mask_sensitive(&String::from_utf8_lossy(&output.stderr));
    let ok = output.status.success();
    append_app_studio_gui_log(
        "publish_dry_run finished",
        &[("exit_code", exit_code.to_string()), ("ok", ok.to_string())],
    );

    Ok(AppStudioPublishRunResult {
        ok,
        exit_code,
        stdout,
        stderr,
        command_line,
        started_at,
        finished_at,
        process_wall_clock_seconds,
        user_message: if ok {
            "GitHub Release publish dry-run completed. No release assets were uploaded.".to_string()
        } else {
            "GitHub Release publish dry-run failed. Review stdout/stderr before publishing."
                .to_string()
        },
        report: None,
        preflight: build_publish_preflight(&root),
    })
}

fn run_publish_prepare_target() -> Result<AppStudioPublishRunResult, String> {
    let root = crate::manifest::project_root().map_err(|error| error.to_string())?;
    let script = root.join("scripts").join("publish_github_release.ps1");
    if !script.is_file() {
        return Err(format!(
            "GitHub Release publish script is missing: {}",
            script.display()
        ));
    }

    let args = vec![
        "-NoProfile".to_string(),
        "-ExecutionPolicy".to_string(),
        "Bypass".to_string(),
        "-File".to_string(),
        script.display().to_string(),
        "-PrepareTargetOnly".to_string(),
        "-SkipBuild".to_string(),
        "-SkipVerify".to_string(),
        "-SkipTag".to_string(),
        "-SkipRemoteVerify".to_string(),
        "-AllowDirty".to_string(),
    ];
    let command_line = command_line_for_log(Path::new("powershell"), &args);
    append_app_studio_gui_log(
        "publish_prepare_target started",
        &[("command", command_line.clone())],
    );

    let started_at = Utc::now().to_rfc3339();
    let started = Instant::now();
    let output = Command::new("powershell")
        .args(&args)
        .current_dir(&root)
        .output()
        .map_err(|error| format!("GitHub Release target preparation could not start: {error}"))?;
    let process_wall_clock_seconds = started.elapsed().as_secs_f64();
    let finished_at = Utc::now().to_rfc3339();
    let exit_code = output.status.code().unwrap_or(-1);
    let stdout = mask_sensitive(&String::from_utf8_lossy(&output.stdout));
    let stderr = mask_sensitive(&String::from_utf8_lossy(&output.stderr));
    let ok = output.status.success();
    append_app_studio_gui_log(
        "publish_prepare_target finished",
        &[("exit_code", exit_code.to_string()), ("ok", ok.to_string())],
    );

    Ok(AppStudioPublishRunResult {
        ok,
        exit_code,
        stdout,
        stderr,
        command_line,
        started_at,
        finished_at,
        process_wall_clock_seconds,
        user_message: if ok {
            "GitHub Release target folder was prepared. Review the listed files before publishing."
                .to_string()
        } else {
            "GitHub Release target preparation failed. Review stdout/stderr before publishing."
                .to_string()
        },
        report: None,
        preflight: build_publish_preflight(&root),
    })
}

fn run_publish_build_verify() -> Result<AppStudioPublishRunResult, String> {
    let root = crate::manifest::project_root().map_err(|error| error.to_string())?;
    let build_script = root.join("scripts").join("build_release.ps1");
    let verify_script = root.join("scripts").join("verify_release.ps1");
    if !build_script.is_file() {
        return Err(format!(
            "Release build script is missing: {}",
            build_script.display()
        ));
    }
    if !verify_script.is_file() {
        return Err(format!(
            "Release verification script is missing: {}",
            verify_script.display()
        ));
    }

    let command_script = format!(
        "$ErrorActionPreference = 'Stop'; & {} -RequireRuntime; if ($LASTEXITCODE -ne 0) {{ exit $LASTEXITCODE }}; & {} -RequireInstaller -RequireAppPacks -RequireRuntime -Strict; if ($LASTEXITCODE -ne 0) {{ exit $LASTEXITCODE }}",
        quote_powershell_single(&build_script.display().to_string()),
        quote_powershell_single(&verify_script.display().to_string())
    );
    let args = vec![
        "-NoProfile".to_string(),
        "-ExecutionPolicy".to_string(),
        "Bypass".to_string(),
        "-Command".to_string(),
        command_script,
    ];
    let command_line = command_line_for_log(Path::new("powershell"), &args);
    append_app_studio_gui_log(
        "publish_build_verify started",
        &[("command", command_line.clone())],
    );

    let started_at = Utc::now().to_rfc3339();
    let started = Instant::now();
    let output = Command::new("powershell")
        .args(&args)
        .current_dir(&root)
        .output()
        .map_err(|error| format!("Release build/verify could not start: {error}"))?;
    let process_wall_clock_seconds = started.elapsed().as_secs_f64();
    let finished_at = Utc::now().to_rfc3339();
    let exit_code = output.status.code().unwrap_or(-1);
    let stdout = mask_sensitive(&sanitize_url_queries_in_text(&String::from_utf8_lossy(
        &output.stdout,
    )));
    let stderr = mask_sensitive(&sanitize_url_queries_in_text(&String::from_utf8_lossy(
        &output.stderr,
    )));
    let ok = output.status.success();
    append_app_studio_gui_log(
        "publish_build_verify finished",
        &[("exit_code", exit_code.to_string()), ("ok", ok.to_string())],
    );

    Ok(AppStudioPublishRunResult {
        ok,
        exit_code,
        stdout,
        stderr,
        command_line,
        started_at,
        finished_at,
        process_wall_clock_seconds,
        user_message: if ok {
            "Release build and verification completed.".to_string()
        } else {
            "Release build or verification failed. Review stdout/stderr before publishing."
                .to_string()
        },
        report: None,
        preflight: build_publish_preflight(&root),
    })
}

fn run_publish_remote_verify(
    request: AppStudioPublishRemoteVerifyRequest,
) -> Result<AppStudioPublishRunResult, String> {
    let root = crate::manifest::project_root().map_err(|error| error.to_string())?;
    let preflight = build_publish_preflight(&root);
    let script = root
        .join("scripts")
        .join("verify_github_release_assets.ps1");
    if !script.is_file() {
        return Err(format!(
            "GitHub Release verification script is missing: {}",
            script.display()
        ));
    }

    let manifest_url = request
        .manifest_url
        .as_deref()
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(str::to_string)
        .or_else(|| preflight.update_manifest_url.clone())
        .or_else(|| preflight.latest_manifest_url.clone())
        .ok_or_else(|| {
            "Remote manifest URL is not available. Run publish preflight and configure updates.manifest_url first.".to_string()
        })?;
    let expected_version = request
        .expected_version
        .as_deref()
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(str::to_string)
        .or_else(|| preflight.version.clone())
        .ok_or_else(|| {
            "Expected version is not available. release/manifest.json must define toolhub.version."
                .to_string()
        })?;

    let mut args = vec![
        "-NoProfile".to_string(),
        "-ExecutionPolicy".to_string(),
        "Bypass".to_string(),
        "-File".to_string(),
        script.display().to_string(),
        "-ManifestUrl".to_string(),
        manifest_url,
        "-ExpectedVersion".to_string(),
        expected_version,
        "-Json".to_string(),
    ];
    if request.download_installer {
        args.push("-DownloadInstaller".to_string());
    }

    let command_line = command_line_for_log(
        Path::new("powershell"),
        &redact_remote_verify_command_args(&args),
    );
    append_app_studio_gui_log(
        "publish_remote_verify started",
        &[
            ("command", command_line.clone()),
            ("download_installer", request.download_installer.to_string()),
        ],
    );

    let started_at = Utc::now().to_rfc3339();
    let started = Instant::now();
    let output = Command::new("powershell")
        .args(&args)
        .current_dir(&root)
        .output()
        .map_err(|error| format!("GitHub Release remote verification could not start: {error}"))?;
    let process_wall_clock_seconds = started.elapsed().as_secs_f64();
    let finished_at = Utc::now().to_rfc3339();
    let exit_code = output.status.code().unwrap_or(-1);
    let stdout_raw = String::from_utf8_lossy(&output.stdout).to_string();
    let report = serde_json::from_str::<Value>(stdout_raw.trim())
        .ok()
        .map(sanitize_remote_verify_report);
    let stdout = match report.as_ref() {
        Some(value) => serde_json::to_string_pretty(value)
            .unwrap_or_else(|_| mask_sensitive(&sanitize_url_queries_in_text(&stdout_raw))),
        None => mask_sensitive(&sanitize_url_queries_in_text(&stdout_raw)),
    };
    let stderr = mask_sensitive(&sanitize_url_queries_in_text(&String::from_utf8_lossy(
        &output.stderr,
    )));
    let ok = output.status.success();
    append_app_studio_gui_log(
        "publish_remote_verify finished",
        &[("exit_code", exit_code.to_string()), ("ok", ok.to_string())],
    );

    Ok(AppStudioPublishRunResult {
        ok,
        exit_code,
        stdout,
        stderr,
        command_line,
        started_at,
        finished_at,
        process_wall_clock_seconds,
        user_message: if ok {
            "GitHub Release remote verification completed.".to_string()
        } else {
            "GitHub Release remote verification failed. Review stdout/stderr and release assets."
                .to_string()
        },
        report,
        preflight: build_publish_preflight(&root),
    })
}

fn run_publish_release(
    request: AppStudioPublishRequest,
) -> Result<AppStudioPublishRunResult, String> {
    if !request.confirm_publish {
        return Err(
            "Publish confirmation is required before creating or updating a GitHub Release."
                .to_string(),
        );
    }

    let root = crate::manifest::project_root().map_err(|error| error.to_string())?;
    let script = root.join("scripts").join("publish_github_release.ps1");
    if !script.is_file() {
        return Err(format!(
            "GitHub Release publish script is missing: {}",
            script.display()
        ));
    }

    let mut args = vec![
        "-NoProfile".to_string(),
        "-ExecutionPolicy".to_string(),
        "Bypass".to_string(),
        "-File".to_string(),
        script.display().to_string(),
    ];
    if request.allow_dirty {
        args.push("-AllowDirty".to_string());
    }
    if request.allow_existing_release {
        args.push("-AllowExistingRelease".to_string());
    }
    if request.update_manifest_installer_url {
        args.push("-UpdateManifestInstallerUrl".to_string());
    }
    if request.draft {
        args.push("-Draft".to_string());
    }
    if request.prerelease {
        args.push("-Prerelease".to_string());
    }
    if request.download_installer_for_remote_verify {
        args.push("-DownloadInstallerForRemoteVerify".to_string());
    }
    if let Some(release_notes) = request
        .release_notes
        .as_deref()
        .map(str::trim)
        .filter(|value| !value.is_empty())
    {
        args.push("-ReleaseNotes".to_string());
        args.push(release_notes.to_string());
    }

    let command_line =
        command_line_for_log(Path::new("powershell"), &redact_publish_command_args(&args));
    append_app_studio_gui_log(
        "publish_release started",
        &[
            ("command", command_line.clone()),
            ("allow_dirty", request.allow_dirty.to_string()),
            (
                "allow_existing_release",
                request.allow_existing_release.to_string(),
            ),
            (
                "update_manifest_installer_url",
                request.update_manifest_installer_url.to_string(),
            ),
            ("draft", request.draft.to_string()),
            ("prerelease", request.prerelease.to_string()),
        ],
    );

    let started_at = Utc::now().to_rfc3339();
    let started = Instant::now();
    let output = Command::new("powershell")
        .args(&args)
        .current_dir(&root)
        .output()
        .map_err(|error| format!("GitHub Release publish could not start: {error}"))?;
    let process_wall_clock_seconds = started.elapsed().as_secs_f64();
    let finished_at = Utc::now().to_rfc3339();
    let exit_code = output.status.code().unwrap_or(-1);
    let stdout = mask_sensitive(&sanitize_url_queries_in_text(&String::from_utf8_lossy(
        &output.stdout,
    )));
    let stderr = mask_sensitive(&sanitize_url_queries_in_text(&String::from_utf8_lossy(
        &output.stderr,
    )));
    let ok = output.status.success();
    append_app_studio_gui_log(
        "publish_release finished",
        &[("exit_code", exit_code.to_string()), ("ok", ok.to_string())],
    );

    Ok(AppStudioPublishRunResult {
        ok,
        exit_code,
        stdout,
        stderr,
        command_line,
        started_at,
        finished_at,
        process_wall_clock_seconds,
        user_message: if ok {
            "GitHub Release publish completed. Review the release URL and remote verification."
                .to_string()
        } else {
            "GitHub Release publish failed. Review stdout/stderr before retrying.".to_string()
        },
        report: None,
        preflight: build_publish_preflight(&root),
    })
}

fn redact_remote_verify_command_args(args: &[String]) -> Vec<String> {
    let mut output = Vec::with_capacity(args.len());
    let mut redact_next_url = false;
    for arg in args {
        if redact_next_url {
            output.push(sanitize_url_query_for_log(arg));
            redact_next_url = false;
            continue;
        }
        output.push(arg.clone());
        if arg == "-ManifestUrl" {
            redact_next_url = true;
        }
    }
    output
}

fn redact_publish_command_args(args: &[String]) -> Vec<String> {
    redact_cli_arg_value(args, "-ReleaseNotes")
}

fn quote_powershell_single(value: &str) -> String {
    format!("'{}'", value.replace('\'', "''"))
}

fn sanitize_url_query_for_log(value: &str) -> String {
    let without_fragment = value.split('#').next().unwrap_or(value);
    without_fragment
        .split('?')
        .next()
        .unwrap_or(without_fragment)
        .to_string()
}

fn sanitize_url_queries_in_text(value: &str) -> String {
    let mut output = String::with_capacity(value.len());
    for (index, segment) in value.split_whitespace().enumerate() {
        if index > 0 {
            output.push(' ');
        }
        output.push_str(&sanitize_possible_url_segment(segment));
    }
    output
}

fn sanitize_possible_url_segment(value: &str) -> String {
    let Some(start) = value.find("https://").or_else(|| value.find("http://")) else {
        return value.to_string();
    };
    let (prefix, rest) = value.split_at(start);
    let end = rest
        .find(|character: char| {
            character.is_whitespace() || matches!(character, '"' | '\'' | ',' | ')' | ']')
        })
        .unwrap_or(rest.len());
    let (url, suffix) = rest.split_at(end);
    format!("{prefix}{}{suffix}", sanitize_url_query_for_log(url))
}

fn sanitize_remote_verify_report(value: Value) -> Value {
    match value {
        Value::String(text) => Value::String(sanitize_report_string(&text)),
        Value::Array(items) => Value::Array(
            items
                .into_iter()
                .map(sanitize_remote_verify_report)
                .collect(),
        ),
        Value::Object(map) => Value::Object(
            map.into_iter()
                .map(|(key, value)| (key, sanitize_remote_verify_report(value)))
                .collect(),
        ),
        other => other,
    }
}

fn sanitize_report_string(value: &str) -> String {
    if value.contains("http://") || value.contains("https://") {
        sanitize_url_queries_in_text(value)
    } else {
        value.to_string()
    }
}

fn push_check(checks: &mut Vec<AppStudioPublishCheck>, id: &str, status: &str, message: &str) {
    checks.push(AppStudioPublishCheck {
        id: id.to_string(),
        status: status.to_string(),
        message: message.to_string(),
    });
}

fn planned_release_target_dir(root: &Path, tag: Option<&str>) -> PathBuf {
    let folder = tag
        .map(sanitize_release_target_folder_name)
        .filter(|value| !value.is_empty())
        .unwrap_or_else(|| "unresolved".to_string());
    root.join("release")
        .join("github_release_targets")
        .join(folder)
}

fn sanitize_release_target_folder_name(value: &str) -> String {
    value
        .chars()
        .map(|ch| {
            if ch.is_ascii_alphanumeric() || matches!(ch, '.' | '-' | '_') {
                ch
            } else {
                '_'
            }
        })
        .collect()
}

fn build_release_target_asset_plan(
    manifest_path: &Path,
    app_manifest_path: &Path,
    installer_path: Option<&Path>,
    installer_file: Option<&str>,
    release_target_dir: &Path,
) -> Vec<AppStudioPublishAsset> {
    let mut assets = Vec::new();
    if let (Some(path), Some(file)) = (installer_path, installer_file) {
        assets.push(build_release_target_asset(
            file,
            Some(path),
            &release_target_dir.join(file),
            false,
            true,
        ));
    } else {
        assets.push(build_release_target_asset(
            "ToolHub_Setup_VERSION.exe",
            None,
            &release_target_dir.join("ToolHub_Setup_VERSION.exe"),
            false,
            true,
        ));
    }
    assets.push(build_release_target_asset(
        "manifest.json",
        Some(manifest_path),
        &release_target_dir.join("manifest.json"),
        false,
        true,
    ));
    assets.push(build_release_target_asset(
        "app_manifest.json",
        Some(app_manifest_path),
        &release_target_dir.join("app_manifest.json"),
        false,
        true,
    ));
    assets.push(build_release_target_asset(
        "checksums.sha256.txt",
        None,
        &release_target_dir.join("checksums.sha256.txt"),
        true,
        true,
    ));
    assets
}

fn build_release_target_asset(
    name: &str,
    source_path: Option<&Path>,
    target_path: &Path,
    generated: bool,
    upload: bool,
) -> AppStudioPublishAsset {
    let source_exists = source_path.map(|path| path.is_file()).unwrap_or(false);
    let target_exists = target_path.is_file();
    let source_sha256 = source_path
        .filter(|path| path.is_file())
        .and_then(|path| sha256_file(path).ok());
    let target_sha256 = if target_exists {
        sha256_file(target_path).ok()
    } else {
        None
    };
    let source_size = source_path
        .filter(|path| path.is_file())
        .and_then(|path| fs::metadata(path).ok())
        .map(|metadata| metadata.len());
    let target_size = if target_exists {
        fs::metadata(target_path)
            .ok()
            .map(|metadata| metadata.len())
    } else {
        None
    };

    AppStudioPublishAsset {
        name: name.to_string(),
        source_path: source_path.map(|path| path.display().to_string()),
        target_path: target_path.display().to_string(),
        source_exists,
        target_exists,
        source_sha256,
        target_sha256,
        source_size,
        target_size,
        generated,
        upload,
    }
}

#[derive(Default)]
struct DirtyFileGroups {
    release_files: Vec<String>,
    runtime_data_files: Vec<String>,
    source_files: Vec<String>,
    other_files: Vec<String>,
}

fn classify_dirty_files(lines: &[String]) -> DirtyFileGroups {
    let mut groups = DirtyFileGroups::default();
    for line in lines {
        let path = dirty_status_path(line);
        if path.is_empty() {
            groups.other_files.push(line.clone());
        } else if is_release_boundary_path(&path) {
            groups.release_files.push(line.clone());
        } else if is_runtime_data_path(&path) {
            groups.runtime_data_files.push(line.clone());
        } else if is_source_path(&path) {
            groups.source_files.push(line.clone());
        } else {
            groups.other_files.push(line.clone());
        }
    }
    groups
}

fn dirty_status_path(line: &str) -> String {
    let path = line
        .get(3..)
        .unwrap_or(line)
        .split(" -> ")
        .last()
        .unwrap_or(line)
        .trim()
        .trim_matches('"');
    path.replace('\\', "/")
}

fn is_release_boundary_path(path: &str) -> bool {
    path.starts_with("release/")
        || path.starts_with("installer/")
        || path == "config.default/launcher.yaml"
        || path == "launcher/package.json"
        || path == "launcher/src-tauri/Cargo.toml"
        || path == "launcher/src-tauri/tauri.conf.json"
        || path == "scripts/build_release.ps1"
        || path == "scripts/verify_release.ps1"
        || path == "scripts/publish_github_release.ps1"
        || path == "scripts/verify_github_release_assets.ps1"
        || path == "scripts/check_all.ps1"
}

fn is_runtime_data_path(path: &str) -> bool {
    path.starts_with("runtime/")
        || path.starts_with("data/")
        || path.starts_with("logs/")
        || path.starts_with("backups/")
        || path.starts_with("config/")
}

fn is_source_path(path: &str) -> bool {
    path.starts_with("launcher/")
        || path.starts_with("runner/")
        || path.starts_with("tools/")
        || path.starts_with("apps/")
        || path.starts_with("scripts/")
        || path.starts_with("docs/")
        || path == "README.md"
        || path == "AGENTS.md"
}

fn read_json_value(path: &Path) -> Option<Value> {
    fs::read_to_string(path)
        .ok()
        .and_then(|text| serde_json::from_str(&text).ok())
}

fn json_path_string(value: &Value, path: &[&str]) -> Option<String> {
    let mut current = value;
    for key in path {
        current = current.get(*key)?;
    }
    current
        .as_str()
        .map(|value| value.to_string())
        .or_else(|| current.as_i64().map(|value| value.to_string()))
}

fn json_path_u64(value: &Value, path: &[&str]) -> Option<u64> {
    let mut current = value;
    for key in path {
        current = current.get(*key)?;
    }
    current.as_u64()
}

fn readiness_count(readiness: &Option<Value>, path: &[&str]) -> usize {
    readiness
        .as_ref()
        .and_then(|value| {
            let mut current = value;
            for key in path {
                current = current.get(*key)?;
            }
            current.as_u64()
        })
        .unwrap_or(0) as usize
}

fn git_output(root: &Path, args: &[&str]) -> Option<String> {
    let output = Command::new("git")
        .args(args)
        .current_dir(root)
        .output()
        .ok()?;
    if !output.status.success() {
        return None;
    }
    let text = String::from_utf8_lossy(&output.stdout).trim().to_string();
    if text.is_empty() {
        None
    } else {
        Some(text)
    }
}

fn git_lines(root: &Path, args: &[&str]) -> Vec<String> {
    Command::new("git")
        .args(args)
        .current_dir(root)
        .output()
        .ok()
        .filter(|output| output.status.success())
        .map(|output| {
            String::from_utf8_lossy(&output.stdout)
                .lines()
                .map(str::trim_end)
                .filter(|line| !line.is_empty())
                .map(str::to_string)
                .collect()
        })
        .unwrap_or_default()
}

fn parse_github_remote(remote: &str) -> Option<(String, String)> {
    let trimmed = remote.trim().trim_end_matches(".git");
    if let Some(rest) = trimmed.strip_prefix("https://github.com/") {
        let (owner, repo) = rest.split_once('/')?;
        return Some((owner.to_string(), repo.to_string()));
    }
    if let Some(rest) = trimmed.strip_prefix("git@github.com:") {
        let (owner, repo) = rest.split_once('/')?;
        return Some((owner.to_string(), repo.to_string()));
    }
    None
}

fn read_update_manifest_url(path: &Path) -> Option<String> {
    let text = fs::read_to_string(path).ok()?;
    let yaml: serde_yaml::Value = serde_yaml::from_str(&text).ok()?;
    for key in ["manifest_url", "source_url", "url"] {
        let value = yaml
            .get("updates")
            .and_then(|updates| updates.get(key))
            .and_then(|value| value.as_str())
            .map(str::trim)
            .filter(|value| !value.is_empty());
        if let Some(value) = value {
            return Some(value.to_string());
        }
    }
    None
}

fn run_release_readiness_json(root: &Path) -> Option<Value> {
    let script = root.join("scripts").join("report_release_readiness.ps1");
    let output = Command::new("powershell")
        .args([
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            script.to_string_lossy().as_ref(),
            "-Json",
        ])
        .current_dir(root)
        .output()
        .ok()?;
    if !output.status.success() {
        return None;
    }
    serde_json::from_slice(&output.stdout).ok()
}

fn sha256_file(path: &Path) -> Result<String, String> {
    let mut file = fs::File::open(path).map_err(|error| error.to_string())?;
    let mut hasher = Sha256::new();
    let mut buffer = [0u8; 8192];
    loop {
        let read = file.read(&mut buffer).map_err(|error| error.to_string())?;
        if read == 0 {
            break;
        }
        hasher.update(&buffer[..read]);
    }
    Ok(format!("{:x}", hasher.finalize()))
}

fn run_approve_action(app_id: String, strict: bool) -> Result<AppStudioRunResult, String> {
    let root = crate::manifest::project_root().map_err(|error| error.to_string())?;
    validate_app_id(&app_id)?;
    let python_candidate = find_python_candidate(&root).ok_or_else(python_missing_message)?;
    let python = python_candidate.path.clone();
    let script = resolve_app_studio_script_for_action(&root, "approve")?;
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
    let cli_args = build_approve_cli_args(&script, &app_id, strict);
    let mut command = Command::new(&python);
    for arg in &cli_args {
        command.arg(arg);
    }
    let output = command
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

fn validate_request(request: &AppStudioImportRequest) -> Result<(), String> {
    let entry = PathBuf::from(request.entry.trim());
    if request.entry.trim().is_empty() {
        return Err("Entryファイルを指定してください。".to_string());
    }
    if !entry.is_file() {
        return Err("Entryファイルが見つかりません。".to_string());
    }
    validate_entry_path(&entry)?;
    validate_source_root_path(&entry, request.source_root.as_deref())?;
    if ![
        "auto",
        "app-env",
        "shared-env",
        "frozen-folder",
        "existing-exe",
    ]
    .contains(&request.build_mode.as_str())
    {
        return Err("BuildModeが不正です。".to_string());
    }
    if let Some(app_id) = clean_optional(&request.app_id) {
        validate_app_id(app_id)?;
    }
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

fn preflight_for_update_request(
    request: &AppStudioUpdateRequest,
    root: &Path,
    python_candidate: Option<PythonCandidate>,
) -> AppStudioPreflightResult {
    let import_request = import_request_from_update(request);
    let mut result = build_import_preflight_result(&import_request, root, python_candidate);
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

#[cfg(test)]
fn manifest_app_entry<'a>(manifest: &'a Value, app_id: &str) -> Option<&'a Value> {
    manifest.get("apps").and_then(|apps| apps.get(app_id))
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

fn read_json(path: &Path) -> Option<Value> {
    let text = std::fs::read_to_string(path).ok()?;
    serde_json::from_str(&text).ok()
}

fn record_icon_proposal_reload_timing(output_dir: &Path, proposal_reload_seconds: f64) {
    let manifest_path = output_dir.join("icon_work").join("candidate_manifest.json");
    let Some(mut manifest) = read_json(&manifest_path) else {
        return;
    };
    if let Some(summary) = manifest
        .get_mut("image_api_summary")
        .and_then(Value::as_object_mut)
    {
        summary.insert(
            "proposal_reload_seconds".to_string(),
            Value::from(proposal_reload_seconds),
        );
        if let Some(timing) = summary
            .get_mut("regeneration_timing")
            .and_then(Value::as_object_mut)
        {
            timing.insert(
                "proposal_reload".to_string(),
                Value::from(proposal_reload_seconds),
            );
        }
    }
    if let Some(last_regeneration) = manifest
        .get_mut("last_regeneration")
        .and_then(Value::as_object_mut)
    {
        if let Some(timing) = last_regeneration
            .get_mut("timings")
            .and_then(Value::as_object_mut)
        {
            timing.insert(
                "proposal_reload".to_string(),
                Value::from(proposal_reload_seconds),
            );
        }
    }
    if let Ok(text) = serde_json::to_string_pretty(&manifest) {
        let _ = std::fs::write(manifest_path, text);
    }
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
        "AI is disabled; CLI will use the ToolHub default icon when no icon is selected."
            .to_string()
    } else if !api_key_present {
        "API key is missing; CLI will use the ToolHub default icon when no icon is selected."
            .to_string()
    } else if !text_model_set && !image_model_set {
        "No AI models are configured; CLI will use the ToolHub default icon when no icon is selected.".to_string()
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
            app_studio_cli_exists: false,
            app_studio_cli_path: String::new(),
            app_studio_repo_root: String::new(),
            app_studio_cli_message: String::new(),
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

#[cfg(test)]
mod tests {
    use super::*;

    fn dummy_openai_api_key() -> String {
        ["sk-", "test1234abcd"].concat()
    }

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
            source_root: None,
            app_id: Some("my_tool".to_string()),
            name: Some("My Tool".to_string()),
            version: None,
            build_mode: "shared-env".to_string(),
            icon_prompt: None,
            icon_style_preset: None,
            icon_style_custom: None,
            icon_revision_image: None,
            metadata: None,
            icon_override: None,
            build_profile: None,
            show_terminal: false,
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
            source_root: None,
            app_id: Some("my_tool".to_string()),
            name: Some("My Tool".to_string()),
            version: None,
            build_mode: "shared-env".to_string(),
            icon_prompt: None,
            icon_style_preset: None,
            icon_style_custom: None,
            icon_revision_image: None,
            metadata: None,
            icon_override: None,
            build_profile: None,
            show_terminal: false,
            create_app_env: false,
            rebuild_app_env: false,
            generate_lock: false,
            build_frozen_folder: false,
            verify_runtime: false,
        };
        let result = build_import_preflight_result(&request, entry.parent().unwrap(), None);
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
        let key = ["sk-", "test123456abcd"].concat();
        let masked = mask_sensitive(&format!("key={} done", key));
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
                app_studio_cli_exists: true,
                app_studio_cli_path: "tools/app_studio/main.py".to_string(),
                app_studio_repo_root: "C:/ToolHub".to_string(),
                app_studio_cli_message: "ready".to_string(),
                credential_supported: true,
                message: "ready".to_string(),
            },
            api_key: Some(dummy_openai_api_key()),
        };
        let mut command = Command::new("python");

        apply_ai_environment(&mut command, &plan);

        let expected_key = dummy_openai_api_key();
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
            Some(expected_key.as_str())
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
                app_studio_cli_exists: true,
                app_studio_cli_path: "tools/app_studio/main.py".to_string(),
                app_studio_repo_root: "C:/ToolHub".to_string(),
                app_studio_cli_message: "ready".to_string(),
                credential_supported: true,
                message: "disabled".to_string(),
            },
            api_key: Some(dummy_openai_api_key()),
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
    fn update_request_preserves_metadata_override() {
        let request = AppStudioUpdateRequest {
            app_id: "sample_app".to_string(),
            entry: "C:\\work\\main.py".to_string(),
            name: Some("Sample App".to_string()),
            current_version: Some("1.0.0".to_string()),
            new_version: "1.0.1".to_string(),
            build_mode: "app-env".to_string(),
            icon_prompt: None,
            icon_style_preset: None,
            icon_style_custom: None,
            icon_revision_image: None,
            metadata: Some(AppStudioEditableMetadata {
                short_description: Some("Updated short".to_string()),
                ..AppStudioEditableMetadata::default()
            }),
            icon_override: None,
            build_profile: None,
            show_terminal: false,
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
        assert!(result.user_message.contains("reference information only"));
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
            r#"{
                "overall_status": "warn",
                "approval_allowed": true,
                "admin_alerts": [
                    {
                        "id": "registration.failed",
                        "severity": "critical",
                        "title": "登録検証に失敗しました",
                        "summary": "summary",
                        "why_dangerous": "risk",
                        "admin_action": "fix",
                        "source": "detail",
                        "check_name": "distribution check"
                    }
                ]
            }"#,
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
        assert_eq!(summary.admin_alerts.len(), 1);
        assert_eq!(summary.admin_alerts[0].why_dangerous, "risk");
        let _ = std::fs::remove_dir_all(root);
    }

    #[test]
    fn read_summary_promotes_execution_fail_check_details() {
        let root = temp_project_root();
        let output = root
            .join("source")
            .join("ToolHub_AppStudio_Output")
            .join("exe_app");
        std::fs::create_dir_all(&output).unwrap();
        std::fs::write(
            output.join("execution_test_result.json"),
            r#"{
                "overall_status": "fail",
                "approval_allowed": false,
                "checks": [
                    {
                        "name": "frozen-folder build",
                        "status": "fail",
                        "detail": "Source entry file is missing before PyInstaller build. entry=C:\\work\\app.py",
                        "approval_category": "fail",
                        "approval_blocking": true
                    }
                ]
            }"#,
        )
        .unwrap();
        std::fs::write(
            output.join("import_plan.json"),
            "{\"app_id\":\"exe_app\",\"selected_build_mode\":\"frozen-folder\"}",
        )
        .unwrap();

        let summary = read_summary(&root, Some("exe_app"), Some(&output));

        assert_eq!(summary.execution_status.as_deref(), Some("fail"));
        assert_eq!(summary.approval_allowed, Some(false));
        let failure = summary.approval_failure_summary.unwrap();
        assert!(failure.contains("frozen-folder build"));
        assert!(failure.contains("Source entry file is missing"));
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
            "{\"app_id\":\"sample\",\"version\":\"1.2.3\",\"selected_build_mode\":\"app-env\",\"metadata_ai_report\":\"status: success\\nmodel: text-model\\nparse_status: success\"}",
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
            "{\"function_interpretation\":{\"primary_action\":\"merge\",\"input_objects\":[\"pdf/document\"],\"output_objects\":[\"pdf/document\"]},\"image_api_summary\":{\"api_candidate_count\":1,\"fallback_candidate_count\":1,\"image_api_success\":true,\"model\":\"gpt-image-2\",\"score_basis\":\"prompt_concept_only\"},\"candidates\":[{\"candidate_id\":\"icon_candidate_1\",\"number\":1,\"source\":\"api_generate\",\"prompt\":\"p1\",\"model\":\"gpt-image-2\",\"status\":\"success\",\"resolution\":\"1024x1024\",\"fallback\":false,\"file_name\":\"icon_candidate_1.png\",\"api\":\"images.generate\",\"content_type\":\"b64_png\",\"concept_id\":\"literal_1\",\"concept\":{\"style_family\":\"modern\",\"composition\":\"pdf merge\"},\"scores\":{\"semantic_clarity\":9},\"score_total\":42,\"score_basis\":\"prompt_concept_only\",\"image_evaluation_status\":\"not_run\"},{\"candidate_id\":\"icon_candidate_2\",\"number\":2,\"source\":\"fallback\",\"prompt\":\"p2\",\"model\":\"local\",\"status\":\"fallback\",\"resolution\":\"512x512\",\"fallback\":true,\"file_name\":\"icon_candidate_2.png\",\"fallback_reason\":\"test fallback\"}]}",
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
        assert!(proposal.metadata.ai_generated);
        assert_eq!(proposal.metadata.ai_status.as_deref(), Some("success"));
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
        assert_eq!(
            proposal
                .icon
                .image_api_summary
                .as_ref()
                .and_then(|value| value.get("api_candidate_count"))
                .and_then(Value::as_u64),
            Some(1)
        );
        assert_eq!(
            proposal.icon.candidates[0].concept_id.as_deref(),
            Some("literal_1")
        );
        assert_eq!(proposal.icon.candidates[0].score_total, Some(42.0));
        assert_eq!(
            proposal.icon.candidates[0].api.as_deref(),
            Some("images.generate")
        );
        assert!(proposal.icon.candidates[1].fallback);
        assert!(proposal
            .metadata
            .release_notes
            .iter()
            .any(|item| item.contains("1.2.3")));
        let _ = std::fs::remove_dir_all(root);
    }

    #[test]
    fn read_ai_proposal_suppresses_metadata_fallback_when_ai_skipped() {
        let root = temp_project_root();
        let output = root.join("output");
        std::fs::create_dir_all(&output).unwrap();
        std::fs::write(
            output.join("proposed_app.yaml"),
            "id: fallback_app\nname: Fallback App\ndisplay:\n  short_description: Thin fallback\n  categories:\n    - Utility\ndetail:\n  description: Generated without AI.\nsearch:\n  keywords:\n    - fallback\nrelease:\n  release_notes:\n    - fallback release\n  change_summary: fallback change\n",
        )
        .unwrap();
        std::fs::write(
            output.join("import_plan.json"),
            "{\"app_id\":\"fallback_app\",\"version\":\"1.0.0\",\"selected_build_mode\":\"shared-env\",\"metadata_ai_report\":\"api: responses.create\\nstatus: skipped\\nmodel: text-model\\nparse_status: not_attempted\\nfallback_reason: secret scan blocked AI submission, AI skipped\"}",
        )
        .unwrap();

        let proposal = read_ai_proposal(Some(&output));

        assert!(proposal.ok);
        assert!(!proposal.metadata.ai_generated);
        assert_eq!(proposal.metadata.name.as_deref(), Some("Fallback App"));
        assert_eq!(proposal.metadata.ai_status.as_deref(), Some("skipped"));
        assert_eq!(
            proposal.metadata.ai_fallback_reason.as_deref(),
            Some("secret scan blocked AI submission, AI skipped")
        );
        assert!(proposal.metadata.short_description.is_none());
        assert!(proposal.metadata.description.is_none());
        assert!(proposal.metadata.categories.is_empty());
        assert!(proposal.metadata.keywords.is_empty());
        assert!(proposal.metadata.release_notes.is_empty());
        assert!(proposal.metadata.change_summary.is_none());
        assert!(proposal
            .warnings
            .iter()
            .any(|warning| warning.contains("fallback metadata")));
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
    fn delete_plan_contract_matches_powershell_fixture_expectations() {
        let root = temp_project_root();
        let app_id = "deleteplan_probe";
        let version = "0.1.0";
        write_delete_plan_fixture(&root, app_id, version);

        let plan = build_delete_plan(&root, app_id).unwrap();

        assert_target(
            &plan.delete_targets,
            "managed_required",
            "delete apps/<app_id>/",
            &root.join("apps").join(app_id),
            true,
        );
        assert_target(
            &plan.delete_targets,
            "managed_required",
            "remove app_manifest entry",
            &root.join("release").join("app_manifest.json"),
            true,
        );
        assert_target(
            &plan.delete_targets,
            "managed_generated",
            "delete App Pack zip",
            &root
                .join("release")
                .join("app_packs")
                .join(format!("{app_id}-{version}.zip")),
            true,
        );
        assert_target(
            &plan.delete_targets,
            "managed_generated",
            "delete staging artifact",
            &root.join("release").join("staging").join(app_id),
            true,
        );
        assert_target(
            &plan.delete_targets,
            "managed_generated",
            "delete staging artifact",
            &root
                .join("release")
                .join("staging")
                .join(format!("{app_id}-{version}")),
            true,
        );
        assert_no_target(
            &plan.delete_targets,
            &root
                .join("release")
                .join("staging")
                .join(format!("{app_id}_other")),
        );
        assert_target(
            &plan.excluded_targets,
            "managed_generated_candidate",
            "review staging candidate",
            &root
                .join("release")
                .join("staging")
                .join(format!("{app_id}_other")),
            false,
        );
        assert_target(
            &plan.delete_targets,
            "managed_generated",
            "delete runtime app_env",
            &root.join("runtime").join("app_envs").join(app_id),
            true,
        );
        assert_target(
            &plan.delete_targets,
            "managed_history",
            "delete App Studio backup",
            &root
                .join("backups")
                .join("app_studio")
                .join("20990101_000000_delete_plan_test")
                .join(app_id),
            true,
        );
        assert!(plan
            .excluded_targets
            .iter()
            .any(|target| target.category == "external_reference" && !target.delete_allowed));
        assert!(plan
            .excluded_targets
            .iter()
            .any(|target| target.category == "user_data" && !target.delete_allowed));
        assert_eq!(
            plan.excluded_targets
                .iter()
                .filter(|target| target.category == "shared_runtime" && !target.delete_allowed)
                .count(),
            2
        );
        assert_eq!(plan.staging_candidate_paths.len(), 1);
        assert_targets_sorted(&plan.delete_targets);
        assert_targets_sorted(&plan.excluded_targets);
        assert!(plan
            .delete_targets
            .iter()
            .chain(plan.excluded_targets.iter())
            .all(|target| !target.normalized_path.is_empty() && !target.comparison_key.is_empty()));
        let _ = std::fs::remove_dir_all(root);
    }

    #[test]
    fn full_delete_apply_removes_only_repo_managed_targets() {
        let root = temp_project_root();
        let app_id = "deleteplan_apply";
        let version = "0.1.0";
        write_delete_plan_fixture(&root, app_id, version);
        std::fs::create_dir_all(root.join("runtime").join("python")).unwrap();
        std::fs::create_dir_all(root.join("runtime").join("web_automation_runtime")).unwrap();
        let snapshot = build_delete_plan(&root, app_id).unwrap();

        let result = full_delete_apply(&root, app_id, Some(&snapshot)).unwrap();

        assert!(result.ok, "{result:?}");
        assert!(result.manifest_entry_removed);
        assert!(!root.join("apps").join(app_id).exists());
        assert!(!root
            .join("release")
            .join("app_packs")
            .join(format!("{app_id}-{version}.zip"))
            .exists());
        assert!(!root.join("release").join("staging").join(app_id).exists());
        assert!(!root
            .join("release")
            .join("staging")
            .join(format!("{app_id}-{version}"))
            .exists());
        assert!(root
            .join("release")
            .join("staging")
            .join(format!("{app_id}_other"))
            .exists());
        assert!(!root.join("runtime").join("app_envs").join(app_id).exists());
        assert!(root.join("runtime").join("python").exists());
        assert!(root.join("runtime").join("web_automation_runtime").exists());
        let manifest = read_json(&root.join("release").join("app_manifest.json")).unwrap();
        assert!(manifest_app_entry(&manifest, app_id).is_none());
        let _ = std::fs::remove_dir_all(root);
    }

    #[test]
    fn full_delete_apply_rejects_stale_snapshot() {
        let root = temp_project_root();
        let app_id = "deleteplan_stale";
        write_delete_plan_fixture(&root, app_id, "0.1.0");
        let mut snapshot = build_delete_plan(&root, app_id).unwrap();
        snapshot.manifest_version = Some("9.9.9".to_string());

        let result = full_delete_apply(&root, app_id, Some(&snapshot));

        assert!(result.is_err());
        assert!(root.join("apps").join(app_id).exists());
        let _ = std::fs::remove_dir_all(root);
    }

    #[test]
    fn full_delete_safety_rejects_outside_delete_target() {
        let root = temp_project_root();
        let app_id = "deleteplan_unsafe";
        write_delete_plan_fixture(&root, app_id, "0.1.0");
        let mut plan = build_delete_plan(&root, app_id).unwrap();
        let outside = std::env::temp_dir().join("toolhub_outside_delete_target");
        plan.delete_targets[0].path = outside.display().to_string();
        plan.delete_targets[0].normalized_path = normalize_plan_path(&plan.delete_targets[0].path);
        plan.delete_targets[0].comparison_key = format!(
            "{}|{}|{}",
            plan.delete_targets[0].category,
            plan.delete_targets[0].action,
            plan.delete_targets[0].normalized_path
        );

        assert!(validate_full_delete_plan(&root, &plan).is_err());
        let _ = std::fs::remove_dir_all(root);
    }

    #[test]
    fn delete_plan_parity_export_from_env() {
        let Ok(root) = std::env::var("TOOLHUB_DELETE_PLAN_PARITY_ROOT") else {
            return;
        };
        let app_id = std::env::var("TOOLHUB_DELETE_PLAN_PARITY_APP_ID")
            .unwrap_or_else(|_| "deleteplan_probe".to_string());
        let out = std::env::var("TOOLHUB_DELETE_PLAN_PARITY_OUT")
            .expect("TOOLHUB_DELETE_PLAN_PARITY_OUT must be set when parity root is set");
        let plan = build_delete_plan(Path::new(&root), &app_id).unwrap();
        std::fs::write(out, serde_json::to_string_pretty(&plan).unwrap()).unwrap();
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
            build_mode: "shared-env".to_string(),
            icon_prompt: None,
            icon_style_preset: None,
            icon_style_custom: None,
            icon_revision_image: None,
            metadata: None,
            icon_override: None,
            build_profile: None,
            show_terminal: false,
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

    #[test]
    fn publish_dirty_file_classification_separates_release_runtime_source_and_other() {
        let lines = vec![
            " M release/manifest.json".to_string(),
            " M scripts/publish_github_release.ps1".to_string(),
            " M runtime/envs/toolhub_env_registry.json".to_string(),
            " M data/app_studio/build_profiles/demo.json".to_string(),
            " M launcher/src/App.tsx".to_string(),
            "?? docs/35_github_release_updater_implementation_plan.md".to_string(),
            " R old.txt -> installer/toolhub_install_dir.nsh".to_string(),
            "?? notes/local.txt".to_string(),
        ];

        let groups = classify_dirty_files(&lines);

        assert_eq!(groups.release_files.len(), 3);
        assert!(groups
            .release_files
            .iter()
            .any(|item| item.contains("release/manifest.json")));
        assert!(groups
            .release_files
            .iter()
            .any(|item| item.contains("scripts/publish_github_release.ps1")));
        assert!(groups
            .release_files
            .iter()
            .any(|item| item.contains("installer/toolhub_install_dir.nsh")));
        assert_eq!(groups.runtime_data_files.len(), 2);
        assert_eq!(groups.source_files.len(), 2);
        assert_eq!(groups.other_files, vec!["?? notes/local.txt".to_string()]);
    }

    #[test]
    fn publish_dirty_status_path_handles_renames_and_quoted_paths() {
        assert_eq!(
            dirty_status_path(" R docs/old.md -> docs/new.md"),
            "docs/new.md"
        );
        assert_eq!(
            dirty_status_path(" M \"launcher/src/App.tsx\""),
            "launcher/src/App.tsx"
        );
        assert_eq!(
            dirty_status_path("?? scripts\\verify_github_release_assets.ps1"),
            "scripts/verify_github_release_assets.ps1"
        );
    }

    #[test]
    fn publish_release_target_folder_uses_sanitized_tag() {
        let root = temp_project_root();
        let target = planned_release_target_dir(&root, Some("v1.2.3/beta"));
        assert!(target.ends_with(Path::new("release/github_release_targets/v1.2.3_beta")));
        let _ = std::fs::remove_dir_all(root);
    }

    #[test]
    fn publish_release_target_asset_plan_marks_generated_checksum() {
        let root = temp_project_root();
        let release_dir = root.join("release");
        let manifest_path = release_dir.join("manifest.json");
        let app_manifest_path = release_dir.join("app_manifest.json");
        let installer_path = release_dir
            .join("dist_installer")
            .join("ToolHub_Setup_1.2.3.exe");
        std::fs::create_dir_all(installer_path.parent().unwrap()).unwrap();
        std::fs::write(&manifest_path, "{}\n").unwrap();
        std::fs::write(&app_manifest_path, "{}\n").unwrap();
        std::fs::write(&installer_path, b"installer").unwrap();

        let target = planned_release_target_dir(&root, Some("v1.2.3"));
        let assets = build_release_target_asset_plan(
            &manifest_path,
            &app_manifest_path,
            Some(&installer_path),
            Some("ToolHub_Setup_1.2.3.exe"),
            &target,
        );

        assert_eq!(assets.len(), 4);
        assert!(assets
            .iter()
            .any(|asset| asset.name == "ToolHub_Setup_1.2.3.exe"
                && asset.source_exists
                && !asset.target_exists));
        assert!(assets
            .iter()
            .any(|asset| asset.name == "checksums.sha256.txt" && asset.generated && asset.upload));
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
        let script = root.join("tools").join("app_studio").join("main.py");
        std::fs::create_dir_all(script.parent().unwrap()).unwrap();
        std::fs::write(script, b"print('app studio')").unwrap();
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
        std::fs::write(
            app_dir.join("icon.svg"),
            "<svg viewBox=\"0 0 64 64\"></svg>",
        )
        .unwrap();
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

    fn write_delete_plan_fixture(root: &Path, app_id: &str, version: &str) {
        let app_dir = root.join("apps").join(app_id);
        std::fs::create_dir_all(&app_dir).unwrap();
        std::fs::write(
            app_dir.join("app.yaml"),
            format!(
                "id: {app_id}\nname: Delete Plan Probe\nadmin:\n  version: {version}\nruntime:\n  required_runtime: python-embedded-toolhub-001\nbuild:\n  source_entry: C:\\External\\ToolHubProbe\\main.py\n  output_mirror: C:\\External\\ToolHubProbe\\ToolHub_AppStudio_Output\\{app_id}\n"
            ),
        )
        .unwrap();
        std::fs::create_dir_all(root.join("release").join("app_packs")).unwrap();
        std::fs::write(
            root.join("release")
                .join("app_packs")
                .join(format!("{app_id}-{version}.zip")),
            "placeholder",
        )
        .unwrap();
        std::fs::create_dir_all(root.join("release").join("staging").join(app_id)).unwrap();
        std::fs::create_dir_all(
            root.join("release")
                .join("staging")
                .join(format!("{app_id}-{version}")),
        )
        .unwrap();
        std::fs::create_dir_all(
            root.join("release")
                .join("staging")
                .join(format!("{app_id}_other")),
        )
        .unwrap();
        std::fs::create_dir_all(root.join("runtime").join("app_envs").join(app_id)).unwrap();
        std::fs::create_dir_all(
            root.join("backups")
                .join("app_studio")
                .join("20990101_000000_delete_plan_test")
                .join(app_id),
        )
        .unwrap();
        std::fs::create_dir_all(
            root.join("backups")
                .join("app_lifecycle")
                .join("20990101_000000_delete_plan_test")
                .join(app_id),
        )
        .unwrap();
        std::fs::write(
            root.join("release").join("app_manifest.json"),
            format!(
                "{{\"apps\":{{\"{app_id}\":{{\"version\":\"{version}\",\"package\":\"app_packs/{app_id}-{version}.zip\",\"sha256\":\"\",\"required_core\":\">=0.1.0\",\"required_runner\":\">=0.1.0\",\"required_runtime\":\"python-embedded-toolhub-001\",\"enabled\":false}}}}}}"
            ),
        )
        .unwrap();
    }

    fn assert_target(
        targets: &[AppStudioDeletePlanTarget],
        category: &str,
        action: &str,
        path: &Path,
        delete_allowed: bool,
    ) {
        let normalized = normalize_plan_path(&path.display().to_string());
        assert!(
            targets.iter().any(|target| {
                target.category == category
                    && target.action == action
                    && target.normalized_path == normalized
                    && target.delete_allowed == delete_allowed
            }),
            "missing target: {category} / {action} / {}",
            path.display()
        );
    }

    fn assert_no_target(targets: &[AppStudioDeletePlanTarget], path: &Path) {
        let normalized = normalize_plan_path(&path.display().to_string());
        assert!(
            targets
                .iter()
                .all(|target| target.normalized_path != normalized),
            "unexpected target: {}",
            path.display()
        );
    }

    fn assert_targets_sorted(targets: &[AppStudioDeletePlanTarget]) {
        let keys: Vec<&str> = targets
            .iter()
            .map(|target| target.comparison_key.as_str())
            .collect();
        let mut sorted = keys.clone();
        sorted.sort_unstable();
        assert_eq!(keys, sorted);
    }
}
