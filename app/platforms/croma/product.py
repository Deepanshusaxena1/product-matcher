"""Croma product pages: `pdpData` inside `window.__INITIAL_DATA__`, whose `classifications` hold the specs.

`window.__INITIAL_DATA__` is JavaScript rather than JSON (it contains `undefined`), so only the `pdpData`
object inside it is decoded. The page says nothing reliable about stock; that comes from the delivery
check in `app.platforms.croma.inventory`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from app.normalize.facts import ListingFacts, fingerprint_from_facts, first_spec
from app.platforms.croma.common import category_from_name
from app.platforms.embedded_json import dig, embedded_json

if TYPE_CHECKING:
    from collections.abc import Iterator

    from app.domain.models import Fingerprint

_PRODUCT_MARKER = '"pdpData":'
_BARE_NUMBER = re.compile(r"^\d+(?:\.\d+)?$")


@dataclass(frozen=True, slots=True)
class CromaProductPage:
    listing_id: str
    title: str
    fingerprint: Fingerprint
    image_url: str | None


def parse_product_page(html: str) -> CromaProductPage | None:
    product = embedded_json(html, _PRODUCT_MARKER)
    listing_id, title = dig(product, "code"), dig(product, "name")
    if not (isinstance(listing_id, str) and isinstance(title, str) and title):
        return None

    specs = dict(_specs(product))
    screen = first_spec(specs, "Screen Size in Inches")
    fingerprint = fingerprint_from_facts(
        ListingFacts(
            category=category_from_name(_leaf_category(product)),
            title=title,
            brand=first_spec(specs, "Brand") or product.get("manufacturer"),
            # "Model Series" is deliberately not used: it can be coarser than the title ("Galaxy S").
            model_number=first_spec(specs, "Model Number"),
            ram=first_spec(specs, "RAM"),
            storage=first_spec(specs, "Internal Storage"),
            screen=f"{screen} inch" if screen and _BARE_NUMBER.match(screen) else screen,
            colour=first_spec(specs, "Brand Color", "Color"),
        )
    )
    image = dig(product, "imageInfo", 0, "url")
    return CromaProductPage(
        listing_id=listing_id,
        title=title,
        fingerprint=fingerprint,
        image_url=image if isinstance(image, str) and image.startswith("https://") else None,
    )


def _leaf_category(product: dict[str, Any]) -> str | None:
    """The deepest category breadcrumb (the last crumb, the product itself, has no category code)."""
    crumbs = [crumb for crumb in dig(product, "pdpBreadcrumbs") or () if dig(crumb, "categoryCode")]
    name = dig(crumbs, -1, "name")
    return name if isinstance(name, str) else None


def _specs(product: dict[str, Any]) -> Iterator[tuple[str, str]]:
    for group in dig(product, "classifications") or ():
        for feature in dig(group, "features") or ():
            name = dig(feature, "name")
            values = [dig(entry, "value") for entry in dig(feature, "featureValues") or ()]
            texts = [value for value in values if isinstance(value, str) and value]
            if isinstance(name, str) and texts:
                yield name, ", ".join(dict.fromkeys(texts))  # Croma sometimes repeats a value ("LG, LG")
