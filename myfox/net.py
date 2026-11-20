"""Shared urllib.request bits: the User-Agent, the network timeout, retries
over a flaky network and the download that keeps reporting while the
network is silent."""

from __future__ import annotations

import http.client
import os
import queue
import socket
import threading
import time
import urllib.error
import urllib.request
from typing import BinaryIO, Callable

from . import i18n

USER_AGENT = "myfox"
# Seconds without an answer before a request gives up.
TIMEOUT = 20
# Pauses before each new try after a transient failure.
RETRY_DELAYS = (2, 5, 10)


def _fetch_missing_roots() -> None:
    """Windows: a site whose root certificate Windows hasn't fetched yet
    fails Python's check (see winapi.fetch_root). Every HTTPS connection
    here (urllib's) then has Windows fetch it and tries once more."""
    import http.client
    import ssl

    connect = http.client.HTTPSConnection.connect

    def connect_fetching_roots(self) -> None:
        try:
            connect(self)
        except ssl.SSLCertVerificationError:
            pem = ssl.get_server_certificate((self.host, self.port), timeout=TIMEOUT)
            from . import winapi

            winapi.fetch_root(ssl.PEM_cert_to_DER_cert(pem))
            # A context reads the roots when it's made.
            self._context = ssl.create_default_context()
            connect(self)

    http.client.HTTPSConnection.connect = connect_fetching_roots


if os.name == "nt":
    _fetch_missing_roots()


def request(url: str, *, method: str | None = None, headers: dict[str, str] | None = None) -> urllib.request.Request:
    hdrs = {"User-Agent": USER_AGENT}
    if headers:
        hdrs.update(headers)
    return urllib.request.Request(url, headers=hdrs, method=method)


def transient(exc: BaseException) -> bool:
    """A failure worth another try: name resolution (getaddrinfo 11002 is
    "try again"), a dropped or timed-out connection, a server error."""
    if isinstance(exc, urllib.error.HTTPError):
        return exc.code >= 500 or exc.code == 429
    if isinstance(exc, urllib.error.URLError):
        exc = exc.reason
    return isinstance(exc, (socket.gaierror, ConnectionError, TimeoutError, socket.timeout,
                            http.client.IncompleteRead))


def urlopen(req: urllib.request.Request | str):
    """urllib.request.urlopen with MyFox's timeout, tried again after a
    transient failure."""
    if isinstance(req, str):
        req = request(req)
    for delay in RETRY_DELAYS + (None,):
        try:
            return urllib.request.urlopen(req, timeout=TIMEOUT)
        except Exception as exc:
            if delay is None or not transient(exc):
                raise
        time.sleep(delay)


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
        got, retries = 0, list(RETRY_DELAYS)
        while not stop.is_set():
            try:
                # After a drop, on from where it stopped.
                req = request(url, headers={"Range": f"bytes={got}-"} if got else None)
                with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                    length = int(resp.headers.get("Content-Length") or 0) or None
                    if got and getattr(resp, "status", 206) != 206:
                        got = 0  # the server sends it all again
                        put(("restart", None))
                    put(("total", length + got if length and got else length))
                    while not stop.is_set():
                        data = resp.read(64 * 1024)
                        put(("data", data))
                        if not data:
                            return
                        got += len(data)
                        retries = list(RETRY_DELAYS)  # it moves: a later drop gets all tries again
            except BaseException as exc:  # handed to the caller's thread
                if not (isinstance(exc, Exception) and transient(exc) and retries):
                    put(("error", exc))
                    return
                put(("retry", None))
                time.sleep(retries.pop(0))

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
            if kind == "retry":
                continue
            if kind == "restart":
                out.seek(0)
                out.truncate()
                done = 0
            elif kind == "total":
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
