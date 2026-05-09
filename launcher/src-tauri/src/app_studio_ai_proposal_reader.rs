use base64::{engine::general_purpose, Engine as _};
use serde::Serialize;
use serde_json::Value;
use std::path::Path;

#[derive(Debug, Serialize, Clone, Default)]
#[serde(rename_all = "camelCase")]
pub struct AppStudioAiMetadataSuggestion {
    pub app_id: Option<String>,
    pub name: Option<String>,
    pub short_description: Option<String>,
    pub description: Option<String>,
    pub categories: Vec<String>,
    pub keywords: Vec<String>,
    pub examples: Vec<String>,
    pub use_cases: Vec<String>,
    pub inputs: Vec<String>,
    pub outputs: Vec<String>,
    pub notes: Vec<String>,
    pub icon_prompt: Option<String>,
    pub release_notes: Vec<String>,
    pub change_summary: Option<String>,
    pub ai_report: Option<String>,
}

#[derive(Debug, Serialize, Clone, Default)]
#[serde(rename_all = "camelCase")]
pub struct AppStudioAiIconCandidateSuggestion {
    pub candidate_id: String,
    pub number: usize,
    pub source: String,
    pub prompt: Option<String>,
    pub model: Option<String>,
    pub status: Option<String>,
    pub resolution: Option<String>,
    pub fallback: bool,
    pub file_name: Option<String>,
    pub url_file_name: Option<String>,
    pub png_data_url: Option<String>,
    pub url: Option<String>,
    pub notes: Option<String>,
    pub revision_of: Option<String>,
    pub api: Option<String>,
    pub content_type: Option<String>,
    pub fallback_reason: Option<String>,
    pub error_category: Option<String>,
    pub concept_id: Option<String>,
    pub concept: Option<Value>,
    pub style_family: Option<String>,
    pub scores: Option<Value>,
    pub score_total: Option<f64>,
    pub score_basis: Option<String>,
    pub semantic_score: Option<f64>,
    pub specificity_score: Option<f64>,
    pub small_size_score: Option<f64>,
    pub aesthetic_score: Option<f64>,
    pub revision_follow_score: Option<f64>,
    pub generic_risk_score: Option<f64>,
    pub quality_total: Option<f64>,
    pub quality_label: Option<String>,
    pub quality_reasons: Vec<String>,
    pub quality_warnings: Vec<String>,
    pub image_evaluation_status: Option<String>,
    pub image_evaluation_note: Option<String>,
}

#[derive(Debug, Serialize, Clone, Default)]
#[serde(rename_all = "camelCase")]
pub struct AppStudioAiIconSuggestion {
    pub prompt_initial: Option<String>,
    pub prompt_revision: Option<String>,
    pub function_interpretation: Option<Value>,
    pub image_api_summary: Option<Value>,
    pub candidate_svg: Option<String>,
    pub final_svg: Option<String>,
    pub fallback_svg: Option<String>,
    pub candidate_png_data_url: Option<String>,
    pub final_png_data_url: Option<String>,
    pub candidate_url: Option<String>,
    pub candidates: Vec<AppStudioAiIconCandidateSuggestion>,
    pub ai_report: Option<String>,
}

#[derive(Debug, Serialize, Clone, Default)]
#[serde(rename_all = "camelCase")]
pub struct AppStudioAiProposal {
    pub ok: bool,
    pub output_dir: Option<String>,
    pub metadata: AppStudioAiMetadataSuggestion,
    pub icon: AppStudioAiIconSuggestion,
    pub warnings: Vec<String>,
}

