"""`PlatformAdapter` for Croma."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from app.domain.models import Platform
from app.domain.ports import ShopProfile, UnexpectedPageError
from app.platforms.croma.common import API_URL, SITE_HEADERS
from app.platforms.croma.inventory import CromaStockChecker, InventoryKey
from app.platforms.croma.product import CromaProductPage, parse_product_page
from app.platforms.croma.search import parse_search_results

if TYPE_CHECKING:
    from app.domain.models import Category, Listing
    from app.domain.ports import FetchedPage, PageFetcher

_SEARCH_URL = f"{API_URL}/searchservices/v1/search"


class CromaAdapter:
    def __init__(self, fetcher: PageFetcher, *, pincode: str, key: InventoryKey | None = None) -> None:
        self._fetcher = fetcher
        self._pincode = pincode
        self._stock = CromaStockChecker(fetcher, key or InventoryKey(fetcher), pincode=pincode)

    @property
    def platform(self) -> Platform:
        return Platform.CROMA

    @property
    def profile(self) -> ShopProfile:
        return ShopProfile(stock_note=f"Croma's stock is for delivery to pincode {self._pincode}.")

    async def search(self, query: str, category: Category) -> list[Listing]:
        # Croma's search spans all departments; the matcher drops results from other categories.
        params = {
            "currentPage": "0",
            "query": f"{query}:relevance",
            "fields": "FULL",
            "channel": "WEB",
            "channelCode": self._pincode,
            "spellOpt": "DEFAULT",
        }
        response = _expect_ok(await self._fetcher.get(_SEARCH_URL, params=params, headers=SITE_HEADERS))
        try:
            results = parse_search_results(response.json())
        except ValueError:
            results = None
        if results is None:
            raise UnexpectedPageError(f"Croma's search for {query!r} did not return search results")
        return results

    async def fetch_details(self, listing: Listing) -> Listing:
        page, availability = await asyncio.gather(
            self._product_page(listing), self._stock.availability(listing.listing_id)
        )
        return listing.model_copy(
            update={
                "fingerprint": page.fingerprint.completed_with(listing.fingerprint),
                "availability": availability,
                "image_url": listing.image_url or page.image_url,
            }
        )

    async def _product_page(self, listing: Listing) -> CromaProductPage:
        page = parse_product_page(_expect_ok(await self._fetcher.get(listing.url)).text)
        if page is None:
            raise UnexpectedPageError(f"Croma's page for {listing.listing_id} is not a product page")
        return page


def _expect_ok(response: FetchedPage) -> FetchedPage:
    if response.status_code != 200:
        raise UnexpectedPageError(f"Croma answered HTTP {response.status_code} for {response.url}")
    return response
