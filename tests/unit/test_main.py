from pathlib import Path

import pytest

from app.config import Settings
from app.domain.models import MatchStatus, Platform
from app.domain.ports import FetchedPage
from app.main import build_live_comparer
from support.fakes import FakeFetcher

PRODUCT_URL = "https://www.amazon.in/dp/B0DHL7YT5S"
PHONE_HTML = (
    Path(__file__).resolve().parents[1] / "fixtures" / "amazon" / "phone_samsung_s24fe.html"
).read_text(encoding="utf-8")


async def test_flipkart_alone_is_fetched_through_its_own_fetcher_when_one_is_given() -> None:
    # Neither fetcher knows any shop page, so every shop fails; what matters is who was asked.
    shared = FakeFetcher({PRODUCT_URL: FetchedPage(status_code=200, url=PRODUCT_URL, text=PHONE_HTML)})
    flipkart_only = FakeFetcher({})

    report = await build_live_comparer(shared, Settings(), flipkart_fetcher=flipkart_only).compare(
        PRODUCT_URL
    )

    assert {result.platform for result in report.results} == {Platform.FLIPKART, Platform.CROMA}
    assert all(result.status is MatchStatus.ERROR for result in report.results)
    assert flipkart_only.requests
    assert all("flipkart.com" in key for key, _ in flipkart_only.requests)
    assert not any("flipkart.com" in key for key, _ in shared.requests)


def test_the_flipkart_proxy_address_is_kept_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MATCHER_FLIPKART_PROXY_URL", "http://user:hunter2@proxy.test:44445")

    settings = Settings()

    assert settings.flipkart_proxy_url is not None
    assert settings.flipkart_proxy_url.get_secret_value() == "http://user:hunter2@proxy.test:44445"
    assert "hunter2" not in repr(settings)


def test_live_mode_starts_with_a_flipkart_proxy() -> None:
    from fastapi.testclient import TestClient

    from app.main import create_app
    from app.services.comparer import LiveProductComparer

    settings = Settings(demo=False, flipkart_proxy_url="http://user:secret@proxy.test:44445")  # type: ignore[arg-type]
    app = create_app(settings=settings)
    with TestClient(app):  # runs startup and shutdown, opening and closing both HTTP sessions
        assert isinstance(app.state.comparer, LiveProductComparer)
