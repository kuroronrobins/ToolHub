use crate::manifest;
use std::env;
use std::fs;
use std::io;
use std::path::PathBuf;

pub fn ensure_user_data() -> io::Result<()> {
    let base = user_data_root();
    let directories = [
        "config",
        "data/logs",
        "data/browser_profiles",
        "data/search_index",
        "data/app_state",
        "backups",
        "update_cache",
    ];

    for directory in directories {
        fs::create_dir_all(base.join(directory))?;
    }

    copy_default_config_if_missing(&base)?;
    Ok(())
}

pub fn user_data_root() -> PathBuf {
    if let Ok(local_app_data) = env::var("LOCALAPPDATA") {
        return PathBuf::from(local_app_data).join("ToolHub");
    }
    if let Ok(home) = env::var("HOME") {
        return PathBuf::from(home).join(".toolhub");
    }
    env::current_dir()
        .unwrap_or_else(|_| PathBuf::from("."))
        .join(".toolhub")
}

fn copy_default_config_if_missing(base: &std::path::Path) -> io::Result<()> {
    let target = base.join("config").join("launcher.yaml");
    if target.is_file() {
        return Ok(());
    }

    if let Some(source) = default_config_candidates()
        .into_iter()
        .find(|candidate| candidate.is_file())
    {
        if let Some(parent) = target.parent() {
            fs::create_dir_all(parent)?;
        }
        fs::copy(source, target)?;
    }
    Ok(())
}

fn default_config_candidates() -> Vec<PathBuf> {
    let mut candidates = Vec::new();

    if let Ok(exe) = env::current_exe() {
        if let Some(exe_dir) = exe.parent() {
            candidates.push(exe_dir.join("config.default").join("launcher.yaml"));
            candidates.push(
                exe_dir
                    .join("resources")
                    .join("config.default")
                    .join("launcher.yaml"),
            );
        }
    }

    if let Ok(current_dir) = env::current_dir() {
        candidates.push(current_dir.join("config.default").join("launcher.yaml"));
    }

    if let Ok(root) = manifest::project_root() {
        candidates.push(root.join("config.default").join("launcher.yaml"));
    }

    candidates
}
