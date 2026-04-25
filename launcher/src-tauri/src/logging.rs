use chrono::Local;
use std::io::Write;
use std::path::Path;

pub fn append_launcher_log(_root: &Path, message: &str) {
    let log_dir = crate::setup::user_data_root()
        .join("data")
        .join("logs")
        .join("launcher");
    if std::fs::create_dir_all(&log_dir).is_err() {
        return;
    }

    let path = log_dir.join("tauri_backend.log");
    if let Ok(mut file) = std::fs::OpenOptions::new().create(true).append(true).open(path) {
        let _ = writeln!(file, "{} {}", Local::now().format("%Y-%m-%d %H:%M:%S"), message);
    }
}

