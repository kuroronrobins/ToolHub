use crate::app_studio_types::AppStudioTimingPhase;
use serde::Serialize;
use serde_json::Value;
use std::path::{Path, PathBuf};

#[derive(Debug, Serialize, Clone, Default)]
#[serde(rename_all = "camelCase")]
pub struct AppStudioResultSummary {
    pub app_id: Option<String>,
    pub output_dir: Option<String>,
    pub selected_build_mode: Option<String>,
    pub execution_status: Option<String>,
    pub approval_allowed: Option<bool>,
    pub runtime_status: Option<String>,
    pub app_pack: Option<String>,
    pub enabled: Option<bool>,
    pub version: Option<String>,
    pub metadata_override_used: bool,
    pub metadata_override_keys: Vec<String>,
    pub icon_override_used: bool,
    pub selected_icon_source: Option<String>,
    pub exe_readiness_status: Option<String>,
    pub manual_checks: Vec<String>,
    pub secret_blocking_count: usize,
    pub secret_warning_count: usize,
    pub secret_manual_check_count: usize,
    pub secret_scan_report: Option<String>,
    pub secret_blocking_findings: Vec<String>,
    pub ai_blocked_by_secret_scan: bool,
    pub apply_blocked_by_secret_scan: bool,
    pub approval_blocking_warnings_count: usize,
    pub non_blocking_warnings_count: usize,
    pub info_count: usize,
    pub unresolved_distribution_risks_count: usize,
    pub approval_blocking_reasons: Vec<String>,
    pub non_blocking_warning_summaries: Vec<String>,
    pub timing_report: Option<String>,
    pub timing_total_seconds: Option<f64>,
    pub timing_estimated_total_seconds: Option<f64>,
    pub timing_actual_total_seconds: Option<f64>,
    pub timing_prediction_error_seconds: Option<f64>,
    pub timing_prediction_source: Option<String>,
    pub timing_wall_clock_total_seconds: Option<f64>,
    pub timing_cli_measured_total_seconds: Option<f64>,
    pub timing_unmeasured_overhead_seconds: Option<f64>,
    pub timing_phases: Vec<AppStudioTimingPhase>,
    pub process_wall_clock_seconds: Option<f64>,
    pub manifest_enabled: Option<bool>,
    pub approval_record_status: Option<String>,
    pub approval_record_path: Option<String>,
    pub approval_failure_summary: Option<String>,
    pub verify_release_status: Option<String>,
    pub verify_release_failure_summary: Option<String>,
    pub catalog_visible: Option<bool>,
    pub catalog_enabled: Option<bool>,
    pub catalog_disabled_reason: Option<String>,
    pub catalog_load_error: Option<String>,
    pub catalog_root: Option<String>,
    pub app_studio_repo_root: Option<String>,
}

pub fn read_summary(
    root: &Path,
    app_id: Option<&str>,
    output_dir: Option<&Path>,
) -> AppStudioResultSummary {
    let mut summary = AppStudioResultSummary::default();
    summary.app_studio_repo_root = Some(root.display().to_string());
    summary.catalog_root = Some(root.display().to_string());
    let output = output_dir
        .map(Path::to_path_buf)
        .or_else(|| app_id.and_then(|id| output_dir_from_app_yaml(root, id)));
    if let Some(path) = output {
        summary.output_dir = Some(path.display().to_string());
        read_import_plan(&path, &mut summary);
        read_execution_result(&path, &mut summary);
        read_runtime_result(&path, &mut summary);
        read_timing_result(&path, &mut summary);
        read_app_pack(&path, &mut summary);
    }
    if summary.app_id.is_none() {
        summary.app_id = app_id.map(str::to_string);
    }
    read_enabled(root, &mut summary);
    read_version(root, &mut summary);
    read_approval_record(root, &mut summary);
    read_catalog_status(root, &mut summary);
    summary
}

