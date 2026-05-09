use crate::app_studio_types::{
    AppStudioEditableMetadata, AppStudioIconOverride, AppStudioImportRequest,
};
use base64::{engine::general_purpose, Engine as _};
use serde_json::{Map, Value};
use std::fs;
use std::path::PathBuf;

pub(crate) fn write_metadata_override_file(
    request: &AppStudioImportRequest,
) -> Result<Option<(PathBuf, Vec<String>)>, String> {
    let Some((payload, keys)) = metadata_override_payload(&request.metadata) else {
        return Ok(None);
    };
    let dir = override_dir("metadata_overrides");
    fs::create_dir_all(&dir)
        .map_err(|_| "Could not create App Studio metadata override directory.".to_string())?;
    let path = override_file_path(&dir, &request.app_id, "json");
    write_json_payload(&path, &payload, "App Studio metadata override")?;
    Ok(Some((path, keys)))
}

pub(crate) fn write_icon_override_file(
    request: &AppStudioImportRequest,
) -> Result<Option<(PathBuf, String)>, String> {
    let Some((payload, source)) = icon_override_payload(&request.icon_override)? else {
        return Ok(None);
    };
    let dir = override_dir("icon_overrides");
    fs::create_dir_all(&dir)
        .map_err(|_| "Could not create App Studio icon override directory.".to_string())?;
    let path = override_file_path(&dir, &request.app_id, "json");
    write_json_payload(&path, &payload, "App Studio icon override")?;
    Ok(Some((path, source)))
}

pub(crate) fn write_icon_revision_image_file(
    request: &AppStudioImportRequest,
) -> Result<Option<PathBuf>, String> {
    let Some(data_url) = request
        .icon_revision_image
        .as_deref()
        .map(str::trim)
        .filter(|value| !value.is_empty())
    else {
        return Ok(None);
    };
    let bytes = decode_icon_revision_png_data_url(data_url)?;
    let dir = override_dir("icon_revision_images");
    fs::create_dir_all(&dir)
        .map_err(|_| "Could not create App Studio icon revision image directory.".to_string())?;
    let path = override_file_path(&dir, &request.app_id, "png");
    fs::write(&path, bytes)
        .map_err(|_| "Could not write App Studio icon revision image file.".to_string())?;
    Ok(Some(path))
}

pub(crate) fn write_build_profile_override_file(
    request: &AppStudioImportRequest,
) -> Result<Option<PathBuf>, String> {
    let Some(payload) = build_profile_payload(&request.build_profile) else {
        return Ok(None);
    };
    let dir = override_dir("build_profile_overrides");
    fs::create_dir_all(&dir)
        .map_err(|_| "Could not create App Studio build profile override directory.".to_string())?;
    let path = override_file_path(&dir, &request.app_id, "json");
    write_json_payload(&path, &payload, "App Studio build profile override")?;
    Ok(Some(path))
}

fn override_dir(name: &str) -> PathBuf {
    crate::setup::user_data_root()
        .join("data")
        .join("app_studio")
        .join(name)
}

fn override_file_path(dir: &std::path::Path, app_id: &Option<String>, extension: &str) -> PathBuf {
    let app_stem = clean_optional(app_id).unwrap_or("pending");
    let stamp = chrono::Local::now().timestamp_millis();
    dir.join(format!(
        "{}_{}.{}",
        safe_file_stem(app_stem),
        stamp,
        extension
    ))
}

fn write_json_payload(path: &std::path::Path, payload: &Value, label: &str) -> Result<(), String> {
    let text = serde_json::to_string_pretty(payload)
        .map_err(|_| format!("Could not serialize {label}."))?;
    fs::write(path, text).map_err(|_| format!("Could not write {label} file."))
}

fn build_profile_payload(build_profile: &Option<Value>) -> Option<Value> {
    let value = build_profile.as_ref()?;
    match value {
        Value::Object(map) if map.is_empty() => None,
        Value::Null => None,
        _ => Some(value.clone()),
    }
}

