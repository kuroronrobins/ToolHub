const OPENAI_TARGET: &str = "ToolHub/OpenAI";
const OPENAI_ACCOUNT: &str = "OPENAI_API_KEY";

pub fn credential_manager_supported() -> bool {
    platform::credential_manager_supported()
}

pub fn save_openai_api_key(api_key: &str) -> Result<(), String> {
    let value = api_key.trim();
    if value.is_empty() {
        return Err("APIキーを入力してください。".to_string());
    }
    platform::save_secret(OPENAI_TARGET, OPENAI_ACCOUNT, value)
}

pub fn read_openai_api_key() -> Result<Option<String>, String> {
    platform::read_secret(OPENAI_TARGET)
}

pub fn delete_openai_api_key() -> Result<(), String> {
    platform::delete_secret(OPENAI_TARGET)
}

pub fn env_openai_api_key() -> Option<String> {
    std::env::var("OPENAI_API_KEY")
        .ok()
        .map(|value| value.trim().to_string())
        .filter(|value| !value.is_empty())
}

pub fn mask_secret(value: &str) -> String {
    let trimmed = value.trim();
    if trimmed.len() <= 4 {
        return "****".to_string();
    }
    let suffix: String = trimmed
        .chars()
        .rev()
        .take(4)
        .collect::<Vec<_>>()
        .into_iter()
        .rev()
        .collect();
    if trimmed.starts_with("sk-") {
        format!("sk-...{suffix}")
    } else {
        format!("...{suffix}")
    }
}

#[cfg(windows)]
mod platform {
    use std::ffi::{c_void, OsStr};
    use std::os::windows::ffi::OsStrExt;
    use std::ptr;
    use std::slice;

    const CRED_TYPE_GENERIC: u32 = 1;
    const CRED_PERSIST_LOCAL_MACHINE: u32 = 2;
    const ERROR_NOT_FOUND: u32 = 1168;

    #[repr(C)]
    struct FileTime {
        dw_low_date_time: u32,
        dw_high_date_time: u32,
    }

    #[repr(C)]
    struct CredentialW {
        flags: u32,
        type_: u32,
        target_name: *mut u16,
        comment: *mut u16,
        last_written: FileTime,
        credential_blob_size: u32,
        credential_blob: *mut u8,
        persist: u32,
        attribute_count: u32,
        attributes: *mut c_void,
        target_alias: *mut u16,
        user_name: *mut u16,
    }

    #[link(name = "Advapi32")]
    extern "system" {
        fn CredWriteW(credential: *const CredentialW, flags: u32) -> i32;
        fn CredReadW(
            target_name: *const u16,
            type_: u32,
            flags: u32,
            credential: *mut *mut CredentialW,
        ) -> i32;
        fn CredDeleteW(target_name: *const u16, type_: u32, flags: u32) -> i32;
        fn CredFree(buffer: *mut c_void);
    }

    #[link(name = "Kernel32")]
    extern "system" {
        fn GetLastError() -> u32;
    }

    pub fn credential_manager_supported() -> bool {
        true
    }

    pub fn save_secret(target: &str, account: &str, value: &str) -> Result<(), String> {
        let mut target_w = to_wide(target);
        let mut account_w = to_wide(account);
        let mut blob = value.as_bytes().to_vec();
        let blob_size =
            u32::try_from(blob.len()).map_err(|_| "APIキーが長すぎます。".to_string())?;
        let credential = CredentialW {
            flags: 0,
            type_: CRED_TYPE_GENERIC,
            target_name: target_w.as_mut_ptr(),
            comment: ptr::null_mut(),
            last_written: FileTime {
                dw_low_date_time: 0,
                dw_high_date_time: 0,
            },
            credential_blob_size: blob_size,
            credential_blob: blob.as_mut_ptr(),
            persist: CRED_PERSIST_LOCAL_MACHINE,
            attribute_count: 0,
            attributes: ptr::null_mut(),
            target_alias: ptr::null_mut(),
            user_name: account_w.as_mut_ptr(),
        };

        let ok = unsafe { CredWriteW(&credential, 0) };
        if ok == 0 {
            return Err("Windows Credential ManagerにAPIキーを保存できませんでした。".to_string());
        }
        Ok(())
    }

    pub fn read_secret(target: &str) -> Result<Option<String>, String> {
        let target_w = to_wide(target);
        let mut credential: *mut CredentialW = ptr::null_mut();
        let ok = unsafe {
            CredReadW(
                target_w.as_ptr(),
                CRED_TYPE_GENERIC,
                0,
                &mut credential as *mut *mut CredentialW,
            )
        };
        if ok == 0 {
            let error = unsafe { GetLastError() };
            if error == ERROR_NOT_FOUND {
                return Ok(None);
            }
            return Err(
                "Windows Credential ManagerからAPIキー状態を読み取れませんでした。".to_string(),
            );
        }
        if credential.is_null() {
            return Ok(None);
        }
        let result = unsafe {
            let credential_ref = &*credential;
            let bytes = slice::from_raw_parts(
                credential_ref.credential_blob,
                credential_ref.credential_blob_size as usize,
            );
            let value = String::from_utf8(bytes.to_vec())
                .map_err(|_| "保存済みAPIキーを読み取れませんでした。".to_string());
            CredFree(credential as *mut c_void);
            value
        }?;
        Ok(Some(result))
    }

    pub fn delete_secret(target: &str) -> Result<(), String> {
        let target_w = to_wide(target);
        let ok = unsafe { CredDeleteW(target_w.as_ptr(), CRED_TYPE_GENERIC, 0) };
        if ok == 0 {
            let error = unsafe { GetLastError() };
            if error == ERROR_NOT_FOUND {
                return Ok(());
            }
            return Err(
                "Windows Credential ManagerからAPIキーを削除できませんでした。".to_string(),
            );
        }
        Ok(())
    }

    fn to_wide(value: &str) -> Vec<u16> {
        OsStr::new(value).encode_wide().chain(Some(0)).collect()
    }
}

#[cfg(not(windows))]
mod platform {
    pub fn credential_manager_supported() -> bool {
        false
    }

    pub fn save_secret(_target: &str, _account: &str, _value: &str) -> Result<(), String> {
        Err("Windows Credential Managerはこの環境では使用できません。".to_string())
    }

    pub fn read_secret(_target: &str) -> Result<Option<String>, String> {
        Ok(None)
    }

    pub fn delete_secret(_target: &str) -> Result<(), String> {
        Err("Windows Credential Managerはこの環境では使用できません。".to_string())
    }
}

#[cfg(test)]
mod tests {
    use super::mask_secret;

    #[test]
    fn api_key_mask_display_hides_secret() {
        let openai_like_key = format!("{}{}", "sk-", "example-visible-abcd");
        assert_eq!(mask_secret(&openai_like_key), "sk-...abcd");
        assert_eq!(mask_secret("short"), "...hort");
    }
}
