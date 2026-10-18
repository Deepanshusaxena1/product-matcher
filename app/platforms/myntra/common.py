"""Vocabulary shared by Myntra's search results and product pages."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.normalize.category import category_from_type_name
from app.platforms.embedded_json import dig

if TYPE_CHECKING:
    from app.domain.models import Category

BASE_URL = "https://www.myntra.com"
STATE_MARKER = "window.__myx"
# Product images are templates: "https://assets.myntassets.com/h_($height),q_($qualityPercentage),w_($width)/v1/...".
_IMAGE_SIZE = {"($height)": "720", "($width)": "540", "($qualityPercentage)": "90"}


def category_from_article_type(*names: Any) -> Category | None:
    """Myntra's article types read like product-type names: "Casual Shoes", "Sports Shoes", "Tshirts"."""
    for name in names:
        text = dig(name, "typeName") if isinstance(name, dict) else name
        if isinstance(text, str) and text:
            return category_from_type_name(text)
    return None


def secure_image_url(template: Any) -> str | None:
    if not isinstance(template, str) or not template:
        return None
    url: str = template
    for placeholder, value in _IMAGE_SIZE.items():
        url = url.replace(placeholder, value)
    return "https://" + url.removeprefix("http://").removeprefix("https://")
