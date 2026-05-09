use crate::admin_session::AdminSessionState;
use crate::app_studio_ai_proposal_reader::read_ai_proposal;
pub use crate::app_studio_ai_proposal_reader::{
    AppStudioAiIconCandidateSuggestion, AppStudioAiIconSuggestion, AppStudioAiMetadataSuggestion,
    AppStudioAiProposal,
};
#[cfg(test)]
use crate::app_studio_cli_args::approval_flag;
use crate::app_studio_cli_args::{
    approval_mode_name, build_approve_cli_args, build_icon_regenerate_cli_args,
    build_image_test_cli_args, build_import_cli_args, import_request_from_update,
    normalize_normal_import_request, AppStudioCliAction, AppStudioIconRegenerateCliOptions,
    AppStudioImportCliOverrides,
};
use crate::app_studio_delete_plan::{build_delete_plan, normalize_plan_path};
use crate::app_studio_overrides::{
    write_build_profile_override_file, write_icon_override_file, write_icon_revision_image_file,
    write_metadata_override_file,
};
use crate::app_studio_preflight::{
    build_import_preflight_result, find_python_candidate, python_missing_message,
    runtime_python_path, validate_app_id, validate_entry_path, validate_source_root_path,
    PythonCandidate,
};
use crate::app_studio_process::{
    append_app_studio_gui_log, command_line_for_log, mask_sensitive, redact_cli_arg_value,
    result_from_process,
};
pub use crate::app_studio_result_reader::AppStudioResultSummary;
use crate::app_studio_result_reader::{output_dir_from_app_yaml, read_summary};
pub use crate::app_studio_types::{
    AppStudioAiDiagnostics, AppStudioDeletePlan, AppStudioDeletePlanTarget,
    AppStudioEditableMetadata, AppStudioFullDeletePostCheckSummary, AppStudioFullDeleteRecord,
    AppStudioFullDeleteResult, AppStudioIconOverride, AppStudioIconRegenerateRequest,
    AppStudioImportRequest, AppStudioManagedApp, AppStudioManagementActionResult,
    AppStudioPreflightResult, AppStudioRegisteredApp, AppStudioRunResult, AppStudioTimingPhase,
    AppStudioUpdateRequest,
};
use serde::Serialize;
use serde_json::{Map, Value};
use std::cmp::Ordering;
use std::collections::BTreeSet;
use std::fs;
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
    Ok(build_ai_env_plan().diagnostics)
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
    let script = root.join("tools").join("app_studio").join("main.py");
    if !script.is_file() {
        return Err("tools/app_studio/main.py was not found.".to_string());
    }
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
    let script = root.join("tools").join("app_studio").join("main.py");
    if !script.is_file() {
        return Err("tools/app_studio/main.py が見つかりません。".to_string());
    }
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
    if !["auto", "app-env", "frozen-folder", "existing-exe"].contains(&request.build_mode.as_str())
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

fn list_managed_apps_from_root(root: &Path) -> Vec<AppStudioManagedApp> {
    let release = read_json(&app_manifest_path(root));
    let release_apps = release
        .as_ref()
        .and_then(|value| value.get("apps"))
        .and_then(Value::as_object);
    let mut app_ids = BTreeSet::new();
    if let Some(apps) = release_apps {
        app_ids.extend(apps.keys().cloned());
    }
    let apps_dir = root.join("apps");
    if let Ok(entries) = fs::read_dir(&apps_dir) {
        for entry in entries.flatten() {
            let path = entry.path();
            if path.is_dir() && path.join("app.yaml").is_file() {
                if let Some(id) = path.file_name().and_then(|value| value.to_str()) {
                    app_ids.insert(id.to_string());
                }
            }
        }
    }

    app_ids
        .into_iter()
        .map(|app_id| {
            managed_app_from_parts(
                root,
                &app_id,
                release_apps.and_then(|apps| apps.get(&app_id)),
            )
        })
        .collect()
}