fn read_import_plan(output_dir: &Path, summary: &mut AppStudioResultSummary) {
    let path = output_dir.join("import_plan.json");
    let Some(json) = read_json(&path) else {
        return;
    };
    if let Some(value) = json.get("app_id").and_then(Value::as_str) {
        summary.app_id = Some(value.to_string());
    }
    if let Some(value) = json.get("selected_build_mode").and_then(Value::as_str) {
        summary.selected_build_mode = Some(value.to_string());
    }
    if let Some(value) = json.get("version").and_then(Value::as_str) {
        summary.version = Some(value.to_string());
    }
    if let Some(value) = json.get("metadata_override_used").and_then(Value::as_bool) {
        summary.metadata_override_used = value;
    }
    if let Some(items) = json.get("metadata_override_keys").and_then(Value::as_array) {
        summary.metadata_override_keys = items
            .iter()
            .filter_map(Value::as_str)
            .map(str::to_string)
            .collect();
    }
    if let Some(value) = json.get("icon_override_used").and_then(Value::as_bool) {
        summary.icon_override_used = value;
    }
    if let Some(value) = json.get("selected_icon_source").and_then(Value::as_str) {
        summary.selected_icon_source = Some(value.to_string());
    }
    if let Some(value) = json.get("exe_readiness_status").and_then(Value::as_str) {
        summary.exe_readiness_status = Some(value.to_string());
    }
    if let Some(items) = json.get("manual_checks").and_then(Value::as_array) {
        summary.manual_checks = items
            .iter()
            .filter_map(Value::as_str)
            .map(str::to_string)
            .collect();
    }
    summary.secret_blocking_count = json
        .get("blocking_secret_findings_count")
        .and_then(Value::as_u64)
        .unwrap_or(0) as usize;
    summary.secret_warning_count = json
        .get("warning_secret_findings_count")
        .and_then(Value::as_u64)
        .unwrap_or(0) as usize;
    summary.secret_manual_check_count = json
        .get("manual_check_secret_findings_count")
        .and_then(Value::as_u64)
        .unwrap_or(0) as usize;
    summary.ai_blocked_by_secret_scan = json
        .get("ai_blocked_by_secret_scan")
        .and_then(Value::as_bool)
        .unwrap_or(false);
    summary.apply_blocked_by_secret_scan = json
        .get("apply_blocked_by_secret_scan")
        .and_then(Value::as_bool)
        .unwrap_or(false);
    if let Some(value) = json.get("secret_scan_report").and_then(Value::as_str) {
        summary.secret_scan_report = Some(value.to_string());
    }
    if let Some(items) = json
        .get("blocking_secret_findings")
        .and_then(Value::as_array)
    {
        summary.secret_blocking_findings = items
            .iter()
            .filter_map(Value::as_str)
            .map(str::to_string)
            .collect();
    }
}

fn read_execution_result(output_dir: &Path, summary: &mut AppStudioResultSummary) {
    let path = output_dir.join("execution_test_result.json");
    let Some(json) = read_json(&path) else {
        return;
    };
    if let Some(value) = json.get("overall_status").and_then(Value::as_str) {
        summary.execution_status = Some(value.to_string());
    }
    if let Some(value) = json.get("approval_allowed").and_then(Value::as_bool) {
        summary.approval_allowed = Some(value);
    }
    summary.approval_blocking_warnings_count = json
        .get("approval_blocking_warnings_count")
        .and_then(Value::as_u64)
        .unwrap_or(0) as usize;
    summary.non_blocking_warnings_count = json
        .get("non_blocking_warnings_count")
        .and_then(Value::as_u64)
        .unwrap_or(0) as usize;
    summary.info_count = json.get("info_count").and_then(Value::as_u64).unwrap_or(0) as usize;
    summary.unresolved_distribution_risks_count = json
        .get("unresolved_distribution_risks_count")
        .and_then(Value::as_u64)
        .unwrap_or(0) as usize;
    summary.approval_blocking_reasons = string_array(json.get("approval_blocking_reasons"));
    summary.non_blocking_warning_summaries =
        string_array(json.get("non_blocking_warning_summaries"));
}

fn read_timing_result(output_dir: &Path, summary: &mut AppStudioResultSummary) {
    let path = output_dir.join("timing_report.json");
    let Some(json) = read_json(&path) else {
        return;
    };
    summary.timing_report = Some(path.display().to_string());
    summary.timing_total_seconds = json
        .get("actual_total_seconds")
        .and_then(number_value)
        .or_else(|| json.get("wall_clock_total_seconds").and_then(number_value))
        .or_else(|| json.get("total_duration_seconds").and_then(number_value));
    summary.timing_estimated_total_seconds =
        json.get("estimated_total_seconds").and_then(number_value);
    summary.timing_actual_total_seconds = json.get("actual_total_seconds").and_then(number_value);
    summary.timing_prediction_error_seconds =
        json.get("prediction_error_seconds").and_then(number_value);
    summary.timing_prediction_source = json
        .get("prediction_source")
        .and_then(Value::as_str)
        .map(str::to_string);
    summary.timing_wall_clock_total_seconds =
        json.get("wall_clock_total_seconds").and_then(number_value);
    summary.timing_cli_measured_total_seconds = json
        .get("cli_measured_total_seconds")
        .and_then(number_value);
    summary.timing_unmeasured_overhead_seconds = json
        .get("unmeasured_overhead_seconds")
        .and_then(number_value);
    if let Some(items) = json.get("phases").and_then(Value::as_array) {
        summary.timing_phases = items
            .iter()
            .filter_map(|item| {
                Some(AppStudioTimingPhase {
                    phase: item.get("phase")?.as_str()?.to_string(),
                    label: item
                        .get("label")
                        .and_then(Value::as_str)
                        .unwrap_or_else(|| item.get("phase").and_then(Value::as_str).unwrap_or(""))
                        .to_string(),
                    status: item
                        .get("status")
                        .and_then(Value::as_str)
                        .unwrap_or("unknown")
                        .to_string(),
                    duration_seconds: item.get("duration_seconds").and_then(Value::as_f64),
                })
            })
            .collect();
    }
}

