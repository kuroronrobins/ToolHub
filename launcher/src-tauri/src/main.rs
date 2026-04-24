mod commands;
mod logging;
mod manifest;
mod runner;

fn main() {
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