fn managed_app_from_parts(
    root: &Path,
    app_id: &str,
    manifest_entry: Option<&Value>,
) -> AppStudioManagedApp {
    let source_dir = root.join("apps").join(app_id);
    let app_yaml = source_dir.join("app.yaml");
    let has_source = app_yaml.is_file();
    let yaml_app = if has_source {
        Some(read_registered_app_from_yaml(&app_yaml, app_id))
    } else {
        None
    };
    let yaml_ok = yaml_app.as_ref().and_then(|result| result.as_ref().ok());
    let yaml_error = yaml_app
        .as_ref()
        .and_then(|result| result.as_ref().err())
        .cloned();
    let enabled = manifest_entry.map(manifest_entry_enabled);
    let management_status = if yaml_error.is_some() {
        "invalid_manifest"
    } else if let Some(enabled) = enabled {
        match (enabled, has_source) {
            (true, true) => "active",
            (false, true) => "disabled_with_source",
            (false, false) => "disabled_stale",
            (true, false) => "enabled_missing_source",
        }
    } else if has_source {
        "source_missing_from_manifest"
    } else {
        "invalid_manifest"
    };
    let package_relative = manifest_entry.and_then(|entry| json_str(entry, "package"));
    let package_path = package_relative
        .as_ref()
        .map(|package| root.join("release").join(package));
    let package_exists = package_path.as_ref().is_some_and(|path| path.is_file());
    let version = manifest_entry
        .and_then(|entry| json_str(entry, "version"))
        .or_else(|| yaml_ok.map(|app| app.version.clone()));
    let name = yaml_ok
        .map(|app| app.name.clone())
        .unwrap_or_else(|| app_id.to_string());
    let plan = build_delete_plan(root, app_id).unwrap_or_default();
    let delete_plan_status = if plan.blocking_reasons.is_empty() {
        "ready"
    } else {
        "blocked"
    };

    AppStudioManagedApp {
        app_id: app_id.to_string(),
        name,
        version,
        enabled,
        management_status: management_status.to_string(),
        has_source,
        source_dir: source_dir.display().to_string(),
        app_yaml_path: app_yaml.display().to_string(),
        package_path: package_path.map(|path| path.display().to_string()),
        package_exists,
        delete_plan_status: delete_plan_status.to_string(),
        delete_target_count: plan.delete_targets.len(),
        excluded_target_count: plan.excluded_targets.len(),
        warning: management_warning(management_status, yaml_error.as_deref()),
        recommended_action: management_recommended_action(management_status).to_string(),
    }
}

fn management_warning(status: &str, yaml_error: Option<&str>) -> Option<String> {
    match status {
        "invalid_manifest" => Some(
            yaml_error
                .map(|error| format!("app.yaml could not be read: {error}"))
                .unwrap_or_else(|| "App definition could not be read.".to_string()),
        ),
        "enabled_missing_source" => {
            Some("enabled=true but apps/<app_id>/app.yaml is missing.".to_string())
        }
        "disabled_stale" => {
            Some("release/app_manifest.json has a disabled entry without app source.".to_string())
        }
        "source_missing_from_manifest" => Some(
            "apps/<app_id>/app.yaml exists but release/app_manifest.json has no entry.".to_string(),
        ),
        _ => None,
    }
}

fn management_recommended_action(status: &str) -> &'static str {
    match status {
        "active" => "Hide if it should not be shown, or inspect the deletion plan before future full delete.",
        "disabled_with_source" => "Can be shown again or inspected with a deletion plan.",
        "disabled_stale" => "Future full delete should remove the stale manifest entry and generated artifacts.",
        "enabled_missing_source" => "Hide first, then recover apps/<app_id>/ from source control or inspect the deletion plan.",
        "source_missing_from_manifest" => "Rebuild the app manifest from apps/ before release.",
        "invalid_manifest" => "Fix app.yaml before changing visibility.",
        _ => "Review the app state.",
    }
}

fn management_set_enabled(
    root: &Path,
    app_id: &str,
    enabled: bool,
) -> Result<AppStudioManagementActionResult, String> {
    let app_id = app_id.trim();
    validate_app_id(app_id)?;
    if enabled && !root.join("apps").join(app_id).join("app.yaml").is_file() {
        return Err("apps/<app_id>/app.yaml is required before showing the app.".to_string());
    }
    let manifest_path = app_manifest_path(root);
    let mut manifest = read_app_manifest_for_write(&manifest_path)?;
    if manifest_app_entry(&manifest, app_id).is_none() {
        return Err(
            "release/app_manifest.json has no entry for this app. Rebuild the app manifest first."
                .to_string(),
        );
    }
    {
        let entry = manifest_app_entry_mut(&mut manifest, app_id)?;
        entry.insert("enabled".to_string(), Value::Bool(enabled));
    }
    write_json_file(&manifest_path, &manifest)?;
    append_app_studio_gui_log(
        "app_management_set_enabled",
        &[
            ("app_id", app_id.to_string()),
            ("enabled", enabled.to_string()),
        ],
    );
    Ok(management_result(
        root,
        app_id,
        format!(
            "{} was {}.",
            app_id,
            if enabled { "shown" } else { "hidden" }
        ),
    ))
}

