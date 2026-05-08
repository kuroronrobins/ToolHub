use crate::manifest::{collect_categories, load_apps};
use crate::runner::{launch_runner, LaunchResult};
use chrono::Utc;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;

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
    pub remote_manifest_version: Option<String>,
    pub remote_manifest_url: Option<String>,
    pub installer_file: Option<String>,
    pub installer_url: Option<String>,
    pub installer_sha256: Option<String>,
    pub installer_size: Option<u64>,
    pub update_cache_path: Option<String>,
    pub last_update_result: Option<Value>,
    pub core: Option<UpdateItem>,
    pub runner: Option<UpdateItem>,
    pub apps: Vec<UpdateItem>,
    pub runtime_update: bool,
    pub notes: Vec<String>,
    pub unsupported_actions: Vec<String>,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct UpdateDownloadRequest {
    pub manifest_url: Option<String>,
    pub installer_url: String,
    pub installer_file: Option<String>,
    pub expected_sha256: String,
    pub expected_size: Option<u64>,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct UpdateDownloadResult {
    pub ok: bool,
    pub status: String,
    pub message: String,
    pub checked_at: String,
    pub manifest_url: Option<String>,
    pub installer_url: String,
    pub cache_path: Option<String>,
    pub expected_sha256: String,
    pub actual_sha256: Option<String>,
    pub expected_size: Option<u64>,
    pub actual_size: Option<u64>,
    pub verified: bool,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct UpdateLaunchRequest {
    pub cache_path: String,
    pub expected_sha256: String,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct UpdateLaunchResult {
    pub ok: bool,
    pub status: String,
    pub message: String,
    pub checked_at: String,
    pub cache_path: String,
    pub actual_sha256: Option<String>,
    pub verified: bool,
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
        update_source_url: update_source_url.clone(),
        config_source: config_lookup.config_source,
        config_path: config_lookup
            .config_path
            .as_ref()
            .map(|path| path.display().to_string()),
        local_manifest_path: local_manifest_path.display().to_string(),
        app_manifest_path: app_manifest_path.display().to_string(),
        remote_manifest_version: None,
        remote_manifest_url: update_source_url.clone(),
        installer_file: None,
        installer_url: None,
        installer_sha256: None,
        installer_size: None,
        update_cache_path: Some(update_cache_dir().display().to_string()),
        last_update_result: read_last_update_result(),
        core,
        runner,
        apps,
        runtime_update,
        notes,
        unsupported_actions: vec![
            "extract".to_string(),
            "replace".to_string(),
            "backup".to_string(),
            "rollback".to_string(),
            "signature_verification".to_string(),
        ],
    })
}

#[tauri::command]
pub fn check_updates_remote() -> Result<UpdateSummary, String> {
    let root = crate::manifest::project_root().map_err(|error| error.to_string())?;
    let local_manifest_path = root.join("release").join("manifest.json");
    let app_manifest_path = root.join("release").join("app_manifest.json");
    let mut notes = vec!["Remote manifest update check is enabled.".to_string()];
    let local_manifest = read_json_file(&local_manifest_path, "release manifest", &mut notes);
    let _app_manifest = read_json_file(&app_manifest_path, "app manifest", &mut notes);
    let current_version = env!("CARGO_PKG_VERSION").to_string();
    let local_manifest_version = local_manifest
        .as_ref()
        .and_then(|value| json_string(value, &["toolhub", "version"]))
        .or_else(|| {
            local_manifest
                .as_ref()
                .and_then(|value| json_string(value, &["core", "version"]))
        });
    let config_lookup = read_update_config(&root);
    notes.extend(config_lookup.notes);
    let update_source_url = config_lookup.source_url.clone();
    let update_source_configured = update_source_url.is_some();
    let update_cache_path = update_cache_dir();
    let last_update_result = read_last_update_result();

    let Some(remote_manifest_url) = update_source_url.clone() else {
        return Ok(UpdateSummary {
            title: "Update source is not configured".to_string(),
            message: "Set updates.manifest_url, updates.source_url, or updates.url before checking a remote manifest.".to_string(),
            status: "source_not_configured".to_string(),
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
            remote_manifest_version: None,
            remote_manifest_url: None,
            installer_file: None,
            installer_url: None,
            installer_sha256: None,
            installer_size: None,
            update_cache_path: Some(update_cache_path.display().to_string()),
            last_update_result,
            core: None,
            runner: None,
            apps: Vec::new(),
            runtime_update: false,
            notes,
            unsupported_actions: update_unsupported_actions(),
        });
    };

    let remote_manifest = match fetch_manifest_json(&root, &remote_manifest_url) {
        Ok(value) => value,
        Err(error) => {
            let status = "remote_manifest_fetch_failed".to_string();
            let message = format!("Remote manifest could not be fetched: {error}");
            let result = json!({
                "operation": "check",
                "status": status,
                "ok": false,
                "checkedAt": Utc::now().to_rfc3339(),
                "manifestUrl": remote_manifest_url.clone(),
                "message": message,
            });
            let _ = write_update_result_log("check", &result);
            notes.push(message.clone());
            return Ok(UpdateSummary {
                title: "Remote update check failed".to_string(),
                message,
                status,
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
                remote_manifest_version: None,
                remote_manifest_url: Some(remote_manifest_url),
                installer_file: None,
                installer_url: None,
                installer_sha256: None,
                installer_size: None,
                update_cache_path: Some(update_cache_path.display().to_string()),
                last_update_result: read_last_update_result(),
                core: None,
                runner: None,
                apps: Vec::new(),
                runtime_update: false,
                notes,
                unsupported_actions: update_unsupported_actions(),
            });
        }
    };

    let remote_manifest_version = json_string(&remote_manifest, &["toolhub", "version"])
        .or_else(|| json_string(&remote_manifest, &["core", "version"]));
    let core = remote_manifest_version
        .as_ref()
        .filter(|version| version_is_newer(version, &current_version))
        .map(|version| UpdateItem {
            label: "ToolHub".to_string(),
            current_version: current_version.clone(),
            next_version: version.clone(),
        });
    let runner = remote_manifest
        .get("runner")
        .and_then(|_| json_string(&remote_manifest, &["runner", "version"]))
        .filter(|version| {
            local_manifest
                .as_ref()
                .and_then(|value| json_string(value, &["runner", "version"]))
                .map(|current| version_is_newer(version, &current))
                .unwrap_or_else(|| version_is_newer(version, &current_version))
        })
        .map(|version| UpdateItem {
            label: "Python App Runner".to_string(),
            current_version: local_manifest
                .as_ref()
                .and_then(|value| json_string(value, &["runner", "version"]))
                .unwrap_or_else(|| current_version.clone()),
            next_version: version,
        });
    let apps = Vec::new();
    notes.push(
        "App Pack unit updates are outside the Beta installer redistribution MVP.".to_string(),
    );
    let runtime_update = manifest_has_newer_runtime(&remote_manifest, local_manifest.as_ref());
    let installer_file = json_string(&remote_manifest, &["toolhub", "installer", "file"]);
    let installer_url_raw = json_string(&remote_manifest, &["toolhub", "installer", "url"]);
    let installer_url = resolve_installer_url(
        &root,
        &remote_manifest_url,
        installer_url_raw.as_deref(),
        installer_file.as_deref(),
    );
    let installer_sha256 = json_string(&remote_manifest, &["toolhub", "installer", "sha256"]);
    let installer_size = json_u64(&remote_manifest, &["toolhub", "installer", "size"]);

    if installer_url.is_none() {
        notes.push(
            "Remote manifest does not define toolhub.installer.url or toolhub.installer.file."
                .to_string(),
        );
    }
    if installer_sha256.is_none() {
        notes.push("Remote manifest does not define toolhub.installer.sha256. Installer launch will stay disabled.".to_string());
    }

    let has_updates = core.is_some() || runner.is_some() || !apps.is_empty() || runtime_update;
    let status = if has_updates {
        "update_available"
    } else {
        "no_update"
    };
    let title = if has_updates {
        "Update available"
    } else {
        "No update found"
    };
    let message = if has_updates {
        "A remote manifest was fetched. Download the latest installer and verify sha256 before launching it."
    } else {
        "The remote manifest was fetched, but no newer ToolHub version was found."
    };
    let result = json!({
        "operation": "check",
        "status": status,
        "ok": true,
        "checkedAt": Utc::now().to_rfc3339(),
        "manifestUrl": remote_manifest_url.clone(),
        "remoteManifestVersion": remote_manifest_version.clone(),
        "installerUrl": installer_url.clone(),
        "installerSha256Present": installer_sha256.is_some(),
    });
    let _ = write_update_result_log("check", &result);

    Ok(UpdateSummary {
        title: title.to_string(),
        message: message.to_string(),
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
        remote_manifest_version,
        remote_manifest_url: Some(remote_manifest_url),
        installer_file,
        installer_url,
        installer_sha256,
        installer_size,
        update_cache_path: Some(update_cache_path.display().to_string()),
        last_update_result: read_last_update_result(),
        core,
        runner,
        apps,
        runtime_update,
        notes,
        unsupported_actions: update_unsupported_actions(),
    })
}

#[tauri::command]
pub fn download_update_installer(
    request: UpdateDownloadRequest,
) -> Result<UpdateDownloadResult, String> {
    let checked_at = Utc::now().to_rfc3339();
    let expected_sha256 = request.expected_sha256.trim().to_ascii_lowercase();
    let mut result = UpdateDownloadResult {
        ok: false,
        status: "not_started".to_string(),
        message: String::new(),
        checked_at,
        manifest_url: request.manifest_url.clone(),
        installer_url: request.installer_url.clone(),
        cache_path: None,
        expected_sha256: expected_sha256.clone(),
        actual_sha256: None,
        expected_size: request.expected_size,
        actual_size: None,
        verified: false,
    };

    if expected_sha256.is_empty() {
        result.status = "sha256_missing".to_string();
        result.message = "Remote manifest does not provide installer sha256.".to_string();
        let _ = write_update_result_log("download", &result);
        return Ok(result);
    }

    let cache_dir = update_cache_dir();
    fs::create_dir_all(&cache_dir).map_err(|error| error.to_string())?;
    let installer_name = safe_installer_file_name(
        request.installer_file.as_deref(),
        Some(request.installer_url.as_str()),
    );
    let cache_path = cache_dir.join(installer_name);
    result.cache_path = Some(cache_path.display().to_string());

    if let Err(error) = fetch_source_to_file(
        &crate::manifest::project_root().map_err(|error| error.to_string())?,
        &request.installer_url,
        &cache_path,
    ) {
        result.status = "download_failed".to_string();
        result.message = format!("Installer download failed: {error}");
        let _ = write_update_result_log("download", &result);
        return Ok(result);
    }

    let metadata = match fs::metadata(&cache_path) {
        Ok(metadata) => metadata,
        Err(error) => {
            result.status = "metadata_failed".to_string();
            result.message = format!("Downloaded installer metadata could not be read: {error}");
            let _ = write_update_result_log("download", &result);
            return Ok(result);
        }
    };
    result.actual_size = Some(metadata.len());
    if let Some(expected_size) = request.expected_size {
        if expected_size != metadata.len() {
            result.status = "size_mismatch".to_string();
            result.message = format!(
                "Downloaded installer size mismatch: expected {expected_size}, got {}.",
                metadata.len()
            );
            let _ = write_update_result_log("download", &result);
            return Ok(result);
        }
    }

    let actual_sha256 = match sha256_file(&cache_path) {
        Ok(hash) => hash,
        Err(error) => {
            result.status = "sha256_failed".to_string();
            result.message =
                format!("Downloaded installer sha256 could not be calculated: {error}");
            let _ = write_update_result_log("download", &result);
            return Ok(result);
        }
    };
    result.actual_sha256 = Some(actual_sha256.clone());
    if actual_sha256 != expected_sha256 {
        result.status = "sha256_mismatch".to_string();
        result.message =
            "Downloaded installer sha256 does not match the remote manifest.".to_string();
        let _ = write_update_result_log("download", &result);
        return Ok(result);
    }

    result.ok = true;
    result.verified = true;
    result.status = "verified".to_string();
    result.message = "Installer downloaded and sha256 verified.".to_string();
    let _ = write_update_result_log("download", &result);
    Ok(result)
}

#[tauri::command]
pub fn launch_verified_update_installer(
    request: UpdateLaunchRequest,
) -> Result<UpdateLaunchResult, String> {
    let checked_at = Utc::now().to_rfc3339();
    let expected_sha256 = request.expected_sha256.trim().to_ascii_lowercase();
    let mut result = UpdateLaunchResult {
        ok: false,
        status: "not_started".to_string(),
        message: String::new(),
        checked_at,
        cache_path: request.cache_path.clone(),
        actual_sha256: None,
        verified: false,
    };

    if expected_sha256.is_empty() {
        result.status = "sha256_missing".to_string();
        result.message = "Expected sha256 is required before launching an installer.".to_string();
        let _ = write_update_result_log("launch", &result);
        return Ok(result);
    }

    let cache_path = PathBuf::from(&request.cache_path);
    if !cache_path.is_file() {
        result.status = "installer_missing".to_string();
        result.message = "Verified installer file is missing from update_cache.".to_string();
        let _ = write_update_result_log("launch", &result);
        return Ok(result);
    }

    let actual_sha256 = match sha256_file(&cache_path) {
        Ok(hash) => hash,
        Err(error) => {
            result.status = "sha256_failed".to_string();
            result.message = format!("Installer sha256 could not be calculated: {error}");
            let _ = write_update_result_log("launch", &result);
            return Ok(result);
        }
    };
    result.actual_sha256 = Some(actual_sha256.clone());
    if actual_sha256 != expected_sha256 {
        result.status = "sha256_mismatch".to_string();
        result.message = "Installer sha256 no longer matches the remote manifest.".to_string();
        let _ = write_update_result_log("launch", &result);
        return Ok(result);
    }

    match Command::new(&cache_path).spawn() {
        Ok(_) => {
            result.ok = true;
            result.verified = true;
            result.status = "launched".to_string();
            result.message =
                "Verified installer was launched. Close ToolHub if the installer asks for it."
                    .to_string();
        }
        Err(error) => {
            result.status = "launch_failed".to_string();
            result.message = format!("Verified installer could not be launched: {error}");
        }
    }
    let _ = write_update_result_log("launch", &result);
    Ok(result)
}

#[tauri::command]
pub fn get_update_result_log() -> Result<Option<Value>, String> {
    Ok(read_last_update_result())
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
    for key in ["manifest_url", "source_url", "url"] {
        if let Some(value) = yaml_string(&value, &["updates", key]) {
            if !value.trim().is_empty() {
                return Ok(Some(value));
            }
        }
    }
    Ok(None)
}

fn fetch_manifest_json(root: &Path, source: &str) -> Result<Value, String> {
    let cache_path = update_cache_dir().join("remote_manifest.json");
    fetch_source_to_file(root, source, &cache_path)?;
    let text = fs::read_to_string(&cache_path).map_err(|error| error.to_string())?;
    serde_json::from_str(&text).map_err(|error| error.to_string())
}

fn fetch_source_to_file(root: &Path, source: &str, destination: &Path) -> Result<(), String> {
    if let Some(parent) = destination.parent() {
        fs::create_dir_all(parent).map_err(|error| error.to_string())?;
    }

    if is_http_url(source) {
        let script = "$ProgressPreference='SilentlyContinue'; Invoke-WebRequest -UseBasicParsing -TimeoutSec 30 -Uri $args[0] -OutFile $args[1]";
        let status = Command::new("powershell")
            .args([
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                script,
            ])
            .arg(source)
            .arg(destination)
            .status()
            .map_err(|error| error.to_string())?;
        if status.success() {
            return Ok(());
        }
        return Err(format!("Invoke-WebRequest exited with status {status}"));
    }

    let source_path = source_to_local_path(root, source);
    fs::copy(&source_path, destination)
        .map(|_| ())
        .map_err(|error| format!("{} ({error})", source_path.display()))
}

fn is_http_url(source: &str) -> bool {
    source.starts_with("https://") || source.starts_with("http://")
}

fn is_file_url(source: &str) -> bool {
    source.starts_with("file://")
}

fn source_to_local_path(root: &Path, source: &str) -> PathBuf {
    if is_file_url(source) {
        let mut path = source.trim_start_matches("file://").replace("%20", " ");
        if cfg!(windows) && path.starts_with('/') && path.chars().nth(2) == Some(':') {
            path = path.trim_start_matches('/').to_string();
        }
        return PathBuf::from(path.replace('/', std::path::MAIN_SEPARATOR_STR));
    }

    let path = PathBuf::from(source);
    if path.is_absolute() {
        path
    } else {
        root.join(path)
    }
}

fn resolve_installer_url(
    root: &Path,
    manifest_url: &str,
    installer_url: Option<&str>,
    installer_file: Option<&str>,
) -> Option<String> {
    if let Some(url) = installer_url
        .map(str::trim)
        .filter(|value| !value.is_empty())
    {
        return Some(url.to_string());
    }
    let file = installer_file
        .map(str::trim)
        .filter(|value| !value.is_empty())?;
    if is_http_url(file) || is_file_url(file) || Path::new(file).is_absolute() {
        return Some(file.to_string());
    }
    if is_http_url(manifest_url) {
        let base = manifest_url.rsplit_once('/').map(|(base, _)| base)?;
        return Some(format!("{}/{}", base, file.replace('\\', "/")));
    }

    let manifest_path = source_to_local_path(root, manifest_url);
    let parent = manifest_path.parent().unwrap_or(root);
    Some(parent.join(file).display().to_string())
}

fn safe_installer_file_name(installer_file: Option<&str>, installer_url: Option<&str>) -> String {
    for candidate in [installer_file, installer_url] {
        if let Some(value) = candidate {
            let normalized = value.trim_end_matches('/').trim_end_matches('\\');
            if let Some(name) = Path::new(normalized)
                .file_name()
                .and_then(|name| name.to_str())
            {
                if !name.trim().is_empty() {
                    return name.to_string();
                }
            }
        }
    }
    "ToolHub_Setup.exe".to_string()
}

fn update_cache_dir() -> PathBuf {
    crate::setup::user_data_root().join("update_cache")
}

fn update_result_log_dir() -> PathBuf {
    crate::setup::user_data_root()
        .join("data")
        .join("logs")
        .join("updater")
}

fn update_result_latest_path() -> PathBuf {
    update_result_log_dir().join("latest_update_result.json")
}

fn write_update_result_log<T: Serialize>(operation: &str, result: &T) -> Result<(), String> {
    let log_dir = update_result_log_dir();
    fs::create_dir_all(&log_dir).map_err(|error| error.to_string())?;
    let value = serde_json::to_value(result).map_err(|error| error.to_string())?;
    let payload = json!({
        "operation": operation,
        "recordedAt": Utc::now().to_rfc3339(),
        "result": value,
    });
    let text = serde_json::to_string_pretty(&payload).map_err(|error| error.to_string())?;
    fs::write(update_result_latest_path(), &text).map_err(|error| error.to_string())?;
    let timestamp = Utc::now().format("%Y%m%d_%H%M%S").to_string();
    fs::write(log_dir.join(format!("{timestamp}_{operation}.json")), text)
        .map_err(|error| error.to_string())?;
    Ok(())
}

fn read_last_update_result() -> Option<Value> {
    let text = fs::read_to_string(update_result_latest_path()).ok()?;
    serde_json::from_str(&text).ok()
}

fn sha256_file(path: &Path) -> Result<String, String> {
    let bytes = fs::read(path).map_err(|error| error.to_string())?;
    let mut hasher = Sha256::new();
    hasher.update(bytes);
    Ok(format!("{:x}", hasher.finalize()))
}

fn json_u64(value: &Value, path: &[&str]) -> Option<u64> {
    let mut current = value;
    for key in path {
        current = current.get(*key)?;
    }
    current
        .as_u64()
        .or_else(|| current.as_str()?.trim().parse::<u64>().ok())
}

fn update_unsupported_actions() -> Vec<String> {
    vec![
        "extract".to_string(),
        "replace".to_string(),
        "backup".to_string(),
        "rollback".to_string(),
        "signature_verification".to_string(),
    ]
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

fn manifest_has_newer_runtime(remote_manifest: &Value, local_manifest: Option<&Value>) -> bool {
    for path in [
        ["runtime", "python", "version"],
        ["runtime", "web_automation_runtime", "version"],
    ] {
        let Some(remote_version) = json_string(remote_manifest, &path) else {
            continue;
        };
        let Some(local_version) = local_manifest.and_then(|manifest| json_string(manifest, &path))
        else {
            return true;
        };
        if version_is_newer(&remote_version, &local_version) {
            return true;
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
