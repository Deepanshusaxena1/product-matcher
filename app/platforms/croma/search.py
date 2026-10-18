"""Croma search results: the API's `products`, named by category through its `lower_categories` facet."""

from __future__ import annotations

import re
from typing import Any

from pydantic import ValidationError

from app.domain.models import Category, Listing, Platform
from app.normalize.facts import ListingFacts, fingerprint_from_facts
from app.platforms.croma.common import absolute_url, category_from_name
from app.platforms.embedded_json import dig

# Phone titles end with the variant, colour last: "SAMSUNG Galaxy S24 5G (8GB RAM, 256GB, Onyx Black)".
_TRAILING_VARIANT = re.compile(r"\(([^()]*)\)\s*$")
_SIZE = re.compile(r"\d\s*(?:GB|TB)\b", re.IGNORECASE)


def parse_search_results(data: Any) -> list[Listing] | None:
    """Every product in the response, in order; None when the response holds no search results."""
    products = dig(data, "products")
    if not isinstance(products, list):
        return None
    category_names = {
        value.get("code"): value.get("name")
        for facet in dig(data, "facets") or ()
        if dig(facet, "code") == "lower_categories"
        for value in dig(facet, "values") or ()
        if isinstance(value, dict)
    }
    listings = (_listing(product, category_names) for product in products if isinstance(product, dict))
    return [listing for listing in listings if listing is not None]


def _listing(product: dict[str, Any], category_names: dict[Any, Any]) -> Listing | None:
    title, url = product.get("name"), absolute_url(product.get("url"))
    if not (isinstance(title, str) and title and url and product.get("code")):
        return None
    category = category_from_name(category_names.get(product.get("categoryL2")))
    price = dig(product, "price", "value")
    try:
        return Listing(
            platform=Platform.CROMA,
            listing_id=str(product["code"]),
            url=url,
            title=title,
            fingerprint=fingerprint_from_facts(
                ListingFacts(
                    category=category,
                    title=title,
                    brand=product.get("manufacturer"),
                    colour=_phone_colour(title) if category is Category.SMARTPHONE else None,
                )
            ),
            price_inr=float(price) if isinstance(price, int | float) else None,
            image_url=product.get("plpImage") or None,
        )
    except ValidationError:
        return None  # a malformed product is skipped rather than failing the whole search


def _phone_colour(title: str) -> str | None:
    variant = _TRAILING_VARIANT.search(title)
    if not variant:
        return None
    colour = variant.group(1).split(",")[-1].strip()
    return colour if colour and not _SIZE.search(colour) else None