fn management_result(
    root: &Path,
    app_id: &str,
    message: String,
) -> AppStudioManagementActionResult {
    let apps = list_managed_apps_from_root(root);
    let target = apps.iter().find(|app| app.app_id == app_id).cloned();
    AppStudioManagementActionResult {
        ok: true,
        message,
        apps,
        target,
    }
}

fn full_delete_apply(
    root: &Path,
    app_id: &str,
    plan_snapshot: Option<&AppStudioDeletePlan>,
) -> Result<AppStudioFullDeleteResult, String> {
    let app_id = app_id.trim();
    validate_app_id(app_id)?;
    let plan = build_delete_plan(root, app_id)?;
    validate_full_delete_plan(root, &plan)?;
    if let Some(snapshot) = plan_snapshot {
        compare_delete_plan_snapshot(snapshot, &plan)?;
    }

    let mut deleted = Vec::new();
    let mut already_clean = Vec::new();
    let mut skipped = Vec::new();
    let mut failed = Vec::new();
    let mut stop_before_manifest = false;

    for target in ordered_full_delete_targets(&plan) {
        let record = delete_full_delete_target(root, target);
        match record.status.as_str() {
            "deleted" => deleted.push(record),
            "already_clean" => already_clean.push(record),
            "skipped" => skipped.push(record),
            _ => {
                stop_before_manifest = true;
                failed.push(record);
                break;
            }
        }
    }

    let mut manifest_entry_removed = false;
    if stop_before_manifest {
        if let Some(target) = plan
            .delete_targets
            .iter()
            .find(|target| is_manifest_entry_target(target))
        {
            skipped.push(full_delete_record_from_target(
                target,
                "skipped",
                "Manifest entry was not removed because an earlier delete step failed.",
            ));
        }
    } else if let Some(target) = plan
        .delete_targets
        .iter()
        .find(|target| is_manifest_entry_target(target))
    {
        match remove_manifest_entry(root, app_id, target) {
            Ok((record, removed)) => {
                manifest_entry_removed = removed;
                match record.status.as_str() {
                    "deleted" => deleted.push(record),
                    "already_clean" => already_clean.push(record),
                    "skipped" => skipped.push(record),
                    _ => failed.push(record),
                }
            }
            Err(error) => failed.push(full_delete_record_from_target(target, "failed", &error)),
        }
    }

    let post_check_summary = full_delete_post_check(root, app_id);
    let ok = failed.is_empty()
        && !post_check_summary.manifest_entry_present
        && post_check_summary.remaining_delete_target_count == 0;
    let message = if ok {
        format!("{app_id} was fully deleted from repository-managed targets.")
    } else {
        format!("{app_id} full delete did not complete. Review failed and remaining targets.")
    };
    let result = AppStudioFullDeleteResult {
        ok,
        message,
        app_id: app_id.to_string(),
        deleted,
        already_clean,
        skipped,
        excluded: plan.excluded_targets.clone(),
        failed,
        manifest_entry_removed,
        post_check_summary,
        apps: list_managed_apps_from_root(root),
    };

    append_app_studio_gui_log(
        "app_management_full_delete",
        &[
            ("app_id", app_id.to_string()),
            ("ok", result.ok.to_string()),
            ("deleted", result.deleted.len().to_string()),
            ("already_clean", result.already_clean.len().to_string()),
            ("failed", result.failed.len().to_string()),
            (
                "manifest_entry_removed",
                result.manifest_entry_removed.to_string(),
            ),
        ],
    );

    Ok(result)
}

