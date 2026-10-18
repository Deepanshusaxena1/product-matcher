from collections.abc import Callable
from urllib.parse import urlencode

import pytest

from app.domain.models import Availability, Category, Platform
from app.domain.ports import FetchError, UnexpectedPageError
from app.platforms.croma.adapter import CromaAdapter
from app.platforms.croma.inventory import InventoryKey
from support.fakes import FakeFetcher, page

SEARCH = "https://api.croma.com/searchservices/v1/search"
INVENTORY = "POST https://api.croma.com/inventory/oms/v2/details-pwa"
ONYX_URL = "https://www.croma.com/samsung-galaxy-s24-5g-8gb-ram-256gb-onyx-black-/p/303849"


def _search_key(query: str) -> str:
    params = {
        "currentPage": "0",
        "query": f"{query}:relevance",
        "fields": "FULL",
        "channel": "WEB",
        "channelCode": "400001",
        "spellOpt": "DEFAULT",
    }
    return f"{SEARCH}?{urlencode(params)}"


def _adapter(fetcher: FakeFetcher) -> CromaAdapter:
    return CromaAdapter(fetcher, pincode="400001", key=InventoryKey(fetcher, configured="k1"))


async def test_search_asks_cromas_search_api_as_its_own_site_does(croma_file: Callable[[str], str]) -> None:
    fetcher = FakeFetcher({_search_key("samsung galaxy s24"): page(croma_file("search_samsung_s24.json"))})

    results = await _adapter(fetcher).search("samsung galaxy s24", Category.SMARTPHONE)

    assert len(results) == 16
    assert all(listing.platform is Platform.CROMA for listing in results)
    assert fetcher.headers[_search_key("samsung galaxy s24")]["origin"] == "https://www.croma.com"


async def test_details_add_the_product_page_and_the_delivery_check(croma_file: Callable[[str], str]) -> None:
    fetcher = FakeFetcher(
        {
            _search_key("samsung galaxy s24"): page(croma_file("search_samsung_s24.json")),
            ONYX_URL: page(croma_file("pdp_samsung_s24_303849.html")),
            INVENTORY: page(croma_file("inventory_out_of_stock.json")),
        }
    )
    adapter = _adapter(fetcher)
    tile = next(
        listing
        for listing in await adapter.search("samsung galaxy s24", Category.SMARTPHONE)
        if listing.listing_id == "303849"
    )

    detailed = await adapter.fetch_details(tile)

    assert detailed.availability is Availability.OUT_OF_STOCK
    assert detailed.fingerprint.model_number == "SM-S921BZKCINS"
    assert (detailed.fingerprint.ram_gb, detailed.fingerprint.storage_gb) == (8, 256)
    assert detailed.price_inr == tile.price_inr  # product pages don't state the price; the search does
    assert detailed.image_url == tile.image_url


def test_croma_says_which_pincode_its_stock_is_for() -> None:
    profile = _adapter(FakeFetcher({})).profile

    assert profile.shows_model_numbers
    assert profile.stock_note == "Croma's stock is for delivery to pincode 400001."


@pytest.mark.parametrize(
    "response", [page("<html>Access denied</html>"), page("{}", status=500)], ids=["not-json", "server-error"]
)
async def test_a_search_that_does_not_return_results_is_unexpected(response: object) -> None:
    fetcher = FakeFetcher({_search_key("lg 43NU870BPLA"): response})  # type: ignore[dict-item]

    with pytest.raises(UnexpectedPageError):
        await _adapter(fetcher).search("lg 43NU870BPLA", Category.TELEVISION)


async def test_a_product_page_that_is_not_a_product_page_is_unexpected(
    croma_file: Callable[[str], str],
) -> None:
    fetcher = FakeFetcher(
        {
            _search_key("samsung galaxy s24"): page(croma_file("search_samsung_s24.json")),
            ONYX_URL: page("<html>Something went wrong</html>"),
            INVENTORY: page(croma_file("inventory_out_of_stock.json")),
        }
    )
    adapter = _adapter(fetcher)
    [tile, *_] = [
        listing
        for listing in await adapter.search("samsung galaxy s24", Category.SMARTPHONE)
        if listing.listing_id == "303849"
    ]

    with pytest.raises(UnexpectedPageError):
        await adapter.fetch_details(tile)


async def test_fetch_failures_reach_the_caller() -> None:
    fetcher = FakeFetcher({_search_key("lg 43NU870BPLA"): FetchError("blocked")})

    with pytest.raises(FetchError):
        await _adapter(fetcher).search("lg 43NU870BPLA", Category.TELEVISION)
