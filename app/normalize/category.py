"""Which of the four supported categories a product is in, and who it is made for."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from app.domain.models import Category, Gender

if TYPE_CHECKING:
    from collections.abc import Sequence

# Checked against one specific name (the deepest breadcrumb, or a product-type name), never a parent
# crumb: "T-shirts, Polos & Shirts" also holds formal shirts.
_CATEGORY_NAMES: tuple[tuple[Category, re.Pattern[str]], ...] = (
    (Category.SMARTPHONE, re.compile(r"\b(?:smart|mobile|cell)\s?phones?\b|^iphones?$", re.IGNORECASE)),
    (Category.TELEVISION, re.compile(r"\btelevisions?\b|\btvs?$", re.IGNORECASE)),
    (
        Category.SNEAKER,
        re.compile(
            r"\bsneakers?\b|\b(?:sports|running|training|walking|casual|basketball|tennis|skate)\s+shoes?\b",
            re.IGNORECASE,
        ),
    ),
    (Category.TSHIRT, re.compile(r"\bt-?\s?shirts?\b|\btees?\b|\bpolos?\b|\bjerseys?\b", re.IGNORECASE)),
)

# Things made for a product, not the product: "Mobile Phone Case", "iPhone Screen Protector", "TV Remote".
_ACCESSORY = re.compile(
    r"\b(?:cases?|covers?|protectors?|guards?|chargers?|cables?|adapters?|holders?|stands?|mounts?|remotes?|skins?)\b",
    re.IGNORECASE,
)

_KIDS = re.compile(r"\b(?:kids?|boys?|girls?|infants?|baby|toddlers?)\b", re.IGNORECASE)
_UNISEX = re.compile(r"\bunisex\b", re.IGNORECASE)
_WOMEN = re.compile(r"\bwom[ae]n(?:'?s)?\b|\bladies\b", re.IGNORECASE)
_MEN = re.compile(r"\bm[ae]n(?:'?s)?\b|\bgents\b", re.IGNORECASE)


def category_from_breadcrumbs(crumbs: Sequence[str]) -> Category | None:
    """The category named by the deepest breadcrumb, if it is one of the four."""
    return category_from_type_name(crumbs[-1]) if crumbs else None


def category_from_type_name(name: str) -> Category | None:
    """The category named by a product-type label such as "Smartphones" or "NANO 4K UHD AI TV"."""
    text = name.strip()
    if _ACCESSORY.search(text):
        return None
    return next((category for category, pattern in _CATEGORY_NAMES if pattern.search(text)), None)


def gender_from(*texts: str) -> Gender | None:
    """The gender named by the first text that names one (pass the most specific text first)."""
    for raw in texts:
        text = raw.replace("’", "'")
        if _KIDS.search(text):
            return Gender.KIDS
        women, men = bool(_WOMEN.search(text)), bool(_MEN.search(text))
        if _UNISEX.search(text) or (women and men):
            return Gender.UNISEX
        if women:
            return Gender.WOMEN
        if men:
            return Gender.MEN
    return None
