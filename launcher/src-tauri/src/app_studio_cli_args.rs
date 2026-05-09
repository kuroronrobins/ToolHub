use crate::app_studio_commands::{AppStudioImportRequest, AppStudioUpdateRequest};
use std::path::{Path, PathBuf};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum AppStudioCliAction {
    Suggest,
    Apply,
}

impl AppStudioCliAction {
    pub(crate) fn from_action_name(action: &str) -> Self {
        if action == "apply" {
            Self::Apply
        } else {
            Self::Suggest
        }
    }

    fn flag(self) -> &'static str {
        match self {
            Self::Apply => "--apply",
            Self::Suggest => "--suggest",
        }
    }
}

#[derive(Debug, Clone, Copy, Default)]
pub(crate) struct AppStudioImportCliOverrides<'a> {
    pub metadata_override: Option<&'a Path>,
    pub icon_override: Option<&'a Path>,
    pub build_profile: Option<&'a Path>,
    pub icon_revision_image: Option<&'a Path>,
}

pub(crate) fn normalize_normal_import_request(
    request: &mut AppStudioImportRequest,
) -> Result<(), String> {
    let entry = PathBuf::from(request.entry.trim());
    if entry
        .extension()
        .and_then(|value| value.to_str())
        .map(|value| value.eq_ignore_ascii_case("exe"))
        .unwrap_or(false)
    {
        return Err("Normal App Studio registration accepts Python source only. Existing exe registration is not available in this flow.".to_string());
    }
    if request.create_app_env || request.rebuild_app_env {
        return Err("Normal App Studio registration uses an internal build_env, not runtime/app_envs options.".to_string());
    }
    request.build_mode = "frozen-folder".to_string();
    request.generate_lock = true;
    request.build_frozen_folder = true;
    request.verify_runtime = true;
    request.create_app_env = false;
    request.rebuild_app_env = false;
    Ok(())
}

pub(crate) fn import_request_from_update(
    request: &AppStudioUpdateRequest,
) -> AppStudioImportRequest {
    AppStudioImportRequest {
        entry: request.entry.clone(),
        source_root: None,
        app_id: Some(request.app_id.clone()),
        name: request.name.clone(),
        version: Some(request.new_version.clone()),
        build_mode: request.build_mode.clone(),
        icon_prompt: request.icon_prompt.clone(),
        icon_style_preset: request.icon_style_preset.clone(),
        icon_style_custom: request.icon_style_custom.clone(),
        icon_revision_image: request.icon_revision_image.clone(),
        metadata: request.metadata.clone(),
        icon_override: request.icon_override.clone(),
        build_profile: request.build_profile.clone(),
        create_app_env: request.create_app_env,
        rebuild_app_env: request.rebuild_app_env,
        generate_lock: request.generate_lock,
        build_frozen_folder: request.build_frozen_folder,
        verify_runtime: request.verify_runtime,
    }
}

pub(crate) fn build_import_cli_args(
    script: &Path,
    request: &AppStudioImportRequest,
    action: AppStudioCliAction,
    overrides: AppStudioImportCliOverrides<'_>,
) -> Vec<String> {
    let mut cli_args = vec![
        script.display().to_string(),
        "import".to_string(),
        "--entry".to_string(),
        request.entry.clone(),
        "--build-mode".to_string(),
        request.build_mode.clone(),
    ];
    if let Some(source_root) = clean_optional(&request.source_root) {
        cli_args.push("--source-root".to_string());
        cli_args.push(source_root.to_string());
    }
    if let Some(app_id) = clean_optional(&request.app_id) {
        cli_args.push("--app-id".to_string());
        cli_args.push(app_id.to_string());
    }
    if let Some(name) = clean_optional(&request.name) {
        cli_args.push("--name".to_string());
        cli_args.push(name.to_string());
    }
    if let Some(version) = clean_optional(&request.version) {
        cli_args.push("--version".to_string());
        cli_args.push(version.to_string());
    }
    if let Some(icon_prompt) = clean_optional(&request.icon_prompt) {
        cli_args.push("--icon-prompt".to_string());
        cli_args.push(icon_prompt.to_string());
    }
    if let Some(style_preset) = clean_optional(&request.icon_style_preset) {
        cli_args.push("--icon-style-preset".to_string());
        cli_args.push(style_preset.to_string());
    }
    if let Some(style_custom) = clean_optional(&request.icon_style_custom) {
        cli_args.push("--icon-style-custom".to_string());
        cli_args.push(style_custom.to_string());
    }
    if let Some(path) = overrides.icon_revision_image {
        cli_args.push("--icon-revision-image".to_string());
        cli_args.push(path.display().to_string());
    }
    if let Some(path) = overrides.metadata_override {
        cli_args.push("--metadata-override".to_string());
        cli_args.push(path.display().to_string());
    }
    if let Some(path) = overrides.icon_override {
        cli_args.push("--icon-override".to_string());
        cli_args.push(path.display().to_string());
    }
    if let Some(path) = overrides.build_profile {
        cli_args.push("--build-profile".to_string());
        cli_args.push(path.display().to_string());
    }
    if request.create_app_env {
        cli_args.push("--create-app-env".to_string());
    }
    if request.rebuild_app_env {
        cli_args.push("--rebuild-app-env".to_string());
    }
    if request.generate_lock {
        cli_args.push("--generate-lock".to_string());
    }
    if request.build_frozen_folder {
        cli_args.push("--build-frozen-folder".to_string());
    }
    if request.verify_runtime {
        cli_args.push("--verify-runtime".to_string());
    }
    cli_args.push(action.flag().to_string());
    cli_args
}

