use crate::app_studio_preflight::validate_app_id;
use crate::app_studio_types::{AppStudioDeletePlan, AppStudioDeletePlanTarget};
use serde_json::Value;
use std::fs;
use std::path::{Path, PathBuf};

pub(crate) fn build_delete_plan(root: &Path, app_id: &str) -> Result<AppStudioDeletePlan, String> {
    let app_id = app_id.trim();
    validate_app_id(app_id)?;
    let source_dir = root.join("apps").join(app_id);
    let app_yaml = source_dir.join("app.yaml");
    let manifest_path = app_manifest_path(root);
    let manifest = read_json(&manifest_path).unwrap_or_else(|| serde_json::json!({ "apps": {} }));
    let manifest_entry = manifest_app_entry(&manifest, app_id);
    let manifest_entry_exists = manifest_entry.is_some();
    let manifest_enabled = manifest_entry.map(manifest_entry_enabled);
    let manifest_version = manifest_entry.and_then(|entry| json_str(entry, "version"));
    let manifest_package = manifest_entry.and_then(|entry| json_str(entry, "package"));
    let app_pack_paths = collect_app_pack_paths(root, app_id, manifest_package.as_deref());
    let (staging_paths, staging_candidate_paths) = collect_staging_paths(
        &root.join("release").join("staging"),
        app_id,
        manifest_version.as_deref(),
    );
    let runtime_app_env = root.join("runtime").join("app_envs").join(app_id);
    let app_studio_backup_paths =
        collect_backup_paths(&root.join("backups").join("app_studio"), app_id);
    let lifecycle_backup_paths =
        collect_backup_paths(&root.join("backups").join("app_lifecycle"), app_id);
    let external_references = collect_external_references(root, &app_yaml);
    let user_data_paths = user_data_excluded_targets(app_id);

    let mut delete_targets = Vec::new();
    let mut excluded_targets = Vec::new();
    let mut warnings = Vec::new();
    let blocking_reasons = Vec::new();

    push_target(
        &mut delete_targets,
        "managed_required",
        &source_dir,
        source_dir.exists(),
        true,
        "delete apps/<app_id>/",
        "Application source of truth. Future full delete removes it.",
    );
    push_target(
        &mut delete_targets,
        "managed_required",
        &manifest_path,
        manifest_entry_exists,
        true,
        "remove app_manifest entry",
        "release/app_manifest.json is a generated index; future full delete removes only this app entry.",
    );
    for path in &app_pack_paths {
        push_target(
            &mut delete_targets,
            "managed_generated",
            path,
            path.exists(),
            true,
            "delete App Pack zip",
            "Generated App Pack for this app.",
        );
    }
    for path in &staging_paths {
        push_target(
            &mut delete_targets,
            "managed_generated",
            path,
            path.exists(),
            true,
            "delete staging artifact",
            "Generated release staging artifact for this app.",
        );
    }
    for path in &staging_candidate_paths {
        push_target(
            &mut excluded_targets,
            "managed_generated_candidate",
            path,
            path.exists(),
            false,
            "review staging candidate",
            "Name contains app_id but does not match strict staging rules; future delete must not remove it automatically.",
        );
    }
    push_target(
        &mut delete_targets,
        "managed_generated",
        &runtime_app_env,
        runtime_app_env.exists(),
        true,
        "delete runtime app_env",
        "App-specific runtime environment. Shared runtimes are excluded.",
    );
    for path in &app_studio_backup_paths {
        push_target(
            &mut delete_targets,
            "managed_history",
            path,
            path.exists(),
            true,
            "delete App Studio backup",
            "Repository-local app backup/history for this app.",
        );
    }
    for path in &lifecycle_backup_paths {
        push_target(
            &mut delete_targets,
            "managed_history",
            path,
            path.exists(),
            true,
            "delete legacy lifecycle backup",
            "Repository-local legacy lifecycle backup/history for this app.",
        );
    }

    if !source_dir.exists()
        && !manifest_entry_exists
        && app_pack_paths.is_empty()
        && app_studio_backup_paths.is_empty()
    {
        warnings.push("No repository-managed app source, manifest entry, App Pack, or App Studio backup was found.".to_string());
    }
    if source_dir.exists() && !app_yaml.is_file() {
        warnings.push("apps/<app_id>/ exists but app.yaml is missing.".to_string());
    }
    if !external_references.is_empty() {
        warnings.push(
            "External absolute paths were found in app.yaml and are excluded from deletion."
                .to_string(),
        );
    }
    if !staging_candidate_paths.is_empty() {
        warnings.push("Potential staging artifacts matched only by partial app_id and were excluded from delete targets.".to_string());
    }

    excluded_targets.extend(external_references.clone());
    excluded_targets.extend(user_data_paths.clone());
    push_target(
        &mut excluded_targets,
        "shared_runtime",
        &root.join("runtime").join("python"),
        root.join("runtime").join("python").exists(),
        false,
        "exclude shared runtime",
        "Shared runtime is not app-owned.",
    );
    push_target(
        &mut excluded_targets,
        "shared_runtime",
        &root.join("runtime").join("web_automation_runtime"),
        root.join("runtime").join("web_automation_runtime").exists(),
        false,
        "exclude shared runtime",
        "Shared runtime is not app-owned.",
    );

    sort_delete_plan_targets(&mut delete_targets);
    sort_delete_plan_targets(&mut excluded_targets);

    Ok(AppStudioDeletePlan {
        app_id: app_id.to_string(),
        source_dir: source_dir.display().to_string(),
        app_yaml: app_yaml.display().to_string(),
        manifest_entry_exists,
        manifest_enabled,
        manifest_version,
        manifest_package,
        app_pack_paths: app_pack_paths
            .iter()
            .map(|path| path.display().to_string())
            .collect(),
        staging_paths: staging_paths
            .iter()
            .map(|path| path.display().to_string())
            .collect(),
        staging_candidate_paths: staging_candidate_paths
            .iter()
            .map(|path| path.display().to_string())
            .collect(),
        runtime_app_env: runtime_app_env.display().to_string(),
        app_studio_backup_paths: app_studio_backup_paths
            .iter()
            .map(|path| path.display().to_string())
            .collect(),
        lifecycle_backup_paths: lifecycle_backup_paths
            .iter()
            .map(|path| path.display().to_string())
            .collect(),
        external_references,
        user_data_paths,
        delete_targets,
        excluded_targets,
        warnings,
        blocking_reasons,
    })
}