pub fn read_ai_proposal(output_dir: Option<&Path>) -> AppStudioAiProposal {
    let mut proposal = AppStudioAiProposal::default();
    let Some(output_dir) = output_dir else {
        proposal
            .warnings
            .push("Output directory was not found. Run Suggest first.".to_string());
        return proposal;
    };
    proposal.output_dir = Some(output_dir.display().to_string());
    if !output_dir.is_dir() {
        proposal
            .warnings
            .push("Output directory does not exist. Run Suggest first.".to_string());
        return proposal;
    }

    let proposed_yaml = output_dir.join("proposed_app.yaml");
    if let Ok(text) = std::fs::read_to_string(&proposed_yaml) {
        if let Ok(yaml) = serde_yaml::from_str::<serde_yaml::Value>(&text) {
            proposal.metadata = metadata_from_yaml(&yaml);
        } else {
            proposal
                .warnings
                .push("proposed_app.yaml could not be parsed.".to_string());
        }
    } else {
        proposal
            .warnings
            .push("proposed_app.yaml was not found. Run Suggest first.".to_string());
    }

    let icon_work = output_dir.join("icon_work");
    proposal.icon.prompt_initial = read_text_optional(&icon_work.join("icon_prompt_initial.md"));
    proposal.icon.prompt_revision = read_text_optional(&icon_work.join("icon_prompt_revision.md"));
    proposal.icon.candidate_svg = read_text_optional(&icon_work.join("icon_candidate_1.svg"));
    proposal.icon.final_svg = read_text_optional(&icon_work.join("icon_final.svg"));
    proposal.icon.fallback_svg = read_text_optional(&icon_work.join("icon_fallback.svg"))
        .or_else(|| proposal.icon.final_svg.clone())
        .or_else(|| proposal.icon.candidate_svg.clone());
    proposal.icon.candidate_url = read_text_optional(&icon_work.join("icon_candidate_1.url.txt"));
    proposal.icon.ai_report = read_text_optional(&icon_work.join("ai_generation_report.md"));
    proposal.icon.function_interpretation = read_icon_function_interpretation(&icon_work);
    proposal.icon.image_api_summary = read_icon_image_api_summary(&icon_work);
    proposal.icon.candidate_png_data_url =
        read_png_data_url_optional(&icon_work.join("icon_candidate_1.png"));
    proposal.icon.final_png_data_url =
        read_png_data_url_optional(&icon_work.join("icon_final.png"));
    proposal.icon.candidates = read_icon_candidates(&icon_work);
    if proposal.icon.candidate_png_data_url.is_none() {
        proposal.icon.candidate_png_data_url = proposal
            .icon
            .candidates
            .iter()
            .find_map(|candidate| candidate.png_data_url.clone());
    }
    if proposal.icon.candidate_url.is_none() {
        proposal.icon.candidate_url = proposal
            .icon
            .candidates
            .iter()
            .find_map(|candidate| candidate.url.clone());
    }

    if proposal.metadata.icon_prompt.is_none() {
        proposal.metadata.icon_prompt = proposal
            .icon
            .prompt_revision
            .clone()
            .filter(|value| !value.trim().is_empty())
            .or_else(|| proposal.icon.prompt_initial.clone());
    }
    fill_metadata_ai_report(output_dir, &mut proposal.metadata);
    fill_release_notes(output_dir, &mut proposal.metadata);
    proposal.ok = proposal.warnings.is_empty()
        || proposal.metadata.name.is_some()
        || proposal.icon.final_png_data_url.is_some()
        || proposal.icon.candidate_png_data_url.is_some()
        || proposal.icon.fallback_svg.is_some();
    proposal
}

fn metadata_from_yaml(yaml: &serde_yaml::Value) -> AppStudioAiMetadataSuggestion {
    AppStudioAiMetadataSuggestion {
        app_id: yaml_str(yaml, &["id"]),
        name: yaml_str(yaml, &["name"]),
        short_description: yaml_str(yaml, &["display", "short_description"]),
        description: yaml_str(yaml, &["detail", "description"]),
        categories: yaml_string_list(yaml, &["display", "categories"]),
        keywords: yaml_string_list(yaml, &["search", "keywords"]),
        examples: yaml_string_list(yaml, &["search", "examples"]),
        use_cases: yaml_string_list(yaml, &["detail", "use_cases"]),
        inputs: yaml_string_list(yaml, &["detail", "inputs"]),
        outputs: yaml_string_list(yaml, &["detail", "outputs"]),
        notes: yaml_string_list(yaml, &["detail", "notes"]),
        icon_prompt: None,
        release_notes: yaml_string_list(yaml, &["release", "release_notes"]),
        change_summary: yaml_str(yaml, &["release", "change_summary"]),
        ai_report: None,
    }
}

fn fill_metadata_ai_report(output_dir: &Path, metadata: &mut AppStudioAiMetadataSuggestion) {
    let Some(json) = read_json(&output_dir.join("import_plan.json")) else {
        return;
    };
    metadata.ai_report = json
        .get("metadata_ai_report")
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(str::to_string);
}

fn fill_release_notes(output_dir: &Path, metadata: &mut AppStudioAiMetadataSuggestion) {
    let Some(json) = read_json(&output_dir.join("import_plan.json")) else {
        return;
    };
    let app_id = json.get("app_id").and_then(Value::as_str).unwrap_or("app");
    let version = json
        .get("version")
        .and_then(Value::as_str)
        .unwrap_or("unknown");
    let mode = json
        .get("selected_build_mode")
        .and_then(Value::as_str)
        .unwrap_or("unknown");
    if metadata.release_notes.is_empty() {
        metadata.release_notes = vec![
            format!("Update {app_id} to version {version}."),
            format!("Build mode: {mode}. Review execution_test_result.json before approval."),
        ];
    }
    if metadata.change_summary.is_none() {
        metadata.change_summary =
            Some(format!("Update {app_id} to version {version} with {mode}."));
    }
}

fn yaml_str(value: &serde_yaml::Value, path: &[&str]) -> Option<String> {
    let mut current = value;
    for key in path {
        current = current.get(*key)?;
    }
    current.as_str().map(str::to_string)
}

