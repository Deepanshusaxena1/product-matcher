"""The Amazon product the user starts from: link in, fingerprinted listing out."""

from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import urljoin, urlsplit

from app.domain.errors import ProductNotFoundError, SourceUnavailableError, UnsupportedCategoryError
from app.domain.models import Listing, Platform
from app.domain.ports import FetchError
from app.sources.amazon.fingerprint import fingerprint_from
from app.sources.amazon.page import is_robot_check, parse_amazon_page
from app.sources.amazon.url import AmazonLink, parse_amazon_link

if TYPE_CHECKING:
    from app.domain.ports import FetchedPage, PageFetcher

_UNREACHABLE = "Amazon.in couldn't be read just now. Please try again in a minute."
_NO_PRODUCT = "There's no Amazon.in product at that link. Open the product and copy its link again."
_SUPPORTED = "You can compare phones, TVs, sneakers and T-shirts."


class AmazonProductSource:
    """Implements `ProductSource` for Amazon.in."""

    def __init__(self, fetcher: PageFetcher, *, max_redirects: int = 5) -> None:
        self._fetcher = fetcher
        self._max_redirects = max_redirects

    async def read(self, product_url: str) -> Listing:
        link = await self._resolve(parse_amazon_link(product_url))
        assert link.asin is not None  # _resolve only returns product links

        response = await self._get(link.fetch_url, follow_redirects=True)
        if response.status_code == 404:
            raise ProductNotFoundError(_NO_PRODUCT)
        if response.status_code != 200 or not _is_amazon(response.url) or is_robot_check(response.text):
            raise SourceUnavailableError(_UNREACHABLE)

        page = parse_amazon_page(response.text)
        if page is None:
            raise SourceUnavailableError(_UNREACHABLE)

        fingerprint = fingerprint_from(page)
        if fingerprint.category is None:
            raise UnsupportedCategoryError(_unsupported(page.breadcrumbs))

        return Listing(
            platform=Platform.AMAZON,
            listing_id=link.asin,
            url=link.fetch_url,
            title=page.title,
            fingerprint=fingerprint,
            availability=page.availability,
            price_inr=page.price_inr,
            image_url=page.image_url,
        )

    async def _resolve(self, link: AmazonLink) -> AmazonLink:
        """Follow a short link hop by hop, re-validating every hop so it can never leave Amazon."""
        for _ in range(self._max_redirects):
            if not link.is_short_link:
                return link
            response = await self._get(link.fetch_url, follow_redirects=False)
            location = response.redirect_location
            if location is None:
                raise ProductNotFoundError(_NO_PRODUCT)
            link = parse_amazon_link(urljoin(link.fetch_url, location))
        if link.is_short_link:
            raise SourceUnavailableError(_UNREACHABLE)
        return link

    async def _get(self, url: str, *, follow_redirects: bool) -> FetchedPage:
        try:
            return await self._fetcher.get(url, follow_redirects=follow_redirects)
        except FetchError as error:
            raise SourceUnavailableError(_UNREACHABLE) from error


def _is_amazon(url: str) -> bool:
    host = (urlsplit(url).hostname or "").lower()
    return host == "amazon.in" or host.endswith(".amazon.in")


def _unsupported(breadcrumbs: tuple[str, ...]) -> str:
    """ "Laptops aren't supported. ...", naming the kind of product by its plainest category name."""
    if not breadcrumbs:
        return f"This product isn't supported. {_SUPPORTED}"
    kind = breadcrumbs[-1]
    # "Traditional Laptops" sits under "Laptops": the parent says the same thing more plainly.
    for parent in reversed(breadcrumbs[:-1]):
        if not kind.casefold().endswith(parent.casefold()):
            break
        kind = parent
    return f"{kind[0].upper()}{kind[1:]} aren't supported. {_SUPPORTED}"