fn icon_override_payload(
    icon_override: &Option<AppStudioIconOverride>,
) -> Result<Option<(Value, String)>, String> {
    let Some(icon_override) = icon_override.as_ref() else {
        return Ok(None);
    };
    let source = icon_override
        .selected_icon_source
        .as_deref()
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .unwrap_or("default_icon");
    if source == "default_icon" || source == "fallback_png" {
        return Ok(None);
    }
    if source != "candidate_png"
        && source != "final_png"
        && source != "ai_candidate_png"
        && source != "uploaded_png"
    {
        return Err("Icon override source is invalid.".to_string());
    }
    let png_data_url = icon_override
        .png_data_url
        .as_deref()
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .ok_or_else(|| "PNG icon data is required when adopting a PNG candidate.".to_string())?;
    if !png_data_url.starts_with("data:image/png;base64,") {
        return Err("PNG icon data must be a data:image/png;base64 URL.".to_string());
    }

    let mut map = Map::new();
    map.insert(
        "selected_icon_source".to_string(),
        Value::String(source.to_string()),
    );
    map.insert(
        "png_base64".to_string(),
        Value::String(png_data_url.to_string()),
    );
    if let Some(candidate_id) = icon_override
        .candidate_id
        .as_deref()
        .map(str::trim)
        .filter(|value| !value.is_empty())
    {
        map.insert(
            "candidate_id".to_string(),
            Value::String(candidate_id.to_string()),
        );
    }
    Ok(Some((Value::Object(map), source.to_string())))
}

fn decode_icon_revision_png_data_url(data_url: &str) -> Result<Vec<u8>, String> {
    let Some(encoded) = data_url.strip_prefix("data:image/png;base64,") else {
        return Err("Icon revision image must be a data:image/png;base64 URL.".to_string());
    };
    let bytes = general_purpose::STANDARD
        .decode(encoded)
        .map_err(|_| "Icon revision image data could not be decoded.".to_string())?;
    if bytes.len() < 8 || &bytes[0..8] != b"\x89PNG\r\n\x1a\n" {
        return Err("Icon revision image must be a PNG data URL.".to_string());
    }
    Ok(bytes)
}

fn metadata_override_payload(
    metadata: &Option<AppStudioEditableMetadata>,
) -> Option<(Value, Vec<String>)> {
    let metadata = metadata.as_ref()?;
    let mut map = Map::new();
    let mut keys = Vec::new();

    insert_string_override(
        &mut map,
        &mut keys,
        "short_description",
        metadata.short_description.as_deref(),
    );
    insert_string_override(
        &mut map,
        &mut keys,
        "description",
        metadata.description.as_deref(),
    );
    insert_string_override(
        &mut map,
        &mut keys,
        "change_summary",
        metadata.change_summary.as_deref(),
    );
    insert_list_override(
        &mut map,
        &mut keys,
        "categories",
        metadata.categories.as_ref(),
    );
    insert_list_override(&mut map, &mut keys, "keywords", metadata.keywords.as_ref());
    insert_list_override(&mut map, &mut keys, "examples", metadata.examples.as_ref());
    insert_list_override(
        &mut map,
        &mut keys,
        "use_cases",
        metadata.use_cases.as_ref(),
    );
    insert_list_override(&mut map, &mut keys, "inputs", metadata.inputs.as_ref());
    insert_list_override(&mut map, &mut keys, "outputs", metadata.outputs.as_ref());
    insert_list_override(&mut map, &mut keys, "notes", metadata.notes.as_ref());
    insert_list_override(
        &mut map,
        &mut keys,
        "release_notes",
        metadata.release_notes.as_ref(),
    );

    if map.is_empty() {
        None
    } else {
        Some((Value::Object(map), keys))
    }
}

fn insert_string_override(
    map: &mut Map<String, Value>,
    keys: &mut Vec<String>,
    key: &str,
    value: Option<&str>,
) {
    let Some(cleaned) = value.map(str::trim).filter(|value| !value.is_empty()) else {
        return;
    };
    map.insert(key.to_string(), Value::String(cleaned.to_string()));
    keys.push(key.to_string());
}

