use serde::{Deserialize, Serialize};
use std::error::Error;
use std::path::{Path, PathBuf};
use std::process::{Command, Output, Stdio};
use std::time::{Duration, Instant};

const RUNNER_RESULT_TIMEOUT: Duration = Duration::from_secs(10);

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

#[derive(Debug, Deserialize, Default)]
struct RawLaunchManifest {
    run: Option<RawLaunchRun>,
}

#[derive(Debug, Deserialize, Default)]
struct RawLaunchRun {
    runner: Option<String>,
    entry: Option<String>,
    mode: Option<String>,
}

#[derive(Debug)]
struct LaunchManifestSummary {
    app_yaml: PathBuf,
    runner: String,
    entry: String,
    mode: String,
}

enum RunnerCommandOutcome {
    Finished(Output),
    TimedOut { pid: u32 },
}

pub fn launch_runner(root: &Path, app_id: &str) -> Result<LaunchResult, Box<dyn Error>> {
    let python = find_python(root).ok_or("Python command was not found")?;
    let runner_script = root.join("runner").join("toolhub_runner").join("main.py");
    if !runner_script.is_file() {
        return Ok(failure(
            app_id,
            "アプリの起動に失敗しました。管理者に連絡してください。",
            None,
        ));
    }

    let result_file = result_file_path(root, app_id)?;
    if let Some(parent) = result_file.parent() {
        std::fs::create_dir_all(parent)?;
    }

    let manifest_summary = read_launch_manifest_summary(root, app_id);
    let root_type = crate::manifest::root_type(root);
    crate::logging::append_launcher_log(
        root,
        &format!(
            "launch app_id={} root={} root_type={} app_yaml={} runner={} entry={} mode={} result_json={} via {:?}",
            app_id,
            root.display(),
            root_type,
            manifest_summary.app_yaml.display(),
            manifest_summary.runner.as_str(),
            manifest_summary.entry.as_str(),
            manifest_summary.mode.as_str(),
            result_file.display(),
            python
        ),
    );

    let user_data_root = crate::setup::user_data_root();
    let mut command = Command::new(&python);
    command
        .arg(runner_script)
        .arg("--project-root")
        .arg(root)
        .arg("--app-id")
        .arg(app_id)
        .arg("--result-json")
        .arg(&result_file)
        .env("TOOLHUB_USER_DATA_ROOT", &user_data_root)
        .current_dir(root);

    let outcome = run_runner_command(&mut command, runner_result_timeout(root_type))?;
    let output = match outcome {
        RunnerCommandOutcome::Finished(output) => output,
        RunnerCommandOutcome::TimedOut { pid } => {
            crate::logging::append_launcher_log(
                root,
                &format!(
                    "runner timeout app_id={} pid={} timeout_seconds={} root={} root_type={} app_yaml={} runner={} entry={} mode={} result_json={}",
                    app_id,
                    pid,
                    RUNNER_RESULT_TIMEOUT.as_secs(),
                    root.display(),
                    root_type,
                    manifest_summary.app_yaml.display(),
                    manifest_summary.runner.as_str(),
                    manifest_summary.entry.as_str(),
                    manifest_summary.mode.as_str(),
                    result_file.display()
                ),
            );
            if result_file.is_file() {
                return read_launch_result(&result_file);
            }
            return Ok(timeout_failure(
                app_id,
                RUNNER_RESULT_TIMEOUT,
                launcher_log_path(),
            ));
        }
    };

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
        return read_launch_result(&result_file);
    }

    Ok(failure(
        app_id,
        "アプリの起動に失敗しました。時間をおいて再実行するか、管理者に連絡してください。",
        None,
    ))
}

fn run_runner_command_with_timeout(
    command: &mut Command,
    timeout: Duration,
) -> Result<RunnerCommandOutcome, Box<dyn Error>> {
    run_runner_command(command, Some(timeout))
}

fn run_runner_command(
    command: &mut Command,
    timeout: Option<Duration>,
) -> Result<RunnerCommandOutcome, Box<dyn Error>> {
    let Some(timeout) = timeout else {
        return Ok(RunnerCommandOutcome::Finished(command.output()?));
    };

    let mut child = command
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()?;
    let pid = child.id();
    let started_at = Instant::now();
    loop {
        if child.try_wait()?.is_some() {
            return Ok(RunnerCommandOutcome::Finished(child.wait_with_output()?));
        }
        if started_at.elapsed() >= timeout {
            let _ = child.kill();
            let _ = child.wait();
            return Ok(RunnerCommandOutcome::TimedOut { pid });
        }
        std::thread::sleep(Duration::from_millis(100));
    }
}

