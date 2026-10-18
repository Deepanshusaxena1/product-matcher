"""Brand names: one canonical lowercase spelling per maker."""

from __future__ import annotations

import re
from types import MappingProxyType
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

_STORE_BYLINE = re.compile(r"^\s*visit the\s+(.*?)\s+store\s*$", re.IGNORECASE)
_BRAND_LABEL = re.compile(r"^\s*brand\s*:\s*", re.IGNORECASE)
_NOT_ALPHANUMERIC = re.compile(r"[^a-z0-9]+")

_PLACEHOLDERS = frozenset({"generic", "unbranded", "no brand", "unknown", "others"})

# Alternative spellings (after lowercasing and dropping punctuation) -> canonical brand.
_ALIASES: Mapping[str, str] = MappingProxyType(
    {
        "one plus": "oneplus",
        "lg electronics": "lg",
        "samsung electronics": "samsung",
        "mi": "xiaomi",
        "redmi": "xiaomi",
        "poco": "xiaomi",
        "u s polo assn": "us polo assn",
        "u s polo": "us polo assn",
        "us polo": "us polo assn",
        "uspa": "us polo assn",
    }
)

# Product lines sold under their own name. They identify the maker but also tell products apart
# ("Redmi Note 13" is not "Poco Note 13"), so model names keep them.
_SUB_BRANDS = frozenset({"redmi", "poco"})


def normalize_brand(raw: str) -> str | None:
    """ "Visit the PUMA Store" -> "puma"; "U.S. POLO ASSN." -> "us polo assn"; placeholders -> None."""
    text = _BRAND_LABEL.sub("", raw)
    byline = _STORE_BYLINE.match(text)
    if byline:
        text = byline.group(1)
    spelling = _NOT_ALPHANUMERIC.sub(" ", text.lower()).strip()
    if not spelling or spelling in _PLACEHOLDERS or "visit the" in spelling:
        return None
    return _ALIASES.get(spelling, spelling)


def brand_words(brand: str) -> frozenset[str]:
    """Words that only name the maker, so a model name can drop them ("lg electronics nu87" -> "nu87")."""
    spellings = [brand, *(alias for alias, canonical in _ALIASES.items() if canonical == brand)]
    return frozenset(word for spelling in spellings for word in spelling.split()) - _SUB_BRANDS