fn validate_full_delete_plan(root: &Path, plan: &AppStudioDeletePlan) -> Result<(), String> {
    let mut errors = Vec::new();
    if !plan.blocking_reasons.is_empty() {
        errors.extend(plan.blocking_reasons.iter().cloned());
    }
    if plan.delete_targets.is_empty() {
        errors.push("Deletion plan has no delete targets.".to_string());
    }
    if !plan.manifest_entry_exists && Path::new(&plan.source_dir).exists() {
        errors.push(
            "apps/<app_id>/ exists without a release/app_manifest.json entry. Rebuild the manifest before full delete."
                .to_string(),
        );
    }

    let manifest_path = app_manifest_path(root);
    let manifest_normalized = normalize_plan_path(&manifest_path.display().to_string());
    let mut delete_normalized_paths = BTreeSet::new();
    for target in &plan.delete_targets {
        if !target.delete_allowed {
            errors.push(format!(
                "Delete target is not marked deleteAllowed=true: {}",
                target.path
            ));
        }
        if matches!(
            target.category.as_str(),
            "external_reference" | "user_data" | "shared_runtime" | "managed_generated_candidate"
        ) {
            errors.push(format!(
                "Forbidden category appears in delete targets: {}",
                target.path
            ));
        }
        if !target.normalized_path.trim().is_empty() {
            delete_normalized_paths.insert(target.normalized_path.clone());
        }
        if is_manifest_entry_target(target) {
            if target.normalized_path != manifest_normalized {
                errors.push(format!(
                    "Manifest entry target must point to release/app_manifest.json: {}",
                    target.path
                ));
            }
            continue;
        }
        if let Err(error) = resolve_safe_delete_target_path(root, target) {
            errors.push(error);
        }
        if is_shared_runtime_path(root, Path::new(&target.path)) {
            errors.push(format!(
                "Shared runtime cannot be a delete target: {}",
                target.path
            ));
        }
    }

    for target in &plan.excluded_targets {
        if target.delete_allowed {
            errors.push(format!(
                "Excluded target must be deleteAllowed=false: {}",
                target.path
            ));
        }
        if delete_normalized_paths.contains(&target.normalized_path) {
            errors.push(format!(
                "Excluded target overlaps a delete target: {}",
                target.path
            ));
        }
    }

    if errors.is_empty() {
        Ok(())
    } else {
        Err(format!(
            "Full delete safety check failed: {}",
            errors.join(" / ")
        ))
    }
}

fn compare_delete_plan_snapshot(
    snapshot: &AppStudioDeletePlan,
    fresh: &AppStudioDeletePlan,
) -> Result<(), String> {
    let mut mismatches = Vec::new();
    if snapshot.app_id != fresh.app_id {
        mismatches.push("appId changed".to_string());
    }
    if snapshot.manifest_entry_exists != fresh.manifest_entry_exists {
        mismatches.push("manifest entry existence changed".to_string());
    }
    if snapshot.manifest_version != fresh.manifest_version {
        mismatches.push("manifest version changed".to_string());
    }
    if snapshot.manifest_package != fresh.manifest_package {
        mismatches.push("manifest package changed".to_string());
    }
    let snapshot_delete_keys: BTreeSet<&str> = snapshot
        .delete_targets
        .iter()
        .map(|target| target.comparison_key.as_str())
        .collect();
    let fresh_delete_keys: BTreeSet<&str> = fresh
        .delete_targets
        .iter()
        .map(|target| target.comparison_key.as_str())
        .collect();
    if snapshot_delete_keys != fresh_delete_keys {
        mismatches.push("delete target set changed".to_string());
    }
    let snapshot_excluded_keys: BTreeSet<&str> = snapshot
        .excluded_targets
        .iter()
        .map(|target| target.comparison_key.as_str())
        .collect();
    let fresh_excluded_keys: BTreeSet<&str> = fresh
        .excluded_targets
        .iter()
        .map(|target| target.comparison_key.as_str())
        .collect();
    if snapshot_excluded_keys != fresh_excluded_keys {
        mismatches.push("excluded target set changed".to_string());
    }

    if mismatches.is_empty() {
        Ok(())
    } else {
        Err(format!(
            "Deletion plan changed after it was displayed. Reload the plan before deleting. ({})",
            mismatches.join(", ")
        ))
    }
}

