"""Myntra search results: `window.__myx.searchData.results.products`."""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from app.domain.models import Listing, Platform
from app.normalize.facts import ListingFacts, fingerprint_from_facts
from app.platforms.embedded_json import dig, embedded_json
from app.platforms.myntra.common import BASE_URL, STATE_MARKER, category_from_article_type, secure_image_url


def parse_search_results(html: str) -> list[Listing] | None:
    """Every product tile on the page, in page order; None when the page holds no search results."""
    products = dig(embedded_json(html, STATE_MARKER), "searchData", "results", "products")
    if not isinstance(products, list):
        return None
    listings = (_listing(product) for product in products if isinstance(product, dict))
    return [listing for listing in listings if listing is not None]


def _listing(product: dict[str, Any]) -> Listing | None:
    title, path = product.get("productName"), product.get("landingPageUrl")
    if not (isinstance(title, str) and title and isinstance(path, str) and product.get("productId")):
        return None
    category = category_from_article_type(product.get("articleType"), product.get("category"))
    price = product.get("price")
    try:
        return Listing(
            platform=Platform.MYNTRA,
            listing_id=str(product["productId"]),
            url=f"{BASE_URL}/{path.lstrip('/')}",
            title=title,
            fingerprint=fingerprint_from_facts(
                ListingFacts(
                    category=category,
                    title=title,
                    brand=product.get("brand"),
                    colour=product.get("primaryColour"),
                    gender=product.get("gender"),
                )
            ),
            # The tile's `inventoryInfo` covers a single size, so stock is left to the product page.
            price_inr=float(price) if isinstance(price, int | float) else None,
            image_url=secure_image_url(product.get("searchImage")),
            sponsored=bool(product.get("isPLA")),
        )
    except ValidationError:
        return None  # a malformed tile is skipped rather than failing the whole search
