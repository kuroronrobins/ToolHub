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

#[derive(Debug, Serialize, Clone)]
#[serde(rename_all = "camelCase")]
pub struct UpdateReleaseNotesUser {
    pub title: Option<String>,
    pub summary: Option<String>,
    pub highlights: Vec<String>,
    pub added_apps: Vec<String>,
    pub recommended: Option<bool>,
}

#[derive(Debug, Serialize, Clone)]
#[serde(rename_all = "camelCase")]
pub struct UpdateReleaseNotesAdmin {
    pub summary: Option<String>,
    pub changes: Vec<String>,
    pub validation: Vec<String>,
}

#[derive(Debug, Serialize, Clone)]
#[serde(rename_all = "camelCase")]
pub struct UpdateReleaseNotes {
    pub schema_version: Option<u64>,
    pub generated_by: Option<String>,
    pub edited_by_admin: Option<bool>,
    pub user: Option<UpdateReleaseNotesUser>,
    pub admin: Option<UpdateReleaseNotesAdmin>,
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
    pub release_notes: Option<UpdateReleaseNotes>,
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
    pub failure_reason: Option<String>,
    pub checked_at: String,
    pub manifest_url: Option<String>,
    pub installer_url: String,
    pub source_kind: String,
    pub local_test_source: bool,
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
    pub target_version: Option<String>,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct UpdateLaunchResult {
    pub ok: bool,
    pub status: String,
    pub message: String,
    pub failure_reason: Option<String>,
    pub checked_at: String,
    pub current_version: String,
    pub target_version: Option<String>,
    pub cache_path: String,
    pub source_kind: String,
    pub expected_sha256: String,
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
        current_version: current_version.clone(),
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
        release_notes: manifest.as_ref().and_then(parse_release_notes),
        update_cache_path: Some(update_cache_dir().display().to_string()),
        last_update_result: read_last_update_result_for_current_version(&current_version),
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
    let last_update_result = read_last_update_result_for_current_version(&current_version);

    let Some(remote_manifest_url) = update_source_url.clone() else {
        return Ok(UpdateSummary {
            title: "Update source is not configured".to_string(),
            message:
                "更新元が設定されていません。配布前に updates.manifest_url などを設定してください。"
                    .to_string(),
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
            release_notes: None,
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
            let message = format!("更新情報を取得できませんでした: {error}");
            let result = json!({
                "operation": "check",
                "status": status,
                "ok": false,
                "checkedAt": Utc::now().to_rfc3339(),
                "manifestUrl": sanitize_url_for_log(&remote_manifest_url),
                "manifestSourceKind": source_kind(&remote_manifest_url),
                "localTestSource": is_local_test_source(&remote_manifest_url),
                "message": message,
                "failureReason": error,
            });
            let _ = write_update_result_log("check", &result);
            notes.push(message.clone());
            return Ok(UpdateSummary {
                title: "更新情報を取得できませんでした".to_string(),
                message,
                status,
                current_version: current_version.clone(),
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
                release_notes: None,
                update_cache_path: Some(update_cache_path.display().to_string()),
                last_update_result: read_last_update_result_for_current_version(&current_version),
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
    let release_notes = parse_release_notes(&remote_manifest);
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
        "新しいToolHubがあります"
    } else {
        "ToolHubは最新です"
    };
    let message = if has_updates {
        "新しいインストーラーを取得できます。管理画面で取得し、検証後に起動してください。"
    } else {
        "配布元の更新情報を確認しましたが、新しいToolHubは見つかりませんでした。"
    };
    let result = json!({
        "operation": "check",
        "status": status,
        "ok": true,
        "checkedAt": Utc::now().to_rfc3339(),
        "manifestUrl": sanitize_url_for_log(&remote_manifest_url),
        "manifestSourceKind": source_kind(&remote_manifest_url),
        "localTestSource": is_local_test_source(&remote_manifest_url),
        "remoteManifestVersion": remote_manifest_version.clone(),
        "installerUrl": installer_url.as_deref().map(sanitize_url_for_log),
        "installerSourceKind": installer_url.as_deref().map(source_kind),
        "installerSha256Present": installer_sha256.is_some(),
    });
    let _ = write_update_result_log("check", &result);

    Ok(UpdateSummary {
        title: title.to_string(),
        message: message.to_string(),
        status: status.to_string(),
        current_version: current_version.clone(),
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
        release_notes,
        update_cache_path: Some(update_cache_path.display().to_string()),
        last_update_result: read_last_update_result_for_current_version(&current_version),
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
        failure_reason: None,
        checked_at,
        manifest_url: request.manifest_url.as_deref().map(sanitize_url_for_log),
        installer_url: sanitize_url_for_log(&request.installer_url),
        source_kind: source_kind(&request.installer_url).to_string(),
        local_test_source: is_local_test_source(&request.installer_url),
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
        result.failure_reason = Some("sha256_missing".to_string());
        let _ = write_update_result_log("download", &result);
        return Ok(result);
    }

    let cache_dir = update_cache_dir();
    fs::create_dir_all(&cache_dir).map_err(|error| error.to_string())?;
    let installer_name = match safe_installer_file_name(
        request.installer_file.as_deref(),
        Some(request.installer_url.as_str()),
    ) {
        Ok(name) => name,
        Err(error) => {
            result.status = "unsafe_installer_name".to_string();
            result.message = error.clone();
            result.failure_reason = Some(error);
            let _ = write_update_result_log("download", &result);
            return Ok(result);
        }
    };
    let cache_path = cache_dir.join(installer_name);
    result.cache_path = Some(cache_path.display().to_string());
    let temp_path = cache_path.with_extension(format!(
        "{}.download",
        cache_path
            .extension()
            .and_then(|extension| extension.to_str())
            .unwrap_or("tmp")
    ));
    let _ = fs::remove_file(&temp_path);

    if let Err(error) = fetch_source_to_file_with_timeout(
        &crate::manifest::project_root().map_err(|error| error.to_string())?,
        &request.installer_url,
        &temp_path,
        300,
    ) {
        result.status = "download_failed".to_string();
        result.message = format!("Installer download failed: {error}");
        result.failure_reason = Some(error);
        let _ = fs::remove_file(&temp_path);
        let _ = write_update_result_log("download", &result);
        return Ok(result);
    }

    let metadata = match fs::metadata(&temp_path) {
        Ok(metadata) => metadata,
        Err(error) => {
            result.status = "metadata_failed".to_string();
            result.message = format!("Downloaded installer metadata could not be read: {error}");
            result.failure_reason = Some(error.to_string());
            let _ = fs::remove_file(&temp_path);
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
            result.failure_reason = Some("size_mismatch".to_string());
            let _ = fs::remove_file(&temp_path);
            let _ = write_update_result_log("download", &result);
            return Ok(result);
        }
    }

    let actual_sha256 = match sha256_file(&temp_path) {
        Ok(hash) => hash,
        Err(error) => {
            result.status = "sha256_failed".to_string();
            result.message =
                format!("Downloaded installer sha256 could not be calculated: {error}");
            result.failure_reason = Some(error);
            let _ = fs::remove_file(&temp_path);
            let _ = write_update_result_log("download", &result);
            return Ok(result);
        }
    };
    result.actual_sha256 = Some(actual_sha256.clone());
    if actual_sha256 != expected_sha256 {
        result.status = "sha256_mismatch".to_string();
        result.message =
            "Downloaded installer sha256 does not match the remote manifest.".to_string();
        result.failure_reason = Some("sha256_mismatch".to_string());
        let _ = fs::remove_file(&temp_path);
        let _ = write_update_result_log("download", &result);
        return Ok(result);
    }

    if let Err(error) = replace_verified_cache_file(&temp_path, &cache_path) {
        result.status = "cache_replace_failed".to_string();
        result.message =
            format!("Verified installer could not be moved into update_cache: {error}");
        result.failure_reason = Some(error);
        let _ = fs::remove_file(&temp_path);
        let _ = write_update_result_log("download", &result);
        return Ok(result);
    }

    result.ok = true;
    result.verified = true;
    result.status = "verified".to_string();
    result.message =
        "Installer downloaded to update_cache and sha256 verified. Existing cache file was replaced only after verification.".to_string();
    let _ = write_update_result_log("download", &result);
    Ok(result)
}

#[tauri::command]
pub fn launch_verified_update_installer(
    request: UpdateLaunchRequest,
) -> Result<UpdateLaunchResult, String> {
    let checked_at = Utc::now().to_rfc3339();
    let expected_sha256 = request.expected_sha256.trim().to_ascii_lowercase();
    let current_version = env!("CARGO_PKG_VERSION").to_string();
    let target_version = request
        .target_version
        .as_deref()
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(str::to_string);
    let mut result = UpdateLaunchResult {
        ok: false,
        status: "not_started".to_string(),
        message: String::new(),
        failure_reason: None,
        checked_at,
        current_version,
        target_version,
        cache_path: request.cache_path.clone(),
        source_kind: "update_cache".to_string(),
        expected_sha256: expected_sha256.clone(),
        actual_sha256: None,
        verified: false,
    };

    if expected_sha256.is_empty() {
        result.status = "sha256_missing".to_string();
        result.message = "Expected sha256 is required before launching an installer.".to_string();
        result.failure_reason = Some("sha256_missing".to_string());
        let _ = write_update_result_log("launch", &result);
        return Ok(result);
    }

    let cache_path = match validate_installer_cache_path(Path::new(&request.cache_path)) {
        Ok(path) => {
            result.cache_path = path.display().to_string();
            path
        }
        Err(error) => {
            result.status = error.status;
            result.message = error.message;
            result.failure_reason = Some(error.reason);
            result.cache_path = request.cache_path;
            result.source_kind = "rejected_path".to_string();
            let _ = write_update_result_log("launch", &result);
            return Ok(result);
        }
    };
    if !cache_path.is_file() {
        result.status = "installer_missing".to_string();
        result.message = "Verified installer file is missing from update_cache.".to_string();
        result.failure_reason = Some("installer_missing".to_string());
        let _ = write_update_result_log("launch", &result);
        return Ok(result);
    }

    let actual_sha256 = match sha256_file(&cache_path) {
        Ok(hash) => hash,
        Err(error) => {
            result.status = "sha256_failed".to_string();
            result.message = format!("Installer sha256 could not be calculated: {error}");
            result.failure_reason = Some(error);
            let _ = write_update_result_log("launch", &result);
            return Ok(result);
        }
    };
    result.actual_sha256 = Some(actual_sha256.clone());
    if actual_sha256 != expected_sha256 {
        result.status = "sha256_mismatch".to_string();
        result.message = "Installer sha256 no longer matches the remote manifest.".to_string();
        result.failure_reason = Some("sha256_mismatch".to_string());
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
            result.failure_reason = Some(error.to_string());
        }
    }
    let _ = write_update_result_log("launch", &result);
    Ok(result)
}

#[tauri::command]
pub fn get_update_result_log() -> Result<Option<Value>, String> {
    Ok(read_last_update_result_for_current_version(env!(
        "CARGO_PKG_VERSION"
    )))
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
    read_update_config_with_user_path(root, &user_config_path)
}

fn read_update_config_with_user_path(root: &Path, user_config_path: &Path) -> UpdateConfigLookup {
    if user_config_path.is_file() {
        match read_update_source_url(user_config_path) {
            Ok(Some(source_url)) => {
                return UpdateConfigLookup {
                    source_url: Some(source_url),
                    config_source: "user".to_string(),
                    config_path: Some(user_config_path.to_path_buf()),
                    notes: Vec::new(),
                };
            }
            Ok(None) => {
                let default_lookup = read_default_update_config(root);
                if default_lookup.source_url.is_some() {
                    let mut notes = vec![format!(
                        "ユーザー設定に更新元URLが設定されていないためdefault設定を参照しました: {}",
                        user_config_path.display()
                    )];
                    notes.extend(default_lookup.notes);
                    return UpdateConfigLookup {
                        notes,
                        ..default_lookup
                    };
                }
                let mut notes = vec!["ユーザー設定に更新元URLが設定されていません。".to_string()];
                notes.extend(default_lookup.notes);
                return UpdateConfigLookup {
                    source_url: None,
                    config_source: "user".to_string(),
                    config_path: Some(user_config_path.to_path_buf()),
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
    fetch_source_to_file_with_timeout(root, source, &cache_path, 30)?;
    let text = fs::read_to_string(&cache_path).map_err(|error| error.to_string())?;
    serde_json::from_str(&text).map_err(|error| error.to_string())
}

#[cfg(test)]
fn fetch_source_to_file(root: &Path, source: &str, destination: &Path) -> Result<(), String> {
    fetch_source_to_file_with_timeout(root, source, destination, 120)
}

fn fetch_source_to_file_with_timeout(
    root: &Path,
    source: &str,
    destination: &Path,
    timeout_seconds: u32,
) -> Result<(), String> {
    if let Some(parent) = destination.parent() {
        fs::create_dir_all(parent).map_err(|error| error.to_string())?;
    }

    if is_plain_http_url(source) {
        return Err("http:// update sources are not allowed. Use https:// for Beta distribution or file:// / relative paths for local tests.".to_string());
    }
    if is_https_url(source) {
        let status = Command::new("powershell")
            .args([
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                powershell_webrequest_script(),
            ])
            .arg(source)
            .arg(destination)
            .arg(timeout_seconds.to_string())
            .status()
            .map_err(|error| error.to_string())?;
        if status.success() {
            return Ok(());
        }
        return Err(format!("Invoke-WebRequest exited with status {status}"));
    }
    if has_url_scheme(source) && !is_file_url(source) {
        return Err(format!(
            "unsupported update source scheme: {}",
            source_kind(source)
        ));
    }

    let source_path = source_to_local_path(root, source);
    fs::copy(&source_path, destination)
        .map(|_| ())
        .map_err(|error| format!("{} ({error})", source_path.display()))
}

fn powershell_webrequest_script() -> &'static str {
    "& { param([string]$Uri, [string]$OutFile, [int]$TimeoutSec) $ErrorActionPreference='Stop'; $ProgressPreference='SilentlyContinue'; [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -UseBasicParsing -TimeoutSec $TimeoutSec -UserAgent 'ToolHub-Updater' -Uri $Uri -OutFile $OutFile }"
}

fn is_https_url(source: &str) -> bool {
    source.starts_with("https://")
}

fn is_plain_http_url(source: &str) -> bool {
    source.starts_with("http://")
}

fn is_http_url(source: &str) -> bool {
    is_https_url(source) || is_plain_http_url(source)
}

fn is_file_url(source: &str) -> bool {
    source.starts_with("file://")
}

fn has_url_scheme(source: &str) -> bool {
    source.contains("://")
}

fn source_kind(source: &str) -> &'static str {
    if is_https_url(source) {
        "remote_https"
    } else if is_plain_http_url(source) {
        "remote_http_blocked"
    } else if is_file_url(source) {
        "local_file_url"
    } else if has_url_scheme(source) {
        "unsupported_scheme"
    } else if Path::new(source).is_absolute() {
        "local_absolute_path"
    } else {
        "local_relative_path"
    }
}

fn is_local_test_source(source: &str) -> bool {
    matches!(
        source_kind(source),
        "local_file_url" | "local_absolute_path" | "local_relative_path"
    )
}

fn sanitize_url_for_log(source: &str) -> String {
    if let Some((prefix, _)) = source.split_once('#') {
        return sanitize_url_for_log(prefix);
    }
    if let Some((prefix, _)) = source.split_once('?') {
        return prefix.to_string();
    }
    source.to_string()
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

#[derive(Debug)]
struct UpdateSafetyError {
    status: String,
    reason: String,
    message: String,
}

fn safe_installer_file_name(
    installer_file: Option<&str>,
    installer_url: Option<&str>,
) -> Result<String, String> {
    for candidate in [installer_file, installer_url] {
        if let Some(value) = candidate {
            let stripped = strip_query_and_fragment(value)
                .trim_end_matches('/')
                .trim_end_matches('\\')
                .to_string();
            let name = stripped
                .rsplit(['/', '\\'])
                .next()
                .unwrap_or("")
                .trim()
                .to_string();
            if !name.is_empty() {
                if let Err(error) = validate_installer_file_name(&name) {
                    return Err(error.message);
                }
                return Ok(name);
            }
        }
    }
    Ok("ToolHub_Setup.exe".to_string())
}

fn strip_query_and_fragment(value: &str) -> &str {
    value.split(['?', '#']).next().unwrap_or(value).trim()
}

fn validate_installer_file_name(name: &str) -> Result<(), UpdateSafetyError> {
    let reason = |reason: &str, message: &str| UpdateSafetyError {
        status: "unsafe_installer_name".to_string(),
        reason: reason.to_string(),
        message: message.to_string(),
    };
    if name.is_empty() || name == "." || name == ".." {
        return Err(reason(
            "empty_installer_file_name",
            "Installer file name is empty or reserved.",
        ));
    }
    if name.contains('/') || name.contains('\\') {
        return Err(reason(
            "installer_file_name_contains_separator",
            "Installer file name must not contain path separators.",
        ));
    }
    if name.chars().any(|character| {
        character.is_control() || matches!(character, ':' | '*' | '?' | '"' | '<' | '>' | '|')
    }) {
        return Err(reason(
            "installer_file_name_contains_unsafe_character",
            "Installer file name contains characters that are unsafe for Windows paths.",
        ));
    }
    let lower = name.to_ascii_lowercase();
    if !allowed_installer_file_extension_name(name) {
        return Err(reason(
            "installer_extension_not_allowed",
            "Installer file extension must be .exe or .msi.",
        ));
    }
    if !lower.contains("toolhub_setup") {
        return Err(reason(
            "installer_name_not_toolhub_setup",
            "Installer file name must contain ToolHub_Setup for the Beta updater.",
        ));
    }
    Ok(())
}

fn allowed_installer_file_extension_path(path: &Path) -> bool {
    path.extension()
        .and_then(|extension| extension.to_str())
        .map(|extension| {
            let extension = extension.to_ascii_lowercase();
            extension == "exe" || extension == "msi"
        })
        .unwrap_or(false)
}

fn allowed_installer_file_extension_name(name: &str) -> bool {
    allowed_installer_file_extension_path(Path::new(name))
}

fn update_cache_dir() -> PathBuf {
    crate::setup::user_data_root().join("update_cache")
}

fn validate_installer_cache_path(path: &Path) -> Result<PathBuf, UpdateSafetyError> {
    validate_installer_cache_path_with_cache_dir(path, &update_cache_dir())
}

fn validate_installer_cache_path_with_cache_dir(
    path: &Path,
    cache_dir: &Path,
) -> Result<PathBuf, UpdateSafetyError> {
    if !path.is_file() {
        return Err(UpdateSafetyError {
            status: "installer_missing".to_string(),
            reason: "installer_missing".to_string(),
            message: "Verified installer file is missing from update_cache.".to_string(),
        });
    }
    let canonical_path = fs::canonicalize(path).map_err(|error| UpdateSafetyError {
        status: "installer_path_invalid".to_string(),
        reason: "installer_path_canonicalize_failed".to_string(),
        message: format!("Installer path could not be resolved: {error}"),
    })?;
    fs::create_dir_all(cache_dir).map_err(|error| UpdateSafetyError {
        status: "update_cache_unavailable".to_string(),
        reason: "update_cache_create_failed".to_string(),
        message: format!("update_cache directory could not be prepared: {error}"),
    })?;
    let canonical_cache = fs::canonicalize(cache_dir).map_err(|error| UpdateSafetyError {
        status: "update_cache_unavailable".to_string(),
        reason: "update_cache_canonicalize_failed".to_string(),
        message: format!("update_cache directory could not be resolved: {error}"),
    })?;
    if !canonical_path.starts_with(&canonical_cache) {
        return Err(UpdateSafetyError {
            status: "installer_path_outside_update_cache".to_string(),
            reason: "installer_path_outside_update_cache".to_string(),
            message: "Installer launch is only allowed from ToolHub update_cache.".to_string(),
        });
    }
    let Some(file_name) = canonical_path.file_name().and_then(|name| name.to_str()) else {
        return Err(UpdateSafetyError {
            status: "unsafe_installer_name".to_string(),
            reason: "installer_file_name_missing".to_string(),
            message: "Installer file name could not be resolved.".to_string(),
        });
    };
    validate_installer_file_name(file_name)?;
    if !allowed_installer_file_extension_path(&canonical_path) {
        return Err(UpdateSafetyError {
            status: "installer_extension_not_allowed".to_string(),
            reason: "installer_extension_not_allowed".to_string(),
            message: "Installer launch is allowed only for .exe or .msi files.".to_string(),
        });
    }
    Ok(canonical_path)
}

fn replace_verified_cache_file(temp_path: &Path, cache_path: &Path) -> Result<(), String> {
    if cache_path.exists() {
        fs::remove_file(cache_path).map_err(|error| error.to_string())?;
    }
    fs::rename(temp_path, cache_path).map_err(|error| error.to_string())
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

fn read_last_update_result_for_current_version(current_version: &str) -> Option<Value> {
    read_last_update_result().map(|value| annotate_last_update_result(value, current_version))
}

fn annotate_last_update_result(mut value: Value, current_version: &str) -> Value {
    if value.get("operation").and_then(Value::as_str) != Some("launch") {
        return value;
    }

    let Some(result) = value.get_mut("result").and_then(Value::as_object_mut) else {
        return value;
    };
    let launch_status = result
        .get("status")
        .and_then(Value::as_str)
        .unwrap_or_default()
        .to_string();
    let Some(target_version) = result
        .get("targetVersion")
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|version| !version.is_empty())
        .map(str::to_string)
    else {
        return value;
    };

    result.insert(
        "observedCurrentVersion".to_string(),
        json!(current_version.to_string()),
    );

    if launch_status != "launched" {
        result.insert("postUpdateStatus".to_string(), json!("not_launched"));
        result.insert(
            "postUpdateMessage".to_string(),
            json!("前回の更新インストーラーは完了状態では記録されていません。"),
        );
        return value;
    }

    let version_confirmed = current_version == target_version.as_str()
        || version_is_newer(current_version, &target_version);
    if version_confirmed {
        result.insert("postUpdateStatus".to_string(), json!("version_confirmed"));
        result.insert(
            "postUpdateMessage".to_string(),
            json!("前回起動した更新インストーラーの対象version以上で起動しています。"),
        );
    } else {
        result.insert("postUpdateStatus".to_string(), json!("version_pending"));
        result.insert(
            "postUpdateMessage".to_string(),
            json!("前回の更新インストーラーは起動済みですが、現在のToolHub versionはまだ対象versionに到達していません。"),
        );
    }
    value
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

fn json_bool(value: &Value, path: &[&str]) -> Option<bool> {
    let mut current = value;
    for key in path {
        current = current.get(*key)?;
    }
    current.as_bool().or_else(|| {
        current
            .as_str()
            .and_then(|text| match text.trim().to_ascii_lowercase().as_str() {
                "true" | "1" | "yes" | "on" => Some(true),
                "false" | "0" | "no" | "off" => Some(false),
                _ => None,
            })
    })
}

fn json_string_list(value: &Value, path: &[&str]) -> Vec<String> {
    let mut current = value;
    for key in path {
        let Some(next) = current.get(*key) else {
            return Vec::new();
        };
        current = next;
    }
    current
        .as_array()
        .map(|items| {
            items
                .iter()
                .filter_map(|item| item.as_str())
                .map(str::trim)
                .filter(|item| !item.is_empty())
                .map(str::to_string)
                .take(8)
                .collect()
        })
        .unwrap_or_default()
}

fn parse_release_notes(manifest: &Value) -> Option<UpdateReleaseNotes> {
    let value = manifest.get("release_notes")?;
    let user = value
        .get("user")
        .and_then(parse_release_notes_user)
        .filter(release_notes_user_has_content);
    let admin = value
        .get("admin")
        .and_then(parse_release_notes_admin)
        .filter(release_notes_admin_has_content);

    if user.is_none() && admin.is_none() {
        return None;
    }

    Some(UpdateReleaseNotes {
        schema_version: json_u64(value, &["schema_version"]),
        generated_by: json_string(value, &["generated_by"]),
        edited_by_admin: json_bool(value, &["edited_by_admin"]),
        user,
        admin,
    })
}

fn parse_release_notes_user(value: &Value) -> Option<UpdateReleaseNotesUser> {
    if !value.is_object() {
        return None;
    }
    Some(UpdateReleaseNotesUser {
        title: json_string(value, &["title"]),
        summary: json_string(value, &["summary"]),
        highlights: json_string_list(value, &["highlights"]),
        added_apps: json_string_list(value, &["added_apps"])
            .into_iter()
            .chain(json_string_list(value, &["addedApps"]))
            .take(8)
            .collect(),
        recommended: json_bool(value, &["recommended"]),
    })
}

fn parse_release_notes_admin(value: &Value) -> Option<UpdateReleaseNotesAdmin> {
    if !value.is_object() {
        return None;
    }
    Some(UpdateReleaseNotesAdmin {
        summary: json_string(value, &["summary"]),
        changes: json_string_list(value, &["changes"]),
        validation: json_string_list(value, &["validation"]),
    })
}

fn release_notes_user_has_content(value: &UpdateReleaseNotesUser) -> bool {
    value.title.is_some()
        || value.summary.is_some()
        || !value.highlights.is_empty()
        || !value.added_apps.is_empty()
        || value.recommended.is_some()
}

fn release_notes_admin_has_content(value: &UpdateReleaseNotesAdmin) -> bool {
    value.summary.is_some() || !value.changes.is_empty() || !value.validation.is_empty()
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

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::{SystemTime, UNIX_EPOCH};

    fn update_safety_test_dir(name: &str) -> PathBuf {
        let stamp = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("clock should be after UNIX_EPOCH")
            .as_nanos();
        let dir = std::env::temp_dir().join(format!(
            "toolhub_update_safety_{}_{}_{}",
            name,
            std::process::id(),
            stamp
        ));
        fs::create_dir_all(&dir).expect("test dir should be creatable");
        dir
    }

    fn write_test_file(path: &Path, content: &[u8]) {
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent).expect("test parent should be creatable");
        }
        fs::write(path, content).expect("test file should be writable");
    }

    #[test]
    fn update_release_notes_parse_user_and_admin_sections() {
        let manifest = json!({
            "release_notes": {
                "schema_version": 1,
                "generated_by": "ai",
                "edited_by_admin": true,
                "user": {
                    "title": "新しいバージョンがあります",
                    "summary": "新しい業務アプリを使えるようになりました。",
                    "highlights": ["会議メモ作成を支援するアプリを追加しました"],
                    "added_apps": ["AgendaSnap"],
                    "recommended": true
                },
                "admin": {
                    "summary": "ToolHub release notes for administrators.",
                    "changes": ["Added release notes manifest support."],
                    "validation": ["cargo test"]
                }
            }
        });

        let notes = parse_release_notes(&manifest).expect("release notes should parse");

        assert_eq!(notes.schema_version, Some(1));
        assert_eq!(notes.generated_by.as_deref(), Some("ai"));
        assert_eq!(notes.edited_by_admin, Some(true));
        let user = notes.user.expect("user notes should exist");
        assert_eq!(user.title.as_deref(), Some("新しいバージョンがあります"));
        assert_eq!(user.highlights.len(), 1);
        assert_eq!(user.added_apps, vec!["AgendaSnap".to_string()]);
        let admin = notes.admin.expect("admin notes should exist");
        assert_eq!(admin.validation, vec!["cargo test".to_string()]);
    }

    #[test]
    fn update_release_notes_ignores_empty_shape() {
        let manifest = json!({
            "release_notes": {
                "schema_version": 1,
                "user": {
                    "summary": "   ",
                    "highlights": []
                }
            }
        });

        assert!(parse_release_notes(&manifest).is_none());
    }

    #[test]
    fn update_config_uses_user_manifest_url_when_present() {
        let root = update_safety_test_dir("config_user_wins_root");
        let user_root = update_safety_test_dir("config_user_wins_user");
        let default_url = "https://example.test/default/manifest.json";
        let user_url = "https://example.test/user/manifest.json";
        write_test_file(
            &root.join("config.default").join("launcher.yaml"),
            format!("updates:\n  manifest_url: {default_url}\n").as_bytes(),
        );
        let user_config = user_root.join("config").join("launcher.yaml");
        write_test_file(
            &user_config,
            format!("updates:\n  manifest_url: {user_url}\n").as_bytes(),
        );

        let lookup = read_update_config_with_user_path(&root, &user_config);

        assert_eq!(lookup.source_url.as_deref(), Some(user_url));
        assert_eq!(lookup.config_source, "user");
        assert_eq!(lookup.config_path.as_deref(), Some(user_config.as_path()));
        let _ = fs::remove_dir_all(root);
        let _ = fs::remove_dir_all(user_root);
    }

    #[test]
    fn update_config_falls_back_to_default_when_user_manifest_url_is_missing() {
        let root = update_safety_test_dir("config_default_fallback_root");
        let user_root = update_safety_test_dir("config_default_fallback_user");
        let default_url = "https://example.test/default/manifest.json";
        write_test_file(
            &root.join("config.default").join("launcher.yaml"),
            format!("updates:\n  manifest_url: {default_url}\n").as_bytes(),
        );
        let user_config = user_root.join("config").join("launcher.yaml");
        write_test_file(
            &user_config,
            b"updates:\n  channel: stable\n  manifest: release/manifest.json\n",
        );

        let lookup = read_update_config_with_user_path(&root, &user_config);
        let default_config = root.join("config.default").join("launcher.yaml");

        assert_eq!(lookup.source_url.as_deref(), Some(default_url));
        assert_eq!(lookup.config_source, "default");
        assert_eq!(
            lookup.config_path.as_deref(),
            Some(default_config.as_path())
        );
        assert!(lookup.notes.iter().any(|note| note.contains("default")));
        let _ = fs::remove_dir_all(root);
        let _ = fs::remove_dir_all(user_root);
    }

    #[test]
    fn update_fetch_script_forces_tls12_and_timeout_argument() {
        let script = powershell_webrequest_script();

        assert!(script.contains("SecurityProtocolType]::Tls12"));
        assert!(script.contains("param([string]$Uri, [string]$OutFile, [int]$TimeoutSec)"));
        assert!(script.contains("TimeoutSec $TimeoutSec"));
        assert!(script.contains("ToolHub-Updater"));
    }

    #[test]
    fn safe_installer_file_name_accepts_toolhub_setup_from_url() {
        let name = safe_installer_file_name(
            None,
            Some("https://example.test/releases/ToolHub_Setup_0.1.0.exe?token=secret"),
        )
        .expect("ToolHub setup exe should be accepted");

        assert_eq!(name, "ToolHub_Setup_0.1.0.exe");
    }

    #[test]
    fn safe_installer_file_name_rejects_non_installer_extension() {
        let error = safe_installer_file_name(None, Some("https://example.test/ToolHub_Setup.zip"))
            .expect_err("zip must not be accepted as an installer");

        assert!(error.contains(".exe or .msi"));
    }

    #[test]
    fn safe_installer_file_name_rejects_non_toolhub_setup_name() {
        let error = safe_installer_file_name(None, Some("https://example.test/Other_Setup.exe"))
            .expect_err("non ToolHub_Setup names must not be accepted");

        assert!(error.contains("ToolHub_Setup"));
    }

    #[test]
    fn source_kind_marks_http_as_blocked_and_file_as_local_test() {
        assert_eq!(
            source_kind("http://example.test/manifest.json"),
            "remote_http_blocked"
        );
        assert!(!is_local_test_source("https://example.test/manifest.json"));
        assert!(is_local_test_source("file:///C:/tmp/manifest.json"));
        assert!(is_local_test_source("release/manifest.json"));
    }

    #[test]
    fn sanitize_url_for_log_drops_query_and_fragment() {
        assert_eq!(
            sanitize_url_for_log("https://example.test/manifest.json?token=secret#section"),
            "https://example.test/manifest.json"
        );
    }

    #[test]
    fn update_safety_fetch_source_rejects_http_before_write() {
        let dir = update_safety_test_dir("http_reject");
        let destination = dir.join("downloaded.bin");

        let error = fetch_source_to_file(
            &dir,
            "http://example.test/ToolHub_Setup_9.9.9.exe",
            &destination,
        )
        .expect_err("http:// must be rejected before download");

        assert!(error.contains("http:// update sources are not allowed"));
        assert!(
            !destination.exists(),
            "blocked http source must not create destination"
        );
        let _ = fs::remove_dir_all(dir);
    }

    #[test]
    fn update_safety_fetch_source_copies_local_file_fixture() {
        let dir = update_safety_test_dir("local_copy");
        let source = dir.join("fixture.bin");
        let destination = dir.join("nested").join("downloaded.bin");
        write_test_file(&source, b"fixture bytes");

        fetch_source_to_file(&dir, source.to_str().expect("utf8 temp path"), &destination)
            .expect("local file fixture should be copied");

        assert_eq!(
            fs::read(&destination).expect("downloaded fixture should be readable"),
            b"fixture bytes"
        );
        let _ = fs::remove_dir_all(dir);
    }

    #[test]
    fn update_safety_fetch_source_rejects_unsupported_scheme() {
        let dir = update_safety_test_dir("unsupported_scheme");
        let destination = dir.join("downloaded.bin");

        let error = fetch_source_to_file(
            &dir,
            "ftp://example.test/ToolHub_Setup_9.9.9.exe",
            &destination,
        )
        .expect_err("unsupported URL schemes must be rejected");

        assert!(error.contains("unsupported update source scheme"));
        assert!(!destination.exists());
        let _ = fs::remove_dir_all(dir);
    }

    #[test]
    fn update_safety_resolve_installer_url_uses_manifest_relative_asset() {
        let root = PathBuf::from(r"C:\toolhub");

        let remote = resolve_installer_url(
            &root,
            "https://example.test/releases/latest/download/manifest.json",
            None,
            Some("ToolHub_Setup_9.9.9.exe"),
        )
        .expect("relative remote asset should resolve against manifest URL");

        assert_eq!(
            remote,
            "https://example.test/releases/latest/download/ToolHub_Setup_9.9.9.exe"
        );

        let local = resolve_installer_url(
            &root,
            "release/manifest.json",
            None,
            Some("ToolHub_Setup_9.9.9.exe"),
        )
        .expect("relative local asset should resolve against manifest file");
        assert!(
            local.ends_with("release\\ToolHub_Setup_9.9.9.exe")
                || local.ends_with("release/ToolHub_Setup_9.9.9.exe")
        );
    }

    #[test]
    fn update_safety_validate_cache_path_accepts_toolhub_setup_inside_cache() {
        let dir = update_safety_test_dir("cache_accept");
        let cache_dir = dir.join("update_cache");
        let installer = cache_dir.join("ToolHub_Setup_9.9.9.exe");
        write_test_file(&installer, b"installer bytes");

        let validated = validate_installer_cache_path_with_cache_dir(&installer, &cache_dir)
            .expect("ToolHub_Setup exe inside update_cache should be accepted");

        assert_eq!(
            validated,
            fs::canonicalize(&installer).expect("installer should canonicalize")
        );
        let _ = fs::remove_dir_all(dir);
    }

    #[test]
    fn update_safety_validate_cache_path_rejects_outside_cache() {
        let dir = update_safety_test_dir("cache_outside");
        let cache_dir = dir.join("update_cache");
        let outside = dir.join("outside").join("ToolHub_Setup_9.9.9.exe");
        write_test_file(&outside, b"installer bytes");

        let error = validate_installer_cache_path_with_cache_dir(&outside, &cache_dir)
            .expect_err("installer outside update_cache must be rejected");

        assert_eq!(error.reason, "installer_path_outside_update_cache");
        let _ = fs::remove_dir_all(dir);
    }

    #[test]
    fn update_safety_validate_cache_path_rejects_bad_name_inside_cache() {
        let dir = update_safety_test_dir("cache_bad_name");
        let cache_dir = dir.join("update_cache");
        let installer = cache_dir.join("Other_Setup.exe");
        write_test_file(&installer, b"installer bytes");

        let error = validate_installer_cache_path_with_cache_dir(&installer, &cache_dir)
            .expect_err("non ToolHub_Setup installer must be rejected");

        assert_eq!(error.reason, "installer_name_not_toolhub_setup");
        let _ = fs::remove_dir_all(dir);
    }

    #[test]
    fn update_safety_annotates_launched_result_after_version_change() {
        let value = json!({
            "operation": "launch",
            "result": {
                "status": "launched",
                "targetVersion": "9.9.9"
            }
        });

        let pending = annotate_last_update_result(value.clone(), "0.1.0");
        assert_eq!(
            pending
                .get("result")
                .and_then(|result| result.get("postUpdateStatus"))
                .and_then(Value::as_str),
            Some("version_pending")
        );

        let confirmed = annotate_last_update_result(value, "9.9.9");
        assert_eq!(
            confirmed
                .get("result")
                .and_then(|result| result.get("postUpdateStatus"))
                .and_then(Value::as_str),
            Some("version_confirmed")
        );
    }
}
