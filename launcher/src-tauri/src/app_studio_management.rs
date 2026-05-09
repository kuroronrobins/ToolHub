use crate::app_studio_delete_plan::build_delete_plan;
use crate::app_studio_preflight::validate_app_id;
use crate::app_studio_process::append_app_studio_gui_log;
use crate::app_studio_types::{
    AppStudioManagedApp, AppStudioManagementActionResult, AppStudioRegisteredApp,
};
use serde::Serialize;
use serde_json::{Map, Value};
use std::collections::BTreeSet;
use std::fs;
use std::path::{Path, PathBuf};

pub(crate) fn list_registered_apps_from_root(root: &Path) -> Vec<AppStudioRegisteredApp> {
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

pub(crate) fn find_registered_app(root: &Path, app_id: &str) -> Option<AppStudioRegisteredApp> {
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

pub(crate) fn list_managed_apps_from_root(root: &Path) -> Vec<AppStudioManagedApp> {
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

pub(crate) fn management_set_enabled(
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

fn read_json(path: &Path) -> Option<Value> {
    let text = std::fs::read_to_string(path).ok()?;
    serde_json::from_str(&text).ok()
}
