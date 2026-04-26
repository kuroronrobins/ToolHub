use base64::{engine::general_purpose, Engine as _};
use serde::{Deserialize, Serialize};
use std::collections::{BTreeSet, HashMap};
use std::env;
use std::error::Error;
use std::path::{Path, PathBuf};

#[derive(Debug, Serialize, Clone)]
#[serde(rename_all = "camelCase")]
pub struct AppInfo {
    pub id: String,
    pub name: String,
    pub icon_svg: Option<String>,
    pub icon_data_url: Option<String>,
    pub short_description: String,
    pub categories: Vec<String>,
    pub detail: AppDetail,
    pub search: AppSearch,
    pub admin: Option<AppAdmin>,
    pub enabled: bool,
    pub disabled_reason: Option<String>,
}

#[derive(Debug, Serialize, Clone)]
#[serde(rename_all = "camelCase")]
pub struct AppDetail {
    pub description: String,
    pub use_cases: Vec<String>,
    pub inputs: Vec<String>,
    pub outputs: Vec<String>,
    pub notes: Vec<String>,
}

#[derive(Debug, Serialize, Clone)]
#[serde(rename_all = "camelCase")]
pub struct AppSearch {
    pub keywords: Vec<String>,
    pub examples: Vec<String>,
}

#[derive(Debug, Serialize, Clone)]
#[serde(rename_all = "camelCase")]
pub struct AppAdmin {
    pub version: Option<String>,
    pub owner: Option<String>,
    pub requirements: Option<String>,
    pub log_dir: Option<String>,
}

#[derive(Debug, Deserialize)]
struct RawManifest {
    id: String,
    name: String,
    display: RawDisplay,
    detail: RawDetail,
    #[serde(default)]
    search: RawSearch,
    run: RawRun,
    admin: Option<RawAdmin>,
}

#[derive(Debug, Deserialize)]
struct RawDisplay {
    icon: String,
    icon_fallback: Option<String>,
    short_description: String,
    categories: Vec<String>,
}

#[derive(Debug, Deserialize)]
struct RawDetail {
    description: String,
    #[serde(default)]
    use_cases: Vec<String>,
    #[serde(default)]
    inputs: Vec<String>,
    #[serde(default)]
    outputs: Vec<String>,
    #[serde(default)]
    notes: Vec<String>,
}

#[derive(Debug, Deserialize, Default)]
struct RawSearch {
    #[serde(default)]
    keywords: Vec<String>,
    #[serde(default)]
    examples: Vec<String>,
}

#[derive(Debug, Deserialize)]
struct RawRun {
    runner: String,
    entry: String,
    mode: String,
}

#[derive(Debug, Deserialize)]
struct RawAdmin {
    version: Option<String>,
    owner: Option<String>,
    requirements: Option<String>,
    log_dir: Option<String>,
}

#[derive(Debug, Deserialize, Default)]
struct RawAppReleaseManifest {
    #[serde(default)]
    apps: HashMap<String, RawAppReleaseEntry>,
}

#[derive(Debug, Deserialize, Default)]
struct RawAppReleaseEntry {
    enabled: Option<bool>,
}

pub fn project_root() -> Result<PathBuf, Box<dyn Error>> {
    if let Ok(value) = env::var("TOOLHUB_ROOT") {
        let path = PathBuf::from(value);
        if looks_like_root(&path) {
            return Ok(path);
        }
    }

    let mut candidates = Vec::new();
    candidates.push(env::current_dir()?);
    candidates.push(PathBuf::from(env!("CARGO_MANIFEST_DIR")));

    for candidate in candidates {
        for ancestor in candidate.ancestors() {
            if looks_like_root(ancestor) {
                return Ok(ancestor.to_path_buf());
            }
        }
    }

    Err("ToolHub project root was not found".into())
}

fn looks_like_root(path: &Path) -> bool {
    path.join("apps").is_dir() && path.join("runner").is_dir() && path.join("launcher").is_dir()
}

