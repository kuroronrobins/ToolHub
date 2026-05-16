from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes
from dataclasses import dataclass


CRED_TYPE_GENERIC = 1
CRED_PERSIST_LOCAL_MACHINE = 2
ERROR_NOT_FOUND = 1168


class CredentialError(RuntimeError):
    pass


@dataclass(frozen=True)
class Credential:
    username: str
    password: str


LPBYTE = ctypes.POINTER(wintypes.BYTE)


class FILETIME(ctypes.Structure):
    _fields_ = [
        ("dwLowDateTime", wintypes.DWORD),
        ("dwHighDateTime", wintypes.DWORD),
    ]


class CREDENTIAL_ATTRIBUTEW(ctypes.Structure):
    _fields_ = [
        ("Keyword", wintypes.LPWSTR),
        ("Flags", wintypes.DWORD),
        ("ValueSize", wintypes.DWORD),
        ("Value", LPBYTE),
    ]


PCREDENTIAL_ATTRIBUTEW = ctypes.POINTER(CREDENTIAL_ATTRIBUTEW)


class CREDENTIALW(ctypes.Structure):
    _fields_ = [
        ("Flags", wintypes.DWORD),
        ("Type", wintypes.DWORD),
        ("TargetName", wintypes.LPWSTR),
        ("Comment", wintypes.LPWSTR),
        ("LastWritten", FILETIME),
        ("CredentialBlobSize", wintypes.DWORD),
        ("CredentialBlob", LPBYTE),
        ("Persist", wintypes.DWORD),
        ("AttributeCount", wintypes.DWORD),
        ("Attributes", PCREDENTIAL_ATTRIBUTEW),
        ("TargetAlias", wintypes.LPWSTR),
        ("UserName", wintypes.LPWSTR),
    ]


PCREDENTIALW = ctypes.POINTER(CREDENTIALW)


def _require_windows() -> None:
    if sys.platform != "win32":
        raise CredentialError("Windows Credential Manager is available only on Windows.")


def _advapi32():
    _require_windows()
    lib = ctypes.WinDLL("Advapi32.dll", use_last_error=True)
    lib.CredReadW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(PCREDENTIALW)]
    lib.CredReadW.restype = wintypes.BOOL
    lib.CredWriteW.argtypes = [PCREDENTIALW, wintypes.DWORD]
    lib.CredWriteW.restype = wintypes.BOOL
    lib.CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
    lib.CredDeleteW.restype = wintypes.BOOL
    lib.CredFree.argtypes = [ctypes.c_void_p]
    lib.CredFree.restype = None
    return lib


def _raise_last_error(action: str, target: str) -> None:
    err = ctypes.get_last_error()
    raise CredentialError(f"{action} failed for credential target '{target}' (WinError {err}).")


def read_credential(target: str) -> Credential | None:
    if not target:
        raise CredentialError("Credential target is empty.")
    lib = _advapi32()
    cred_ptr = PCREDENTIALW()
    ok = lib.CredReadW(target, CRED_TYPE_GENERIC, 0, ctypes.byref(cred_ptr))
    if not ok:
        err = ctypes.get_last_error()
        if err == ERROR_NOT_FOUND:
            return None
        _raise_last_error("CredReadW", target)

    try:
        cred = cred_ptr.contents
        username = cred.UserName or ""
        if cred.CredentialBlob and cred.CredentialBlobSize:
            raw = ctypes.string_at(cred.CredentialBlob, cred.CredentialBlobSize)
            password = raw.decode("utf-16-le", errors="ignore")
        else:
            password = ""
        return Credential(username=username, password=password)
    finally:
        lib.CredFree(cred_ptr)


def credential_exists(target: str) -> bool:
    return read_credential(target) is not None


def write_credential(target: str, username: str, password: str) -> None:
    if not target:
        raise CredentialError("Credential target is empty.")
    if not username:
        raise CredentialError("Username is empty.")

    lib = _advapi32()
    password_bytes = (password or "").encode("utf-16-le")
    blob = ctypes.create_string_buffer(password_bytes)

    cred = CREDENTIALW()
    cred.Flags = 0
    cred.Type = CRED_TYPE_GENERIC
    cred.TargetName = target
    cred.Comment = "XCgate AutoUpload credential"
    cred.CredentialBlobSize = len(password_bytes)
    cred.CredentialBlob = ctypes.cast(blob, LPBYTE)
    cred.Persist = CRED_PERSIST_LOCAL_MACHINE
    cred.AttributeCount = 0
    cred.Attributes = None
    cred.TargetAlias = None
    cred.UserName = username

    ok = lib.CredWriteW(ctypes.byref(cred), 0)
    if not ok:
        _raise_last_error("CredWriteW", target)


def delete_credential(target: str) -> bool:
    if not target:
        raise CredentialError("Credential target is empty.")
    lib = _advapi32()
    ok = lib.CredDeleteW(target, CRED_TYPE_GENERIC, 0)
    if ok:
        return True
    err = ctypes.get_last_error()
    if err == ERROR_NOT_FOUND:
        return False
    _raise_last_error("CredDeleteW", target)
    return False
