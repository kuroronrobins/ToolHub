use crate::manifest::{collect_categories, load_apps};
use crate::runner::{launch_runner, LaunchResult};

#[tauri::command]
pub fn list_apps() -> Result<Vec<crate::manifest::AppInfo>, String> {
    let root = crate::manifest::project_root().map_err(|error| error.to_string())?;
    load_apps(&root).map_err(|error| error.to_string())
}

#[tauri::command]
pub fn get_categories() -> Result<Vec<String>, String> {
    let root = crate::manifest::project_root().map_err(|error| error.to_string())?;
    let apps = load_apps(&root).map_err(|error| error.to_string())?;
    Ok(collect_categories(&apps))
}

#[tauri::command]
pub fn launch_app(app_id: String) -> Result<LaunchResult, String> {
    let root = crate::manifest::project_root().map_err(|error| error.to_string())?;
    launch_runner(&root, &app_id).map_err(|error| error.to_string())
}

#[tauri::command]
pub fn get_recent_logs(app_id: Option<String>) -> Result<Vec<String>, String> {
    let root = crate::manifest::project_root().map_err(|error| error.to_string())?;
    let base = match app_id {
        Some(id) => root.join("data").join("logs").join(id),
        None => root.join("data").join("logs").join("launcher"),
    };

    if !base.is_dir() {
        return Ok(Vec::new());
    }

    let mut entries = std::fs::read_dir(base)
        .map_err(|error| error.to_string())?
        .filter_map(Result::ok)
        .filter_map(|entry| {
            let metadata = entry.metadata().ok()?;
            if !metadata.is_file() {
                return None;
            }
            let modified = metadata.modified().ok()?;
            Some((modified, entry.path().display().to_string()))
        })
        .collect::<Vec<_>>();

    entries.sort_by(|a, b| b.0.cmp(&a.0));
    Ok(entries.into_iter().take(10).map(|(_, path)| path).collect())
}

