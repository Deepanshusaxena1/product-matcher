"""`PageFetcher` over curl_cffi, which presents a real Chrome TLS fingerprint.

Plain Python HTTP clients are refused by Croma's CDN on their TLS handshake alone, so every shop is fetched
through the same impersonating session.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, Protocol, cast

from curl_cffi import CurlError
from curl_cffi.requests import AsyncSession

from app.domain.ports import FetchedPage, FetchError

if TYPE_CHECKING:
    from collections.abc import Mapping

_RETRYABLE_STATUSES = frozenset({429, 500, 502, 503, 504})  # throttled or a passing server fault
_REFUSED_STATUSES = frozenset({401, 403})  # blocked: asking again straight away won't help


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
    ) -> None:
        self._session = session
        self._timeout_s = timeout_s
        self._attempts = attempts
        self._backoff_s = backoff_s

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
        failure = "no attempt made"
        for attempt in range(self._attempts):
            if attempt:
                await asyncio.sleep(self._backoff_s * 2 ** (attempt - 1))
            try:
                response = await self._session.request(method, url, timeout=self._timeout_s, **kwargs)
            except CurlError as error:  # connection, TLS and timeout failures
                failure = f"{type(error).__name__}: {error}"
                continue

            status = int(response.status_code)
            if status in _REFUSED_STATUSES:
                raise FetchError(f"{method} {url} was refused with HTTP {status}")
            if status in _RETRYABLE_STATUSES:
                failure = f"HTTP {status}"
                continue
            return FetchedPage(
                status_code=status,
                url=str(response.url),
                text=response.text,
                headers={name.lower(): value for name, value in response.headers.items()},
            )
        raise FetchError(f"{method} {url} failed after {self._attempts} attempts ({failure})")
