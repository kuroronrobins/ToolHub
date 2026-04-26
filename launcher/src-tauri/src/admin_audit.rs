use chrono::Local;
use std::io::Write;

pub fn append_admin_event(event: &str) {
    append_admin_event_with_attrs(event, &[]);
}

pub fn append_admin_event_with_attrs(event: &str, attrs: &[(&str, String)]) {
    let log_dir = crate::setup::user_data_root()
        .join("data")
        .join("logs")
        .join("admin");
    if std::fs::create_dir_all(&log_dir).is_err() {
        return;
    }

    let path = log_dir.join("admin.log");
    if let Ok(mut file) = std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(path)
    {
        let mut line = format!("{} {}", Local::now().to_rfc3339(), event);
        for (key, value) in attrs {
            if !key.trim().is_empty() && !value.trim().is_empty() {
                line.push(' ');
                line.push_str(key);
                line.push('=');
                line.push_str(value);
            }
        }
        let _ = writeln!(file, "{line}");
    }
}
