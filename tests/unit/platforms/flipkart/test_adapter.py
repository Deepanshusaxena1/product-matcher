from collections.abc import Callable

import pytest

from app.domain.models import Availability, Category, Fingerprint, Listing, Platform
from app.domain.ports import FetchError, ShopProfile, UnexpectedPageError
from app.platforms.flipkart.adapter import FlipkartAdapter
from support.fakes import FakeFetcher, page

SEARCH = "https://www.flipkart.com/search"
GRAPHITE_OOS_URL = "https://www.flipkart.com/samsung-galaxy-s24-fe-5g-graphite-128-gb/p/itmfbdcb1f478cbf?pid=MOBH92ADUFBMDXZX"


async def test_search_returns_every_tile_of_the_results_page(flipkart_page: Callable[[str], str]) -> None:
    fetcher = FakeFetcher(
        {f"{SEARCH}?q=samsung+galaxy+s24+fe": page(flipkart_page("search_samsung_s24fe.html"))}
    )

    results = await FlipkartAdapter(fetcher).search("samsung galaxy s24 fe", Category.SMARTPHONE)

    assert len(results) > 20
    assert all(listing.platform is Platform.FLIPKART for listing in results)


async def test_details_complete_a_search_tile_with_the_product_page(
    flipkart_page: Callable[[str], str],
) -> None:
    tile = Listing(
        platform=Platform.FLIPKART,
        listing_id="MOBH92ADUFBMDXZX",
        url=GRAPHITE_OOS_URL,
        title="Samsung Galaxy S24 FE 5G (Graphite, 128 GB)",
        fingerprint=Fingerprint(category=Category.SMARTPHONE, brand="samsung", ram_gb=8),
        availability=Availability.UNKNOWN,
        price_inr=39999,
        image_url="https://rukmini1.flixcart.com/image/416/416/x.jpeg?q=70",
    )
    fetcher = FakeFetcher({GRAPHITE_OOS_URL: page(flipkart_page("pdp_samsung_s24fe_graphite_oos.html"))})

    detailed = await FlipkartAdapter(fetcher).fetch_details(tile)

    assert detailed.url == GRAPHITE_OOS_URL
    assert detailed.availability is Availability.OUT_OF_STOCK
    assert detailed.price_inr == 38998  # the product page's price is the current one
    assert detailed.image_url == tile.image_url  # the tile's image is already sized for display
    assert detailed.fingerprint.model_number == "S721B-SM"
    assert (detailed.fingerprint.ram_gb, detailed.fingerprint.storage_gb) == (8, 128)


@pytest.mark.parametrize(
    "response",
    [
        page("<html><body>Please verify you are a human</body></html>"),
        page("", status=500),
    ],
    ids=["robot-page", "server-error"],
)
async def test_a_search_that_does_not_return_results_is_unexpected(response: object) -> None:
    fetcher = FakeFetcher({f"{SEARCH}?q=lg+43nu870bpla": response})  # type: ignore[dict-item]

    with pytest.raises(UnexpectedPageError):
        await FlipkartAdapter(fetcher).search("lg 43nu870bpla", Category.TELEVISION)


async def test_fetch_failures_reach_the_caller() -> None:
    fetcher = FakeFetcher({f"{SEARCH}?q=lg+43nu870bpla": FetchError("blocked")})

    with pytest.raises(FetchError):
        await FlipkartAdapter(fetcher).search("lg 43nu870bpla", Category.TELEVISION)


def test_flipkart_shows_model_numbers_and_has_no_stock_caveat() -> None:
    assert FlipkartAdapter(FakeFetcher({})).profile == ShopProfile()
