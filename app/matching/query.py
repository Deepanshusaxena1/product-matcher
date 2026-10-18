"""What to type into a shop's search box to find the Amazon product."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.domain.models import Category

if TYPE_CHECKING:
    from app.domain.models import Fingerprint

# Codes that pin down one product (a TV's model number, a shoe's style code) are searched first: when the
# shop indexes them, the first query finds the exact listing.
_SEARCH_BY_CODE = frozenset({Category.TELEVISION, Category.SNEAKER, Category.TSHIRT})
_FASHION_NOUN = {Category.SNEAKER: "sneakers", Category.TSHIRT: "t-shirt"}


def search_queries(fingerprint: Fingerprint, *, by_code: bool = True) -> list[str]:
    """Queries from most to least specific, without repeats or empty parts.

    `by_code=False` is for shops whose search doesn't know model numbers or style codes.
    """
    brand, model = fingerprint.brand, fingerprint.model
    queries: list[str | None] = []
    if by_code and fingerprint.category in _SEARCH_BY_CODE and fingerprint.model_number:
        queries.append(_join(brand, fingerprint.model_number))

    match fingerprint.category:
        case Category.SMARTPHONE:
            queries.append(_join(brand, model))
        case Category.TELEVISION:
            size = f"{fingerprint.screen_in:g} inch" if fingerprint.screen_in else None
            queries.append(_join(brand, model, size))
        case Category.SNEAKER | Category.TSHIRT:
            colour = fingerprint.colour.lower() if fingerprint.colour else None
            gender = fingerprint.gender.value if fingerprint.gender else None
            noun = _FASHION_NOUN[fingerprint.category]
            queries.append(_join(brand, model, colour, gender, noun))
            queries.append(_join(brand, model, noun))  # shops' searches can trip over colour names

    return list(dict.fromkeys(query for query in queries if query))


def _join(*parts: str | None) -> str | None:
    text = " ".join(part for part in parts if part)
    return text or None
