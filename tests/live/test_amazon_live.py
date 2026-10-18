"""Reads real Amazon.in pages. Opt-in: `uv run pytest -m live tests/live`."""

from collections.abc import AsyncIterator

import pytest

from app.domain.models import Category, Fingerprint
from app.infra.http import CurlPageFetcher
from app.sources.amazon.reader import AmazonProductSource

pytestmark = pytest.mark.live


@pytest.fixture
async def source() -> AsyncIterator[AmazonProductSource]:
    fetcher = CurlPageFetcher.impersonating_chrome()
    yield AmazonProductSource(fetcher)
    await fetcher.aclose()


@pytest.mark.parametrize(
    ("asin", "expected"),
    [
        ("B0DHL7YT5S", {"category": Category.SMARTPHONE, "brand": "samsung", "ram_gb": 8, "storage_gb": 128}),
        ("B0CS69QQTG", {"category": Category.SMARTPHONE, "brand": "samsung", "ram_gb": 8, "storage_gb": 256}),
        ("B0GTZ9TSDJ", {"category": Category.TELEVISION, "brand": "lg", "screen_in": 43.0}),
        ("B0983NTYZ5", {"category": Category.SNEAKER, "brand": "nike", "colour_families": ("white",)}),
        ("B0DDTHBCJP", {"category": Category.TSHIRT, "brand": "puma", "colour_families": ("black",)}),
    ],
)
async def test_sample_products_are_fingerprinted_from_the_live_site(
    source: AmazonProductSource, asin: str, expected: dict[str, object]
) -> None:
    listing = await source.read(f"https://www.amazon.in/dp/{asin}")

    actual = listing.fingerprint.model_dump(include=set(expected))
    assert actual == Fingerprint.model_validate(expected).model_dump(include=set(expected))