fn yaml_string_list(value: &serde_yaml::Value, path: &[&str]) -> Vec<String> {
    let mut current = value;
    for key in path {
        let serde_yaml::Value::Mapping(map) = current else {
            return Vec::new();
        };
        let Some(next) = map.get(&serde_yaml::Value::String((*key).to_string())) else {
            return Vec::new();
        };
        current = next;
    }
    match current {
        serde_yaml::Value::Sequence(items) => items
            .iter()
            .filter_map(|item| item.as_str().map(|value| value.trim().to_string()))
            .filter(|value| !value.is_empty())
            .collect(),
        serde_yaml::Value::String(value) if !value.trim().is_empty() => {
            vec![value.trim().to_string()]
        }
        _ => Vec::new(),
    }
}

fn read_text_optional(path: &Path) -> Option<String> {
    std::fs::read_to_string(path)
        .ok()
        .map(|value| value.trim().to_string())
        .filter(|value| !value.is_empty())
}

fn read_png_data_url_optional(path: &Path) -> Option<String> {
    let bytes = std::fs::read(path).ok()?;
    Some(format!(
        "data:image/png;base64,{}",
        general_purpose::STANDARD.encode(bytes)
    ))
}

fn read_icon_function_interpretation(icon_work: &Path) -> Option<Value> {
    read_json(&icon_work.join("candidate_manifest.json"))
        .and_then(|json| json.get("function_interpretation").cloned())
        .filter(|value| !value.is_null())
}

fn read_icon_image_api_summary(icon_work: &Path) -> Option<Value> {
    read_json(&icon_work.join("candidate_manifest.json"))
        .and_then(|json| json.get("image_api_summary").cloned())
        .filter(|value| !value.is_null())
}

