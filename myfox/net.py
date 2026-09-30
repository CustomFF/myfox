"""Shared urllib.request bits — one User-Agent constant instead of four
copies of the same string across firefox/apply/addons/version."""

from __future__ import annotations

import urllib.request

USER_AGENT = "myfox"


def request(url: str, *, method: str | None = None, headers: dict[str, str] | None = None) -> urllib.request.Request:
    hdrs = {"User-Agent": USER_AGENT}
    if headers:
        hdrs.update(headers)
    return urllib.request.Request(url, headers=hdrs, method=method)