pub(crate) fn build_approve_cli_args(script: &Path, app_id: &str, strict: bool) -> Vec<String> {
    vec![
        script.display().to_string(),
        "approve".to_string(),
        "--app-id".to_string(),
        app_id.to_string(),
        approval_flag(strict).to_string(),
    ]
}

pub(crate) fn approval_flag(strict: bool) -> &'static str {
    if strict {
        "--strict-approval"
    } else {
        "--allow-warnings"
    }
}

pub(crate) fn approval_mode_name(strict: bool) -> &'static str {
    if strict {
        "StrictApproval"
    } else {
        "AllowWarnings"
    }
}

#[derive(Debug, Clone, Copy)]
pub(crate) struct AppStudioIconRegenerateCliOptions<'a> {
    pub app_id: &'a str,
    pub output_dir: &'a Path,
    pub user_revision_instruction: &'a str,
    pub revision_mode: &'a str,
    pub candidate_count: usize,
    pub image_quality_mode: &'a str,
    pub base_candidate_id: Option<&'a str>,
    pub icon_style_preset: Option<&'a str>,
    pub icon_style_custom: Option<&'a str>,
}

pub(crate) fn build_icon_regenerate_cli_args(
    script: &Path,
    options: AppStudioIconRegenerateCliOptions<'_>,
) -> Vec<String> {
    let mut cli_args = vec![
        script.display().to_string(),
        "icon-regenerate".to_string(),
        "--app-id".to_string(),
        options.app_id.to_string(),
        "--output-dir".to_string(),
        options.output_dir.display().to_string(),
        "--user-revision-instruction".to_string(),
        options.user_revision_instruction.to_string(),
        "--revision-mode".to_string(),
        options.revision_mode.to_string(),
        "--candidate-count".to_string(),
        options.candidate_count.to_string(),
        "--image-quality-mode".to_string(),
        options.image_quality_mode.to_string(),
    ];
    if let Some(base_candidate_id) = options.base_candidate_id {
        cli_args.push("--base-candidate-id".to_string());
        cli_args.push(base_candidate_id.to_string());
    }
    if let Some(style_preset) = options.icon_style_preset {
        cli_args.push("--icon-style-preset".to_string());
        cli_args.push(style_preset.to_string());
    }
    if let Some(style_custom) = options.icon_style_custom {
        cli_args.push("--icon-style-custom".to_string());
        cli_args.push(style_custom.to_string());
    }
    cli_args
}

pub(crate) fn build_image_test_cli_args(
    script: &Path,
    model_override: Option<&str>,
) -> Vec<String> {
    let mut cli_args = vec![script.display().to_string(), "image-test".to_string()];
    if let Some(model) = model_override
        .map(str::trim)
        .filter(|value| !value.is_empty())
    {
        cli_args.push("--image-model".to_string());
        cli_args.push(model.to_string());
    }
    cli_args
}

