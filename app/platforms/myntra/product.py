"""Myntra product pages: `window.__myx.pdpData` (name, brand, base colour, who it is for, sizes in stock)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from app.domain.models import Availability
from app.normalize.facts import ListingFacts, fingerprint_from_facts
from app.platforms.embedded_json import dig, embedded_json
from app.platforms.myntra.common import STATE_MARKER, category_from_article_type, secure_image_url

if TYPE_CHECKING:
    from app.domain.models import Fingerprint


@dataclass(frozen=True, slots=True)
class MyntraProductPage:
    listing_id: str
    title: str
    fingerprint: Fingerprint
    availability: Availability
    price_inr: float | None
    image_url: str | None


def parse_product_page(html: str) -> MyntraProductPage | None:
    product = dig(embedded_json(html, STATE_MARKER), "pdpData")
    listing_id, title = dig(product, "id"), dig(product, "name")
    if listing_id is None or not (isinstance(title, str) and title):
        return None

    analytics = dig(product, "analytics") or {}
    fingerprint = fingerprint_from_facts(
        ListingFacts(
            category=category_from_article_type(analytics.get("articleType")),
            title=title,
            brand=dig(product, "brand", "name") or analytics.get("brand"),
            colour=product.get("baseColour"),
            gender=analytics.get("gender"),
        )
    )
    price = dig(product, "price", "discounted")
    return MyntraProductPage(
        listing_id=str(listing_id),
        title=title,
        fingerprint=fingerprint,
        availability=_availability(product),
        price_inr=float(price) if isinstance(price, int | float) else None,
        image_url=secure_image_url(dig(product, "media", "albums", 0, "images", 0, "secureSrc")),
    )


def _availability(product: dict[str, Any]) -> Availability:
    """In stock when at least one size can be bought."""
    out_of_stock = dig(product, "flags", "outOfStock")
    if out_of_stock is True:
        return Availability.OUT_OF_STOCK
    sizes = [size for size in dig(product, "sizes") or () if isinstance(size, dict)]
    if sizes:
        any_size = any(size.get("available") is True for size in sizes)
        return Availability.IN_STOCK if any_size else Availability.OUT_OF_STOCK
    return Availability.IN_STOCK if out_of_stock is False else Availability.UNKNOWN