fn read_icon_candidates(icon_work: &Path) -> Vec<AppStudioAiIconCandidateSuggestion> {
    let mut candidates = Vec::new();
    if let Some(json) = read_json(&icon_work.join("candidate_manifest.json")) {
        if let Some(items) = json.get("candidates").and_then(Value::as_array) {
            for (index, item) in items.iter().enumerate() {
                let file_name = item
                    .get("file_name")
                    .and_then(Value::as_str)
                    .map(str::trim)
                    .filter(|value| !value.is_empty())
                    .map(str::to_string);
                let url_file_name = item
                    .get("url_file_name")
                    .and_then(Value::as_str)
                    .map(str::trim)
                    .filter(|value| !value.is_empty())
                    .map(str::to_string);
                let png_data_url = file_name
                    .as_deref()
                    .and_then(|name| read_png_data_url_optional(&icon_work.join(name)));
                let url = item
                    .get("url")
                    .and_then(Value::as_str)
                    .map(str::trim)
                    .filter(|value| !value.is_empty())
                    .map(str::to_string)
                    .or_else(|| {
                        url_file_name
                            .as_deref()
                            .and_then(|name| read_text_optional(&icon_work.join(name)))
                    });
                candidates.push(AppStudioAiIconCandidateSuggestion {
                    candidate_id: item
                        .get("candidate_id")
                        .or_else(|| item.get("id"))
                        .and_then(Value::as_str)
                        .map(str::to_string)
                        .unwrap_or_else(|| format!("icon_candidate_{}", index + 1)),
                    number: item
                        .get("number")
                        .and_then(Value::as_u64)
                        .map(|value| value as usize)
                        .unwrap_or(index + 1),
                    source: item
                        .get("source")
                        .and_then(Value::as_str)
                        .unwrap_or("unknown")
                        .to_string(),
                    prompt: item
                        .get("prompt")
                        .and_then(Value::as_str)
                        .map(str::to_string),
                    model: item
                        .get("model")
                        .and_then(Value::as_str)
                        .map(str::to_string),
                    status: item
                        .get("status")
                        .and_then(Value::as_str)
                        .map(str::to_string),
                    resolution: item
                        .get("resolution")
                        .and_then(Value::as_str)
                        .map(str::to_string),
                    fallback: item
                        .get("fallback")
                        .and_then(Value::as_bool)
                        .unwrap_or(false),
                    file_name,
                    url_file_name,
                    png_data_url,
                    url,
                    notes: item
                        .get("notes")
                        .and_then(Value::as_str)
                        .map(str::to_string),
                    revision_of: item
                        .get("revision_of")
                        .and_then(Value::as_str)
                        .map(str::to_string),
                    api: item.get("api").and_then(Value::as_str).map(str::to_string),
                    content_type: item
                        .get("content_type")
                        .and_then(Value::as_str)
                        .map(str::to_string),
                    fallback_reason: item
                        .get("fallback_reason")
                        .and_then(Value::as_str)
                        .map(str::to_string),
                    error_category: item
                        .get("error_category")
                        .and_then(Value::as_str)
                        .map(str::to_string),
                    concept_id: item
                        .get("concept_id")
                        .and_then(Value::as_str)
                        .map(str::to_string),
                    concept: item.get("concept").cloned(),
                    style_family: item
                        .get("concept")
                        .and_then(|concept| concept.get("style_family"))
                        .and_then(Value::as_str)
                        .map(str::to_string),
                    scores: item.get("scores").cloned(),
                    score_total: item.get("score_total").and_then(Value::as_f64),
                    score_basis: item
                        .get("score_basis")
                        .and_then(Value::as_str)
                        .map(str::to_string),
                    semantic_score: item.get("semantic_score").and_then(Value::as_f64),
                    specificity_score: item.get("specificity_score").and_then(Value::as_f64),
                    small_size_score: item.get("small_size_score").and_then(Value::as_f64),
                    aesthetic_score: item.get("aesthetic_score").and_then(Value::as_f64),
                    revision_follow_score: item
                        .get("revision_follow_score")
                        .and_then(Value::as_f64),
                    generic_risk_score: item.get("generic_risk_score").and_then(Value::as_f64),
                    quality_total: item.get("quality_total").and_then(Value::as_f64),
                    quality_label: item
                        .get("quality_label")
                        .and_then(Value::as_str)
                        .map(str::to_string),
                    quality_reasons: string_array(item.get("quality_reasons")),
                    quality_warnings: string_array(item.get("quality_warnings")),
                    image_evaluation_status: item
                        .get("image_evaluation_status")
                        .and_then(Value::as_str)
                        .map(str::to_string),
                    image_evaluation_note: item
                        .get("image_evaluation_note")
                        .and_then(Value::as_str)
                        .map(str::to_string),
                });
            }
        }
    }
    if candidates.is_empty() {
        if let Some(png_data_url) =
            read_png_data_url_optional(&icon_work.join("icon_candidate_1.png"))
        {
            candidates.push(AppStudioAiIconCandidateSuggestion {
                candidate_id: "icon_candidate_1".to_string(),
                number: 1,
                source: "legacy".to_string(),
                prompt: read_text_optional(&icon_work.join("icon_prompt_revision.md"))
                    .or_else(|| read_text_optional(&icon_work.join("icon_prompt_initial.md"))),
                model: None,
                status: Some("legacy".to_string()),
                resolution: None,
                fallback: false,
                file_name: Some("icon_candidate_1.png".to_string()),
                url_file_name: None,
                png_data_url: Some(png_data_url),
                url: None,
                notes: Some("Legacy icon_candidate_1.png candidate.".to_string()),
                revision_of: None,
                api: None,
                content_type: None,
                fallback_reason: None,
                error_category: None,
                concept_id: None,
                concept: None,
                style_family: None,
                scores: None,
                score_total: None,
                score_basis: None,
                semantic_score: None,
                specificity_score: None,
                small_size_score: None,
                aesthetic_score: None,
                revision_follow_score: None,
                generic_risk_score: None,
                quality_total: None,
                quality_label: None,
                quality_reasons: Vec::new(),
                quality_warnings: Vec::new(),
                image_evaluation_status: None,
                image_evaluation_note: None,
            });
        } else if let Some(url) = read_text_optional(&icon_work.join("icon_candidate_1.url.txt")) {
            candidates.push(AppStudioAiIconCandidateSuggestion {
                candidate_id: "icon_candidate_1".to_string(),
                number: 1,
                source: "legacy".to_string(),
                prompt: read_text_optional(&icon_work.join("icon_prompt_revision.md"))
                    .or_else(|| read_text_optional(&icon_work.join("icon_prompt_initial.md"))),
                model: None,
                status: Some("legacy".to_string()),
                resolution: None,
                fallback: false,
                file_name: None,
                url_file_name: Some("icon_candidate_1.url.txt".to_string()),
                png_data_url: None,
                url: Some(url),
                notes: Some("Legacy icon_candidate_1.url.txt candidate.".to_string()),
                revision_of: None,
                api: None,
                content_type: None,
                fallback_reason: None,
                error_category: None,
                concept_id: None,
                concept: None,
                style_family: None,
                scores: None,
                score_total: None,
                score_basis: None,
                semantic_score: None,
                specificity_score: None,
                small_size_score: None,
                aesthetic_score: None,
                revision_follow_score: None,
                generic_risk_score: None,
                quality_total: None,
                quality_label: None,
                quality_reasons: Vec::new(),
                quality_warnings: Vec::new(),
                image_evaluation_status: None,
                image_evaluation_note: None,
            });
        }
    }
    candidates
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

fn read_json(path: &Path) -> Option<Value> {
    let text = std::fs::read_to_string(path).ok()?;
    serde_json::from_str(&text).ok()
}
