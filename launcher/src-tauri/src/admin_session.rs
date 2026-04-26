use chrono::{DateTime, Duration, Utc};
use serde::Serialize;
use std::sync::Mutex;

const SESSION_TTL_MINUTES: i64 = 30;

#[derive(Debug, Serialize, Clone)]
#[serde(rename_all = "camelCase")]
pub struct AdminSessionStatus {
    pub authenticated: bool,
    pub expires_at: Option<String>,
}

pub struct AdminSessionState {
    expires_at: Mutex<Option<DateTime<Utc>>>,
}

impl AdminSessionState {
    pub fn new() -> Self {
        Self {
            expires_at: Mutex::new(None),
        }
    }

    pub fn login(&self) -> Result<AdminSessionStatus, String> {
        let expires_at = Utc::now() + Duration::minutes(SESSION_TTL_MINUTES);
        let mut guard = self
            .expires_at
            .lock()
            .map_err(|_| "管理者セッションを更新できませんでした。".to_string())?;
        *guard = Some(expires_at);
        Ok(Self::status_from(guard.clone()))
    }

    pub fn logout(&self) -> Result<(), String> {
        let mut guard = self
            .expires_at
            .lock()
            .map_err(|_| "管理者セッションを更新できませんでした。".to_string())?;
        *guard = None;
        Ok(())
    }

    pub fn status(&self) -> Result<AdminSessionStatus, String> {
        let mut guard = self
            .expires_at
            .lock()
            .map_err(|_| "管理者セッションを確認できませんでした。".to_string())?;
        if let Some(expires_at) = guard.as_ref() {
            if expires_at.to_owned() <= Utc::now() {
                *guard = None;
            }
        }
        Ok(Self::status_from(guard.clone()))
    }

    pub fn require_authenticated(&self) -> Result<(), String> {
        let status = self.status()?;
        if status.authenticated {
            Ok(())
        } else {
            Err("管理者セッションの有効期限が切れました。再ログインしてください。".to_string())
        }
    }

    fn status_from(expires_at: Option<DateTime<Utc>>) -> AdminSessionStatus {
        match expires_at {
            Some(value) if value > Utc::now() => AdminSessionStatus {
                authenticated: true,
                expires_at: Some(value.to_rfc3339()),
            },
            _ => AdminSessionStatus {
                authenticated: false,
                expires_at: None,
            },
        }
    }
}
