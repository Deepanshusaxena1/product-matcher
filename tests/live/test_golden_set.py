"""The golden set: real Amazon products whose answer on each shop was checked by hand.

Opt-in, against the live sites: `uv run pytest -m live tests/live/test_golden_set.py`. The priority is
precision: a listing the matcher claims must agree on every must-match attribute, and a product a shop
doesn't sell must never be reported as found.
"""

import json
from pathlib import Path
from typing import Any

import pytest

from app.domain.models import MatchStatus
from app.matching.rules import assess
from app.services.comparer import LiveProductComparer

pytestmark = pytest.mark.live

GOLDEN = json.loads((Path(__file__).parent / "golden_set.json").read_text(encoding="utf-8"))
OUTCOMES = {
    "found": {MatchStatus.IN_STOCK, MatchStatus.OUT_OF_STOCK},
    "not_listed": {MatchStatus.NOT_LISTED},
}


@pytest.mark.parametrize("product", GOLDEN["products"], ids=lambda product: product["asin"])
async def test_each_shop_gives_the_hand_checked_answer(
    comparer: LiveProductComparer, product: dict[str, Any]
) -> None:
    report = await comparer.compare(f"https://www.amazon.in/dp/{product['asin']}")

    for result in report.results:
        expected = set().union(*(OUTCOMES[outcome] for outcome in product["expect"][result.platform]))
        assert result.status in expected, f"{result.platform}: {result.reason} ({product['why']})"
        if result.listing is not None:  # never a false match
            assert assess(report.source.fingerprint, result.listing, final=True).confirmed
