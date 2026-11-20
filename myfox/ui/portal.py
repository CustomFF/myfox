"""Native directory picker via xdg-desktop-portal (org.freedesktop.portal.
FileChooser) over D-Bus – the desktop routes it to its own dialog (KDE,
GNOME, ...), nothing like kdialog/zenity has to be installed.

The portal answers asynchronously: OpenFile returns a request handle, the
chosen URIs arrive later in that request's Response signal.
https://flatpak.github.io/xdg-desktop-portal/docs/doc-org.freedesktop.portal.FileChooser.html
"""

from __future__ import annotations

import os
import secrets
import urllib.parse

from .. import _vendor

_vendor.ensure_on_path()

from jeepney import DBusAddress, DBusErrorResponse, MatchRule, message_bus, new_method_call  # noqa: E402
from jeepney.wrappers import unwrap_msg  # noqa: E402
from jeepney.io.blocking import Proxy, open_dbus_connection  # noqa: E402

_FILE_CHOOSER = DBusAddress(
    "/org/freedesktop/portal/desktop", bus_name="org.freedesktop.portal.Desktop",
    interface="org.freedesktop.portal.FileChooser",
)


def pick_directory(title: str, initial: str | None = None, timeout: float = 3600) -> str | None:
    """Blocks until the user picks or cancels; returns the path, or None on
    cancel or when no portal is reachable. Run it off the UI thread.
    Windows: its own folder dialog."""
    if os.name == "nt":
        return _windows_pick(title, initial)
    try:
        with open_dbus_connection(bus="SESSION") as conn:
            token = "myfox_" + secrets.token_hex(8)
            sender = conn.unique_name[1:].replace(".", "_")
            handle = f"/org/freedesktop/portal/desktop/request/{sender}/{token}"
            rule = MatchRule(type="signal", interface="org.freedesktop.portal.Request", member="Response", path=handle)
            Proxy(message_bus, conn).AddMatch(rule)

            options = {"handle_token": ("s", token), "directory": ("b", True), "modal": ("b", True)}
            if initial:
                # Spec: a NUL-terminated byte string, not "s".
                options["current_folder"] = ("ay", initial.encode() + b"\0")
            with conn.filter(rule) as responses:
                # unwrap_msg raises on an error reply (e.g. no portal service),
                # instead of waiting for a Response that never comes.
                unwrap_msg(conn.send_and_get_reply(
                    new_method_call(_FILE_CHOOSER, "OpenFile", "ssa{sv}", ("", title, options)), timeout=10,
                ))
                response = conn.recv_until_filtered(responses, timeout=timeout)
    except (OSError, KeyError, TimeoutError, ValueError, DBusErrorResponse):
        return None

    code, results = response.body
    uris = results.get("uris", (None, []))[1]
    if code != 0 or not uris:
        return None
    parsed = urllib.parse.urlparse(uris[0])
    if parsed.scheme != "file":
        return None
    return urllib.parse.unquote(parsed.path) or None


def _windows_pick(title: str, initial: str | None) -> str | None:
    """The Explorer-style folder dialog (IFileOpenDialog), with an address
    bar and a folder field to paste a path into; owned by the window in
    front (ours, the user just clicked it), so it's modal to it."""
    import ctypes
    from ctypes import wintypes

    class GUID(ctypes.Structure):
        _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), ("Data3", wintypes.WORD),
                    ("Data4", ctypes.c_ubyte * 8)]

        def __init__(self, text: str) -> None:
            super().__init__()
            ctypes.oledll.ole32.CLSIDFromString(text, ctypes.byref(self))

    def call(obj: ctypes.c_void_p, index: int, *args) -> int:
        vtable = ctypes.cast(obj, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)))[0]
        # byref() results pass as plain pointers.
        types = [ctypes.c_void_p if type(a).__name__ == "CArgObject" else type(a) for a in args]
        proto = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, *types)
        return proto(vtable[index])(obj, *args)

    fos_pickfolders, fos_forcefilesystem, fos_pathmustexist = 0x20, 0x40, 0x800
    sigdn_filesyspath = ctypes.c_int(0x80058000 - (1 << 32))
    ole32, shell32, user32 = ctypes.windll.ole32, ctypes.windll.shell32, ctypes.windll.user32
    owner = wintypes.HWND(user32.GetForegroundWindow())
    ole32.CoInitializeEx(None, 0x2)  # apartment-threaded, as the dialog wants
    dialog, folder, item = ctypes.c_void_p(), ctypes.c_void_p(), ctypes.c_void_p()
    try:
        if ole32.CoCreateInstance(ctypes.byref(GUID("{DC1C5A9C-E88A-4DDE-A5A1-60F82A20AEF7}")), None, 1,
                                  ctypes.byref(GUID("{D57C7288-D4AD-4768-BE02-9D969532D960}")),
                                  ctypes.byref(dialog)) < 0:
            return None
        options = wintypes.DWORD()
        call(dialog, 10, ctypes.byref(options))  # GetOptions
        call(dialog, 9, wintypes.DWORD(options.value | fos_pickfolders | fos_forcefilesystem | fos_pathmustexist))
        call(dialog, 17, wintypes.LPCWSTR(title))  # SetTitle
        if initial and os.path.isdir(initial):
            shell32.SHCreateItemFromParsingName.argtypes = [wintypes.LPCWSTR, ctypes.c_void_p, ctypes.c_void_p,
                                                            ctypes.POINTER(ctypes.c_void_p)]
            if shell32.SHCreateItemFromParsingName(initial, None,
                                                   ctypes.byref(GUID("{43826D1E-E718-42EE-BC55-A1E261C37BFE}")),
                                                   ctypes.byref(folder)) >= 0:
                call(dialog, 12, folder)  # SetFolder
        if call(dialog, 3, owner) < 0:  # Show; cancel is an error HRESULT too
            return None
        if call(dialog, 20, ctypes.byref(item)) < 0:  # GetResult
            return None
        path = ctypes.c_wchar_p()
        if call(item, 5, sigdn_filesyspath, ctypes.byref(path)) < 0:  # IShellItem::GetDisplayName
            return None
        try:
            return path.value or None
        finally:
            ole32.CoTaskMemFree(path)
    except (OSError, TypeError, ValueError):
        return None
    finally:
        for obj in (item, folder, dialog):
            if obj:
                call(obj, 2)  # Release
        ole32.CoUninitialize()
