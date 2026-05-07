mod admin_audit;
mod admin_auth;
mod admin_commands;
mod admin_session;
mod ai_settings;
mod app_studio_commands;
mod commands;
mod logging;
mod manifest;
mod runner;
mod secret_store;
mod setup;

fn main() {
    if let Err(error) = setup::ensure_user_data() {
        eprintln!("failed to initialize ToolHub user data directories: {error}");
    }

    tauri::Builder::default()
        .manage(admin_session::AdminSessionState::new())
        .invoke_handler(tauri::generate_handler![
            commands::list_apps,
            commands::get_categories,
            commands::launch_app,
            commands::get_recent_logs,
            commands::check_updates_mvp,
            admin_commands::admin_is_password_set,
            admin_commands::admin_set_password,
            admin_commands::admin_login,
            admin_commands::admin_logout,
            admin_commands::admin_session_status,
            admin_commands::ai_get_settings,
            admin_commands::ai_save_settings,
            admin_commands::ai_get_api_key_status,
            admin_commands::ai_save_api_key,
            admin_commands::ai_delete_api_key,
            admin_commands::ai_test_connection,
            admin_commands::ai_probe_image_models,
            admin_commands::ai_test_image_generation,
            app_studio_commands::app_studio_list_registered_apps,
            app_studio_commands::app_studio_management_list_apps,
            app_studio_commands::app_studio_management_set_enabled,
            app_studio_commands::app_studio_delete_plan,
            app_studio_commands::app_studio_full_delete_apply,
            app_studio_commands::app_studio_suggest,
            app_studio_commands::app_studio_apply,
            app_studio_commands::app_studio_update_suggest,
            app_studio_commands::app_studio_update_apply,
            app_studio_commands::app_studio_approve,
            app_studio_commands::app_studio_update_approve,
            app_studio_commands::app_studio_read_result,
            app_studio_commands::app_studio_read_ai_proposal,
            app_studio_commands::app_studio_regenerate_icon,
            app_studio_commands::app_studio_ai_diagnostics,
            app_studio_commands::app_studio_open_output_dir,
            app_studio_commands::app_studio_preflight,
            app_studio_commands::app_studio_update_preflight,
            app_studio_commands::app_studio_pick_entry_file
        ])
        .run(tauri::generate_context!())
        .expect("failed to run ToolHub");
}