fn push_target(
    targets: &mut Vec<AppStudioDeletePlanTarget>,
    category: &str,
    path: &Path,
    exists: bool,
    delete_allowed: bool,
    action: &str,
    note: &str,
) {
    let path_text = path.display().to_string();
    let normalized_path = normalize_plan_path(&path_text);
    let comparison_key = format!("{category}|{action}|{normalized_path}");
    targets.push(AppStudioDeletePlanTarget {
        category: category.to_string(),
        path: path_text,
        normalized_path,
        exists,
        delete_allowed,
        action: action.to_string(),
        comparison_key,
        note: note.to_string(),
    });
}

fn push_target_string(
    targets: &mut Vec<AppStudioDeletePlanTarget>,
    category: &str,
    path: &str,
    exists: bool,
    delete_allowed: bool,
    action: &str,
    note: &str,
) {
    let normalized_path = normalize_plan_path(path);
    let comparison_key = format!("{category}|{action}|{normalized_path}");
    targets.push(AppStudioDeletePlanTarget {
        category: category.to_string(),
        path: path.to_string(),
        normalized_path,
        exists,
        delete_allowed,
        action: action.to_string(),
        comparison_key,
        note: note.to_string(),
    });
}

pub(crate) fn normalize_plan_path(path: &str) -> String {
    path.replace('\\', "/")
        .trim_end_matches('/')
        .to_ascii_lowercase()
}

