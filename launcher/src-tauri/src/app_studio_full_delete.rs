use crate::app_studio_delete_plan::{build_delete_plan, normalize_plan_path};
use crate::app_studio_management::list_managed_apps_from_root;
use crate::app_studio_preflight::validate_app_id;
use crate::app_studio_process::append_app_studio_gui_log;
use crate::app_studio_types::{
    AppStudioDeletePlan, AppStudioDeletePlanTarget, AppStudioFullDeletePostCheckSummary,
    AppStudioFullDeleteRecord, AppStudioFullDeleteResult,
};
use serde::Serialize;
use serde_json::Value;
use std::collections::BTreeSet;
use std::fs;
use std::path::{Path, PathBuf};

pub(crate) fn full_delete_apply(
    root: &Path,
    app_id: &str,
    plan_snapshot: Option<&AppStudioDeletePlan>,
) -> Result<AppStudioFullDeleteResult, String> {
    let app_id = app_id.trim();
    validate_app_id(app_id)?;
    let plan = build_delete_plan(root, app_id)?;
    validate_full_delete_plan(root, &plan)?;
    if let Some(snapshot) = plan_snapshot {
        compare_delete_plan_snapshot(snapshot, &plan)?;
    }

    let mut deleted = Vec::new();
    let mut already_clean = Vec::new();
    let mut skipped = Vec::new();
    let mut failed = Vec::new();
    let mut stop_before_manifest = false;

    for target in ordered_full_delete_targets(&plan) {
        let record = delete_full_delete_target(root, target);
        match record.status.as_str() {
            "deleted" => deleted.push(record),
            "already_clean" => already_clean.push(record),
            "skipped" => skipped.push(record),
            _ => {
                stop_before_manifest = true;
                failed.push(record);
                break;
            }
        }
    }

    let mut manifest_entry_removed = false;
    if stop_before_manifest {
        if let Some(target) = plan
            .delete_targets
            .iter()
            .find(|target| is_manifest_entry_target(target))
        {
            skipped.push(full_delete_record_from_target(
                target,
                "skipped",
                "Manifest entry was not removed because an earlier delete step failed.",
            ));
        }
    } else if let Some(target) = plan
        .delete_targets
        .iter()
        .find(|target| is_manifest_entry_target(target))
    {
        match remove_manifest_entry(root, app_id, target) {
            Ok((record, removed)) => {
                manifest_entry_removed = removed;
                match record.status.as_str() {
                    "deleted" => deleted.push(record),
                    "already_clean" => already_clean.push(record),
                    "skipped" => skipped.push(record),
                    _ => failed.push(record),
                }
            }
            Err(error) => failed.push(full_delete_record_from_target(target, "failed", &error)),
        }
    }

    let post_check_summary = full_delete_post_check(root, app_id);
    let ok = failed.is_empty()
        && !post_check_summary.manifest_entry_present
        && post_check_summary.remaining_delete_target_count == 0;
    let message = if ok {
        format!("{app_id} was fully deleted from repository-managed targets.")
    } else {
        format!("{app_id} full delete did not complete. Review failed and remaining targets.")
    };
    let result = AppStudioFullDeleteResult {
        ok,
        message,
        app_id: app_id.to_string(),
        deleted,
        already_clean,
        skipped,
        excluded: plan.excluded_targets.clone(),
        failed,
        manifest_entry_removed,
        post_check_summary,
        apps: list_managed_apps_from_root(root),
    };

    append_app_studio_gui_log(
        "app_management_full_delete",
        &[
            ("app_id", app_id.to_string()),
            ("ok", result.ok.to_string()),
            ("deleted", result.deleted.len().to_string()),
            ("already_clean", result.already_clean.len().to_string()),
            ("failed", result.failed.len().to_string()),
            (
                "manifest_entry_removed",
                result.manifest_entry_removed.to_string(),
            ),
        ],
    );

    Ok(result)
}

