"""Native directory picker via xdg-desktop-portal (org.freedesktop.portal.
FileChooser) over D-Bus — the desktop routes it to its own dialog (KDE,
GNOME, ...), nothing like kdialog/zenity has to be installed.

The portal answers asynchronously: OpenFile returns a request handle, the
chosen URIs arrive later in that request's Response signal.
https://flatpak.github.io/xdg-desktop-portal/docs/doc-org.freedesktop.portal.FileChooser.html
"""

from __future__ import annotations

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
    cancel or when no portal is reachable. Run it off the UI thread."""
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
