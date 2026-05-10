use crate::app_studio_types::{AppStudioImportRequest, AppStudioPreflightResult};
use std::path::{Path, PathBuf};

#[derive(Debug, Clone)]
pub(crate) struct PythonCandidate {
    pub(crate) source: String,
    pub(crate) path: PathBuf,
}

pub(crate) fn runtime_python_path(root: &Path) -> PathBuf {
    root.join("runtime").join("python").join(if cfg!(windows) {
        "python.exe"
    } else {
        "python"
    })
}

pub(crate) fn find_python_candidate(root: &Path) -> Option<PythonCandidate> {
    let embedded = runtime_python_path(root);
    if embedded.is_file() {
        return Some(PythonCandidate {
            source: "runtime".to_string(),
            path: embedded,
        });
    }
    find_on_path(if cfg!(windows) {
        "python.exe"
    } else {
        "python"
    })
    .or_else(|| find_on_path("python"))
    .map(|path| PythonCandidate {
        source: "python".to_string(),
        path,
    })
    .or_else(|| {
        find_on_path("py").map(|path| PythonCandidate {
            source: "py".to_string(),
            path,
        })
    })
}

pub(crate) fn build_import_preflight_result(
    request: &AppStudioImportRequest,
    root: &Path,
    python_candidate: Option<PythonCandidate>,
) -> AppStudioPreflightResult {
    let mut warnings = Vec::new();
    let mut errors = Vec::new();

    let entry = PathBuf::from(request.entry.trim());
    let entry_exists = !request.entry.trim().is_empty() && entry.is_file();
    if request.entry.trim().is_empty() {
        errors.push("Entryファイルを指定してください。".to_string());
    } else if !entry_exists {
        errors.push("Entryファイルが見つかりません。".to_string());
    } else if let Err(error) = validate_entry_path(&entry) {
        errors.push(error);
    }
    if entry_exists {
        if let Err(error) = validate_source_root_path(&entry, request.source_root.as_deref()) {
            errors.push(error);
        }
    }
    if entry
        .extension()
        .and_then(|value| value.to_str())
        .map(|value| value.eq_ignore_ascii_case("exe"))
        .unwrap_or(false)
    {
        errors.push("Normal App Studio registration accepts Python source only. Existing exe registration is not available in this flow.".to_string());
    }

    let build_mode_valid = ["auto", "shared-env"].contains(&request.build_mode.as_str());
    if !build_mode_valid {
        errors.push("BuildModeが不正です。".to_string());
    }

    if request.create_app_env || request.rebuild_app_env {
        errors.push("Normal App Studio registration uses shared versioned runtime environments, not runtime/app_envs options.".to_string());
    }

    let app_id_valid = match clean_optional(&request.app_id) {
        Some(app_id) => match validate_app_id(app_id) {
            Ok(()) => true,
            Err(error) => {
                errors.push(error);
                false
            }
        },
        None => {
            warnings.push("AppIdが未入力です。CLI側の自動生成に任せます。".to_string());
            true
        }
    };

    let cli_status = crate::app_studio_cli::app_studio_cli_status(root);
    if !cli_status.cli_exists {
        errors.push(cli_status.message.clone());
    }

    let runtime_python_exists = runtime_python_path(root).is_file();

    let (python_source, python_path) = match python_candidate {
        Some(candidate) => (candidate.source, Some(candidate.path.display().to_string())),
        None => {
            errors.push(python_missing_message());
            ("missing".to_string(), None)
        }
    };

    AppStudioPreflightResult {
        ok: errors.is_empty(),
        entry_exists,
        app_id_valid,
        build_mode_valid,
        app_studio_cli_exists: cli_status.cli_exists,
        app_studio_cli_path: cli_status.cli_path,
        app_studio_repo_root: cli_status.repo_root,
        app_studio_cli_message: cli_status.message,
        python_source,
        python_path,
        runtime_python_exists,
        warnings,
        errors,
    }
}

pub(crate) fn validate_entry_path(entry: &Path) -> Result<(), String> {
    let lower = entry.to_string_lossy().to_lowercase();
    for marker in [".env", ".pem", ".key", "credentials", "secrets", "token"] {
        if lower.contains(marker) {
            return Err("Entryファイルのパスに秘密情報らしい名前が含まれています。".to_string());
        }
    }
    Ok(())
}

