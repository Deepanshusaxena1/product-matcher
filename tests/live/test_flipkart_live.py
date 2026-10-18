"""Compares the five sample products against live Flipkart. Opt-in: `uv run pytest -m live tests/live`.

Stock changes daily, so these assert that the product is found and that the listing really is the same
product (every must-match attribute agrees), not a particular stock status.
"""

import pytest

from app.domain.models import MatchStatus, Platform
from app.matching.rules import assess
from app.services.comparer import LiveProductComparer

pytestmark = pytest.mark.live


@pytest.mark.parametrize("asin", ["B0DHL7YT5S", "B0CS69QQTG", "B0GTZ9TSDJ", "B0983NTYZ5", "B0DDTHBCJP"])
async def test_each_sample_is_found_on_flipkart_as_the_same_product(
    comparer: LiveProductComparer, asin: str
) -> None:
    report = await comparer.compare(f"https://www.amazon.in/dp/{asin}")

    flipkart = next(result for result in report.results if result.platform is Platform.FLIPKART)
    assert flipkart.status in {MatchStatus.IN_STOCK, MatchStatus.OUT_OF_STOCK}, flipkart.reason
    assert flipkart.listing is not None
    assert assess(report.source.fingerprint, flipkart.listing, final=True).confirmed
