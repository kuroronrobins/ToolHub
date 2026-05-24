"""Windows Credential Manager API key provider."""
from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes
from typing import Protocol

from agendasnap.apikeys.base import ApiKeyProvider


CRED_TYPE_GENERIC = 1
CRED_PERSIST_LOCAL_MACHINE = 2


class WinCredError(RuntimeError):
    """Credential Manager operation failed without exposing credential values."""


class WinCredUnavailableError(WinCredError):
    """Credential Manager is not available on this platform."""


class _CredentialStore(Protocol):
    def is_supported(self) -> bool:
        ...

    def read(self, target_name: str) -> str | None:
        ...

    def write(self, target_name: str, key: str) -> None:
        ...

    def delete(self, target_name: str) -> bool:
        ...


class _FILETIME(ctypes.Structure):
    _fields_ = [
        ("dwLowDateTime", wintypes.DWORD),
        ("dwHighDateTime", wintypes.DWORD),
    ]


class _CREDENTIAL_ATTRIBUTEW(ctypes.Structure):
    _fields_ = [
        ("Keyword", wintypes.LPWSTR),
        ("Flags", wintypes.DWORD),
        ("ValueSize", wintypes.DWORD),
        ("Value", ctypes.POINTER(ctypes.c_ubyte)),
    ]


class _CREDENTIALW(ctypes.Structure):
    _fields_ = [
        ("Flags", wintypes.DWORD),
        ("Type", wintypes.DWORD),
        ("TargetName", wintypes.LPWSTR),
        ("Comment", wintypes.LPWSTR),
        ("LastWritten", _FILETIME),
        ("CredentialBlobSize", wintypes.DWORD),
        ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
        ("Persist", wintypes.DWORD),
        ("AttributeCount", wintypes.DWORD),
        ("Attributes", ctypes.POINTER(_CREDENTIAL_ATTRIBUTEW)),
        ("TargetAlias", wintypes.LPWSTR),
        ("UserName", wintypes.LPWSTR),
    ]


class _WindowsCredentialStore:
    def __init__(self) -> None:
        self._advapi32 = None
        if sys.platform == "win32":
            self._advapi32 = ctypes.WinDLL("Advapi32.dll", use_last_error=True)
            self._cred_read = self._advapi32.CredReadW
            self._cred_read.argtypes = [
                wintypes.LPCWSTR,
                wintypes.DWORD,
                wintypes.DWORD,
                ctypes.POINTER(ctypes.POINTER(_CREDENTIALW)),
            ]
            self._cred_read.restype = wintypes.BOOL

            self._cred_write = self._advapi32.CredWriteW
            self._cred_write.argtypes = [ctypes.POINTER(_CREDENTIALW), wintypes.DWORD]
            self._cred_write.restype = wintypes.BOOL

            self._cred_delete = self._advapi32.CredDeleteW
            self._cred_delete.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
            self._cred_delete.restype = wintypes.BOOL

            self._cred_free = self._advapi32.CredFree
            self._cred_free.argtypes = [wintypes.LPVOID]
            self._cred_free.restype = None

    def is_supported(self) -> bool:
        return self._advapi32 is not None

    def _ensure_supported(self) -> None:
        if not self.is_supported():
            raise WinCredUnavailableError("Windows資格情報マネージャーはこの環境では利用できません。")

    @staticmethod
    def _last_error_message(prefix: str) -> str:
        code = ctypes.get_last_error()
        if code == 1168:
            return "not found"
        return f"{prefix} failed with Windows error {code}"

    def read(self, target_name: str) -> str | None:
        self._ensure_supported()
        cred_ptr = ctypes.POINTER(_CREDENTIALW)()
        ok = self._cred_read(target_name, CRED_TYPE_GENERIC, 0, ctypes.byref(cred_ptr))
        if not ok:
            code = ctypes.get_last_error()
            if code == 1168:
                return None
            raise WinCredError(self._last_error_message("Credential read"))
        try:
            size = int(cred_ptr.contents.CredentialBlobSize or 0)
            if size <= 0:
                return None
            raw = ctypes.string_at(cred_ptr.contents.CredentialBlob, size)
            return raw.decode("utf-16-le").rstrip("\x00") or None
        finally:
            self._cred_free(cred_ptr)

    def write(self, target_name: str, key: str) -> None:
        self._ensure_supported()
        blob = key.encode("utf-16-le")
        blob_buf = ctypes.create_string_buffer(blob)
        cred_record = _CREDENTIALW()
        cred_record.Flags = 0
        cred_record.Type = CRED_TYPE_GENERIC
        cred_record.TargetName = target_name
        cred_record.Comment = "AgendaSnap API key"
        cred_record.CredentialBlobSize = len(blob)
        cred_record.CredentialBlob = ctypes.cast(blob_buf, ctypes.POINTER(ctypes.c_ubyte))
        cred_record.Persist = CRED_PERSIST_LOCAL_MACHINE
        cred_record.AttributeCount = 0
        cred_record.Attributes = None
        cred_record.TargetAlias = None
        cred_record.UserName = "AgendaSnap"
        ok = self._cred_write(ctypes.byref(cred_record), 0)
        if not ok:
            raise WinCredError(self._last_error_message("Credential write"))

    def delete(self, target_name: str) -> bool:
        self._ensure_supported()
        ok = self._cred_delete(target_name, CRED_TYPE_GENERIC, 0)
        if ok:
            return True
        code = ctypes.get_last_error()
        if code == 1168:
            return False
        raise WinCredError(self._last_error_message("Credential delete"))


class WinCredProvider(ApiKeyProvider):
    def __init__(self, target_name: str = "AgendaSnap/OpenAI", store: _CredentialStore | None = None):
        self.target_name = str(target_name or "").strip() or "AgendaSnap/OpenAI"
        self._store = store or _WindowsCredentialStore()

    def get_key(self) -> str | None:
        try:
            return self._store.read(self.target_name)
        except WinCredUnavailableError:
            return None
        except WinCredError:
            return None
        except Exception:
            return None

    def set_key(self, key: str) -> None:
        clean_key = str(key or "").strip()
        if not clean_key:
            raise ValueError("APIキーが空です。")
        try:
            self._store.write(self.target_name, clean_key)
        except WinCredUnavailableError:
            raise
        except WinCredError:
            raise WinCredError("Windows資格情報への保存に失敗しました。") from None
        except Exception:  # noqa: BLE001
            raise WinCredError("Windows資格情報への保存に失敗しました。") from None

    def delete_key(self) -> bool:
        try:
            return self._store.delete(self.target_name)
        except WinCredUnavailableError:
            return False
        except WinCredError:
            return False
        except Exception:
            return False

    def has_key(self) -> bool:
        return bool(self.get_key())

    def is_supported(self) -> bool:
        return bool(self._store.is_supported())

    def describe_status(self) -> dict[str, object]:
        supported = self.is_supported()
        present = self.has_key() if supported else False
        if not supported:
            message = "Windows資格情報マネージャーはこの環境では利用できません。"
        elif present:
            message = "Windows資格情報に登録済みです。"
        else:
            message = "Windows資格情報に未登録です。"
        return {
            "target_name": self.target_name,
            "supported": supported,
            "present": present,
            "message": message,
        }
