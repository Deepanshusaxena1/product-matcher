"""`PageFetcher` over curl_cffi, which presents a real Chrome TLS fingerprint.

Plain Python HTTP clients are refused by Croma's CDN on their TLS handshake alone, so every shop is fetched
through the same impersonating session.

The fetcher is shared by every comparison in the app, so it is also where each shop is kept from being asked
too much at once: a few requests per host at a time, and a throttled request waits as long as the shop asks.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import TYPE_CHECKING, Any, Protocol, cast
from urllib.parse import urlsplit

from curl_cffi import CurlError
from curl_cffi.requests import AsyncSession

from app.domain.ports import FetchedPage, FetchError

if TYPE_CHECKING:
    from collections.abc import Mapping

_RETRYABLE_STATUSES = frozenset({429, 500, 502, 503, 504})  # throttled or a passing server fault
_REFUSED_STATUSES = frozenset({401, 403})  # blocked: asking again straight away won't help
_THROTTLED = 429


class HttpSession(Protocol):
    """The slice of `curl_cffi.requests.AsyncSession` the fetcher uses."""

    async def request(self, method: str, url: str, **kwargs: Any) -> Any: ...

    async def close(self) -> None: ...


class CurlPageFetcher:
    def __init__(
        self,
        session: HttpSession,
        *,
        timeout_s: float = 15.0,
        attempts: int = 3,
        backoff_s: float = 0.5,
        throttle_backoff_s: float = 2.0,
        max_wait_s: float = 10.0,
        max_per_host: int = 2,
    ) -> None:
        self._session = session
        self._timeout_s = timeout_s
        self._attempts = attempts
        self._backoff_s = backoff_s
        # A 429 means "slow down": wait longer than for a server fault, or as long as Retry-After says.
        self._throttle_backoff_s = throttle_backoff_s
        self._max_wait_s = max_wait_s
        self._host_slots: defaultdict[str, asyncio.Semaphore] = defaultdict(
            lambda: asyncio.Semaphore(max_per_host)
        )

    @classmethod
    def impersonating_chrome(cls, **options: Any) -> CurlPageFetcher:
        # curl_cffi types `method` as a Literal; the fetcher only ever passes "GET" and "POST".
        return cls(cast("HttpSession", AsyncSession(impersonate="chrome")), **options)

    async def aclose(self) -> None:
        await self._session.close()

    async def get(
        self,
        url: str,
        *,
        params: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
        follow_redirects: bool = True,
    ) -> FetchedPage:
        return await self._request(
            "GET",
            url,
            params=dict(params) if params else None,
            headers=dict(headers) if headers else None,
            allow_redirects=follow_redirects,
        )

    async def post_json(
        self, url: str, payload: Any, *, headers: Mapping[str, str] | None = None
    ) -> FetchedPage:
        return await self._request(
            "POST", url, json=payload, headers=dict(headers) if headers else None, allow_redirects=True
        )

    async def _request(self, method: str, url: str, **kwargs: Any) -> FetchedPage:
        slots = self._host_slots[urlsplit(url).netloc]
        failure = "no attempt made"
        wait_s = 0.0
        for attempt in range(self._attempts):
            if attempt:
                await asyncio.sleep(wait_s)
            try:
                async with slots:
                    response = await self._session.request(method, url, timeout=self._timeout_s, **kwargs)
            except CurlError as error:  # connection, TLS and timeout failures
                failure = f"{type(error).__name__}: {error}"
                wait_s = self._backoff_s * 2.0**attempt
                continue

            status = int(response.status_code)
            headers = {name.lower(): value for name, value in response.headers.items()}
            if status in _REFUSED_STATUSES:
                raise FetchError(f"{method} {url} was refused with HTTP {status}")
            if status in _RETRYABLE_STATUSES:
                failure = f"HTTP {status}"
                wait_s = self._wait_after(status, headers.get("retry-after"), attempt)
                continue
            return FetchedPage(status_code=status, url=str(response.url), text=response.text, headers=headers)
        raise FetchError(f"{method} {url} failed after {self._attempts} attempts ({failure})")

    def _wait_after(self, status: int, retry_after: str | None, attempt: int) -> float:
        if status != _THROTTLED:
            return self._backoff_s * 2.0**attempt
        try:
            asked = float(retry_after) if retry_after else None
        except ValueError:  # an HTTP date: rare, and not worth parsing
            asked = None
        wait_s = asked if asked is not None else self._throttle_backoff_s * 2.0**attempt
        return min(wait_s, self._max_wait_s)