fn number_value(value: &Value) -> Option<f64> {
    value
        .as_f64()
        .or_else(|| value.as_i64().map(|number| number as f64))
        .or_else(|| value.as_u64().map(|number| number as f64))
}

fn read_runtime_result(output_dir: &Path, summary: &mut AppStudioResultSummary) {
    let path = output_dir.join("runtime_check_result.json");
    let Some(json) = read_json(&path) else {
        return;
    };
    if let Some(value) = json.get("overall_status").and_then(Value::as_str) {
        summary.runtime_status = Some(value.to_string());
    }
}

fn string_array(value: Option<&Value>) -> Vec<String> {
    value
        .and_then(Value::as_array)
        .map(|items| {
            items
                .iter()
                .filter_map(Value::as_str)
                .map(str::to_string)
                .collect()
        })
        .unwrap_or_default()
}

fn read_app_pack(output_dir: &Path, summary: &mut AppStudioResultSummary) {
    let app_pack_dir = output_dir.join("app_pack");
    let Ok(entries) = std::fs::read_dir(app_pack_dir) else {
        return;
    };
    for entry in entries.flatten() {
        let path = entry.path();
        if path.extension().and_then(|value| value.to_str()) == Some("zip") {
            summary.app_pack = Some(path.display().to_string());
            return;
        }
    }
}

fn read_enabled(root: &Path, summary: &mut AppStudioResultSummary) {
    let Some(app_id) = summary.app_id.as_deref() else {
        return;
    };
    let Some(json) = read_json(&root.join("release").join("app_manifest.json")) else {
        return;
    };
    summary.manifest_enabled = json
        .get("apps")
        .and_then(|apps| apps.get(app_id))
        .and_then(|entry| entry.get("enabled"))
        .and_then(Value::as_bool);
    summary.enabled = summary.manifest_enabled;
}

fn read_approval_record(root: &Path, summary: &mut AppStudioResultSummary) {
    let Some(app_id) = summary.app_id.as_deref() else {
        return;
    };
    let path = root
        .join("data")
        .join("logs")
        .join("app_studio")
        .join(format!("{app_id}_approval_record.md"));
    if !path.is_file() {
        return;
    }
    summary.approval_record_path = Some(path.display().to_string());
    let Ok(text) = std::fs::read_to_string(&path) else {
        summary.approval_failure_summary = Some("approval_record.md could not be read".to_string());
        return;
    };
    summary.approval_record_status = parse_record_bullet(&text, "status");
    summary.verify_release_status = parse_record_bullet(&text, "verify_release_after");
    let failures = section_bullets(&text, "## Failures");
    if !failures.is_empty() {
        summary.approval_failure_summary = Some(failures.join(" | "));
    }
    let verify_failures = extract_json_array_preview(&text, "\"rollback_failures\"")
        .or_else(|| extract_json_array_preview(&text, "\"new_failures\""))
        .or_else(|| extract_ng_lines_preview(&text));
    summary.verify_release_failure_summary = verify_failures;
}

