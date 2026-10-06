"""Desktop notifications over D-Bus (org.freedesktop.Notifications) — the
"tray" message every desktop shows, without notify-send being installed.
https://specifications.freedesktop.org/notification-spec/latest/
"""

from __future__ import annotations

from pathlib import Path

from .. import _vendor

_vendor.ensure_on_path()

from jeepney import DBusAddress, DBusErrorResponse, new_method_call  # noqa: E402
from jeepney.io.blocking import open_dbus_connection  # noqa: E402
from jeepney.wrappers import unwrap_msg  # noqa: E402

_NOTIFICATIONS = DBusAddress(
    "/org/freedesktop/Notifications", bus_name="org.freedesktop.Notifications",
    interface="org.freedesktop.Notifications",
)
_ICON = Path(__file__).resolve().parent / "assets" / "icon-256.png"


def send(summary: str, body: str) -> bool:
    """True if the desktop took the notification; False without a session
    bus or a notification service (the caller prints instead)."""
    try:
        with open_dbus_connection(bus="SESSION") as conn:
            # Notify(app_name, replaces_id, app_icon, summary, body, actions, hints, expire_timeout)
            msg = new_method_call(_NOTIFICATIONS, "Notify", "susssasa{sv}i",
                                  ("MyFox", 0, str(_ICON), summary, body, [], {}, -1))
            unwrap_msg(conn.send_and_get_reply(msg, timeout=5))
    except (OSError, KeyError, TimeoutError, ValueError, DBusErrorResponse):
        return False
    return True