pub fn load_apps(root: &Path) -> Result<Vec<AppInfo>, Box<dyn Error>> {
    let apps_dir = root.join("apps");
    if !apps_dir.is_dir() {
        return Ok(Vec::new());
    }

    let release_enabled = load_release_enabled(root).unwrap_or_default();
    let mut apps = Vec::new();
    for entry in std::fs::read_dir(apps_dir)? {
        let entry = entry?;
        let app_dir = entry.path();
        if !app_dir.is_dir() {
            continue;
        }
        let manifest_path = app_dir.join("app.yaml");
        if !manifest_path.is_file() {
            continue;
        }
        let mut app = match load_one_app(&app_dir, &manifest_path) {
            Ok(app) => app,
            Err(error) => disabled_app(&app_dir, error.to_string()),
        };
        if release_enabled.get(&app.id) == Some(&false) {
            app.enabled = false;
            app.disabled_reason =
                Some("release/app_manifest.json で無効化されています。".to_string());
        }
        apps.push(app);
    }

    apps.sort_by(|a, b| a.name.cmp(&b.name));
    Ok(apps)
}

fn load_release_enabled(root: &Path) -> Result<HashMap<String, bool>, Box<dyn Error>> {
    let path = root.join("release").join("app_manifest.json");
    if !path.is_file() {
        return Ok(HashMap::new());
    }
    let text = std::fs::read_to_string(path)?;
    let raw: RawAppReleaseManifest = serde_json::from_str(&text)?;
    Ok(raw
        .apps
        .into_iter()
        .filter_map(|(id, entry)| entry.enabled.map(|enabled| (id, enabled)))
        .collect())
}

fn load_one_app(app_dir: &Path, manifest_path: &Path) -> Result<AppInfo, Box<dyn Error>> {
    let yaml = std::fs::read_to_string(manifest_path)?;
    let raw: RawManifest = serde_yaml::from_str(&yaml)?;
    validate_run(&raw.run)?;

    let icon_path = app_dir.join(&raw.display.icon);
    let icon_data_url = read_icon_data_url(&icon_path)?;
    let icon_svg = if icon_data_url.is_none() {
        read_icon_svg(&icon_path)?.or_else(|| {
            raw.display
                .icon_fallback
                .as_deref()
                .and_then(|fallback| read_icon_svg(&app_dir.join(fallback)).ok())
                .flatten()
        })
    } else {
        raw.display
            .icon_fallback
            .as_deref()
            .and_then(|fallback| read_icon_svg(&app_dir.join(fallback)).ok())
            .flatten()
    };

    Ok(AppInfo {
        id: raw.id,
        name: raw.name,
        icon_svg,
        icon_data_url,
        short_description: raw.display.short_description,
        categories: raw.display.categories,
        detail: AppDetail {
            description: raw.detail.description,
            use_cases: raw.detail.use_cases,
            inputs: raw.detail.inputs,
            outputs: raw.detail.outputs,
            notes: raw.detail.notes,
        },
        search: AppSearch {
            keywords: raw.search.keywords,
            examples: raw.search.examples,
        },
        admin: raw.admin.map(|admin| AppAdmin {
            version: admin.version,
            owner: admin.owner,
            requirements: admin.requirements,
            log_dir: admin.log_dir,
        }),
        enabled: true,
        disabled_reason: None,
    })
}

fn validate_run(run: &RawRun) -> Result<(), Box<dyn Error>> {
    let runners = [
        "python",
        "cli",
        "exe",
        "playwright_python",
        "python_app_env",
    ];
    if !runners.contains(&run.runner.as_str()) {
        return Err(format!("unsupported runner: {}", run.runner).into());
    }

    let modes = ["gui", "cli", "background"];
    if !modes.contains(&run.mode.as_str()) {
        return Err(format!("unsupported mode: {}", run.mode).into());
    }

    if run.entry.trim().is_empty() {
        return Err("run.entry is required".into());
    }

    Ok(())
}

fn read_icon_data_url(path: &Path) -> Result<Option<String>, Box<dyn Error>> {
    if !path.is_file() {
        return Ok(None);
    }
    let extension = path
        .extension()
        .and_then(|value| value.to_str())
        .unwrap_or("");
    if extension.eq_ignore_ascii_case("png") {
        let bytes = std::fs::read(path)?;
        return Ok(Some(format!(
            "data:image/png;base64,{}",
            general_purpose::STANDARD.encode(bytes)
        )));
    }
    Ok(None)
}

fn read_icon_svg(path: &Path) -> Result<Option<String>, Box<dyn Error>> {
    if path.is_file()
        && path
            .extension()
            .and_then(|value| value.to_str())
            .is_some_and(|extension| extension.eq_ignore_ascii_case("svg"))
    {
        return Ok(Some(std::fs::read_to_string(path)?));
    }
    Ok(None)
}

