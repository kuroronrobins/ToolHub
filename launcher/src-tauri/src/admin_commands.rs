use crate::admin_session::{AdminSessionState, AdminSessionStatus};
use crate::ai_settings::{AiConnectionTestResult, AiImageGenerationTestResult, AiSettings, ApiKeyStatus};
use tauri::State;

#[tauri::command]
pub fn admin_is_password_set() -> Result<bool, String> {
    Ok(crate::admin_auth::is_password_set_at(
        &crate::setup::user_data_root(),
    ))
}

#[tauri::command]
pub fn admin_set_password(
    password: String,
    confirm_password: String,
    session: State<AdminSessionState>,
) -> Result<AdminSessionStatus, String> {
    let user_data_root = crate::setup::user_data_root();
    if crate::admin_auth::is_password_set_at(&user_data_root) {
        return Err("管理者パスワードは既に設定済みです。".to_string());
    }
    crate::admin_auth::set_password_at(&user_data_root, &password, &confirm_password)?;
    crate::admin_audit::append_admin_event("admin_password_created");
    session.login()
}

#[tauri::command]
pub fn admin_login(
    password: String,
    session: State<AdminSessionState>,
) -> Result<AdminSessionStatus, String> {
    match crate::admin_auth::verify_password_at(&crate::setup::user_data_root(), &password) {
        Ok(true) => {
            crate::admin_audit::append_admin_event("admin_login_success");
            session.login()
        }
        Ok(false) => {
            crate::admin_audit::append_admin_event("admin_login_failed");
            Err("管理者パスワードが正しくありません。".to_string())
        }
        Err(error) => {
            crate::admin_audit::append_admin_event("admin_login_failed");
            Err(error)
        }
    }
}

#[tauri::command]
pub fn admin_logout(session: State<AdminSessionState>) -> Result<(), String> {
    session.logout()?;
    crate::admin_audit::append_admin_event("admin_logout");
    Ok(())
}

#[tauri::command]
pub fn admin_session_status(
    session: State<AdminSessionState>,
) -> Result<AdminSessionStatus, String> {
    session.status()
}

#[tauri::command]
pub fn ai_get_settings(session: State<AdminSessionState>) -> Result<AiSettings, String> {
    session.require_authenticated()?;
    crate::ai_settings::load_settings_at(&crate::setup::user_data_root())
}

#[tauri::command]
pub fn ai_save_settings(
    settings: AiSettings,
    session: State<AdminSessionState>,
) -> Result<AiSettings, String> {
    session.require_authenticated()?;
    let saved = crate::ai_settings::save_settings_at(&crate::setup::user_data_root(), settings)?;
    crate::admin_audit::append_admin_event("ai_settings_saved");
    Ok(saved)
}

#[tauri::command]
pub fn ai_get_api_key_status(session: State<AdminSessionState>) -> Result<ApiKeyStatus, String> {
    session.require_authenticated()?;
    Ok(crate::ai_settings::api_key_status())
}

#[tauri::command]
pub fn ai_save_api_key(api_key: String, session: State<AdminSessionState>) -> Result<(), String> {
    session.require_authenticated()?;
    let trimmed = api_key.trim().to_string();
    crate::secret_store::save_openai_api_key(&trimmed)?;
    crate::admin_audit::append_admin_event_with_attrs(
        "api_key_saved",
        &[
            ("source", "windows_credential_manager".to_string()),
            ("masked", crate::secret_store::mask_secret(&trimmed)),
        ],
    );
    Ok(())
}

#[tauri::command]
pub fn ai_delete_api_key(session: State<AdminSessionState>) -> Result<(), String> {
    session.require_authenticated()?;
    crate::secret_store::delete_openai_api_key()?;
    crate::admin_audit::append_admin_event("api_key_deleted");
    Ok(())
}

#[tauri::command]
pub fn ai_test_connection(
    session: State<AdminSessionState>,
) -> Result<AiConnectionTestResult, String> {
    session.require_authenticated()?;
    crate::ai_settings::test_connection_at(&crate::setup::user_data_root())
}

#[tauri::command]
pub async fn ai_test_image_generation(
    session: State<'_, AdminSessionState>,
) -> Result<AiImageGenerationTestResult, String> {
    session.require_authenticated()?;
    tauri::async_runtime::spawn_blocking(crate::app_studio_commands::run_image_generation_test)
        .await
        .map_err(|_| "画像生成テストを完了できませんでした。".to_string())?
}
