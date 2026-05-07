use crate::manifest::{collect_categories, load_apps};
use crate::runner::{launch_runner, LaunchResult};
use serde::Serialize;
use serde_json::Value;
use std::fs;
use std::path::{Path, PathBuf};

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct UpdateItem {
    pub label: String,
    pub current_version: String,
    pub next_version: String,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct UpdateSummary {
    pub title: String,
    pub message: String,
    pub status: String,
    pub current_version: String,
    pub local_manifest_version: Option<String>,
    pub update_source_configured: bool,
    pub update_source_url: Option<String>,
    pub config_source: String,
    pub config_path: Option<String>,
    pub local_manifest_path: String,
    pub app_manifest_path: String,
    pub core: Option<UpdateItem>,
    pub runner: Option<UpdateItem>,
    pub apps: Vec<UpdateItem>,
    pub runtime_update: bool,
    pub notes: Vec<String>,
    pub unsupported_actions: Vec<String>,
}

#[derive(Debug)]
struct UpdateConfigLookup {
    source_url: Option<String>,
    config_source: String,
    config_path: Option<PathBuf>,
    notes: Vec<String>,
}

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
    let user_data_root = crate::setup::user_data_root();
    let base = match app_id {
        Some(id) => user_data_root.join("data").join("logs").join(id),
        None => user_data_root.join("data").join("logs").join("launcher"),
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

#[tauri::command]
pub fn check_updates_mvp() -> Result<UpdateSummary, String> {
    let root = crate::manifest::project_root().map_err(|error| error.to_string())?;
    let local_manifest_path = root.join("release").join("manifest.json");
    let app_manifest_path = root.join("release").join("app_manifest.json");
    let mut notes = vec![
        "これは読み取り専用の更新確認MVPです。".to_string(),
        "ダウンロード、展開、置換、バックアップ、ロールバック、署名検証は未実装です。".to_string(),
    ];
    let manifest = read_json_file(&local_manifest_path, "release manifest", &mut notes);
    let app_manifest = read_json_file(&app_manifest_path, "app manifest", &mut notes);
    let current_version = env!("CARGO_PKG_VERSION").to_string();
    let local_manifest_version = manifest
        .as_ref()
        .and_then(|value| json_string(value, &["toolhub", "version"]))
        .or_else(|| {
            manifest
                .as_ref()
                .and_then(|value| json_string(value, &["core", "version"]))
        });
    let config_lookup = read_update_config(&root);
    notes.extend(config_lookup.notes);
    let update_source_url = config_lookup.source_url;
    let update_source_configured = update_source_url.is_some();
    if !update_source_configured {
        notes.push(
            "更新元URLが未設定のため、ローカルのrelease manifestのみ確認しました。".to_string(),
        );
    }

    let core = local_manifest_version
        .as_ref()
        .filter(|version| version_is_newer(version, &current_version))
        .map(|version| UpdateItem {
            label: "ToolHub".to_string(),
            current_version: current_version.clone(),
            next_version: version.clone(),
        });
    let runner = manifest
        .as_ref()
        .and_then(|value| json_string(value, &["runner", "version"]))
        .filter(|version| version_is_newer(version, &current_version))
        .map(|version| UpdateItem {
            label: "Python App Runner".to_string(),
            current_version: current_version.clone(),
            next_version: version,
        });
    let apps = update_app_items(&root, app_manifest.as_ref());
    let runtime_update = manifest_has_runtime_update(manifest.as_ref());
    let has_updates = core.is_some() || runner.is_some() || !apps.is_empty() || runtime_update;
    let status = if !update_source_configured {
        "source_not_configured"
    } else if has_updates {
        "update_available"
    } else {
        "no_update"
    };
    let title = match status {
        "update_available" => "更新候補があります",
        "no_update" => "更新は見つかりませんでした",
        _ => "更新元未設定",
    }
    .to_string();
    let message = match status {
        "update_available" => "更新候補があります。ただし現在は確認のみで、適用は管理者機能です。",
        "no_update" => "設定済み更新元とローカルmanifestの比較準備はできています。現在は読み取り専用確認までです。",
        _ => "ローカルmanifestを確認しましたが、更新元URLが未設定です。ダウンロードと適用は未実装です。",
    }
    .to_string();

    Ok(UpdateSummary {
        title,
        message,
        status: status.to_string(),
        current_version,
        local_manifest_version,
        update_source_configured,
        update_source_url,
        config_source: config_lookup.config_source,
        config_path: config_lookup
            .config_path
            .as_ref()
            .map(|path| path.display().to_string()),
        local_manifest_path: local_manifest_path.display().to_string(),
        app_manifest_path: app_manifest_path.display().to_string(),
        core,
        runner,
        apps,
        runtime_update,
        notes,
        unsupported_actions: vec![
            "download".to_string(),
            "extract".to_string(),
            "replace".to_string(),
            "backup".to_string(),
            "rollback".to_string(),
            "signature_verification".to_string(),
        ],
    })
}

fn read_json_file(path: &Path, label: &str, notes: &mut Vec<String>) -> Option<Value> {
    let text = match fs::read_to_string(path) {
        Ok(text) => text,
        Err(error) => {
            notes.push(format!(
                "{label}を読み取れませんでした: {} ({error})",
                path.display()
            ));
            return None;
        }
    };
    match serde_json::from_str(&text) {
        Ok(value) => Some(value),
        Err(error) => {
            notes.push(format!(
                "{label}をJSONとして解析できませんでした: {} ({error})",
                path.display()
            ));
            None
        }
    }
}

fn read_update_config(root: &Path) -> UpdateConfigLookup {
    let user_config_path = crate::setup::user_data_root()
        .join("config")
        .join("launcher.yaml");
    if user_config_path.is_file() {
        match read_update_source_url(&user_config_path) {
            Ok(source_url) => {
                let mut notes = Vec::new();
                if source_url.is_none() {
                    notes.push("ユーザー設定に更新元URLが設定されていません。".to_string());
                }
                return UpdateConfigLookup {
                    source_url,
                    config_source: "user".to_string(),
                    config_path: Some(user_config_path),
                    notes,
                };
            }
            Err(error) => {
                let default_lookup = read_default_update_config(root);
                let mut notes = vec![format!(
                    "ユーザー設定を読み取れなかったためdefault設定を参照しました: {} ({error})",
                    user_config_path.display()
                )];
                notes.extend(default_lookup.notes);
                return UpdateConfigLookup {
                    notes,
                    ..default_lookup
                };
            }
        }
    }

    let mut default_lookup = read_default_update_config(root);
    default_lookup.notes.insert(
        0,
        format!(
            "ユーザー設定ファイルがないためdefault設定を参照しました: {}",
            user_config_path.display()
        ),
    );
    default_lookup
}

fn read_default_update_config(root: &Path) -> UpdateConfigLookup {
    let default_config_path = root.join("config.default").join("launcher.yaml");
    if default_config_path.is_file() {
        match read_update_source_url(&default_config_path) {
            Ok(source_url) => {
                let mut notes = Vec::new();
                if source_url.is_none() {
                    notes.push("default設定に更新元URLが設定されていません。".to_string());
                }
                return UpdateConfigLookup {
                    source_url,
                    config_source: "default".to_string(),
                    config_path: Some(default_config_path),
                    notes,
                };
            }
            Err(error) => {
                return UpdateConfigLookup {
                    source_url: None,
                    config_source: "missing".to_string(),
                    config_path: Some(default_config_path.clone()),
                    notes: vec![format!(
                        "default設定を読み取れませんでした: {} ({error})",
                        default_config_path.display()
                    )],
                };
            }
        }
    }

    UpdateConfigLookup {
        source_url: None,
        config_source: "missing".to_string(),
        config_path: None,
        notes: vec![format!(
            "default設定ファイルが見つかりません: {}",
            default_config_path.display()
        )],
    }
}

fn read_update_source_url(path: &Path) -> Result<Option<String>, String> {
    let text = fs::read_to_string(path).map_err(|error| error.to_string())?;
    let value: serde_yaml::Value =
        serde_yaml::from_str(&text).map_err(|error| error.to_string())?;
    for key in ["source_url", "manifest_url", "url"] {
        if let Some(value) = yaml_string(&value, &["updates", key]) {
            if !value.trim().is_empty() {
                return Ok(Some(value));
            }
        }
    }
    Ok(None)
}

fn yaml_string(value: &serde_yaml::Value, path: &[&str]) -> Option<String> {
    let mut current = value;
    for key in path {
        let serde_yaml::Value::Mapping(map) = current else {
            return None;
        };
        current = map.get(&serde_yaml::Value::String((*key).to_string()))?;
    }
    current
        .as_str()
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(str::to_string)
}

fn json_string(value: &Value, path: &[&str]) -> Option<String> {
    let mut current = value;
    for key in path {
        current = current.get(*key)?;
    }
    current
        .as_str()
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(str::to_string)
}

fn update_app_items(root: &Path, app_manifest: Option<&Value>) -> Vec<UpdateItem> {
    let mut items = Vec::new();
    let Ok(apps) = load_apps(root) else {
        return items;
    };
    let Some(app_entries) = app_manifest
        .and_then(|value| value.get("apps"))
        .and_then(Value::as_object)
    else {
        return items;
    };
    for app in apps {
        let Some(manifest_entry) = app_entries.get(&app.id) else {
            continue;
        };
        let Some(next_version) = manifest_entry.get("version").and_then(Value::as_str) else {
            continue;
        };
        let current_version = app
            .admin
            .as_ref()
            .and_then(|admin| admin.version.clone())
            .unwrap_or_else(|| "0.0.0".to_string());
        if version_is_newer(next_version, &current_version) {
            items.push(UpdateItem {
                label: app.name,
                current_version,
                next_version: next_version.to_string(),
            });
        }
    }
    items
}

fn manifest_has_runtime_update(manifest: Option<&Value>) -> bool {
    let Some(manifest) = manifest else {
        return false;
    };
    for path in [
        ["runtime", "python", "version"],
        ["runtime", "web_automation_runtime", "version"],
    ] {
        if let Some(version) = json_string(manifest, &path) {
            if !version.is_empty() {
                return true;
            }
        }
    }
    false
}

fn version_is_newer(next: &str, current: &str) -> bool {
    let next_parts = parse_version(next);
    let current_parts = parse_version(current);
    next_parts > current_parts
}

fn parse_version(value: &str) -> Vec<u64> {
    value
        .split(|character: char| !character.is_ascii_digit())
        .filter(|part| !part.is_empty())
        .map(|part| part.parse::<u64>().unwrap_or(0))
        .collect()
}