fn read_catalog_status(root: &Path, summary: &mut AppStudioResultSummary) {
    let Some(app_id) = summary.app_id.as_deref() else {
        return;
    };
    let app_yaml = root.join("apps").join(app_id).join("app.yaml");
    if !app_yaml.is_file() {
        summary.catalog_visible = Some(false);
        summary.catalog_enabled = Some(false);
        summary.catalog_disabled_reason = Some("app_yaml_missing".to_string());
        return;
    }
    match crate::manifest::load_apps(root) {
        Ok(apps) => {
            if let Some(app) = apps.into_iter().find(|app| app.id == app_id) {
                summary.catalog_enabled = Some(app.enabled);
                summary.catalog_visible = Some(app.enabled);
                if !app.enabled {
                    summary.catalog_disabled_reason = app
                        .disabled_reason
                        .or_else(|| Some("disabled_by_manifest_or_catalog_validation".to_string()));
                }
            } else {
                summary.catalog_visible = Some(false);
                summary.catalog_enabled = Some(false);
                summary.catalog_disabled_reason = Some("not_found_in_catalog".to_string());
            }
        }
        Err(error) => {
            summary.catalog_visible = Some(false);
            summary.catalog_enabled = Some(false);
            summary.catalog_load_error = Some(error.to_string());
            summary.catalog_disabled_reason = Some("catalog_load_error".to_string());
        }
    }
}

fn parse_record_bullet(text: &str, key: &str) -> Option<String> {
    let prefix = format!("- {key}:");
    text.lines().find_map(|line| {
        let trimmed = line.trim();
        trimmed
            .strip_prefix(&prefix)
            .map(|value| value.trim().trim_matches('`').trim().to_string())
            .filter(|value| !value.is_empty())
    })
}

fn section_bullets(text: &str, heading: &str) -> Vec<String> {
    let mut in_section = false;
    let mut items = Vec::new();
    for line in text.lines() {
        let trimmed = line.trim();
        if trimmed.starts_with("## ") {
            in_section = trimmed == heading;
            continue;
        }
        if in_section {
            if let Some(value) = trimmed.strip_prefix("- ") {
                if !value.trim().is_empty() {
                    items.push(value.trim().to_string());
                }
            }
        }
    }
    items
}

fn extract_ng_lines_preview(text: &str) -> Option<String> {
    let lines = text
        .lines()
        .filter(|line| line.contains("[NG]"))
        .map(|line| line.trim().to_string())
        .take(5)
        .collect::<Vec<_>>();
    if lines.is_empty() {
        None
    } else {
        Some(lines.join(" | "))
    }
}

fn extract_json_array_preview(text: &str, key: &str) -> Option<String> {
    let start = text.find(key)?;
    let rest = &text[start..];
    let open = rest.find('[')?;
    let close = rest[open..].find(']')?;
    let raw = &rest[open..=open + close];
    let value: Value = serde_json::from_str(raw).ok()?;
    let items = value
        .as_array()?
        .iter()
        .filter_map(Value::as_str)
        .take(5)
        .map(str::to_string)
        .collect::<Vec<_>>();
    if items.is_empty() {
        None
    } else {
        Some(items.join(" | "))
    }
}

fn read_version(root: &Path, summary: &mut AppStudioResultSummary) {
    let Some(app_id) = summary.app_id.as_deref() else {
        return;
    };
    let manifest_version =
        read_json(&root.join("release").join("app_manifest.json")).and_then(|json| {
            json.get("apps")
                .and_then(|apps| apps.get(app_id))
                .and_then(|entry| entry.get("version"))
                .and_then(Value::as_str)
                .map(str::to_string)
        });
    if let Some(version) = manifest_version {
        summary.version = Some(version);
        return;
    }
    if summary.version.is_none() {
        if let Ok(text) = std::fs::read_to_string(root.join("apps").join(app_id).join("app.yaml")) {
            if let Ok(yaml) = serde_yaml::from_str::<serde_yaml::Value>(&text) {
                if let Some(version) = yaml_str(&yaml, &["admin", "version"]) {
                    summary.version = Some(version);
                }
            }
        }
    }
}

pub fn output_dir_from_app_yaml(root: &Path, app_id: &str) -> Option<PathBuf> {
    let app_yaml = root.join("apps").join(app_id).join("app.yaml");
    let text = std::fs::read_to_string(app_yaml).ok()?;
    for line in text.lines() {
        let trimmed = line.trim();
        if trimmed.starts_with("output_mirror:") {
            let value = trimmed.split_once(':')?.1.trim();
            let value = value.trim_matches('"').trim_matches('\'');
            if !value.is_empty() {
                return Some(PathBuf::from(value));
            }
        }
    }
    None
}

fn read_json(path: &Path) -> Option<Value> {
    let text = std::fs::read_to_string(path).ok()?;
    serde_json::from_str(&text).ok()
}

fn yaml_str(value: &serde_yaml::Value, path: &[&str]) -> Option<String> {
    let mut current = value;
    for key in path {
        current = current.get(*key)?;
    }
    current.as_str().map(str::to_string)
}
