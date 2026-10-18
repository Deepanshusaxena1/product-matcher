from collections.abc import Mapping
from typing import Any
from urllib.parse import urlencode

from app.domain.ports import FetchedPage


def page(text: str, *, status: int = 200, url: str = "https://example.test/") -> FetchedPage:
    return FetchedPage(status_code=status, url=url, text=text)


class FakeFetcher:
    """Serves canned responses and records every request.

    GET responses are keyed by URL, plus "?<query string>" when the request has parameters; POST responses
    by "POST <url>".
    """

    def __init__(self, responses: Mapping[str, FetchedPage | Exception]) -> None:
        self._responses = responses
        self.requests: list[tuple[str, bool]] = []
        self.headers: dict[str, Mapping[str, str]] = {}  # the headers last sent with each request key
        self.posted: list[tuple[str, Any]] = []

    async def get(
        self,
        url: str,
        *,
        params: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
        follow_redirects: bool = True,
    ) -> FetchedPage:
        key = f"{url}?{urlencode(params)}" if params else url
        self.requests.append((key, follow_redirects))
        return self._answer(key, headers)

    async def post_json(
        self, url: str, payload: Any, *, headers: Mapping[str, str] | None = None
    ) -> FetchedPage:
        self.posted.append((url, payload))
        return self._answer(f"POST {url}", headers)

    def _answer(self, key: str, headers: Mapping[str, str] | None) -> FetchedPage:
        self.headers[key] = headers or {}
        if key not in self._responses:
            raise AssertionError(f"unexpected request: {key}")
        response = self._responses[key]
        if isinstance(response, Exception):
            raise response
        return response