pub(crate) fn validate_full_delete_plan(
    root: &Path,
    plan: &AppStudioDeletePlan,
) -> Result<(), String> {
    let mut errors = Vec::new();
    if !plan.blocking_reasons.is_empty() {
        errors.extend(plan.blocking_reasons.iter().cloned());
    }
    if plan.delete_targets.is_empty() {
        errors.push("Deletion plan has no delete targets.".to_string());
    }
    if !plan.manifest_entry_exists && Path::new(&plan.source_dir).exists() {
        errors.push(
            "apps/<app_id>/ exists without a release/app_manifest.json entry. Rebuild the manifest before full delete."
                .to_string(),
        );
    }

    let manifest_path = app_manifest_path(root);
    let manifest_normalized = normalize_plan_path(&manifest_path.display().to_string());
    let mut delete_normalized_paths = BTreeSet::new();
    for target in &plan.delete_targets {
        if !target.delete_allowed {
            errors.push(format!(
                "Delete target is not marked deleteAllowed=true: {}",
                target.path
            ));
        }
        if matches!(
            target.category.as_str(),
            "external_reference" | "user_data" | "shared_runtime" | "managed_generated_candidate"
        ) {
            errors.push(format!(
                "Forbidden category appears in delete targets: {}",
                target.path
            ));
        }
        if !target.normalized_path.trim().is_empty() {
            delete_normalized_paths.insert(target.normalized_path.clone());
        }
        if is_manifest_entry_target(target) {
            if target.normalized_path != manifest_normalized {
                errors.push(format!(
                    "Manifest entry target must point to release/app_manifest.json: {}",
                    target.path
                ));
            }
            continue;
        }
        if let Err(error) = resolve_safe_delete_target_path(root, target) {
            errors.push(error);
        }
        if is_shared_runtime_path(root, Path::new(&target.path)) {
            errors.push(format!(
                "Shared runtime cannot be a delete target: {}",
                target.path
            ));
        }
    }

    for target in &plan.excluded_targets {
        if target.delete_allowed {
            errors.push(format!(
                "Excluded target must be deleteAllowed=false: {}",
                target.path
            ));
        }
        if delete_normalized_paths.contains(&target.normalized_path) {
            errors.push(format!(
                "Excluded target overlaps a delete target: {}",
                target.path
            ));
        }
    }

    if errors.is_empty() {
        Ok(())
    } else {
        Err(format!(
            "Full delete safety check failed: {}",
            errors.join(" / ")
        ))
    }
}

fn compare_delete_plan_snapshot(
    snapshot: &AppStudioDeletePlan,
    fresh: &AppStudioDeletePlan,
) -> Result<(), String> {
    let mut mismatches = Vec::new();
    if snapshot.app_id != fresh.app_id {
        mismatches.push("appId changed".to_string());
    }
    if snapshot.manifest_entry_exists != fresh.manifest_entry_exists {
        mismatches.push("manifest entry existence changed".to_string());
    }
    if snapshot.manifest_version != fresh.manifest_version {
        mismatches.push("manifest version changed".to_string());
    }
    if snapshot.manifest_package != fresh.manifest_package {
        mismatches.push("manifest package changed".to_string());
    }
    let snapshot_delete_keys: BTreeSet<&str> = snapshot
        .delete_targets
        .iter()
        .map(|target| target.comparison_key.as_str())
        .collect();
    let fresh_delete_keys: BTreeSet<&str> = fresh
        .delete_targets
        .iter()
        .map(|target| target.comparison_key.as_str())
        .collect();
    if snapshot_delete_keys != fresh_delete_keys {
        mismatches.push("delete target set changed".to_string());
    }
    let snapshot_excluded_keys: BTreeSet<&str> = snapshot
        .excluded_targets
        .iter()
        .map(|target| target.comparison_key.as_str())
        .collect();
    let fresh_excluded_keys: BTreeSet<&str> = fresh
        .excluded_targets
        .iter()
        .map(|target| target.comparison_key.as_str())
        .collect();
    if snapshot_excluded_keys != fresh_excluded_keys {
        mismatches.push("excluded target set changed".to_string());
    }

    if mismatches.is_empty() {
        Ok(())
    } else {
        Err(format!(
            "Deletion plan changed after it was displayed. Reload the plan before deleting. ({})",
            mismatches.join(", ")
        ))
    }
}

fn ordered_full_delete_targets(plan: &AppStudioDeletePlan) -> Vec<&AppStudioDeletePlanTarget> {
    let mut ordered = Vec::new();
    let mut seen = BTreeSet::new();
    for action in [
        "delete App Pack zip",
        "delete staging artifact",
        "delete runtime app_env",
        "delete App Studio backup",
        "delete legacy lifecycle backup",
        "delete apps/<app_id>/",
    ] {
        for target in plan
            .delete_targets
            .iter()
            .filter(|target| target.action == action && !is_manifest_entry_target(target))
        {
            seen.insert(target.comparison_key.clone());
            ordered.push(target);
        }
    }
    for target in plan.delete_targets.iter().filter(|target| {
        !is_manifest_entry_target(target) && !seen.contains(&target.comparison_key)
    }) {
        ordered.push(target);
    }
    ordered
}