pub(crate) fn validate_source_root_path(
    entry: &Path,
    source_root: Option<&str>,
) -> Result<(), String> {
    let Some(value) = source_root.map(str::trim).filter(|value| !value.is_empty()) else {
        return Ok(());
    };
    let root = PathBuf::from(value);
    if !root.is_dir() {
        return Err("sourceRootフォルダが見つかりません。".to_string());
    }
    let entry_path = entry
        .canonicalize()
        .map_err(|_| "Entryファイルのパスを解決できません。".to_string())?;
    let root_path = root
        .canonicalize()
        .map_err(|_| "sourceRootフォルダのパスを解決できません。".to_string())?;
    if root_path.parent().is_none() || root_path.parent() == Some(root_path.as_path()) {
        return Err(
            "sourceRootが広すぎます。アプリのプロジェクトフォルダを指定してください。".to_string(),
        );
    }
    if !entry_path.starts_with(&root_path) {
        return Err("EntryファイルはsourceRoot配下に配置してください。".to_string());
    }
    Ok(())
}

pub(crate) fn validate_app_id(app_id: &str) -> Result<(), String> {
    let value = app_id.trim();
    if value.is_empty() || value.len() > 64 {
        return Err("AppIdは1文字以上64文字以下で指定してください。".to_string());
    }
    let mut chars = value.chars();
    let Some(first) = chars.next() else {
        return Err("AppIdを指定してください。".to_string());
    };
    if !first.is_ascii_lowercase() && !first.is_ascii_digit() {
        return Err("AppIdは英小文字または数字で開始してください。".to_string());
    }
    if !value
        .chars()
        .all(|ch| ch.is_ascii_lowercase() || ch.is_ascii_digit() || ch == '_' || ch == '-')
    {
        return Err(
            "AppIdには英小文字、数字、ハイフン、アンダースコアのみ使用できます。".to_string(),
        );
    }
    Ok(())
}

pub(crate) fn python_missing_message() -> String {
    "App Studioを実行するPythonが見つかりません。runtime/python/python.exeを配置するか、管理者の開発環境にpythonまたはpyを用意してください。通常ランチャー機能には影響しません。".to_string()
}

