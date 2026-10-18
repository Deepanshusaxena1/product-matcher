"""Compares the sample products against live Croma and Myntra. Opt-in: `uv run pytest -m live tests/live`.

Stock changes daily, so a product Croma or Myntra sells is checked for being the same product (every
must-match attribute agrees), not for a particular stock status. What they don't sell was verified by
hand on 2026-10-17/18.
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
        ("B0DHL7YT5S", Platform.CROMA, {MatchStatus.NOT_LISTED}),  # Croma has no Galaxy S24 FE
        ("B0CS69QQTG", Platform.CROMA, FOUND),  # Galaxy S24, Onyx Black, 8/256
        ("B0GTZ9TSDJ", Platform.CROMA, FOUND),  # LG 43NU870BPLA
        # Myntra lists a "Court Vision Low", but nothing it shows says it is the Next Nature edition.
        ("B0983NTYZ5", Platform.MYNTRA, {MatchStatus.NOT_LISTED}),
        ("B0DDTHBCJP", Platform.MYNTRA, {MatchStatus.NOT_LISTED}),  # no style code, so never confirmed
    ],
)
async def test_each_sample_gets_its_known_answer(
    comparer: LiveProductComparer, asin: str, platform: Platform, expected: set[MatchStatus]
) -> None:
    report = await comparer.compare(f"https://www.amazon.in/dp/{asin}")

    result = next(result for result in report.results if result.platform is platform)
    assert result.status in expected, result.reason
    if result.listing is not None:
        assert assess(report.source.fingerprint, result.listing, final=True).confirmed