fn ordered_full_delete_targets(plan: &AppStudioDeletePlan) -> Vec<&AppStudioDeletePlanTarget> {
    let mut ordered = Vec::new();
    let mut seen = BTreeSet::new();
    for action in [
        "delete App Pack zip",
        "delete staging artifact",
        "delete runtime app_env",
        "delete App Studio backup",
        "delete legacy lifecycle backup",
        "delete apps/<app_id>/",
    ] {
        for target in plan
            .delete_targets
            .iter()
            .filter(|target| target.action == action && !is_manifest_entry_target(target))
        {
            seen.insert(target.comparison_key.clone());
            ordered.push(target);
        }
    }
    for target in plan.delete_targets.iter().filter(|target| {
        !is_manifest_entry_target(target) && !seen.contains(&target.comparison_key)
    }) {
        ordered.push(target);
    }
    ordered
}

fn delete_full_delete_target(
    root: &Path,
    target: &AppStudioDeletePlanTarget,
) -> AppStudioFullDeleteRecord {
    let Ok(path) = resolve_safe_delete_target_path(root, target) else {
        return full_delete_record_from_target(
            target,
            "failed",
            "Target path failed safety resolution.",
        );
    };
    if !path.exists() {
        return full_delete_record_from_target(
            target,
            "already_clean",
            "Target was already missing.",
        );
    }
    let delete_result = if path.is_dir() {
        fs::remove_dir_all(&path)
    } else {
        fs::remove_file(&path)
    };
    match delete_result {
        Ok(()) if !path.exists() => full_delete_record_from_target(
            target,
            "deleted",
            "Deleted repository-managed app target.",
        ),
        Ok(()) => full_delete_record_from_target(
            target,
            "failed",
            "Target still exists after deletion attempt.",
        ),
        Err(error) => full_delete_record_from_target(target, "failed", &error.to_string()),
    }
}

fn remove_manifest_entry(
    root: &Path,
    app_id: &str,
    target: &AppStudioDeletePlanTarget,
) -> Result<(AppStudioFullDeleteRecord, bool), String> {
    let manifest_path = app_manifest_path(root);
    let mut manifest = read_app_manifest_for_write(&manifest_path)?;
    let apps = manifest
        .get_mut("apps")
        .and_then(Value::as_object_mut)
        .ok_or_else(|| "release/app_manifest.json apps object was not found.".to_string())?;
    let removed = apps.remove(app_id).is_some();
    if removed {
        write_json_file(&manifest_path, &manifest)?;
        Ok((
            full_delete_record_from_target(
                target,
                "deleted",
                "Removed only the app entry from release/app_manifest.json.",
            ),
            true,
        ))
    } else {
        Ok((
            full_delete_record_from_target(
                target,
                "already_clean",
                "Manifest entry was already absent.",
            ),
            false,
        ))
    }
}

fn full_delete_post_check(root: &Path, app_id: &str) -> AppStudioFullDeletePostCheckSummary {
    let manifest = read_json(&app_manifest_path(root));
    let manifest_json_valid = manifest.is_some();
    let manifest_entry_present = manifest
        .as_ref()
        .and_then(|value| value.get("apps"))
        .and_then(|apps| apps.get(app_id))
        .is_some();
    let fresh_plan = build_delete_plan(root, app_id).unwrap_or_default();
    let remaining_delete_targets: Vec<String> = fresh_plan
        .delete_targets
        .iter()
        .filter(|target| !is_manifest_entry_target(target) && target.exists)
        .map(|target| target.comparison_key.clone())
        .collect();
    AppStudioFullDeletePostCheckSummary {
        manifest_json_valid,
        manifest_entry_present,
        remaining_delete_target_count: remaining_delete_targets.len(),
        remaining_delete_targets,
    }
}

fn full_delete_record_from_target(
    target: &AppStudioDeletePlanTarget,
    status: &str,
    note: &str,
) -> AppStudioFullDeleteRecord {
    AppStudioFullDeleteRecord {
        category: target.category.clone(),
        action: target.action.clone(),
        path: target.path.clone(),
        normalized_path: target.normalized_path.clone(),
        comparison_key: target.comparison_key.clone(),
        status: status.to_string(),
        note: note.to_string(),
    }
}