fn find_on_path(command: &str) -> Option<PathBuf> {
    let path = std::env::var_os("PATH")?;
    for dir in std::env::split_paths(&path) {
        let candidate = dir.join(command);
        if candidate.is_file() {
            return Some(candidate);
        }
        if cfg!(windows) {
            let exe_candidate = dir.join(format!("{command}.exe"));
            if exe_candidate.is_file() {
                return Some(exe_candidate);
            }
        }
    }
    None
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
    use crate::app_studio_types::AppStudioImportRequest;
    use serde_json::Value;
    use std::time::{SystemTime, UNIX_EPOCH};

    fn temp_root(name: &str) -> PathBuf {
        let suffix = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        std::env::temp_dir().join(format!("toolhub_app_studio_preflight_{name}_{suffix}"))
    }

    fn base_request(entry: &Path) -> AppStudioImportRequest {
        AppStudioImportRequest {
            entry: entry.display().to_string(),
            source_root: entry.parent().map(|path| path.display().to_string()),
            app_id: Some("my_tool".to_string()),
            name: Some("My Tool".to_string()),
            version: None,
            build_mode: "auto".to_string(),
            icon_prompt: None,
            icon_style_preset: None,
            icon_style_custom: None,
            icon_revision_image: None,
            metadata: None,
            icon_override: None,
            build_profile: None,
            create_app_env: false,
            rebuild_app_env: false,
            generate_lock: false,
            build_frozen_folder: false,
            verify_runtime: false,
        }
    }

    fn python_candidate() -> PythonCandidate {
        PythonCandidate {
            source: "python".to_string(),
            path: PathBuf::from("C:/Python/python.exe"),
        }
    }

    fn write_app_studio_cli(root: &Path) {
        let script = root.join("tools").join("app_studio").join("main.py");
        std::fs::create_dir_all(script.parent().unwrap()).unwrap();
        std::fs::write(script, b"print('app studio')").unwrap();
    }

    #[test]
    fn runtime_python_path_uses_existing_layout() {
        let root = PathBuf::from("C:/repo");
        let expected_name = if cfg!(windows) {
            "python.exe"
        } else {
            "python"
        };

        assert_eq!(
            runtime_python_path(&root),
            root.join("runtime").join("python").join(expected_name)
        );
    }

    #[test]
    fn find_python_candidate_prefers_embedded_runtime() {
        let root = temp_root("runtime_priority");
        let runtime_python = runtime_python_path(&root);
        std::fs::create_dir_all(runtime_python.parent().unwrap()).unwrap();
        std::fs::write(&runtime_python, b"").unwrap();

        let candidate = find_python_candidate(&root).expect("runtime python should be found");

        assert_eq!(candidate.source, "runtime");
        assert_eq!(candidate.path, runtime_python);

        let _ = std::fs::remove_dir_all(root);
    }

    #[test]
    fn build_import_preflight_result_accepts_python_entry_and_serializes_camel_case() {
        let root = temp_root("python_entry");
        let source = root.join("source");
        let entry = source.join("main.py");
        std::fs::create_dir_all(&source).unwrap();
        std::fs::write(&entry, b"print('ok')").unwrap();
        write_app_studio_cli(&root);
        let request = base_request(&entry);

        let result = build_import_preflight_result(&request, &root, Some(python_candidate()));

        assert!(result.ok);
        assert!(result.entry_exists);
        assert!(result.app_id_valid);
        assert!(result.build_mode_valid);
        assert!(result.app_studio_cli_exists);
        assert!(
            result
                .app_studio_cli_path
                .ends_with("tools\\app_studio\\main.py")
                || result
                    .app_studio_cli_path
                    .ends_with("tools/app_studio/main.py")
        );
        assert_eq!(result.python_source, "python");
        assert!(!result.runtime_python_exists);

        let value = serde_json::to_value(&result).expect("preflight result should serialize");
        assert_eq!(value["entryExists"], Value::Bool(true));
        assert_eq!(value["appIdValid"], Value::Bool(true));
        assert_eq!(value["buildModeValid"], Value::Bool(true));
        assert_eq!(value["appStudioCliExists"], Value::Bool(true));
        assert_eq!(value["pythonSource"], Value::String("python".to_string()));
        assert!(value.get("entry_exists").is_none());

        let mut shared_env_request = request.clone();
        shared_env_request.build_mode = "shared-env".to_string();
        let shared_env_result =
            build_import_preflight_result(&shared_env_request, &root, Some(python_candidate()));
        assert!(shared_env_result.build_mode_valid);

        let _ = std::fs::remove_dir_all(root);
    }

    #[test]
    fn build_import_preflight_result_rejects_exe_entry_and_invalid_app_id() {
        let root = temp_root("exe_entry");
        let source = root.join("source");
        let entry = source.join("app.exe");
        std::fs::create_dir_all(&source).unwrap();
        std::fs::write(&entry, b"not really an exe").unwrap();
        write_app_studio_cli(&root);
        let mut request = base_request(&entry);
        request.app_id = Some("BadId".to_string());

        let result = build_import_preflight_result(&request, &root, Some(python_candidate()));

        assert!(!result.ok);
        assert!(result.entry_exists);
        assert!(!result.app_id_valid);
        assert!(result.build_mode_valid);
        assert!(result
            .errors
            .iter()
            .any(|item| item.contains("Existing exe registration is not available")));
        assert!(result.errors.iter().any(|item| item.contains("AppId")));

        let _ = std::fs::remove_dir_all(root);
    }

    #[test]
    fn build_import_preflight_result_blocks_when_app_studio_cli_is_missing() {
        let root = temp_root("missing_cli");
        let source = root.join("source");
        let entry = source.join("main.py");
        std::fs::create_dir_all(&source).unwrap();
        std::fs::write(&entry, b"print('ok')").unwrap();
        let request = base_request(&entry);

        let result = build_import_preflight_result(&request, &root, Some(python_candidate()));

        assert!(!result.ok);
        assert!(!result.app_studio_cli_exists);
        assert!(result
            .errors
            .iter()
            .any(|item| item.contains("App Studio CLI")));

        let _ = std::fs::remove_dir_all(root);
    }
}
