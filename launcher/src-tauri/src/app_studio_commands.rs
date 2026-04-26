use crate::admin_session::AdminSessionState;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::cmp::Ordering;
use std::path::{Path, PathBuf};
use std::process::Command;
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
    pub create_app_env: bool,
    pub rebuild_app_env: bool,
    pub generate_lock: bool,
    pub build_frozen_folder: bool,
    pub verify_runtime: bool,
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

#[derive(Debug, Clone)]
struct PythonCandidate {
    source: String,
    path: PathBuf,
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
    request: AppStudioImportRequest,
    action: &str,
) -> Result<AppStudioRunResult, String> {
    let root = crate::manifest::project_root().map_err(|error| error.to_string())?;
    validate_request(&request)?;
    let python_candidate = find_python_candidate(&root).ok_or_else(python_missing_message)?;
    let python = python_candidate.path.clone();
    let script = root.join("tools").join("app_studio").join("main.py");
    if !script.is_file() {
        return Err("tools/app_studio/main.py が見つかりません。".to_string());
    }

    append_app_studio_gui_log(
        &format!("{action} started"),
        &[
            ("app_id", request.app_id.clone().unwrap_or_default()),
            ("build_mode", request.build_mode.clone()),
            ("python_source", python_candidate.source.clone()),
        ],
    );

    let mut command = Command::new(&python);
    command
        .arg(script)
        .arg("import")
        .arg("--entry")
        .arg(&request.entry)
        .arg("--build-mode")
        .arg(&request.build_mode);
    if let Some(app_id) = clean_optional(&request.app_id) {
        command.arg("--app-id").arg(app_id);
    }
    if let Some(name) = clean_optional(&request.name) {
        command.arg("--name").arg(name);
    }
    if let Some(version) = clean_optional(&request.version) {
        command.arg("--version").arg(version);
    }
    if let Some(icon_prompt) = clean_optional(&request.icon_prompt) {
        command.arg("--icon-prompt").arg(icon_prompt);
    }
    if request.create_app_env {
        command.arg("--create-app-env");
    }
    if request.rebuild_app_env {
        command.arg("--rebuild-app-env");
    }
    if request.generate_lock {
        command.arg("--generate-lock");
    }
    if request.build_frozen_folder {
        command.arg("--build-frozen-folder");
    }
    if request.verify_runtime {
        command.arg("--verify-runtime");
    }
    command.arg(if action == "apply" {
        "--apply"
    } else {
        "--suggest"
    });

    let output = command
        .current_dir(&root)
        .output()
        .map_err(|_| "App Studioを起動できませんでした。".to_string())?;
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
            ("output_dir", summary.output_dir.clone().unwrap_or_default()),
            ("python_source", python_candidate.source),
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
    let output = Command::new(&python)
        .arg(script)
        .arg("approve")
        .arg("--app-id")
        .arg(&app_id)
        .arg(approval_flag(strict))
        .current_dir(&root)
        .output()
        .map_err(|_| "App Studio承認処理を起動できませんでした。".to_string())?;
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
    success_message: &str,
) -> AppStudioRunResult {
    AppStudioRunResult {
        ok,
        exit_code,
        stdout,
        stderr,
        user_message: if ok {
            success_message.to_string()
        } else {
            "App Studio処理に失敗しました。ログを確認してください。".to_string()
        },
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

    let build_mode_valid =
        ["auto", "app-env", "frozen-folder", "existing-exe"].contains(&request.build_mode.as_str());
    if !build_mode_valid {
        errors.push("BuildModeが不正です。".to_string());
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
    if !runtime_python_exists {
        warnings.push(
            "runtime/python/python.exe は未配置です。開発環境Python fallbackになる可能性があります。"
                .to_string(),
        );
    }

    let (python_source, python_path) = match python_candidate {
        Some(candidate) => {
            if candidate.source != "runtime" {
                warnings.push(
                    "開発環境Python fallbackを使用します。正式配布前はToolHub同梱runtimeで再確認してください。"
                        .to_string(),
                );
            }
            (candidate.source, Some(candidate.path.display().to_string()))
        }
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

fn read_summary(
    root: &Path,
    app_id: Option<&str>,
    output_dir: Option<&Path>,
) -> AppStudioResultSummary {
    let mut summary = AppStudioResultSummary::default();
    let output = output_dir
        .map(Path::to_path_buf)
        .or_else(|| app_id.and_then(|id| output_dir_from_app_yaml(root, id)));
    if let Some(path) = output {
        summary.output_dir = Some(path.display().to_string());
        read_import_plan(&path, &mut summary);
        read_execution_result(&path, &mut summary);
        read_runtime_result(&path, &mut summary);
        read_app_pack(&path, &mut summary);
    }
    if summary.app_id.is_none() {
        summary.app_id = app_id.map(str::to_string);
    }
    read_enabled(root, &mut summary);
    read_version(root, &mut summary);
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
    summary.enabled = json
        .get("apps")
        .and_then(|apps| apps.get(app_id))
        .and_then(|entry| entry.get("enabled"))
        .and_then(Value::as_bool);
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
$dialog.Filter = 'Python or executable (*.py;*.exe)|*.py;*.exe|Python files (*.py)|*.py|Executable files (*.exe)|*.exe|All files (*.*)|*.*'
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
            build_mode: "app-env".to_string(),
            icon_prompt: None,
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
        let masked = mask_sensitive("key=sk-test123456abcd done");
        assert!(masked.contains("sk-...abcd"));
        assert!(!masked.contains("test123456"));
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
            build_mode: "app-env".to_string(),
            icon_prompt: None,
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
