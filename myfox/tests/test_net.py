from __future__ import annotations

import io
import socket
import threading
import unittest
from unittest import mock

from myfox import i18n, net
from myfox.install_form import Cancelled


class _Response:
    def __init__(self, chunks, total=None, block=None):
        self.headers = {"Content-Length": str(total)} if total else {}
        self._chunks = list(chunks)
        self._block = block

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self, _n):
        if self._block is not None:
            self._block.wait(5)
            return b""
        item = self._chunks.pop(0) if self._chunks else b""
        if isinstance(item, BaseException):
            raise item
        return item


class DownloadTests(unittest.TestCase):
    def _download(self, response, **kwargs):
        out = io.BytesIO()
        with mock.patch("urllib.request.urlopen", return_value=response):
            net.download("https://example.org/f", out, **kwargs)
        return out.getvalue()

    def test_writes_the_data_and_reports_each_chunk(self):
        done = []
        data = self._download(_Response([b"abc", b"def"], total=6), on_data=lambda d, t: done.append((d, t)))
        self.assertEqual(data, b"abcdef")
        self.assertEqual(done, [(3, 6), (6, 6)])

    def test_a_silent_network_is_reported_every_second_then_given_up(self):
        block = threading.Event()
        self.addCleanup(block.set)
        waits = []
        with mock.patch.object(net, "TIMEOUT", 1), self.assertRaises(TimeoutError) as raised:
            self._download(_Response([], block=block), on_wait=waits.append)
        self.assertEqual(waits, [1])
        self.assertEqual(str(raised.exception), i18n.t("err_network_silent", 1))

    def test_a_stop_while_waiting_comes_through_at_once(self):
        block = threading.Event()
        self.addCleanup(block.set)

        def stop(_seconds):
            raise Cancelled()

        with self.assertRaises(Cancelled):
            self._download(_Response([], block=block), on_wait=stop)

    def test_a_socket_timeout_says_the_network_is_silent(self):
        with self.assertRaises(TimeoutError) as raised:
            self._download(_Response([b"a", socket.timeout("timed out")]))
        self.assertEqual(str(raised.exception), i18n.t("err_network_silent", net.TIMEOUT))


if __name__ == "__main__":
    unittest.main()
