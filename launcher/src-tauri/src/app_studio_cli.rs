use std::path::{Path, PathBuf};

#[derive(Debug, Clone)]
pub(crate) struct AppStudioCliStatus {
    pub(crate) repo_root: String,
    pub(crate) cli_path: String,
    pub(crate) cli_exists: bool,
    pub(crate) tools_dir_exists: bool,
    pub(crate) app_studio_dir_exists: bool,
    pub(crate) message: String,
}

pub(crate) fn app_studio_script_path(root: &Path) -> PathBuf {
    root.join("tools").join("app_studio").join("main.py")
}

pub(crate) fn app_studio_cli_status(root: &Path) -> AppStudioCliStatus {
    let tools_dir = root.join("tools");
    let app_studio_dir = tools_dir.join("app_studio");
    let cli_path = app_studio_script_path(root);
    let cli_exists = cli_path.is_file();
    let message = if cli_exists {
        "App Studio CLI is available.".to_string()
    } else {
        "App Studio CLI がこの ToolHub に含まれていません。ToolHub を再ビルドまたは再インストールしてください。".to_string()
    };

    AppStudioCliStatus {
        repo_root: root.display().to_string(),
        cli_path: cli_path.display().to_string(),
        cli_exists,
        tools_dir_exists: tools_dir.is_dir(),
        app_studio_dir_exists: app_studio_dir.is_dir(),
        message,
    }
}

pub(crate) fn resolve_app_studio_script(root: &Path) -> Result<PathBuf, AppStudioCliStatus> {
    let script = app_studio_script_path(root);
    let status = app_studio_cli_status(root);
    if status.cli_exists {
        Ok(script)
    } else {
        Err(status)
    }
}
