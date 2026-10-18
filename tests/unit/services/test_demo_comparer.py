import pytest

from app.domain.errors import InvalidProductUrlError
from app.domain.models import (
    Category,
    ComparisonReport,
    Fingerprint,
    Listing,
    MatchStatus,
    Platform,
    PlatformResult,
)
from app.services.demo import DemoProductComparer


@pytest.fixture(scope="module")
def comparer() -> DemoProductComparer:
    return DemoProductComparer.bundled()


async def test_a_sample_link_returns_its_bundled_scenario(comparer: DemoProductComparer) -> None:
    report = await comparer.compare(
        "https://www.amazon.in/Samsung-Galaxy-Smartphone/dp/B0DHL7YT5S/ref=sr_1_3"
    )

    assert report.source.listing_id == "B0DHL7YT5S"
    assert report.demo


async def test_any_other_amazon_link_gets_the_same_sample_every_time(comparer: DemoProductComparer) -> None:
    first = await comparer.compare("https://www.amazon.in/dp/B000000001")
    again = await comparer.compare("https://www.amazon.in/dp/B000000001")

    assert first == again
    assert first.demo


async def test_short_links_get_a_sample_without_being_resolved(comparer: DemoProductComparer) -> None:
    report = await comparer.compare("https://amzn.in/d/5xYz123")

    assert report.demo


async def test_links_that_are_not_amazon_are_rejected_even_in_demo_mode(
    comparer: DemoProductComparer,
) -> None:
    with pytest.raises(InvalidProductUrlError):
        await comparer.compare("https://www.flipkart.com/samsung-galaxy-s24-fe/p/itm123")


def test_every_bundled_scenario_answers_exactly_its_categorys_platforms(
    comparer: DemoProductComparer,
) -> None:
    for scenario in comparer.scenarios:
        category = scenario.source.fingerprint.category
        assert category is not None
        assert tuple(result.platform for result in scenario.results) == category.platforms


def test_the_bundled_scenarios_show_every_result_state(comparer: DemoProductComparer) -> None:
    statuses = {result.status for scenario in comparer.scenarios for result in scenario.results}

    assert statuses == set(MatchStatus)


def test_scenarios_missing_a_platform_are_refused_at_startup() -> None:
    source = Listing(
        platform=Platform.AMAZON,
        listing_id="B0TEST0001",
        url="https://www.amazon.in/dp/B0TEST0001",
        title="Test phone",
        fingerprint=Fingerprint(category=Category.SMARTPHONE),
    )
    flipkart_only = ComparisonReport(
        source=source,
        results=(PlatformResult(platform=Platform.FLIPKART, status=MatchStatus.NOT_LISTED, reason="None"),),
    )

    with pytest.raises(ValueError, match="B0TEST0001"):
        DemoProductComparer([flipkart_only])


async def test_the_stream_sends_the_sample_source_then_its_results(comparer: DemoProductComparer) -> None:
    from app.domain.models import PlatformChecked, SourceRead

    events = [event async for event in comparer.stream("https://www.amazon.in/dp/B0DHL7YT5S")]

    assert isinstance(events[0], SourceRead)
    assert events[0].demo
    assert [type(event) for event in events[1:]] == [PlatformChecked, PlatformChecked]