fn sort_delete_plan_targets(targets: &mut [AppStudioDeletePlanTarget]) {
    targets.sort_by(|a, b| a.comparison_key.cmp(&b.comparison_key));
}

fn collect_app_pack_paths(
    root: &Path,
    app_id: &str,
    manifest_package: Option<&str>,
) -> Vec<PathBuf> {
    let app_packs_dir = root.join("release").join("app_packs");
    let mut paths = Vec::new();
    if let Some(package) = manifest_package {
        paths.push(root.join("release").join(package));
    }
    if let Ok(entries) = fs::read_dir(&app_packs_dir) {
        let prefix = format!("{app_id}-");
        for entry in entries.flatten() {
            let path = entry.path();
            let Some(name) = path.file_name().and_then(|value| value.to_str()) else {
                continue;
            };
            if name.starts_with(&prefix)
                && name.ends_with(".zip")
                && !paths.iter().any(|existing| existing == &path)
            {
                paths.push(path);
            }
        }
    }
    paths.sort();
    paths
}

fn collect_staging_paths(
    root: &Path,
    app_id: &str,
    version: Option<&str>,
) -> (Vec<PathBuf>, Vec<PathBuf>) {
    let mut targets = Vec::new();
    let mut candidates = Vec::new();
    collect_staging_paths_inner(root, root, app_id, version, &mut targets, &mut candidates);
    targets.sort();
    targets.dedup();
    candidates.sort();
    candidates.dedup();
    (targets, candidates)
}

fn collect_staging_paths_inner(
    staging_root: &Path,
    current: &Path,
    app_id: &str,
    version: Option<&str>,
    targets: &mut Vec<PathBuf>,
    candidates: &mut Vec<PathBuf>,
) {
    let Ok(entries) = fs::read_dir(current) else {
        return;
    };
    for entry in entries.flatten() {
        let path = entry.path();
        match classify_staging_path(staging_root, &path, app_id, version) {
            StagingPathMatch::Target => {
                targets.push(path);
                continue;
            }
            StagingPathMatch::Candidate => {
                candidates.push(path);
                continue;
            }
            StagingPathMatch::None => {}
        }
        if path.is_dir() {
            collect_staging_paths_inner(staging_root, &path, app_id, version, targets, candidates);
        }
    }
}

enum StagingPathMatch {
    Target,
    Candidate,
    None,
}

fn classify_staging_path(
    staging_root: &Path,
    path: &Path,
    app_id: &str,
    version: Option<&str>,
) -> StagingPathMatch {
    let relative = path.strip_prefix(staging_root).unwrap_or(path);
    let version_prefix = version
        .filter(|value| !value.trim().is_empty())
        .map(|value| format!("{app_id}-{value}"));
    let mut contains_only = false;
    for component in relative.components() {
        let Some(segment) = component.as_os_str().to_str() else {
            continue;
        };
        if segment == app_id {
            return StagingPathMatch::Target;
        }
        if let Some(prefix) = version_prefix.as_deref() {
            if segment == prefix
                || segment.starts_with(&format!("{prefix}."))
                || segment.starts_with(&format!("{prefix}-"))
            {
                return StagingPathMatch::Target;
            }
        }
        if segment
            .to_ascii_lowercase()
            .contains(&app_id.to_ascii_lowercase())
        {
            contains_only = true;
        }
    }
    if contains_only {
        StagingPathMatch::Candidate
    } else {
        StagingPathMatch::None
    }
}

fn collect_backup_paths(root: &Path, app_id: &str) -> Vec<PathBuf> {
    let mut paths = Vec::new();
    collect_backup_paths_inner(root, app_id, &mut paths);
    paths.sort();
    paths
}

