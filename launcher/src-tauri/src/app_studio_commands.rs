use crate::admin_session::AdminSessionState;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::path::{Path, PathBuf};
use std::process::Command;
use tauri::State;

#[derive(Debug, Deserialize, Clone)]
#[serde(rename_all = "camelCase")]
pub struct AppStudioImportRequest {
    pub entry: String,
    pub app_id: Option<String>,
    pub name: Option<String>,
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
pub struct AppStudioResultSummary {
    pub app_id: Option<String>,
    pub output_dir: Option<String>,
    pub selected_build_mode: Option<String>,
    pub execution_status: Option<String>,
    pub approval_allowed: Option<bool>,
    pub runtime_status: Option<String>,
    pub app_pack: Option<String>,
    pub enabled: Option<bool>,
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
}
