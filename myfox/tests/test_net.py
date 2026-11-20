from __future__ import annotations

import io
import socket
import threading
import unittest
import urllib.error
from unittest import mock

from myfox import i18n, net
from myfox.install_form import Cancelled


class _Response:
    def __init__(self, chunks, total=None, block=None, status=200):
        self.status = status
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

    def test_a_socket_timeout_says_the_network_is_silent_once_the_tries_are_used_up(self):
        with mock.patch.object(net, "RETRY_DELAYS", ()), self.assertRaises(TimeoutError) as raised:
            self._download(_Response([b"a", socket.timeout("timed out")]))
        self.assertEqual(str(raised.exception), i18n.t("err_network_silent", net.TIMEOUT))

    def _download_responses(self, responses):
        out, requests = io.BytesIO(), []

        def urlopen(req, timeout):
            requests.append(req.get_header("Range"))
            item = responses.pop(0)
            if isinstance(item, BaseException):
                raise item
            return item

        with mock.patch("urllib.request.urlopen", side_effect=urlopen), mock.patch("time.sleep"):
            net.download("https://example.org/f", out)
        return out.getvalue(), requests

    def test_a_dropped_download_goes_on_from_where_it_stopped(self):
        data, requests = self._download_responses([
            _Response([b"abc", ConnectionResetError()], total=6),
            urllib.error.URLError(socket.gaierror(11002, "getaddrinfo failed")),
            _Response([b"def"], total=3, status=206),
        ])
        self.assertEqual(data, b"abcdef")
        self.assertEqual(requests, [None, "bytes=3-", "bytes=3-"])

    def test_a_server_ignoring_the_range_starts_the_file_over(self):
        data, _ = self._download_responses([
            _Response([b"abc", ConnectionResetError()], total=6),
            _Response([b"abcdef"], total=6, status=200),
        ])
        self.assertEqual(data, b"abcdef")

    def test_a_lasting_failure_comes_through_after_the_tries(self):
        failure = urllib.error.URLError(socket.gaierror(11002, "getaddrinfo failed"))
        with self.assertRaises(urllib.error.URLError):
            self._download_responses([failure] * (len(net.RETRY_DELAYS) + 1))


class UrlopenTests(unittest.TestCase):
    def test_a_transient_failure_is_tried_again(self):
        failure = urllib.error.URLError(socket.gaierror(11002, "getaddrinfo failed"))
        with mock.patch("urllib.request.urlopen", side_effect=[failure, "ok"]) as urlopen, \
                mock.patch("time.sleep") as sleep:
            self.assertEqual(net.urlopen("https://example.org/"), "ok")
        self.assertEqual(urlopen.call_count, 2)
        sleep.assert_called_once_with(net.RETRY_DELAYS[0])

    def test_a_client_error_is_not(self):
        failure = urllib.error.HTTPError("https://example.org/", 404, "Not Found", {}, None)
        with mock.patch("urllib.request.urlopen", side_effect=failure) as urlopen, \
                self.assertRaises(urllib.error.HTTPError):
            net.urlopen("https://example.org/")
        self.assertEqual(urlopen.call_count, 1)


if __name__ == "__main__":
    unittest.main()