fn delete_full_delete_target(
    root: &Path,
    target: &AppStudioDeletePlanTarget,
) -> AppStudioFullDeleteRecord {
    let Ok(path) = resolve_safe_delete_target_path(root, target) else {
        return full_delete_record_from_target(
            target,
            "failed",
            "Target path failed safety resolution.",
        );
    };
    if !path.exists() {
        return full_delete_record_from_target(
            target,
            "already_clean",
            "Target was already missing.",
        );
    }
    let delete_result = if path.is_dir() {
        fs::remove_dir_all(&path)
    } else {
        fs::remove_file(&path)
    };
    match delete_result {
        Ok(()) if !path.exists() => full_delete_record_from_target(
            target,
            "deleted",
            "Deleted repository-managed app target.",
        ),
        Ok(()) => full_delete_record_from_target(
            target,
            "failed",
            "Target still exists after deletion attempt.",
        ),
        Err(error) => full_delete_record_from_target(target, "failed", &error.to_string()),
    }
}

fn remove_manifest_entry(
    root: &Path,
    app_id: &str,
    target: &AppStudioDeletePlanTarget,
) -> Result<(AppStudioFullDeleteRecord, bool), String> {
    let manifest_path = app_manifest_path(root);
    let mut manifest = read_app_manifest_for_write(&manifest_path)?;
    let apps = manifest
        .get_mut("apps")
        .and_then(Value::as_object_mut)
        .ok_or_else(|| "release/app_manifest.json apps object was not found.".to_string())?;
    let removed = apps.remove(app_id).is_some();
    if removed {
        write_json_file(&manifest_path, &manifest)?;
        Ok((
            full_delete_record_from_target(
                target,
                "deleted",
                "Removed only the app entry from release/app_manifest.json.",
            ),
            true,
        ))
    } else {
        Ok((
            full_delete_record_from_target(
                target,
                "already_clean",
                "Manifest entry was already absent.",
            ),
            false,
        ))
    }
}

fn full_delete_post_check(root: &Path, app_id: &str) -> AppStudioFullDeletePostCheckSummary {
    let manifest = read_json(&app_manifest_path(root));
    let manifest_json_valid = manifest.is_some();
    let manifest_entry_present = manifest
        .as_ref()
        .and_then(|value| value.get("apps"))
        .and_then(|apps| apps.get(app_id))
        .is_some();
    let fresh_plan = build_delete_plan(root, app_id).unwrap_or_default();
    let remaining_delete_targets: Vec<String> = fresh_plan
        .delete_targets
        .iter()
        .filter(|target| !is_manifest_entry_target(target) && target.exists)
        .map(|target| target.comparison_key.clone())
        .collect();
    AppStudioFullDeletePostCheckSummary {
        manifest_json_valid,
        manifest_entry_present,
        remaining_delete_target_count: remaining_delete_targets.len(),
        remaining_delete_targets,
    }
}

fn full_delete_record_from_target(
    target: &AppStudioDeletePlanTarget,
    status: &str,
    note: &str,
) -> AppStudioFullDeleteRecord {
    AppStudioFullDeleteRecord {
        category: target.category.clone(),
        action: target.action.clone(),
        path: target.path.clone(),
        normalized_path: target.normalized_path.clone(),
        comparison_key: target.comparison_key.clone(),
        status: status.to_string(),
        note: note.to_string(),
    }
}

fn resolve_safe_delete_target_path(
    root: &Path,
    target: &AppStudioDeletePlanTarget,
) -> Result<PathBuf, String> {
    let path = PathBuf::from(&target.path);
    if path
        .components()
        .any(|component| matches!(component, std::path::Component::ParentDir))
    {
        return Err(format!(
            "Delete target contains path traversal: {}",
            target.path
        ));
    }
    let full_path = if path.is_absolute() {
        path
    } else {
        root.join(path)
    };
    if !path_is_strict_child_of(&full_path, root) {
        return Err(format!(
            "Delete target is not safely inside the project root: {}",
            target.path
        ));
    }
    Ok(full_path)
}

fn path_is_strict_child_of(path: &Path, root: &Path) -> bool {
    let root_path = root.to_path_buf();
    let full_path = if path.is_absolute() {
        path.to_path_buf()
    } else {
        root_path.join(path)
    };
    let root_norm = normalize_plan_path(&root_path.display().to_string());
    let full_norm = normalize_plan_path(&full_path.display().to_string());
    full_norm != root_norm && full_norm.starts_with(&format!("{root_norm}/"))
}

fn is_manifest_entry_target(target: &AppStudioDeletePlanTarget) -> bool {
    target.action == "remove app_manifest entry"
}

fn is_shared_runtime_path(root: &Path, path: &Path) -> bool {
    let shared_python = root.join("runtime").join("python");
    let shared_web = root.join("runtime").join("web_automation_runtime");
    let path_norm = normalize_plan_path(&path.display().to_string());
    path_norm == normalize_plan_path(&shared_python.display().to_string())
        || path_norm == normalize_plan_path(&shared_web.display().to_string())
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

fn read_json(path: &Path) -> Option<Value> {
    let text = std::fs::read_to_string(path).ok()?;
    serde_json::from_str(&text).ok()
}
