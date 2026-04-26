use base64::{engine::general_purpose::STANDARD as BASE64, Engine as _};
use chrono::Local;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::path::{Path, PathBuf};

const HASH_ALGORITHM: &str = "pbkdf2-hmac-sha256";
const ITERATIONS: u32 = 210_000;
const SALT_BYTES: usize = 16;
const HASH_BYTES: usize = 32;

#[derive(Debug, Serialize, Deserialize)]
pub struct AdminAuthFile {
    pub schema_version: u8,
    pub hash_algorithm: String,
    pub password_hash: String,
    pub salt: String,
    pub iterations: u32,
    pub created_at: String,
    pub updated_at: String,
}

pub fn auth_config_path(user_data_root: &Path) -> PathBuf {
    user_data_root.join("config").join("admin_auth.json")
}

pub fn is_password_set_at(user_data_root: &Path) -> bool {
    auth_config_path(user_data_root).is_file()
}

pub fn set_password_at(
    user_data_root: &Path,
    password: &str,
    confirm_password: &str,
) -> Result<(), String> {
    validate_password(password, confirm_password)?;

    let mut salt = [0_u8; SALT_BYTES];
    getrandom::getrandom(&mut salt)
        .map_err(|_| "パスワード設定に必要な乱数を生成できませんでした。".to_string())?;
    let hash = derive_password_hash(password.as_bytes(), &salt, ITERATIONS);
    let now = Local::now().to_rfc3339();
    let config = AdminAuthFile {
        schema_version: 1,
        hash_algorithm: HASH_ALGORITHM.to_string(),
        password_hash: BASE64.encode(hash),
        salt: BASE64.encode(salt),
        iterations: ITERATIONS,
        created_at: now.clone(),
        updated_at: now,
    };

    let path = auth_config_path(user_data_root);
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent).map_err(|error| error.to_string())?;
    }
    let text = serde_json::to_string_pretty(&config).map_err(|error| error.to_string())?;
    std::fs::write(path, text).map_err(|error| error.to_string())
}

pub fn verify_password_at(user_data_root: &Path, password: &str) -> Result<bool, String> {
    let path = auth_config_path(user_data_root);
    if !path.is_file() {
        return Ok(false);
    }

    let text = std::fs::read_to_string(path)
        .map_err(|_| "管理者認証設定を読み込めませんでした。".to_string())?;
    let config: AdminAuthFile = serde_json::from_str(&text)
        .map_err(|_| "管理者認証設定を読み込めませんでした。".to_string())?;
    if config.schema_version != 1 || config.hash_algorithm != HASH_ALGORITHM {
        return Err("管理者認証設定の形式に対応していません。".to_string());
    }

    let salt = BASE64
        .decode(config.salt.as_bytes())
        .map_err(|_| "管理者認証設定を読み込めませんでした。".to_string())?;
    let expected = BASE64
        .decode(config.password_hash.as_bytes())
        .map_err(|_| "管理者認証設定を読み込めませんでした。".to_string())?;
    let actual = derive_password_hash(password.as_bytes(), &salt, config.iterations);
    Ok(constant_time_eq(&actual, &expected))
}

fn validate_password(password: &str, confirm_password: &str) -> Result<(), String> {
    if password != confirm_password {
        return Err("確認用パスワードが一致しません。".to_string());
    }
    if password.chars().count() < 8 {
        return Err("管理者パスワードは8文字以上にしてください。".to_string());
    }
    if password.trim().is_empty() {
        return Err("空白のみのパスワードは使用できません。".to_string());
    }
    Ok(())
}

fn derive_password_hash(password: &[u8], salt: &[u8], iterations: u32) -> [u8; HASH_BYTES] {
    let mut block_salt = Vec::with_capacity(salt.len() + 4);
    block_salt.extend_from_slice(salt);
    block_salt.extend_from_slice(&1_u32.to_be_bytes());

    let mut u = hmac_sha256(password, &block_salt);
    let mut output = u;
    for _ in 1..iterations {
        u = hmac_sha256(password, &u);
        for index in 0..HASH_BYTES {
            output[index] ^= u[index];
        }
    }
    output
}

fn hmac_sha256(key: &[u8], message: &[u8]) -> [u8; HASH_BYTES] {
    let mut key_block = [0_u8; 64];
    if key.len() > 64 {
        let digest = Sha256::digest(key);
        key_block[..HASH_BYTES].copy_from_slice(&digest);
    } else {
        key_block[..key.len()].copy_from_slice(key);
    }

    let mut outer = [0x5c_u8; 64];
    let mut inner = [0x36_u8; 64];
    for index in 0..64 {
        outer[index] ^= key_block[index];
        inner[index] ^= key_block[index];
    }

    let mut inner_hasher = Sha256::new();
    inner_hasher.update(inner);
    inner_hasher.update(message);
    let inner_digest = inner_hasher.finalize();

    let mut outer_hasher = Sha256::new();
    outer_hasher.update(outer);
    outer_hasher.update(inner_digest);
    let digest = outer_hasher.finalize();
    digest.into()
}

fn constant_time_eq(left: &[u8], right: &[u8]) -> bool {
    if left.len() != right.len() {
        return false;
    }
    let mut diff = 0_u8;
    for (a, b) in left.iter().zip(right.iter()) {
        diff |= a ^ b;
    }
    diff == 0
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
        std::env::temp_dir().join(format!("toolhub_admin_auth_{label}_{stamp}"))
    }

    #[test]
    fn password_hash_verify_success() {
        let root = temp_root("success");
        set_password_at(&root, "StrongPass123", "StrongPass123").unwrap();
        assert!(verify_password_at(&root, "StrongPass123").unwrap());
        let _ = std::fs::remove_dir_all(root);
    }

    #[test]
    fn password_hash_verify_failure() {
        let root = temp_root("failure");
        set_password_at(&root, "StrongPass123", "StrongPass123").unwrap();
        assert!(!verify_password_at(&root, "WrongPass123").unwrap());
        let _ = std::fs::remove_dir_all(root);
    }

    #[test]
    fn salt_is_unique_for_each_password_file() {
        let root_a = temp_root("salt_a");
        let root_b = temp_root("salt_b");
        set_password_at(&root_a, "StrongPass123", "StrongPass123").unwrap();
        set_password_at(&root_b, "StrongPass123", "StrongPass123").unwrap();
        let file_a: AdminAuthFile =
            serde_json::from_str(&std::fs::read_to_string(auth_config_path(&root_a)).unwrap())
                .unwrap();
        let file_b: AdminAuthFile =
            serde_json::from_str(&std::fs::read_to_string(auth_config_path(&root_b)).unwrap())
                .unwrap();
        assert_ne!(file_a.salt, file_b.salt);
        let _ = std::fs::remove_dir_all(root_a);
        let _ = std::fs::remove_dir_all(root_b);
    }

    #[test]
    fn missing_admin_auth_file_means_password_is_not_set() {
        let root = temp_root("missing");
        assert!(!is_password_set_at(&root));
        let _ = std::fs::remove_dir_all(root);
    }

    #[test]
    fn pbkdf2_hmac_sha256_matches_known_vector() {
        let hash = derive_password_hash(b"password", b"salt", 1);
        assert_eq!(
            to_hex(&hash),
            "120fb6cffcf8b32c43e7225256c4f837a86548c92ccc35480805987cb70be17b"
        );
    }

    fn to_hex(bytes: &[u8]) -> String {
        bytes.iter().map(|value| format!("{value:02x}")).collect()
    }
}
