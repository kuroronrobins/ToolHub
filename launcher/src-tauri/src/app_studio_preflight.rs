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

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::{SystemTime, UNIX_EPOCH};

    fn temp_root(name: &str) -> PathBuf {
        let suffix = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        std::env::temp_dir().join(format!("toolhub_app_studio_preflight_{name}_{suffix}"))
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
}
