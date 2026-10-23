"""Shared urllib.request bits: the User-Agent, the network timeout and the
download that keeps reporting while the network is silent."""

from __future__ import annotations

import queue
import socket
import threading
import urllib.error
import urllib.request
from typing import BinaryIO, Callable

from . import i18n

USER_AGENT = "myfox"
# Seconds without an answer before a request gives up.
TIMEOUT = 20


def request(url: str, *, method: str | None = None, headers: dict[str, str] | None = None) -> urllib.request.Request:
    hdrs = {"User-Agent": USER_AGENT}
    if headers:
        hdrs.update(headers)
    return urllib.request.Request(url, headers=hdrs, method=method)


def download(url: str, out: BinaryIO, on_data: Callable[[int, int | None], None] | None = None,
             on_wait: Callable[[int], None] | None = None) -> None:
    """Writes `url` into `out`. The network is read in a thread, so while
    it's silent on_wait(seconds) still comes once a second; on_data(done,
    total or None) comes per chunk. Either may raise to stop."""
    chunks: queue.Queue = queue.Queue(maxsize=16)
    stop = threading.Event()

    def put(item) -> None:
        while not stop.is_set():
            try:
                chunks.put(item, timeout=0.5)
                return
            except queue.Full:
                pass

    def read() -> None:
        try:
            with urllib.request.urlopen(request(url), timeout=TIMEOUT) as resp:
                put(("total", int(resp.headers.get("Content-Length") or 0) or None))
                while not stop.is_set():
                    data = resp.read(64 * 1024)
                    put(("data", data))
                    if not data:
                        return
        except BaseException as exc:  # handed to the caller's thread
            put(("error", exc))

    threading.Thread(target=read, daemon=True).start()
    total, done, waited = None, 0, 0
    try:
        while True:
            try:
                kind, value = chunks.get(timeout=1)
            except queue.Empty:
                waited += 1
                # The socket timeout doesn't cover name resolution.
                if waited > TIMEOUT:
                    raise TimeoutError(i18n.t("err_network_silent", TIMEOUT)) from None
                if on_wait:
                    on_wait(waited)
                continue
            waited = 0
            if kind == "error":
                reason = value.reason if isinstance(value, urllib.error.URLError) else value
                # socket.timeout is TimeoutError only from Python 3.10 on.
                if isinstance(reason, (TimeoutError, socket.timeout)):
                    raise TimeoutError(i18n.t("err_network_silent", TIMEOUT)) from value
                raise value
            if kind == "total":
                total = value
            elif not value:
                return
            else:
                out.write(value)
                done += len(value)
                if on_data:
                    on_data(done, total)
    finally:
        stop.set()
