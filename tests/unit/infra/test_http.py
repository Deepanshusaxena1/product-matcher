from dataclasses import dataclass, field
from typing import Any

import pytest
from curl_cffi import CurlError

from app.domain.ports import FetchError
from app.infra.http import CurlPageFetcher


@dataclass
class FakeResponse:
    status_code: int
    url: str = "https://example.test/final"
    text: str = "ok"
    headers: dict[str, str] = field(default_factory=dict)


class FakeSession:
    """Answers each request with the next queued outcome and records the call."""

    def __init__(self, *outcomes: FakeResponse | Exception) -> None:
        self._outcomes = list(outcomes)
        self.calls: list[dict[str, Any]] = []

    async def request(self, method: str, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append({"method": method, "url": url, **kwargs})
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    async def close(self) -> None:
        pass


def _fetcher(session: FakeSession, attempts: int = 3) -> CurlPageFetcher:
    return CurlPageFetcher(session, attempts=attempts, backoff_s=0)


async def test_a_page_comes_back_with_its_final_url_and_lower_case_headers() -> None:
    session = FakeSession(FakeResponse(200, text="<html>", headers={"Content-Type": "text/html"}))

    page = await _fetcher(session).get("https://example.test/start", params={"q": "s24"})

    assert (page.status_code, page.url, page.text) == (200, "https://example.test/final", "<html>")
    assert page.headers == {"content-type": "text/html"}
    assert session.calls[0]["params"] == {"q": "s24"}
    assert session.calls[0]["allow_redirects"] is True


async def test_redirects_can_be_left_unfollowed() -> None:
    session = FakeSession(FakeResponse(301, headers={"Location": "https://www.amazon.in/dp/B0DHL7YT5S"}))

    page = await _fetcher(session).get("https://amzn.in/d/x", follow_redirects=False)

    assert session.calls[0]["allow_redirects"] is False
    assert page.redirect_location == "https://www.amazon.in/dp/B0DHL7YT5S"


async def test_a_not_found_page_is_an_answer_not_a_failure() -> None:
    page = await _fetcher(FakeSession(FakeResponse(404))).get("https://example.test/missing")

    assert page.status_code == 404


async def test_throttling_and_network_errors_are_retried() -> None:
    session = FakeSession(FakeResponse(503), CurlError("connection reset"), FakeResponse(200))

    page = await _fetcher(session).get("https://example.test/")

    assert page.status_code == 200
    assert len(session.calls) == 3


async def test_giving_up_after_the_last_attempt_raises_fetch_error() -> None:
    session = FakeSession(FakeResponse(429), FakeResponse(429))

    with pytest.raises(FetchError, match="429"):
        await _fetcher(session, attempts=2).get("https://example.test/")


async def test_a_refusal_is_not_retried() -> None:
    session = FakeSession(FakeResponse(403))

    with pytest.raises(FetchError, match="403"):
        await _fetcher(session).get("https://example.test/")

    assert len(session.calls) == 1


async def test_json_is_posted_with_the_given_headers() -> None:
    session = FakeSession(FakeResponse(200, text='{"ok": true}'))

    page = await _fetcher(session).post_json("https://api.test/v1", {"a": 1}, headers={"x-key": "k"})

    assert page.json() == {"ok": True}
    assert session.calls[0]["method"] == "POST"
    assert session.calls[0]["json"] == {"a": 1}
    assert session.calls[0]["headers"] == {"x-key": "k"}