fn clean_optional(value: &Option<String>) -> Option<&str> {
    value
        .as_deref()
        .map(str::trim)
        .filter(|value| !value.is_empty())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::app_studio_commands::{AppStudioEditableMetadata, AppStudioIconOverride};
    use serde_json::json;

    fn base_import_request() -> AppStudioImportRequest {
        AppStudioImportRequest {
            entry: "C:\\work\\sample\\main.py".to_string(),
            source_root: None,
            app_id: Some("sample_app".to_string()),
            name: Some("Sample App".to_string()),
            version: Some("1.2.3".to_string()),
            build_mode: "frozen-folder".to_string(),
            icon_prompt: None,
            icon_style_preset: None,
            icon_style_custom: None,
            icon_revision_image: None,
            metadata: None,
            icon_override: None,
            build_profile: None,
            create_app_env: false,
            rebuild_app_env: false,
            generate_lock: true,
            build_frozen_folder: true,
            verify_runtime: true,
        }
    }

    fn has_arg_pair(args: &[String], key: &str, value: &str) -> bool {
        args.windows(2)
            .any(|pair| pair[0] == key && pair[1] == value)
    }

    #[test]
    fn normal_import_request_forces_frozen_folder_distribution_flags() {
        let mut request = base_import_request();
        request.build_mode = "auto".to_string();
        request.generate_lock = false;
        request.build_frozen_folder = false;
        request.verify_runtime = false;

        normalize_normal_import_request(&mut request).unwrap();

        assert_eq!(request.build_mode, "frozen-folder");
        assert!(request.generate_lock);
        assert!(request.build_frozen_folder);
        assert!(request.verify_runtime);
        assert!(!request.create_app_env);
        assert!(!request.rebuild_app_env);
    }

    #[test]
    fn normal_import_request_rejects_existing_exe_flow() {
        let mut request = base_import_request();
        request.entry = "C:\\work\\sample\\app.exe".to_string();

        let error = normalize_normal_import_request(&mut request).unwrap_err();

        assert!(error.contains("Python source only"));
    }

    #[test]
    fn import_suggest_args_keep_existing_flag_order() {
        let script = Path::new("tools/app_studio/main.py");
        let mut request = base_import_request();
        request.source_root = Some("C:\\work\\sample".to_string());
        request.icon_prompt = Some(" blue tool ".to_string());
        request.icon_style_preset = Some("flat".to_string());
        request.icon_style_custom = Some("thin lines".to_string());

        let args = build_import_cli_args(
            script,
            &request,
            AppStudioCliAction::Suggest,
            AppStudioImportCliOverrides {
                icon_revision_image: Some(Path::new("revision.png")),
                metadata_override: Some(Path::new("metadata.json")),
                icon_override: Some(Path::new("icon.json")),
                build_profile: Some(Path::new("profile.json")),
            },
        );

        assert_eq!(args[0], script.display().to_string());
        assert_eq!(args[1], "import");
        assert_eq!(args[2], "--entry");
        assert_eq!(args[3], request.entry);
        assert_eq!(args[4], "--build-mode");
        assert_eq!(args[5], "frozen-folder");
        assert!(has_arg_pair(&args, "--source-root", "C:\\work\\sample"));
        assert!(has_arg_pair(&args, "--app-id", "sample_app"));
        assert!(has_arg_pair(&args, "--name", "Sample App"));
        assert!(has_arg_pair(&args, "--version", "1.2.3"));
        assert!(has_arg_pair(&args, "--icon-prompt", "blue tool"));
        assert!(has_arg_pair(&args, "--icon-style-preset", "flat"));
        assert!(has_arg_pair(&args, "--icon-style-custom", "thin lines"));
        assert!(args.contains(&"--metadata-override".to_string()));
        assert!(args.contains(&"--icon-override".to_string()));
        assert!(args.contains(&"--build-profile".to_string()));
        assert!(args.contains(&"--generate-lock".to_string()));
        assert!(args.contains(&"--build-frozen-folder".to_string()));
        assert!(args.contains(&"--verify-runtime".to_string()));
        assert_eq!(args.last().map(String::as_str), Some("--suggest"));
    }

    #[test]
    fn import_apply_args_skip_false_build_options() {
        let script = Path::new("tools/app_studio/main.py");
        let mut request = base_import_request();
        request.generate_lock = false;
        request.build_frozen_folder = false;
        request.verify_runtime = false;

        let args = build_import_cli_args(
            script,
            &request,
            AppStudioCliAction::Apply,
            AppStudioImportCliOverrides::default(),
        );

        assert!(!args.contains(&"--generate-lock".to_string()));
        assert!(!args.contains(&"--build-frozen-folder".to_string()));
        assert!(!args.contains(&"--verify-runtime".to_string()));
        assert_eq!(args.last().map(String::as_str), Some("--apply"));
    }

    #[test]
    fn update_request_maps_to_import_request_without_source_root() {
        let update = AppStudioUpdateRequest {
            app_id: "sample_app".to_string(),
            entry: "C:\\work\\sample\\main.py".to_string(),
            name: Some("Sample App".to_string()),
            current_version: Some("1.2.2".to_string()),
            new_version: "1.2.3".to_string(),
            build_mode: "frozen-folder".to_string(),
            icon_prompt: Some("icon".to_string()),
            icon_style_preset: Some("flat".to_string()),
            icon_style_custom: Some("custom".to_string()),
            icon_revision_image: Some("data:image/png;base64,AAAA".to_string()),
            metadata: Some(AppStudioEditableMetadata {
                short_description: Some("short".to_string()),
                ..Default::default()
            }),
            icon_override: Some(AppStudioIconOverride {
                selected_icon_source: Some("adopted_png".to_string()),
                png_data_url: Some("data:image/png;base64,AAAA".to_string()),
                candidate_id: Some("candidate-1".to_string()),
            }),
            build_profile: Some(json!({"hidden_imports": ["pkg"]})),
            create_app_env: false,
            rebuild_app_env: false,
            generate_lock: true,
            build_frozen_folder: true,
            verify_runtime: true,
        };

        let import = import_request_from_update(&update);

        assert_eq!(import.entry, update.entry);
        assert_eq!(import.source_root, None);
        assert_eq!(import.app_id.as_deref(), Some("sample_app"));
        assert_eq!(import.version.as_deref(), Some("1.2.3"));
        assert_eq!(
            import
                .metadata
                .as_ref()
                .and_then(|metadata| metadata.short_description.as_deref()),
            Some("short")
        );
        assert_eq!(
            import
                .icon_override
                .as_ref()
                .and_then(|icon| icon.selected_icon_source.as_deref()),
            Some("adopted_png")
        );
        assert!(import.build_profile.is_some());
    }

    #[test]
    fn approve_args_include_strict_or_allow_warnings_flag() {
        let script = Path::new("tools/app_studio/main.py");

        assert_eq!(
            build_approve_cli_args(script, "sample_app", true),
            vec![
                script.display().to_string(),
                "approve".to_string(),
                "--app-id".to_string(),
                "sample_app".to_string(),
                "--strict-approval".to_string(),
            ]
        );
        assert_eq!(approval_flag(false), "--allow-warnings");
        assert_eq!(approval_mode_name(true), "StrictApproval");
    }

    #[test]
    fn icon_regenerate_args_include_optional_controls_only_when_present() {
        let script = Path::new("tools/app_studio/main.py");
        let args = build_icon_regenerate_cli_args(
            script,
            AppStudioIconRegenerateCliOptions {
                app_id: "sample_app",
                output_dir: Path::new("out"),
                user_revision_instruction: "make it simpler",
                revision_mode: "refine",
                candidate_count: 2,
                image_quality_mode: "high",
                base_candidate_id: Some("candidate-1"),
                icon_style_preset: Some("flat"),
                icon_style_custom: None,
            },
        );

        assert!(has_arg_pair(&args, "--app-id", "sample_app"));
        assert!(has_arg_pair(&args, "--output-dir", "out"));
        assert!(has_arg_pair(
            &args,
            "--user-revision-instruction",
            "make it simpler"
        ));
        assert!(has_arg_pair(&args, "--revision-mode", "refine"));
        assert!(has_arg_pair(&args, "--candidate-count", "2"));
        assert!(has_arg_pair(&args, "--image-quality-mode", "high"));
        assert!(has_arg_pair(&args, "--base-candidate-id", "candidate-1"));
        assert!(has_arg_pair(&args, "--icon-style-preset", "flat"));
        assert!(!args.contains(&"--icon-style-custom".to_string()));
    }

    #[test]
    fn image_test_args_trim_model_override() {
        let script = Path::new("tools/app_studio/main.py");

        assert_eq!(
            build_image_test_cli_args(script, Some(" gpt-image-1 ")),
            vec![
                script.display().to_string(),
                "image-test".to_string(),
                "--image-model".to_string(),
                "gpt-image-1".to_string(),
            ]
        );
        assert_eq!(
            build_image_test_cli_args(script, Some(" ")),
            vec![script.display().to_string(), "image-test".to_string()]
        );
    }
}