fn resolve_safe_delete_target_path(
    root: &Path,
    target: &AppStudioDeletePlanTarget,
) -> Result<PathBuf, String> {
    let path = PathBuf::from(&target.path);
    if path
        .components()
        .any(|component| matches!(component, std::path::Component::ParentDir))
    {
        return Err(format!(
            "Delete target contains path traversal: {}",
            target.path
        ));
    }
    let full_path = if path.is_absolute() {
        path
    } else {
        root.join(path)
    };
    if !path_is_strict_child_of(&full_path, root) {
        return Err(format!(
            "Delete target is not safely inside the project root: {}",
            target.path
        ));
    }
    Ok(full_path)
}

fn path_is_strict_child_of(path: &Path, root: &Path) -> bool {
    let root_path = root.to_path_buf();
    let full_path = if path.is_absolute() {
        path.to_path_buf()
    } else {
        root_path.join(path)
    };
    let root_norm = normalize_plan_path(&root_path.display().to_string());
    let full_norm = normalize_plan_path(&full_path.display().to_string());
    full_norm != root_norm && full_norm.starts_with(&format!("{root_norm}/"))
}

fn is_manifest_entry_target(target: &AppStudioDeletePlanTarget) -> bool {
    target.action == "remove app_manifest entry"
}

fn is_shared_runtime_path(root: &Path, path: &Path) -> bool {
    let shared_python = root.join("runtime").join("python");
    let shared_web = root.join("runtime").join("web_automation_runtime");
    let path_norm = normalize_plan_path(&path.display().to_string());
    path_norm == normalize_plan_path(&shared_python.display().to_string())
        || path_norm == normalize_plan_path(&shared_web.display().to_string())
}

fn read_app_manifest_for_write(path: &Path) -> Result<Value, String> {
    let text = fs::read_to_string(path).map_err(|error| {
        format!(
            "release/app_manifest.json could not be read: {} ({error})",
            path.display()
        )
    })?;
    serde_json::from_str(&text).map_err(|error| {
        format!(
            "release/app_manifest.json could not be parsed: {} ({error})",
            path.display()
        )
    })
}

fn app_manifest_path(root: &Path) -> PathBuf {
    root.join("release").join("app_manifest.json")
}

fn manifest_app_entry<'a>(manifest: &'a Value, app_id: &str) -> Option<&'a Value> {
    manifest.get("apps").and_then(|apps| apps.get(app_id))
}

fn manifest_app_entry_mut<'a>(
    manifest: &'a mut Value,
    app_id: &str,
) -> Result<&'a mut Map<String, Value>, String> {
    let apps = manifest
        .get_mut("apps")
        .and_then(Value::as_object_mut)
        .ok_or_else(|| "release/app_manifest.json apps object was not found.".to_string())?;
    apps.get_mut(app_id)
        .and_then(Value::as_object_mut)
        .ok_or_else(|| "release/app_manifest.json has no entry for this app.".to_string())
}

fn manifest_entry_enabled(entry: &Value) -> bool {
    entry
        .get("enabled")
        .and_then(Value::as_bool)
        .unwrap_or(true)
}

fn json_str(value: &Value, key: &str) -> Option<String> {
    value
        .get(key)
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(str::to_string)
}

fn write_json_file<T: Serialize>(path: &Path, value: &T) -> Result<(), String> {
    let text = serde_json::to_string_pretty(value).map_err(|error| {
        format!(
            "JSON could not be generated for {} ({error})",
            path.display()
        )
    })?;
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|error| {
            format!(
                "folder could not be created: {} ({error})",
                parent.display()
            )
        })?;
    }
    fs::write(path, format!("{text}\n"))
        .map_err(|error| format!("JSON could not be written: {} ({error})", path.display()))
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
            build_mode: "frozen-folder".to_string(),
            icon_prompt: None,
            icon_style_preset: None,
            icon_style_custom: None,
            icon_revision_image: None,
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
            source_root: None,
            app_id: Some("my_tool".to_string()),
            name: Some("My Tool".to_string()),
            version: None,
            build_mode: "app-env".to_string(),
            icon_prompt: None,
            icon_style_preset: None,
            icon_style_custom: None,
            icon_revision_image: None,
            metadata: None,
            icon_override: None,
            build_profile: None,
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
            build_mode: "frozen-folder".to_string(),
            icon_prompt: None,
            icon_style_preset: None,
            icon_style_custom: None,
            icon_revision_image: None,
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
