use chrono::Local;
use serde::{Deserialize, Serialize};
use std::path::{Path, PathBuf};

const DEFAULT_API_KEY_SOURCE: &str = "windows_credential_manager";
const DEFAULT_IMAGE_MODEL: &str = "gpt-image-2";

#[derive(Debug, Serialize, Deserialize, Clone)]
#[serde(rename_all = "camelCase")]
pub struct AiSettings {
    pub ai_enabled: bool,
    pub text_model: String,
    pub image_model: String,
    pub api_key_source: String,
    pub updated_at: Option<String>,
}

#[derive(Debug, Serialize, Deserialize)]
struct AiSettingsFile {
    schema_version: u8,
    ai_enabled: bool,
    text_model: String,
    image_model: String,
    api_key_source: String,
    updated_at: String,
}

#[derive(Debug, Serialize, Clone)]
#[serde(rename_all = "camelCase")]
pub struct ApiKeyStatus {
    pub state: String,
    pub source: Option<String>,
    pub masked: Option<String>,
    pub credential_supported: bool,
    pub message: String,
}

#[derive(Debug, Serialize, Clone)]
#[serde(rename_all = "camelCase")]
pub struct AiConnectionTestResult {
    pub ok: bool,
    pub message: String,
    pub key_source: Option<String>,
    pub text_model_set: bool,
    pub image_model_set: bool,
}

pub fn settings_path(user_data_root: &Path) -> PathBuf {
    user_data_root.join("config").join("app_studio_ai.json")
}

pub fn load_settings_at(user_data_root: &Path) -> Result<AiSettings, String> {
    let path = settings_path(user_data_root);
    if !path.is_file() {
        return Ok(default_settings());
    }
    let text = std::fs::read_to_string(path).map_err(|error| error.to_string())?;
    let file: AiSettingsFile = serde_json::from_str(&text).map_err(|error| error.to_string())?;
    Ok(AiSettings {
        ai_enabled: file.ai_enabled,
        text_model: file.text_model,
        image_model: if file.image_model.trim().is_empty() {
            DEFAULT_IMAGE_MODEL.to_string()
        } else {
            file.image_model
        },
        api_key_source: file.api_key_source,
        updated_at: Some(file.updated_at),
    })
}

pub fn save_settings_at(user_data_root: &Path, settings: AiSettings) -> Result<AiSettings, String> {
    let now = Local::now().to_rfc3339();
    let cleaned = AiSettings {
        ai_enabled: settings.ai_enabled,
        text_model: settings.text_model.trim().to_string(),
        image_model: if settings.image_model.trim().is_empty() {
            DEFAULT_IMAGE_MODEL.to_string()
        } else {
            settings.image_model.trim().to_string()
        },
        api_key_source: if settings.api_key_source.trim().is_empty() {
            DEFAULT_API_KEY_SOURCE.to_string()
        } else {
            settings.api_key_source.trim().to_string()
        },
        updated_at: Some(now.clone()),
    };
    let file = AiSettingsFile {
        schema_version: 1,
        ai_enabled: cleaned.ai_enabled,
        text_model: cleaned.text_model.clone(),
        image_model: cleaned.image_model.clone(),
        api_key_source: cleaned.api_key_source.clone(),
        updated_at: now,
    };
    let path = settings_path(user_data_root);
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent).map_err(|error| error.to_string())?;
    }
    let text = serde_json::to_string_pretty(&file).map_err(|error| error.to_string())?;
    std::fs::write(path, text).map_err(|error| error.to_string())?;
    Ok(cleaned)
}

pub fn default_settings() -> AiSettings {
    AiSettings {
        ai_enabled: false,
        text_model: String::new(),
        image_model: DEFAULT_IMAGE_MODEL.to_string(),
        api_key_source: DEFAULT_API_KEY_SOURCE.to_string(),
        updated_at: None,
    }
}

