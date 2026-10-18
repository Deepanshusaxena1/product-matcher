import asyncio
import contextlib
from datetime import UTC, datetime

import pytest

from app.domain.errors import UnsupportedCategoryError
from app.domain.models import (
    Category,
    Fingerprint,
    Listing,
    MatchStatus,
    Platform,
    PlatformChecked,
    PlatformResult,
    SourceRead,
)
from app.domain.ports import FetchError, PlatformAdapter, ShopProfile
from app.services.comparer import LiveProductComparer

TV = Listing(
    platform=Platform.AMAZON,
    listing_id="B0GTZ9TSDJ",
    url="https://www.amazon.in/dp/B0GTZ9TSDJ",
    title="LG 108 cms (43 inches) NU87 TV 43NU870BPLA",
    fingerprint=Fingerprint(
        category=Category.TELEVISION, brand="lg", model_number="43NU870BPLA", screen_in=43
    ),
)


class FakeSource:
    def __init__(self, listing: Listing | Exception) -> None:
        self._listing = listing

    async def read(self, product_url: str) -> Listing:
        if isinstance(self._listing, Exception):
            raise self._listing
        return self._listing


class NamedAdapter:
    def __init__(self, platform: Platform) -> None:
        self._platform = platform

    @property
    def platform(self) -> Platform:
        return self._platform

    @property
    def profile(self) -> ShopProfile:
        return ShopProfile()

    async def search(self, query: str, category: Category) -> list[Listing]:
        raise AssertionError("the fake finder never searches")

    async def fetch_details(self, listing: Listing) -> Listing:
        raise AssertionError("the fake finder never opens pages")


class FakeFinder:
    """Answers per platform with a canned result, an exception, or a delay that never ends in a result."""

    def __init__(
        self,
        outcomes: dict[Platform, PlatformResult | Exception | float],
        delays: dict[Platform, float] | None = None,
    ) -> None:
        self._outcomes = outcomes
        self._delays = delays or {}

    async def find(self, source: Listing, adapter: PlatformAdapter) -> PlatformResult:
        await asyncio.sleep(self._delays.get(adapter.platform, 0))
        outcome = self._outcomes[adapter.platform]
        if isinstance(outcome, float):
            await asyncio.sleep(outcome)
            raise AssertionError("should have timed out")
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _not_listed(platform: Platform) -> PlatformResult:
    return PlatformResult(platform=platform, status=MatchStatus.NOT_LISTED, reason="Not sold here.")


def _comparer(
    outcomes: dict[Platform, PlatformResult | Exception | float], **options: float
) -> LiveProductComparer:
    return LiveProductComparer(
        FakeSource(TV),
        adapters=[NamedAdapter(platform) for platform in outcomes],
        finder=FakeFinder(outcomes),
        **options,
    )


async def test_each_platform_for_the_category_gets_one_result_in_order() -> None:
    comparer = _comparer(
        {Platform.CROMA: _not_listed(Platform.CROMA), Platform.FLIPKART: _not_listed(Platform.FLIPKART)}
    )

    report = await comparer.compare(TV.url)

    assert report.source == TV
    assert [result.platform for result in report.results] == [Platform.FLIPKART, Platform.CROMA]
    assert not report.demo


async def test_a_platform_without_an_adapter_is_reported_as_not_checked() -> None:
    comparer = _comparer({Platform.FLIPKART: _not_listed(Platform.FLIPKART)})

    report = await comparer.compare(TV.url)

    croma = report.results[1]
    assert croma.status is MatchStatus.ERROR
    assert "Croma" in croma.reason


async def test_a_failing_platform_is_reported_as_could_not_check_without_affecting_others() -> None:
    comparer = _comparer(
        {Platform.FLIPKART: FetchError("blocked"), Platform.CROMA: _not_listed(Platform.CROMA)}
    )

    report = await comparer.compare(TV.url)

    flipkart, croma = report.results
    assert flipkart.status is MatchStatus.ERROR
    assert "Couldn't check Flipkart" in flipkart.reason
    assert croma.status is MatchStatus.NOT_LISTED


