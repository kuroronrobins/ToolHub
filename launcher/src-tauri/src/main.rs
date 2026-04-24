mod commands;
mod logging;
mod manifest;
mod runner;
mod setup;

fn main() {
    if let Err(error) = setup::ensure_user_data() {
        eprintln!("failed to initialize ToolHub user data directories: {error}");
    }

    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![
            commands::list_apps,
            commands::get_categories,
            commands::launch_app,
            commands::get_recent_logs
        ])
        .run(tauri::generate_context!())
        .expect("failed to run ToolHub");
}