pub fn api_key_status() -> ApiKeyStatus {
    let credential_supported = crate::secret_store::credential_manager_supported();
    if credential_supported {
        match crate::secret_store::read_openai_api_key() {
            Ok(Some(value)) => {
                return ApiKeyStatus {
                    state: "registered".to_string(),
                    source: Some("windows_credential_manager".to_string()),
                    masked: Some(crate::secret_store::mask_secret(&value)),
                    credential_supported,
                    message: "Windows Credential Managerに登録済みです。".to_string(),
                };
            }
            Ok(None) => {}
            Err(error) => {
                return ApiKeyStatus {
                    state: "credential_unavailable".to_string(),
                    source: Some("windows_credential_manager".to_string()),
                    masked: None,
                    credential_supported,
                    message: error,
                };
            }
        }
    }

    if let Some(value) = crate::secret_store::env_openai_api_key() {
        return ApiKeyStatus {
            state: "env_available".to_string(),
            source: Some("environment".to_string()),
            masked: Some(crate::secret_store::mask_secret(&value)),
            credential_supported,
            message: "環境変数 OPENAI_API_KEY を使用できます。".to_string(),
        };
    }

    ApiKeyStatus {
        state: "missing".to_string(),
        source: None,
        masked: None,
        credential_supported,
        message: if credential_supported {
            "OpenAI APIキーは未登録です。".to_string()
        } else {
            "Windows Credential Managerはこの環境では使用できません。環境変数 OPENAI_API_KEY は未設定です。".to_string()
        },
    }
}

pub fn test_connection_at(user_data_root: &Path) -> Result<AiConnectionTestResult, String> {
    let settings = load_settings_at(user_data_root)?;
    let status = api_key_status();
    let has_key = matches!(status.state.as_str(), "registered" | "env_available");
    let text_model_set = !settings.text_model.trim().is_empty();
    let image_model_set = !settings.image_model.trim().is_empty();
    let ok = settings.ai_enabled && has_key;
    let message = if ok {
        "接続テストはキー存在確認まで完了しました。実API呼び出しは未実装です。".to_string()
    } else if !settings.ai_enabled {
        "AI機能がOFFです。キー確認のみ行いました。".to_string()
    } else {
        "OpenAI APIキーが未登録です。".to_string()
    };

    Ok(AiConnectionTestResult {
        ok,
        message,
        key_source: status.source,
        text_model_set,
        image_model_set,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::{SystemTime, UNIX_EPOCH};

    fn temp_root(label: &str) -> PathBuf {
        let stamp = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        std::env::temp_dir().join(format!("toolhub_ai_settings_{label}_{stamp}"))
    }

    #[test]
    fn ai_settings_save_load_roundtrip() {
        let root = temp_root("roundtrip");
        let saved = save_settings_at(
            &root,
            AiSettings {
                ai_enabled: true,
                text_model: " text-model ".to_string(),
                image_model: " image-model ".to_string(),
                api_key_source: String::new(),
                updated_at: None,
            },
        )
        .unwrap();
        assert!(saved.ai_enabled);
        assert_eq!(saved.text_model, "text-model");
        let loaded = load_settings_at(&root).unwrap();
        assert_eq!(loaded.image_model, "image-model");
        assert_eq!(loaded.api_key_source, DEFAULT_API_KEY_SOURCE);
        let _ = std::fs::remove_dir_all(root);
    }

    #[test]
    fn default_image_model_is_png_generation_candidate() {
        let settings = default_settings();
        assert_eq!(settings.image_model, "gpt-image-2");
    }

    #[test]
    fn empty_saved_image_model_uses_default_candidate() {
        let root = temp_root("image_default");
        let saved = save_settings_at(
            &root,
            AiSettings {
                ai_enabled: true,
                text_model: String::new(),
                image_model: String::new(),
                api_key_source: String::new(),
                updated_at: None,
            },
        )
        .unwrap();
        assert_eq!(saved.image_model, "gpt-image-2");
        let _ = std::fs::remove_dir_all(root);
    }
}
