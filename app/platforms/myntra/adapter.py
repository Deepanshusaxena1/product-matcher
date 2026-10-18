"""`PlatformAdapter` for Myntra."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from app.domain.models import Availability, Platform
from app.domain.ports import ShopProfile, UnexpectedPageError
from app.platforms.myntra.common import BASE_URL
from app.platforms.myntra.product import parse_product_page
from app.platforms.myntra.search import parse_search_results

if TYPE_CHECKING:
    from app.domain.models import Category, Listing
    from app.domain.ports import FetchedPage, PageFetcher

_NOT_SLUG = re.compile(r"[^a-z0-9]+")

# Myntra's pages never state style codes, and a product is sold size by size.
_PROFILE = ShopProfile(
    shows_model_numbers=False, stock_note="In stock means at least one size is available on Myntra."
)


class MyntraAdapter:
    def __init__(self, fetcher: PageFetcher) -> None:
        self._fetcher = fetcher

    @property
    def platform(self) -> Platform:
        return Platform.MYNTRA

    @property
    def profile(self) -> ShopProfile:
        return _PROFILE

    async def search(self, query: str, category: Category) -> list[Listing]:
        # Myntra's search box opens /<query-slug>?rawQuery=<query>; the slug alone may land on a curated page.
        slug = _NOT_SLUG.sub("-", query.lower()).strip("-")
        response = _expect_ok(await self._fetcher.get(f"{BASE_URL}/{slug}", params={"rawQuery": query}))
        results = parse_search_results(response.text)
        if results is None:
            raise UnexpectedPageError(f"Myntra's search for {query!r} returned a page without results")
        return results

    async def fetch_details(self, listing: Listing) -> Listing:
        page = parse_product_page(_expect_ok(await self._fetcher.get(listing.url)).text)
        if page is None:
            raise UnexpectedPageError(f"Myntra's page for {listing.listing_id} is not a product page")
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
        raise UnexpectedPageError(f"Myntra answered HTTP {response.status_code} for {response.url}")
    return response
