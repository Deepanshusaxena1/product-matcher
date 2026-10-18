from collections.abc import Callable

import pytest

from app.domain.models import Availability, Category, Listing, Platform
from app.domain.ports import FetchError, UnexpectedPageError
from app.platforms.myntra.adapter import MyntraAdapter
from support.fakes import FakeFetcher, page

QUERY = "nike court vision low white men sneakers"
LOW_URL = "https://www.myntra.com/casual-shoes/nike/nike-men-court-vision-low-sneakers/27306858/buy"
SEARCH_KEY = (
    "https://www.myntra.com/nike-court-vision-low-white-men-sneakers"
    "?rawQuery=nike+court+vision+low+white+men+sneakers"
)


async def test_search_opens_the_results_page_for_the_query(myntra_page: Callable[[str], str]) -> None:
    fetcher = FakeFetcher({SEARCH_KEY: page(myntra_page("search_nike_court_vision.html"))})

    results = await MyntraAdapter(fetcher).search(QUERY, Category.SNEAKER)

    assert len(results) == 14
    assert all(listing.platform is Platform.MYNTRA for listing in results)


async def test_details_complete_a_tile_with_its_product_page(myntra_page: Callable[[str], str]) -> None:
    tile = Listing(
        platform=Platform.MYNTRA,
        listing_id="27306858",
        url=LOW_URL,
        title="Nike Men Court Vision Low Sneakers",
        price_inr=4999,
        image_url="https://assets.myntassets.com/assets/images/27306858/x.jpg",
    )
    fetcher = FakeFetcher({LOW_URL: page(myntra_page("pdp_nike_court_vision_low.html"))})

    detailed = await MyntraAdapter(fetcher).fetch_details(tile)

    assert detailed.availability is Availability.IN_STOCK
    assert detailed.price_inr == 4271
    assert detailed.fingerprint.colour == "White"
    assert detailed.image_url == tile.image_url


def test_myntra_shows_no_style_codes_and_counts_any_size_as_in_stock() -> None:
    profile = MyntraAdapter(FakeFetcher({})).profile

    assert not profile.shows_model_numbers
    assert profile.stock_note == "In stock means at least one size is available on Myntra."


@pytest.mark.parametrize(
    "response",
    [page("<html>Oops! Something went wrong</html>"), page("", status=503)],
    ids=["no-data", "error"],
)
async def test_a_search_that_does_not_return_results_is_unexpected(response: object) -> None:
    fetcher = FakeFetcher({SEARCH_KEY: response})  # type: ignore[dict-item]

    with pytest.raises(UnexpectedPageError):
        await MyntraAdapter(fetcher).search(QUERY, Category.SNEAKER)


async def test_fetch_failures_reach_the_caller() -> None:
    fetcher = FakeFetcher({SEARCH_KEY: FetchError("blocked")})

    with pytest.raises(FetchError):
        await MyntraAdapter(fetcher).search(QUERY, Category.SNEAKER)
