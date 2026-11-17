"""The terminal under the TUI: raw mode, waiting for a key, reading keys.

POSIX: termios and select, as picotui itself does it. Windows: the console
API. Its virtual-terminal modes make it speak picotui's language (escape
sequences out, and keys coming in as the sequences a Unix terminal sends);
only the reading differs: the typed characters are taken from the console's
key events (os.read on the console mangles non-ASCII ones, and msvcrt's
kbhit/getwch lose them when they come through a pseudo-console, as over
SSH). use_for_picotui() points picotui here on Windows, picotui itself
staying as it is.
"""

from __future__ import annotations

import os
import time

WINDOWS = os.name == "nt"

# Console modes (wincon.h).
_ENABLE_PROCESSED_INPUT = 0x0001
_ENABLE_LINE_INPUT = 0x0002
_ENABLE_ECHO_INPUT = 0x0004
_ENABLE_QUICK_EDIT_MODE = 0x0040
_ENABLE_EXTENDED_FLAGS = 0x0080
_ENABLE_VIRTUAL_TERMINAL_INPUT = 0x0200
_ENABLE_PROCESSED_OUTPUT = 0x0001
_ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
_STD_INPUT_HANDLE = -10
_STD_OUTPUT_HANDLE = -11
_UTF8 = 65001

_saved = None
_pending = ""  # Windows: characters taken from the console, not read yet


_KEY_EVENT = 0x0001


def _input_record():
    import ctypes
    from ctypes import wintypes

    class KeyEvent(ctypes.Structure):
        _fields_ = [("bKeyDown", wintypes.BOOL), ("wRepeatCount", wintypes.WORD),
                    ("wVirtualKeyCode", wintypes.WORD), ("wVirtualScanCode", wintypes.WORD),
                    ("uChar", wintypes.WCHAR), ("dwControlKeyState", wintypes.DWORD)]

    class Event(ctypes.Union):
        _fields_ = [("KeyEvent", KeyEvent), ("_size", ctypes.c_byte * 16)]

    class InputRecord(ctypes.Structure):
        _fields_ = [("EventType", wintypes.WORD), ("Event", Event)]

    return InputRecord


_InputRecord = _input_record() if WINDOWS else None


def _kernel32():
    import ctypes

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.GetStdHandle.restype = ctypes.c_void_p
    return k32


def _get_mode(k32, handle) -> int:
    import ctypes
    from ctypes import wintypes

    mode = wintypes.DWORD()
    if not k32.GetConsoleMode(handle, ctypes.byref(mode)):
        raise OSError("not a console")
    return mode.value


def raw_on() -> None:
    """Keys one at a time, unechoed, ^C as a key; escape sequences drawn."""
    global _saved
    if not WINDOWS:
        import termios
        import tty

        _saved = termios.tcgetattr(0)
        tty.setraw(0)
        return
    k32 = _kernel32()
    stdin, stdout = k32.GetStdHandle(_STD_INPUT_HANDLE), k32.GetStdHandle(_STD_OUTPUT_HANDLE)
    in_mode, out_mode = _get_mode(k32, stdin), _get_mode(k32, stdout)
    _saved = (stdin, stdout, in_mode, out_mode, k32.GetConsoleCP(), k32.GetConsoleOutputCP())
    raw = in_mode & ~(_ENABLE_LINE_INPUT | _ENABLE_ECHO_INPUT | _ENABLE_PROCESSED_INPUT | _ENABLE_QUICK_EDIT_MODE)
    k32.SetConsoleMode(stdin, raw | _ENABLE_EXTENDED_FLAGS | _ENABLE_VIRTUAL_TERMINAL_INPUT)
    k32.SetConsoleMode(stdout, out_mode | _ENABLE_PROCESSED_OUTPUT | _ENABLE_VIRTUAL_TERMINAL_PROCESSING)
    k32.SetConsoleOutputCP(_UTF8)
    k32.SetConsoleCP(_UTF8)


def raw_off() -> None:
    global _saved
    if _saved is None:
        return
    if not WINDOWS:
        import termios

        termios.tcsetattr(0, termios.TCSANOW, _saved)
    else:
        stdin, stdout, in_mode, out_mode, in_cp, out_cp = _saved
        k32 = _kernel32()
        k32.SetConsoleMode(stdin, in_mode)
        k32.SetConsoleMode(stdout, out_mode)
        k32.SetConsoleCP(in_cp)
        k32.SetConsoleOutputCP(out_cp)
    _saved = None


def size() -> tuple[int, int]:
    """(columns, rows)."""
    try:
        cols, rows = os.get_terminal_size(1)
    except OSError:
        return 80, 24
    return cols, rows


def _take_events() -> None:
    """Windows: moves the characters of the waiting key presses into
    _pending; other events (key releases, focus, resizing) are dropped."""
    global _pending
    import ctypes
    from ctypes import wintypes

    k32 = _kernel32()
    stdin = ctypes.c_void_p(k32.GetStdHandle(_STD_INPUT_HANDLE))
    count = wintypes.DWORD()
    if not k32.GetNumberOfConsoleInputEvents(stdin, ctypes.byref(count)) or not count.value:
        return
    records = (_InputRecord * count.value)()
    got = wintypes.DWORD()
    if not k32.ReadConsoleInputW(stdin, records, count.value, ctypes.byref(got)):
        return
    chars = [r.Event.KeyEvent.uChar * max(1, r.Event.KeyEvent.wRepeatCount) for r in records[:got.value]
             if r.EventType == _KEY_EVENT and r.Event.KeyEvent.bKeyDown and r.Event.KeyEvent.uChar != "\0"]
    # Characters past the BMP come as two halves (surrogates).
    _pending += "".join(chars).encode("utf-16-le", "surrogatepass").decode("utf-16-le", "replace")


def ready(timeout: float) -> bool:
    """Whether a key comes within `timeout` seconds (without reading it)."""
    if not WINDOWS:
        import select

        return bool(select.select([0], [], [], timeout)[0])
    deadline = time.monotonic() + timeout
    while True:
        _take_events()
        if _pending or time.monotonic() >= deadline:
            return bool(_pending)
        time.sleep(0.02)


def read() -> bytes:
    """What has been typed (waiting for at least one key), as a Unix
    terminal would give it: UTF-8, escape sequences for special keys."""
    global _pending
    if not WINDOWS:
        return os.read(0, 32)
    while not ready(1):
        pass
    text, _pending = _pending[:32], _pending[32:]
    return text.encode("utf-8", errors="replace")


class _OsReadingConsole:
    """picotui's basewidget reads keys with os.read(0, …): this stands in
    for its `os` there, everything but read going to the real one."""

    def __getattr__(self, name):
        return getattr(os, name)

    @staticmethod
    def read(fd: int, n: int) -> bytes:
        return read() if fd == 0 else os.read(fd, n)


def use_for_picotui() -> None:
    """Windows: picotui's terminal handling (termios, os.read, the size
    asked of the terminal) through this module."""
    if not WINDOWS:
        return
    import picotui.basewidget
    from picotui.screen import Screen

    Screen.init_tty = classmethod(lambda cls: raw_on())
    Screen.deinit_tty = classmethod(lambda cls: raw_off())
    Screen.screen_size = classmethod(lambda cls: size())
    picotui.basewidget.os = _OsReadingConsole()
