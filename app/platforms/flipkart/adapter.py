"""`PlatformAdapter` for Flipkart."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.domain.models import Availability, Platform
from app.domain.ports import ShopProfile, UnexpectedPageError
from app.platforms.flipkart.common import BASE_URL
from app.platforms.flipkart.product import parse_product_page
from app.platforms.flipkart.search import parse_search_results

if TYPE_CHECKING:
    from app.domain.models import Category, Listing
    from app.domain.ports import FetchedPage, PageFetcher

_SEARCH_URL = f"{BASE_URL}/search"


class FlipkartAdapter:
    def __init__(self, fetcher: PageFetcher) -> None:
        self._fetcher = fetcher

    @property
    def platform(self) -> Platform:
        return Platform.FLIPKART

    @property
    def profile(self) -> ShopProfile:
        return ShopProfile()  # product pages state model numbers and style codes; stock is not regional

    async def search(self, query: str, category: Category) -> list[Listing]:
        # Flipkart's search spans all departments; the matcher drops results from other categories.
        response = _expect_ok(await self._fetcher.get(_SEARCH_URL, params={"q": query}))
        results = parse_search_results(response.text)
        if results is None:
            raise UnexpectedPageError(f"Flipkart's search for {query!r} returned a page without results")
        return results

    async def fetch_details(self, listing: Listing) -> Listing:
        response = _expect_ok(await self._fetcher.get(listing.url))
        page = parse_product_page(response.text)
        if page is None:
            raise UnexpectedPageError(f"Flipkart's page for {listing.listing_id} is not a product page")
        return listing.model_copy(
            update={
                "fingerprint": page.fingerprint.completed_with(listing.fingerprint),
                "availability": (
                    page.availability
                    if page.availability is not Availability.UNKNOWN
                    else listing.availability
                ),
                "price_inr": page.price_inr if page.price_inr is not None else listing.price_inr,
                "image_url": listing.image_url or page.image_url,
            }
        )


def _expect_ok(response: FetchedPage) -> FetchedPage:
    if response.status_code != 200:
        raise UnexpectedPageError(f"Flipkart answered HTTP {response.status_code} for {response.url}")
    return response
