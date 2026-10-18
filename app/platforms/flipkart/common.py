"""Vocabulary shared by Flipkart's search results and product pages."""

from __future__ import annotations

import re
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

from app.domain.models import Availability, Category

if TYPE_CHECKING:
    from collections.abc import Mapping

BASE_URL = "https://www.flipkart.com"
STATE_MARKER = "window.__INITIAL_STATE__"

# Flipkart's own product-type labels ("vertical", analytics categories, the schema's "category").
_CATEGORY_LABELS: tuple[tuple[Category, re.Pattern[str]], ...] = (
    (Category.SMARTPHONE, re.compile(r"^(?:handset|mobile)$", re.IGNORECASE)),
    (Category.TELEVISION, re.compile(r"^television$", re.IGNORECASE)),
    (Category.TSHIRT, re.compile(r"t_?shirt|polo|jersey", re.IGNORECASE)),
    (Category.SNEAKER, re.compile(r"shoe|sneaker|footwear", re.IGNORECASE)),
)
_FORMAL = re.compile(r"formal", re.IGNORECASE)

_AVAILABILITY: Mapping[str, Availability] = MappingProxyType(
    {
        "IN_STOCK": Availability.IN_STOCK,
        "OUT_OF_STOCK": Availability.OUT_OF_STOCK,
        "SOLD_OUT": Availability.OUT_OF_STOCK,
        "COMING_SOON": Availability.OUT_OF_STOCK,
        "TEMPORARILY_UNAVAILABLE": Availability.OUT_OF_STOCK,
        "PERMANENTLY_DISCONTINUED": Availability.OUT_OF_STOCK,
    }
)
_IMAGE_SIZE = "416"
_IMAGE_QUALITY = "70"


def category_from_labels(*labels: Any) -> Category | None:
    texts = [label for label in labels if isinstance(label, str) and label]
    if any(_FORMAL.search(text) for text in texts):
        return None  # formal shoes and shirts are outside the four categories
    for category, pattern in _CATEGORY_LABELS:
        if any(pattern.search(text) for text in texts):
            return category
    return None


def availability_from(status: Any) -> Availability:
    return (
        _AVAILABILITY.get(status, Availability.UNKNOWN) if isinstance(status, str) else Availability.UNKNOWN
    )


def image_url_from(template: Any) -> str | None:
    """Flipkart image URLs are templates: "http://rukmini1.flixcart.com/image/{@width}/{@height}/...?q={@quality}"."""
    if not isinstance(template, str) or not template:
        return None
    url = template.replace("{@width}", _IMAGE_SIZE).replace("{@height}", _IMAGE_SIZE)
    url = url.replace("{@quality}", _IMAGE_QUALITY)
    return "https://" + url.removeprefix("http://").removeprefix("https://")