fn disabled_app(app_dir: &Path, reason: String) -> AppInfo {
    let id = app_dir
        .file_name()
        .and_then(|value| value.to_str())
        .unwrap_or("invalid_app")
        .to_string();
    AppInfo {
        id: id.clone(),
        name: id,
        icon_svg: None,
        icon_data_url: None,
        short_description: "このアプリ定義を読み込めませんでした。".to_string(),
        categories: vec!["未分類".to_string()],
        detail: AppDetail {
            description: "アプリ定義に問題があります。管理者に確認してください。".to_string(),
            use_cases: Vec::new(),
            inputs: Vec::new(),
            outputs: Vec::new(),
            notes: Vec::new(),
        },
        search: AppSearch {
            keywords: Vec::new(),
            examples: Vec::new(),
        },
        admin: None,
        enabled: false,
        disabled_reason: Some(reason),
    }
}

pub fn collect_categories(apps: &[AppInfo]) -> Vec<String> {
    let mut set = BTreeSet::new();
    for app in apps.iter().filter(|app| app.enabled) {
        for category in &app.categories {
            if !category.trim().is_empty() {
                set.insert(category.to_string());
            }
        }
    }

    let mut categories = vec!["すべて".to_string()];
    categories.extend(set);
    categories
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::{SystemTime, UNIX_EPOCH};

    #[test]
    fn collect_categories_includes_all_first() {
        let apps = vec![AppInfo {
            id: "a".to_string(),
            name: "A".to_string(),
            icon_svg: None,
            icon_data_url: None,
            short_description: "desc".to_string(),
            categories: vec!["CSV".to_string()],
            detail: AppDetail {
                description: "desc".to_string(),
                use_cases: Vec::new(),
                inputs: Vec::new(),
                outputs: Vec::new(),
                notes: Vec::new(),
            },
            search: AppSearch {
                keywords: Vec::new(),
                examples: Vec::new(),
            },
            admin: None,
            enabled: true,
            disabled_reason: None,
        }];

        assert_eq!(
            collect_categories(&apps),
            vec!["すべて".to_string(), "CSV".to_string()]
        );
    }

    #[test]
    fn load_one_app_reads_png_icon_and_svg_fallback() {
        let root = temp_app_dir();
        std::fs::write(root.join("icon.png"), b"\x89PNG\r\n\x1a\n").unwrap();
        std::fs::write(root.join("icon.svg"), "<svg viewBox=\"0 0 64 64\"></svg>").unwrap();
        let manifest = root.join("app.yaml");
        std::fs::write(
            &manifest,
            "id: png_app\nname: PNG App\ndisplay:\n  icon: icon.png\n  icon_fallback: icon.svg\n  short_description: desc\n  categories:\n    - CSV\ndetail:\n  description: desc\nrun:\n  runner: cli\n  entry: main.py\n  mode: cli\n",
        )
        .unwrap();

        let app = load_one_app(&root, &manifest).unwrap();

        assert!(app
            .icon_data_url
            .unwrap()
            .starts_with("data:image/png;base64,"));
        assert!(app.icon_svg.unwrap().contains("<svg"));
        let _ = std::fs::remove_dir_all(root);
    }

    #[test]
    fn load_one_app_keeps_existing_svg_icon() {
        let root = temp_app_dir();
        std::fs::write(root.join("icon.svg"), "<svg viewBox=\"0 0 64 64\"></svg>").unwrap();
        let manifest = root.join("app.yaml");
        std::fs::write(
            &manifest,
            "id: svg_app\nname: SVG App\ndisplay:\n  icon: icon.svg\n  short_description: desc\n  categories:\n    - CSV\ndetail:\n  description: desc\nrun:\n  runner: cli\n  entry: main.py\n  mode: cli\n",
        )
        .unwrap();

        let app = load_one_app(&root, &manifest).unwrap();

        assert!(app.icon_data_url.is_none());
        assert!(app.icon_svg.unwrap().contains("<svg"));
        let _ = std::fs::remove_dir_all(root);
    }

    fn temp_app_dir() -> PathBuf {
        let stamp = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let root = std::env::temp_dir().join(format!("toolhub_manifest_icon_{stamp}"));
        std::fs::create_dir_all(&root).unwrap();
        root
    }
}