fn runner_result_timeout(root_type: &str) -> Option<Duration> {
    if root_type == "dev_build_artifact" {
        Some(RUNNER_RESULT_TIMEOUT)
    } else {
        None
    }
}

fn find_python(root: &Path) -> Option<PathBuf> {
    let embedded = root.join("runtime").join("python").join(if cfg!(windows) {
        "python.exe"
    } else {
        "python"
    });
    if embedded.is_file() {
        return Some(embedded);
    }
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

fn read_launch_manifest_summary(root: &Path, app_id: &str) -> LaunchManifestSummary {
    let app_yaml = root.join("apps").join(app_id).join("app.yaml");
    let mut summary = LaunchManifestSummary {
        app_yaml: app_yaml.clone(),
        runner: "-".to_string(),
        entry: "-".to_string(),
        mode: "-".to_string(),
    };

    let Ok(text) = std::fs::read_to_string(&app_yaml) else {
        return summary;
    };
    let Ok(raw) = serde_yaml::from_str::<RawLaunchManifest>(&text) else {
        return summary;
    };
    if let Some(run) = raw.run {
        summary.runner = non_empty_or_dash(run.runner);
        summary.entry = non_empty_or_dash(run.entry);
        summary.mode = non_empty_or_dash(run.mode);
    }
    summary
}

fn non_empty_or_dash(value: Option<String>) -> String {
    let value = value.unwrap_or_default();
    if value.trim().is_empty() {
        "-".to_string()
    } else {
        value
    }
}

fn read_launch_result(path: &Path) -> Result<LaunchResult, Box<dyn Error>> {
    let text = std::fs::read_to_string(path)?;
    let result: LaunchResult = serde_json::from_str(&text)?;
    Ok(result)
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

fn launcher_log_path() -> String {
    crate::setup::user_data_root()
        .join("data")
        .join("logs")
        .join("launcher")
        .join("tauri_backend.log")
        .display()
        .to_string()
}

fn timeout_failure(app_id: &str, timeout: Duration, log_path: String) -> LaunchResult {
    let message = format!(
        "起動処理が{}秒以内に完了しませんでした。アプリ定義または登録先が古い可能性があります。ToolHubのログを確認してください。",
        timeout.as_secs()
    );
    LaunchResult {
        ok: false,
        app_id: app_id.to_string(),
        user_message: message.clone(),
        log_path: Some(log_path),
        events: vec![LaunchEvent {
            event_type: None,
            kind: "error".to_string(),
            message,
            progress: Some(100),
        }],
    }
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

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn reads_launch_manifest_summary() {
        let root = std::env::temp_dir().join(format!(
            "toolhub_runner_manifest_{}",
            chrono::Local::now()
                .timestamp_nanos_opt()
                .unwrap_or_default()
        ));
        let app_dir = root.join("apps").join("sample_app");
        std::fs::create_dir_all(&app_dir).unwrap();
        std::fs::write(
            app_dir.join("app.yaml"),
            "id: sample_app\nrun:\n  runner: exe\n  entry: bin/sample.exe\n  mode: gui\n",
        )
        .unwrap();

        let summary = read_launch_manifest_summary(&root, "sample_app");

        assert_eq!(summary.runner, "exe");
        assert_eq!(summary.entry, "bin/sample.exe");
        assert_eq!(summary.mode, "gui");
        let _ = std::fs::remove_dir_all(root);
    }

    #[test]
    fn runner_command_times_out() {
        let mut command = if cfg!(windows) {
            let mut command = Command::new("cmd");
            command.args(["/C", "ping -n 3 127.0.0.1 > NUL"]);
            command
        } else {
            let mut command = Command::new("sh");
            command.args(["-c", "sleep 5"]);
            command
        };

        let outcome =
            run_runner_command_with_timeout(&mut command, Duration::from_millis(100)).unwrap();

        assert!(matches!(outcome, RunnerCommandOutcome::TimedOut { .. }));
    }

    #[test]
    fn timeout_is_limited_to_dev_build_artifact_root() {
        assert_eq!(
            runner_result_timeout("dev_build_artifact"),
            Some(RUNNER_RESULT_TIMEOUT)
        );
        assert_eq!(runner_result_timeout("dev_source"), None);
        assert_eq!(runner_result_timeout("installed_resource"), None);
        assert_eq!(runner_result_timeout("user_data"), None);
    }
}