async def test_a_platform_that_takes_too_long_is_reported_as_could_not_check() -> None:
    comparer = _comparer(
        {Platform.FLIPKART: 5.0, Platform.CROMA: _not_listed(Platform.CROMA)}, platform_timeout_s=0.05
    )

    report = await comparer.compare(TV.url)

    assert report.results[0].status is MatchStatus.ERROR
    assert "took too long" in report.results[0].reason


async def test_problems_with_the_amazon_link_reach_the_caller() -> None:
    comparer = LiveProductComparer(
        FakeSource(UnsupportedCategoryError("not supported")), adapters=[], finder=FakeFinder({})
    )

    with pytest.raises(UnsupportedCategoryError):
        await comparer.compare(TV.url)


def test_the_comparer_says_which_platforms_it_can_search() -> None:
    comparer = _comparer({Platform.MYNTRA: 0.0, Platform.FLIPKART: 0.0})

    assert comparer.connected_platforms == (Platform.FLIPKART, Platform.MYNTRA)


NOW = datetime(2026, 10, 18, 12, 0, tzinfo=UTC)


async def test_the_stream_sends_the_source_first_then_each_shop_as_soon_as_it_answers() -> None:
    outcomes: dict[Platform, PlatformResult | Exception | float] = {
        Platform.FLIPKART: _not_listed(Platform.FLIPKART),
        Platform.CROMA: _not_listed(Platform.CROMA),
    }
    comparer = LiveProductComparer(
        FakeSource(TV),
        adapters=[NamedAdapter(platform) for platform in outcomes],
        finder=FakeFinder(outcomes, delays={Platform.FLIPKART: 0.05}),
        clock=lambda: NOW,
    )

    events = [event async for event in comparer.stream(TV.url)]

    assert events[0] == SourceRead(source=TV, platforms=(Platform.FLIPKART, Platform.CROMA))
    assert [event.result.platform for event in events[1:] if isinstance(event, PlatformChecked)] == [
        Platform.CROMA,
        Platform.FLIPKART,
    ]


async def test_each_answer_says_when_it_was_checked() -> None:
    comparer = LiveProductComparer(
        FakeSource(TV),
        adapters=[NamedAdapter(Platform.FLIPKART)],
        finder=FakeFinder({Platform.FLIPKART: _not_listed(Platform.FLIPKART)}),
        clock=lambda: NOW,
    )

    report = await comparer.compare(TV.url)

    assert {result.checked_at for result in report.results} == {NOW}


async def test_an_answer_that_already_knows_when_it_was_checked_keeps_that_time() -> None:
    earlier = _not_listed(Platform.FLIPKART).model_copy(
        update={"checked_at": datetime(2026, 10, 18, tzinfo=UTC)}
    )
    comparer = LiveProductComparer(
        FakeSource(TV),
        adapters=[NamedAdapter(Platform.FLIPKART)],
        finder=FakeFinder({Platform.FLIPKART: earlier}),
        clock=lambda: NOW,
    )

    report = await comparer.compare(TV.url)

    assert report.results[0].checked_at == earlier.checked_at


async def test_shops_still_being_checked_are_stopped_when_the_listener_leaves() -> None:
    started = asyncio.Event()
    cancelled = asyncio.Event()

    class SlowFinder:
        async def find(self, source: Listing, adapter: PlatformAdapter) -> PlatformResult:
            started.set()
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                cancelled.set()
                raise
            raise AssertionError("should have been cancelled")

    comparer = LiveProductComparer(
        FakeSource(TV), adapters=[NamedAdapter(Platform.FLIPKART)], finder=SlowFinder()
    )
    events = comparer.stream(TV.url)

    await anext(events)  # the source
    waiting = asyncio.ensure_future(anext(events))
    await started.wait()
    waiting.cancel()  # what the server does when the browser disconnects
    with contextlib.suppress(asyncio.CancelledError):
        await waiting
    await events.aclose()

    await asyncio.wait_for(cancelled.wait(), timeout=1)
