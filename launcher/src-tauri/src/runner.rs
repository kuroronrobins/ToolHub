use serde::{Deserialize, Serialize};
use std::error::Error;
use std::path::{Path, PathBuf};
use std::process::Command;

#[derive(Debug, Serialize, Deserialize, Clone)]
#[serde(rename_all = "camelCase")]
pub struct LaunchEvent {
    pub event_type: Option<String>,
    #[serde(rename = "type")]
    pub kind: String,
    pub message: String,
    pub progress: Option<u8>,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
#[serde(rename_all = "camelCase")]
pub struct LaunchResult {
    pub ok: bool,
    pub app_id: String,
    pub user_message: String,
    pub log_path: Option<String>,
    pub events: Vec<LaunchEvent>,
}

pub fn launch_runner(root: &Path, app_id: &str) -> Result<LaunchResult, Box<dyn Error>> {
    let python = find_python().ok_or("Python command was not found")?;
    let runner_script = root.join("runner").join("toolhub_runner").join("main.py");
    if !runner_script.is_file() {
        return Ok(failure(app_id, "アプリの起動に失敗しました。管理者に連絡してください。", None));
    }

    let result_file = result_file_path(root, app_id)?;
    if let Some(parent) = result_file.parent() {
        std::fs::create_dir_all(parent)?;
    }

    crate::logging::append_launcher_log(root, &format!("launch app_id={} via {:?}", app_id, python));

    let user_data_root = crate::setup::user_data_root();
    let output = Command::new(&python)
        .arg(runner_script)
        .arg("--project-root")
        .arg(root)
        .arg("--app-id")
        .arg(app_id)
        .arg("--result-json")
        .arg(&result_file)
        .env("TOOLHUB_USER_DATA_ROOT", &user_data_root)
        .current_dir(root)
        .output()?;

    crate::logging::append_launcher_log(
        root,
        &format!(
            "runner finished app_id={} status={} stdout_bytes={} stderr_bytes={}",
            app_id,
            output.status,
            output.stdout.len(),
            output.stderr.len()
        ),
    );

    if result_file.is_file() {
        let text = std::fs::read_to_string(&result_file)?;
        let result: LaunchResult = serde_json::from_str(&text)?;
        return Ok(result);
    }

    Ok(failure(
        app_id,
        "アプリの起動に失敗しました。時間をおいて再実行するか、管理者に連絡してください。",
        None,
    ))
}

fn find_python() -> Option<PathBuf> {
    for command in ["python", "py"] {
        if let Some(path) = find_on_path(command) {
            return Some(path);
        }
    }
    None
}

fn find_on_path(command: &str) -> Option<PathBuf> {
    let path = std::env::var_os("PATH")?;
    for dir in std::env::split_paths(&path) {
        let candidate = dir.join(command);
        if candidate.is_file() {
            return Some(candidate);
        }
        if cfg!(windows) {
            let cmd_candidate = dir.join(format!("{}.cmd", command));
            if cmd_candidate.is_file() {
                return Some(cmd_candidate);
            }
            let exe_candidate = dir.join(format!("{}.exe", command));
            if exe_candidate.is_file() {
                return Some(exe_candidate);
            }
        }
    }
    None
}

fn result_file_path(_root: &Path, app_id: &str) -> Result<PathBuf, Box<dyn Error>> {
    let timestamp = chrono::Local::now().format("%Y%m%d_%H%M%S").to_string();
    let safe_app_id = app_id.replace(['\\', '/', ':'], "_");
    Ok(crate::setup::user_data_root()
        .join("data")
        .join("logs")
        .join("launcher")
        .join(format!("result_{}_{}.json", safe_app_id, timestamp)))
}

fn failure(app_id: &str, message: &str, log_path: Option<String>) -> LaunchResult {
    LaunchResult {
        ok: false,
        app_id: app_id.to_string(),
        user_message: message.to_string(),
        log_path,
        events: vec![LaunchEvent {
            event_type: None,
            kind: "error".to_string(),
            message: message.to_string(),
            progress: None,
        }],
    }
}

