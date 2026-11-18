"""Store the DART API key in the current user's native credential store.

Native libraries are loaded lazily. This module never invokes a subprocess or
requests credential-store authentication UI.
"""
from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

_SERVICE = b"aisy.financial-statements"
_ACCOUNT = b"DART_API_KEY"
_TARGET = "aisy.financial-statements/DART_API_KEY"


class CredentialError(RuntimeError):
    """A safe, value-free credential-store error."""


def _failure() -> CredentialError:
    return CredentialError("The system credential store could not complete the request.")


def _mac_key(value: bytes | None) -> bytes | None:
    security = ctypes.CDLL("/System/Library/Frameworks/Security.framework/Security")
    core = ctypes.CDLL("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
    pointer = ctypes.c_void_p
    uint = ctypes.c_uint32
    status = ctypes.c_int32
    security.SecKeychainSetUserInteractionAllowed.argtypes = [ctypes.c_ubyte]
    security.SecKeychainSetUserInteractionAllowed.restype = status
    security.SecKeychainGetUserInteractionAllowed.argtypes = [ctypes.POINTER(ctypes.c_ubyte)]
    security.SecKeychainGetUserInteractionAllowed.restype = status
    security.SecKeychainFindGenericPassword.argtypes = [pointer, uint, pointer, uint, pointer,
                                                       ctypes.POINTER(uint), ctypes.POINTER(pointer), ctypes.POINTER(pointer)]
    security.SecKeychainFindGenericPassword.restype = status
    security.SecKeychainItemFreeContent.argtypes = [pointer, pointer]
    security.SecKeychainItemFreeContent.restype = status
    security.SecKeychainItemModifyAttributesAndData.argtypes = [pointer, pointer, uint, pointer]
    security.SecKeychainItemModifyAttributesAndData.restype = status
    security.SecKeychainAddGenericPassword.argtypes = [pointer, uint, pointer, uint, pointer, uint, pointer, ctypes.POINTER(pointer)]
    security.SecKeychainAddGenericPassword.restype = status
    core.CFRelease.argtypes = [pointer]
    core.CFRelease.restype = None
    allowed = ctypes.c_ubyte()
    if security.SecKeychainGetUserInteractionAllowed(ctypes.byref(allowed)) != 0:
        raise _failure()
    if security.SecKeychainSetUserInteractionAllowed(False) != 0:
        raise _failure()
    length, data, item = uint(), pointer(), pointer()
    try:
        result = security.SecKeychainFindGenericPassword(
            None, len(_SERVICE), _SERVICE, len(_ACCOUNT), _ACCOUNT,
            ctypes.byref(length), ctypes.byref(data), ctypes.byref(item))
        if result == -25300:  # errSecItemNotFound
            if value is None:
                return None
            result = security.SecKeychainAddGenericPassword(
                None, len(_SERVICE), _SERVICE, len(_ACCOUNT), _ACCOUNT,
                len(value), value, None)
            if result != 0:
                raise _failure()
            return None
        if result != 0:
            raise _failure()
        if value is None:
            return ctypes.string_at(data, length.value)
        if security.SecKeychainItemModifyAttributesAndData(item, None, len(value), value) != 0:
            raise _failure()
        return None
    finally:
        if data.value:
            security.SecKeychainItemFreeContent(None, data)
        if item.value:
            core.CFRelease(item)
        security.SecKeychainSetUserInteractionAllowed(allowed.value)


class _Credential(ctypes.Structure):
    _fields_ = [
        ("Flags", wintypes.DWORD), ("Type", wintypes.DWORD),
        ("TargetName", wintypes.LPWSTR), ("Comment", wintypes.LPWSTR),
        ("LastWritten", wintypes.FILETIME), ("CredentialBlobSize", wintypes.DWORD),
        ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
        ("Persist", wintypes.DWORD), ("AttributeCount", wintypes.DWORD),
        ("Attributes", ctypes.c_void_p), ("TargetAlias", wintypes.LPWSTR),
        ("UserName", wintypes.LPWSTR),
    ]


def _windows_key(value: bytes | None) -> bytes | None:
    native = ctypes.WinDLL("Advapi32.dll", use_last_error=True)
    credential_ptr = ctypes.POINTER(_Credential)
    native.CredReadW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                ctypes.POINTER(credential_ptr)]
    native.CredReadW.restype = wintypes.BOOL
    native.CredWriteW.argtypes = [credential_ptr, wintypes.DWORD]
    native.CredWriteW.restype = wintypes.BOOL
    native.CredFree.argtypes = [ctypes.c_void_p]
    native.CredFree.restype = None
    if value is not None:
        if len(value) > 2560:  # CRED_MAX_CREDENTIAL_BLOB_SIZE
            raise _failure()
        blob = (ctypes.c_ubyte * len(value)).from_buffer_copy(value)
        credential = _Credential()
        credential.Type = 1  # CRED_TYPE_GENERIC
        credential.TargetName = _TARGET
        credential.UserName = _ACCOUNT.decode("ascii")
        credential.CredentialBlobSize = len(value)
        credential.CredentialBlob = ctypes.cast(blob, ctypes.POINTER(ctypes.c_ubyte))
        credential.Persist = 2  # CRED_PERSIST_LOCAL_MACHINE (current user)
        if not native.CredWriteW(ctypes.byref(credential), 0):
            raise _failure()
        return None
    credential = credential_ptr()
    if not native.CredReadW(_TARGET, 1, 0, ctypes.byref(credential)):
        if ctypes.get_last_error() == 1168:  # ERROR_NOT_FOUND
            return None
        raise _failure()
    try:
        return ctypes.string_at(credential.contents.CredentialBlob,
                                credential.contents.CredentialBlobSize)
    finally:
        native.CredFree(credential)


def _operate(value: bytes | None) -> bytes | None:
    try:
        if sys.platform == "darwin":
            return _mac_key(value)
        if sys.platform == "win32":
            return _windows_key(value)
        raise CredentialError("A supported system credential store is required.")
    except CredentialError:
        raise
    except Exception:
        raise _failure() from None


def get_key() -> str | None:
    """Return the stored key, or None when no key has been stored."""
    result = _operate(None)
    if result is None:
        return None
    try:
        return result.decode("utf-8")
    except UnicodeError:
        raise _failure() from None


def save_key(value: str) -> None:
    """Create or replace the current user's stored key without displaying UI."""
    if not isinstance(value, str) or not value or "\x00" in value:
        raise CredentialError("A nonempty API key is required.")
    try:
        encoded = value.encode("utf-8")
    except UnicodeError:
        raise _failure() from None
    _operate(encoded)
