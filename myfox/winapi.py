"""What Windows has instead of /proc and lock symlinks, through ctypes.
Imported only on Windows."""

from __future__ import annotations

import ctypes
import os
from ctypes import wintypes
from pathlib import Path

_TH32CS_SNAPPROCESS = 0x2
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_INVALID_HANDLE_VALUE = wintypes.HANDLE(-1).value
_MAX_PATH = 32768


class _ProcessEntry(ctypes.Structure):
    _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                ("th32DefaultHeapID", ctypes.c_void_p), ("th32ModuleID", wintypes.DWORD),
                ("cntThreads", wintypes.DWORD), ("th32ParentProcessID", wintypes.DWORD),
                ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD),
                ("szExeFile", wintypes.WCHAR * 260)]


_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
_kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
_kernel32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(_ProcessEntry)]
_kernel32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(_ProcessEntry)]
_kernel32.OpenProcess.restype = wintypes.HANDLE
_kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
_kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                                 ctypes.POINTER(wintypes.DWORD)]
_kernel32.CloseHandle.argtypes = [wintypes.HANDLE]


def _image(pid: int) -> str | None:
    handle = _kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return None
    try:
        buf = ctypes.create_unicode_buffer(_MAX_PATH)
        size = wintypes.DWORD(_MAX_PATH)
        if not _kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return None
        return buf.value
    finally:
        _kernel32.CloseHandle(handle)


def processes() -> list[tuple[int, Path]]:
    """(pid, its executable) of every process whose executable can be read
    (other users' and protected ones can't, which is fine: ours can)."""
    snap = _kernel32.CreateToolhelp32Snapshot(_TH32CS_SNAPPROCESS, 0)
    if snap == _INVALID_HANDLE_VALUE:
        raise ctypes.WinError(ctypes.get_last_error())
    found = []
    try:
        entry = _ProcessEntry()
        entry.dwSize = ctypes.sizeof(_ProcessEntry)
        more = _kernel32.Process32FirstW(snap, ctypes.byref(entry))
        while more:
            image = _image(entry.th32ProcessID) if entry.th32ProcessID else None
            if image:
                found.append((entry.th32ProcessID, Path(image)))
            more = _kernel32.Process32NextW(snap, ctypes.byref(entry))
    finally:
        _kernel32.CloseHandle(snap)
    return found


def is_locked(path: Path) -> bool:
    """Whether a running program holds `path` open without sharing it, as
    Firefox does its profile's parent.lock."""
    try:
        with open(path, "ab"):
            return False
    except FileNotFoundError:
        return False
    except PermissionError:
        return True


# ─── The user's PATH ─────────────────────────────────────────────────────

def _broadcast_environment() -> None:
    """Tells Explorer the environment changed, so terminals opened from now
    on see the new PATH without signing out."""
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    result = wintypes.DWORD()
    user32.SendMessageTimeoutW(wintypes.HWND(0xFFFF), 0x001A, 0, "Environment", 0x0002, 5000,
                               ctypes.byref(result))


def _user_path(update=None) -> list[str]:
    import winreg

    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0,
                        winreg.KEY_READ | winreg.KEY_WRITE) as key:
        try:
            value, kind = winreg.QueryValueEx(key, "Path")
        except FileNotFoundError:
            value, kind = "", winreg.REG_EXPAND_SZ
        entries = [e for e in value.split(";") if e]
        if update is not None:
            changed = update(entries)
            if changed != entries:
                winreg.SetValueEx(key, "Path", 0, kind, ";".join(changed))
                _broadcast_environment()
            entries = changed
        return entries


def _same(a: str, b: str) -> bool:
    return os.path.normcase(os.path.normpath(os.path.expandvars(a))) == os.path.normcase(os.path.normpath(b))


def add_to_user_path(directory: Path) -> None:
    _user_path(lambda entries: entries if any(_same(e, str(directory)) for e in entries)
               else entries + [str(directory)])


def remove_from_user_path(directory: Path) -> None:
    _user_path(lambda entries: [e for e in entries if not _same(e, str(directory))])


def in_user_path(directory: Path) -> bool:
    return any(_same(e, str(directory)) for e in _user_path())


# ─── Root certificates ───────────────────────────────────────────────────

class _CertUsage(ctypes.Structure):
    _fields_ = [("cUsageIdentifier", wintypes.DWORD), ("rgpszUsageIdentifier", ctypes.c_void_p)]


class _CertUsageMatch(ctypes.Structure):
    _fields_ = [("dwType", wintypes.DWORD), ("Usage", _CertUsage)]


class _ChainPara(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("RequestedUsage", _CertUsageMatch)]


def fetch_root(der: bytes) -> None:
    """Has Windows build the chain of a server's certificate. Windows keeps
    only some root certificates on disk and fetches the others the first
    time its own checks need them; Python sees the ones on disk alone, so
    a site whose root no Windows program has needed yet fails there. This
    is such a check: afterwards the root is on disk."""
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    crypt32.CertCreateCertificateContext.restype = ctypes.c_void_p
    crypt32.CertCreateCertificateContext.argtypes = [wintypes.DWORD, ctypes.c_char_p, wintypes.DWORD]
    crypt32.CertGetCertificateChain.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                                                ctypes.POINTER(_ChainPara), wintypes.DWORD, ctypes.c_void_p,
                                                ctypes.POINTER(ctypes.c_void_p)]
    crypt32.CertFreeCertificateChain.argtypes = [ctypes.c_void_p]
    crypt32.CertFreeCertificateContext.argtypes = [ctypes.c_void_p]
    cert = crypt32.CertCreateCertificateContext(0x10001, der, len(der))
    if not cert:
        return
    try:
        para = _ChainPara()
        para.cbSize = ctypes.sizeof(_ChainPara)
        chain = ctypes.c_void_p()
        if crypt32.CertGetCertificateChain(None, cert, None, None, ctypes.byref(para), 0, None, ctypes.byref(chain)):
            crypt32.CertFreeCertificateChain(chain)
    finally:
        crypt32.CertFreeCertificateContext(cert)


def started_in_own_console() -> bool:
    """Whether this runs in a console window opened for it (a Start menu
    shortcut), not in a terminal someone works in: then only this process
    and the myfox.cmd that started it are in it."""
    processes = (wintypes.DWORD * 8)()
    count = _kernel32.GetConsoleProcessList(processes, 8)
    return 0 < count <= 2
