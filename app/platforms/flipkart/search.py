"""Flipkart search results: `pageDataV4.page.data[*][*].widget` slots of type PRODUCT_SUMMARY."""

from __future__ import annotations

import re
from typing import Any

from pydantic import ValidationError

from app.domain.models import Category, Listing, Platform
from app.normalize.facts import ListingFacts, fingerprint_from_facts
from app.platforms.embedded_json import dig, embedded_json
from app.platforms.flipkart.common import (
    BASE_URL,
    STATE_MARKER,
    availability_from,
    category_from_labels,
    image_url_from,
)

# The colour leads the variant in phone titles: "Samsung Galaxy S24 FE 5G (Blue, 128 GB)".
_PHONE_COLOUR = re.compile(r"\(([^,()]+),\s*\d+\s*(?:GB|TB)\b", re.IGNORECASE)
_COLOUR_SPEC = re.compile(r"^colou?r\s*:\s*(.+)$", re.IGNORECASE)


def parse_search_results(html: str) -> list[Listing] | None:
    """Every product tile on the page, in page order; None when the page holds no search results."""
    slots_by_row = dig(embedded_json(html, STATE_MARKER), "pageDataV4", "page", "data")
    if not isinstance(slots_by_row, dict):
        return None

    listings: list[Listing] = []
    for slots in slots_by_row.values():
        for slot in slots if isinstance(slots, list) else ():
            if dig(slot, "widget", "type") != "PRODUCT_SUMMARY":
                continue
            for product in dig(slot, "widget", "data", "products") or ():
                listing = _listing(product)
                if listing is not None:
                    listings.append(listing)
    return listings


def _listing(product: Any) -> Listing | None:
    info = dig(product, "productInfo", "value")
    titles = dig(info, "titles") or {}
    title = titles.get("title") or titles.get("newTitle")
    if not (dig(info, "id") and dig(info, "baseUrl") and title):
        return None

    analytics = dig(info, "analyticsData") or {}
    category = category_from_labels(
        info.get("vertical"),
        analytics.get("vertical"),
        analytics.get("subCategory"),
        analytics.get("category"),
    )
    key_specs = [spec for spec in info.get("keySpecs") or () if isinstance(spec, str)]
    subtitle = titles.get("subtitle") if isinstance(titles.get("subtitle"), str) else None

    try:
        return Listing(
            platform=Platform.FLIPKART,
            listing_id=info["id"],
            url=BASE_URL + info["baseUrl"],
            title=title,
            fingerprint=fingerprint_from_facts(
                ListingFacts(
                    category=category,
                    title=title,
                    brand=titles.get("superTitle"),
                    # TV tiles show the model number as the subtitle ("43NU870BPLA").
                    model_number=subtitle if category is Category.TELEVISION else None,
                    variant=" ".join([*key_specs[:1], subtitle or ""]) or None,
                    colour=_colour(category, title, key_specs, subtitle),
                )
            ),
            availability=availability_from(dig(info, "availability", "displayState")),
            price_inr=_selling_price(dig(info, "pricing", "prices")),
            image_url=image_url_from(dig(info, "media", "images", 0, "url")),
            sponsored=bool(dig(product, "adInfo")),
        )
    except ValidationError:
        return None  # a malformed tile is skipped rather than failing the whole search


def _colour(category: Category | None, title: str, key_specs: list[str], subtitle: str | None) -> str | None:
    if category is Category.SMARTPHONE:
        match = _PHONE_COLOUR.search(title)
        return match.group(1).strip() if match else None
    for spec in key_specs:  # fashion tiles: "Colour: White"
        match = _COLOUR_SPEC.match(spec)
        if match:
            return match.group(1).strip()
    if subtitle and " , " in subtitle:  # fashion tiles: "White , 11" (colour, then size)
        return subtitle.split(" , ", 1)[0].strip()
    return None


def _selling_price(prices: Any) -> float | None:
    selling = [
        price["value"]
        for price in prices or ()
        if isinstance(price, dict)
        and not price.get("strikeOff")
        and isinstance(price.get("value"), int | float)
    ]
    return float(selling[-1]) if selling else None
