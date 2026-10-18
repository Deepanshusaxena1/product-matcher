"""Flipkart product pages: stock, price and the full spec table of one listing.

Read from `multiWidgetState`: the stock flag Flipkart's own page uses (`pls.availabilityStatus`), the
schema.org block (`seoData.schema`) and the specification cells, which pair a `label_0` name with a
`label_1` list of values.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from app.domain.models import Availability
from app.normalize.facts import ListingFacts, fingerprint_from_facts, first_spec
from app.platforms.embedded_json import dig, embedded_json
from app.platforms.flipkart.common import STATE_MARKER, availability_from, category_from_labels

if TYPE_CHECKING:
    from collections.abc import Iterator

    from app.domain.models import Fingerprint

_SCHEMA_AVAILABILITY = {
    "https://schema.org/InStock": Availability.IN_STOCK,
    "https://schema.org/OutOfStock": Availability.OUT_OF_STOCK,
}


@dataclass(frozen=True, slots=True)
class FlipkartProductPage:
    listing_id: str
    title: str
    fingerprint: Fingerprint
    availability: Availability
    price_inr: float | None
    image_url: str | None


def parse_product_page(html: str) -> FlipkartProductPage | None:
    state = embedded_json(html, STATE_MARKER)
    page = dig(state, "multiWidgetState", "pageDataResponse")
    schema = next((item for item in dig(page, "seoData", "schema") or () if isinstance(item, dict)), {})
    listing_id = dig(page, "pageContext", "productId") or schema.get("sku")
    title = schema.get("name")
    if not (isinstance(listing_id, str) and isinstance(title, str) and title):
        return None

    specs = dict(_spec_cells(state))
    category = category_from_labels(schema.get("category"))
    fingerprint = fingerprint_from_facts(
        ListingFacts(
            category=category,
            title=title,
            brand=first_spec(specs, "Brand") or dig(schema, "brand", "name"),
            model_name=first_spec(specs, "Model Name"),
            model_number=first_spec(specs, "Model Number", "Style Code", "Article Number"),
            ram=first_spec(specs, "RAM"),
            storage=first_spec(specs, "Internal Storage"),
            screen=first_spec(specs, "Display Size"),
            colour=first_spec(specs, "Brand Color", "Color") or schema.get("color"),
            gender=first_spec(specs, "Ideal For"),
        )
    )
    price = dig(schema, "offers", "price")
    return FlipkartProductPage(
        listing_id=listing_id,
        title=title,
        fingerprint=fingerprint,
        availability=_availability(page, schema),
        price_inr=float(price) if isinstance(price, int | float) else None,
        image_url=next((url for url in schema.get("image") or () if isinstance(url, str)), None),
    )


def _availability(page: Any, schema: dict[str, Any]) -> Availability:
    status = dig(page, "pageContext", "fdpEventTracking", "events", "psi", "pls", "availabilityStatus")
    availability = availability_from(status)
    if availability is Availability.UNKNOWN:
        availability = _SCHEMA_AVAILABILITY.get(dig(schema, "offers", "availability"), Availability.UNKNOWN)
    return availability


def _spec_cells(node: Any) -> Iterator[tuple[str, str]]:
    """Specification cells, wherever they sit in the widget tree; the first cell with a label wins."""
    seen: set[str] = set()
    stack = [node]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            label, values = dig(current, "label_0", "value", "text"), dig(current, "label_1", "value", "text")
            # Only real spec rows carry a list of values; other label pairs are page furniture ("₹0 off").
            if isinstance(label, str) and isinstance(values, list) and label.strip().casefold() not in seen:
                seen.add(label.strip().casefold())
                yield label.strip(), ", ".join(str(value) for value in values)
            stack.extend(reversed(list(current.values())))
        elif isinstance(current, list):
            stack.extend(reversed(current))
