from collections.abc import AsyncIterator

import pytest

from app.domain.models import (
    Category,
    ComparisonEvent,
    Fingerprint,
    Listing,
    MatchStatus,
    Platform,
    PlatformChecked,
    PlatformResult,
    SourceRead,
)
from app.services.report import collect_report

PHONE = Listing(
    platform=Platform.AMAZON,
    listing_id="B0DHL7YT5S",
    url="https://www.amazon.in/dp/B0DHL7YT5S",
    title="Samsung Galaxy S24 FE",
    fingerprint=Fingerprint(category=Category.SMARTPHONE, brand="samsung"),
)


def _checked(platform: Platform) -> PlatformChecked:
    return PlatformChecked(
        result=PlatformResult(platform=platform, status=MatchStatus.NOT_LISTED, reason="-")
    )


async def _events(*events: ComparisonEvent) -> AsyncIterator[ComparisonEvent]:
    for event in events:
        yield event


async def test_results_are_reported_in_the_categorys_platform_order_whatever_order_they_finish() -> None:
    report = await collect_report(
        _events(
            SourceRead(source=PHONE, platforms=(Platform.FLIPKART, Platform.CROMA), demo=True),
            _checked(Platform.CROMA),
            _checked(Platform.FLIPKART),
        )
    )

    assert report.source == PHONE
    assert [result.platform for result in report.results] == [Platform.FLIPKART, Platform.CROMA]
    assert report.demo


async def test_a_stream_that_does_not_start_with_the_source_is_rejected() -> None:
    with pytest.raises(ValueError, match="source"):
        await collect_report(_events(_checked(Platform.CROMA)))
