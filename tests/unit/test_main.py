import asyncio
from pathlib import Path
from typing import Any

import pytest

from app.config import Settings
from app.domain.models import MatchStatus, Platform
from app.domain.ports import FetchedPage
from app.main import build_live_comparer
from support.fakes import FakeFetcher

AMAZON = Path(__file__).resolve().parents[1] / "fixtures" / "amazon"
PHONE_URL = "https://www.amazon.in/dp/B0DHL7YT5S"
POLO_URL = "https://www.amazon.in/dp/B0DDTHBCJP"


def _amazon(url: str, fixture: str, fetcher: type[FakeFetcher] = FakeFetcher) -> FakeFetcher:
    """A fetcher that knows only this Amazon page, so every shop it is asked for fails."""
    html = (AMAZON / fixture).read_text(encoding="utf-8")
    return fetcher({url: FetchedPage(status_code=200, url=url, text=html)})


def _hosts(fetcher: FakeFetcher) -> set[str]:
    return {key.split("/")[2] for key, _ in fetcher.requests}


async def test_by_default_flipkart_and_myntra_go_through_the_proxy_and_the_rest_go_direct() -> None:
    # Neither fetcher knows any shop page, so every shop fails; what matters is who was asked.
    direct = _amazon(POLO_URL, "polo_puma_687093.html")
    proxied = FakeFetcher({})

    report = await build_live_comparer(direct, Settings(), proxied_fetcher=proxied).compare(POLO_URL)

    assert all(result.status is MatchStatus.ERROR for result in report.results)
    assert _hosts(proxied) == {"www.flipkart.com", "www.myntra.com"}
    assert _hosts(direct) & {"www.flipkart.com", "www.myntra.com"} == set()


async def test_the_proxied_shops_can_be_chosen() -> None:
    direct = _amazon(PHONE_URL, "phone_samsung_s24fe.html")
    proxied = FakeFetcher({})
    settings = Settings(proxied_shops=(Platform.CROMA,))

    await build_live_comparer(direct, settings, proxied_fetcher=proxied).compare(PHONE_URL)

    assert _hosts(proxied)
    assert all("croma.com" in host for host in _hosts(proxied))
    assert "www.flipkart.com" in _hosts(direct)


async def test_without_a_proxy_every_shop_goes_direct() -> None:
    direct = _amazon(PHONE_URL, "phone_samsung_s24fe.html")

    report = await build_live_comparer(direct, Settings()).compare(PHONE_URL)

    assert {result.platform for result in report.results} == {Platform.FLIPKART, Platform.CROMA}
    assert "www.flipkart.com" in _hosts(direct)


class SlowFetcher(FakeFetcher):
    async def get(self, url: str, **options: Any) -> FetchedPage:
        await asyncio.sleep(0.2)
        return await super().get(url, **options)

    async def post_json(self, url: str, payload: Any, **options: Any) -> FetchedPage:
        await asyncio.sleep(0.2)
        return await super().post_json(url, payload, **options)


async def test_the_proxied_shops_get_their_own_time_limit() -> None:
    # Every shop request is slower than the default limit; only the proxied Flipkart has time to answer.
    direct = _amazon(PHONE_URL, "phone_samsung_s24fe.html", SlowFetcher)
    settings = Settings(platform_timeout_s=0.05, proxied_platform_timeout_s=5.0)

    report = await build_live_comparer(direct, settings, proxied_fetcher=SlowFetcher({})).compare(PHONE_URL)

    flipkart, croma = report.results
    assert "Couldn't check Flipkart" in flipkart.reason  # it failed, but it wasn't cut short
    assert "took too long" in croma.reason


def test_the_proxied_shops_are_read_from_a_comma_separated_list(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MATCHER_PROXIED_SHOPS", "Flipkart, croma")

    assert Settings().proxied_shops == (Platform.FLIPKART, Platform.CROMA)


@pytest.mark.parametrize("name", ["MATCHER_PROXY_URL", "MATCHER_FLIPKART_PROXY_URL"])
def test_the_proxy_address_is_read_under_either_name_and_kept_secret(
    monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    monkeypatch.setenv(name, "http://user:hunter2@proxy.test:44445")

    settings = Settings()

    assert settings.proxy_url is not None
    assert settings.proxy_url.get_secret_value() == "http://user:hunter2@proxy.test:44445"
    assert "hunter2" not in repr(settings)


def test_an_empty_proxy_address_does_not_hide_the_older_name(monkeypatch: pytest.MonkeyPatch) -> None:
    # A host may create the new variable empty while the working address still sits under the old name.
    monkeypatch.setenv("MATCHER_PROXY_URL", "")
    monkeypatch.setenv("MATCHER_FLIPKART_PROXY_URL", "http://user:secret@proxy.test:44445")

    settings = Settings()

    assert settings.proxy_url is not None
    assert settings.proxy_url.get_secret_value() == "http://user:secret@proxy.test:44445"


def test_live_mode_starts_with_a_proxy() -> None:
    from fastapi.testclient import TestClient

    from app.main import create_app
    from app.services.comparer import LiveProductComparer

    settings = Settings(demo=False, proxy_url="http://user:secret@proxy.test:44445")  # type: ignore[arg-type]
    app = create_app(settings=settings)
    with TestClient(app):  # runs startup and shutdown, opening and closing both HTTP sessions
        assert isinstance(app.state.comparer, LiveProductComparer)