fn collect_backup_paths_inner(root: &Path, app_id: &str, paths: &mut Vec<PathBuf>) {
    let Ok(entries) = fs::read_dir(root) else {
        return;
    };
    for entry in entries.flatten() {
        let path = entry.path();
        if path.is_dir() {
            if path.file_name().and_then(|value| value.to_str()) == Some(app_id) {
                paths.push(path.clone());
            }
            collect_backup_paths_inner(&path, app_id, paths);
        }
    }
}

fn collect_external_references(root: &Path, app_yaml: &Path) -> Vec<AppStudioDeletePlanTarget> {
    let Ok(text) = fs::read_to_string(app_yaml) else {
        return Vec::new();
    };
    let Ok(yaml) = serde_yaml::from_str::<serde_yaml::Value>(&text) else {
        return Vec::new();
    };
    let mut refs = Vec::new();
    collect_external_references_inner(root, &yaml, "$", &mut refs);
    refs.sort_by(|a, b| a.path.cmp(&b.path).then(a.action.cmp(&b.action)));
    refs.dedup_by(|a, b| a.path == b.path && a.action == b.action);
    refs
}

fn collect_external_references_inner(
    root: &Path,
    value: &serde_yaml::Value,
    logical_path: &str,
    refs: &mut Vec<AppStudioDeletePlanTarget>,
) {
    match value {
        serde_yaml::Value::String(text) => {
            let trimmed = text.trim();
            let path = Path::new(trimmed);
            if path.is_absolute() && !path_starts_with(path, root) {
                push_target_string(
                    refs,
                    "external_reference",
                    trimmed,
                    path.exists(),
                    false,
                    "exclude external app.yaml reference",
                    &format!(
                        "External absolute path recorded in app.yaml at {logical_path}. Future delete must not remove it."
                    ),
                );
            }
        }
        serde_yaml::Value::Sequence(items) => {
            for (index, item) in items.iter().enumerate() {
                collect_external_references_inner(
                    root,
                    item,
                    &format!("{logical_path}[{index}]"),
                    refs,
                );
            }
        }
        serde_yaml::Value::Mapping(map) => {
            for (key, item) in map {
                let key_text = key.as_str().unwrap_or("?");
                collect_external_references_inner(
                    root,
                    item,
                    &format!("{logical_path}.{key_text}"),
                    refs,
                );
            }
        }
        _ => {}
    }
}

fn user_data_excluded_targets(app_id: &str) -> Vec<AppStudioDeletePlanTarget> {
    let user_root = crate::setup::user_data_root();
    let mut targets = Vec::new();
    for path in [
        user_root.join("data"),
        user_root.join("data").join("logs"),
        user_root.join("data").join("browser_profiles"),
        user_root.join("data").join("app_state"),
        user_root.join("data").join("app_state").join(app_id),
    ] {
        push_target(
            &mut targets,
            "user_data",
            &path,
            path.exists(),
            false,
            "exclude user data",
            "User data is outside repository-managed app deletion.",
        );
    }
    targets
}

fn path_starts_with(path: &Path, base: &Path) -> bool {
    let Ok(full_path) = path
        .canonicalize()
        .or_else(|_| Ok::<PathBuf, std::io::Error>(path.to_path_buf()))
    else {
        return false;
    };
    let Ok(full_base) = base
        .canonicalize()
        .or_else(|_| Ok::<PathBuf, std::io::Error>(base.to_path_buf()))
    else {
        return false;
    };
    full_path.starts_with(full_base)
}

fn app_manifest_path(root: &Path) -> PathBuf {
    root.join("release").join("app_manifest.json")
}

fn manifest_app_entry<'a>(manifest: &'a Value, app_id: &str) -> Option<&'a Value> {
    manifest.get("apps").and_then(|apps| apps.get(app_id))
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

fn read_json(path: &Path) -> Option<Value> {
    let text = fs::read_to_string(path).ok()?;
    serde_json::from_str(&text).ok()
}
