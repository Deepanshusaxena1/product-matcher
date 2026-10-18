"""Fashion products outside the five samples, against live Flipkart and Myntra. Opt-in: `-m live`.

They cover what the samples don't: a brand name before a "|" in the title, adidas style codes that sit in
Amazon's part number, colours a shop names more simply than Amazon, and a T-shirt Myntra can't identify.
Checked by hand on 2026-10-18.
"""

import pytest

from app.domain.models import MatchStatus, Platform
from app.matching.rules import assess
from app.services.comparer import LiveProductComparer

pytestmark = pytest.mark.live

FOUND = {MatchStatus.IN_STOCK, MatchStatus.OUT_OF_STOCK}


@pytest.mark.parametrize(
    ("asin", "platform", "expected"),
    [
        ("B0BSLKJPXV", Platform.FLIPKART, FOUND),  # Puma | Smashic: style code 39437102
        ("B09VSZNT7Z", Platform.FLIPKART, FOUND),  # adidas Grand Court Base 2.0: style code GW9250
        ("B0DSFRSPRK", Platform.FLIPKART, {MatchStatus.NOT_LISTED}),  # Flipkart has JK8211, not JK2072
        ("B0DSFRSPRK", Platform.MYNTRA, {MatchStatus.NOT_LISTED}),  # Myntra has no Streeet Icon
        ("B0DDTHBCJP", Platform.MYNTRA, {MatchStatus.NOT_LISTED}),  # a polo is never matched by name alone
    ],
)
async def test_each_product_gets_its_known_answer(
    comparer: LiveProductComparer, asin: str, platform: Platform, expected: set[MatchStatus]
) -> None:
    report = await comparer.compare(f"https://www.amazon.in/dp/{asin}")

    result = next(result for result in report.results if result.platform is platform)
    assert result.status in expected, result.reason
    if result.listing is not None:
        assert assess(report.source.fingerprint, result.listing, final=True).confirmed