fn insert_list_override(
    map: &mut Map<String, Value>,
    keys: &mut Vec<String>,
    key: &str,
    value: Option<&Vec<String>>,
) {
    let Some(value) = value else {
        return;
    };
    let items: Vec<Value> = value
        .iter()
        .map(|item| item.trim())
        .filter(|item| !item.is_empty())
        .map(|item| Value::String(item.to_string()))
        .collect();
    if items.is_empty() {
        return;
    }
    map.insert(key.to_string(), Value::Array(items));
    keys.push(key.to_string());
}

fn clean_optional(value: &Option<String>) -> Option<&str> {
    value
        .as_deref()
        .map(str::trim)
        .filter(|value| !value.is_empty())
}

fn safe_file_stem(value: &str) -> String {
    let stem: String = value
        .chars()
        .map(|character| {
            if character.is_ascii_alphanumeric() || character == '_' || character == '-' {
                character
            } else {
                '_'
            }
        })
        .collect();
    if stem.is_empty() {
        "pending".to_string()
    } else {
        stem
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn metadata_override_payload_uses_only_non_empty_fields() {
        let metadata = Some(AppStudioEditableMetadata {
            short_description: Some(" Short ".to_string()),
            categories: Some(vec!["utility".to_string(), " ".to_string()]),
            keywords: Some(vec!["alpha".to_string()]),
            ..Default::default()
        });

        let (payload, keys) = metadata_override_payload(&metadata).unwrap();
        let object = payload.as_object().unwrap();

        assert_eq!(keys, vec!["short_description", "categories", "keywords"]);
        assert_eq!(
            object.get("short_description").and_then(Value::as_str),
            Some("Short")
        );
        assert_eq!(
            object.get("categories").and_then(Value::as_array).unwrap(),
            &vec![Value::String("utility".to_string())]
        );
    }

    #[test]
    fn icon_override_payload_accepts_png_data_url_only_for_adopted_png() {
        let icon_override = Some(AppStudioIconOverride {
            selected_icon_source: Some("candidate_png".to_string()),
            png_data_url: Some("data:image/png;base64,iVBORw0KGgo=".to_string()),
            candidate_id: Some("candidate_1".to_string()),
        });

        let (payload, source) = icon_override_payload(&icon_override).unwrap().unwrap();
        let object = payload.as_object().unwrap();

        assert_eq!(source, "candidate_png");
        assert_eq!(
            object.get("selected_icon_source").and_then(Value::as_str),
            Some("candidate_png")
        );
        assert_eq!(
            object.get("candidate_id").and_then(Value::as_str),
            Some("candidate_1")
        );
        assert!(object.get("png_base64").is_some());
        assert!(icon_override_payload(&Some(AppStudioIconOverride {
            selected_icon_source: Some("default_icon".to_string()),
            png_data_url: None,
            candidate_id: None,
        }))
        .unwrap()
        .is_none());
        assert!(icon_override_payload(&Some(AppStudioIconOverride {
            selected_icon_source: Some("candidate_png".to_string()),
            png_data_url: Some("not-base64".to_string()),
            candidate_id: None,
        }))
        .is_err());
    }

    #[test]
    fn build_profile_payload_skips_empty_values() {
        assert!(build_profile_payload(&None).is_none());
        assert!(build_profile_payload(&Some(Value::Null)).is_none());
        assert!(build_profile_payload(&Some(json!({}))).is_none());
        assert_eq!(
            build_profile_payload(&Some(json!({"create_app_env": true}))).unwrap(),
            json!({"create_app_env": true})
        );
    }

    #[test]
    fn icon_revision_image_decode_requires_png_data_url() {
        let png = decode_icon_revision_png_data_url("data:image/png;base64,iVBORw0KGgo=").unwrap();
        assert_eq!(&png[0..8], b"\x89PNG\r\n\x1a\n");
        assert!(decode_icon_revision_png_data_url("data:image/jpeg;base64,iVBORw0KGgo=").is_err());
        assert!(decode_icon_revision_png_data_url("data:image/png;base64,AAAA").is_err());
    }

    #[test]
    fn safe_file_stem_preserves_existing_filename_policy() {
        assert_eq!(safe_file_stem("app-id_1"), "app-id_1");
        assert_eq!(safe_file_stem("app id/1"), "app_id_1");
        assert_eq!(safe_file_stem(""), "pending");
    }
}
