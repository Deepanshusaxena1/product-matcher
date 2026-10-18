"""Colours: shops' marketing names ("Phantom Black", "Midnight Navy") reduced to base colour families."""

from __future__ import annotations

import re
from types import MappingProxyType
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

_FAMILY_WORDS: Mapping[str, frozenset[str]] = MappingProxyType(
    {
        "black": frozenset({"black", "onyx", "jet", "ebony", "midnight", "obsidian", "noir"}),
        "white": frozenset({"white", "ivory", "pearl", "snow", "chalk", "sail"}),
        "grey": frozenset({"grey", "gray", "graphite", "charcoal", "slate", "ash", "titanium", "smoke"}),
        "silver": frozenset({"silver", "platinum", "chrome"}),
        "blue": frozenset(
            {"blue", "navy", "indigo", "cobalt", "teal", "aqua", "turquoise", "denim", "azure"}
        ),
        "green": frozenset({"green", "mint", "olive", "lime", "sage", "emerald", "forest", "jade"}),
        "red": frozenset({"red", "maroon", "burgundy", "crimson", "wine", "scarlet", "cherry"}),
        "pink": frozenset({"pink", "rose", "magenta", "fuchsia", "blush"}),
        "purple": frozenset({"purple", "violet", "lavender", "lilac", "plum", "mauve"}),
        "yellow": frozenset({"yellow", "mustard", "lemon"}),
        "orange": frozenset({"orange", "coral", "rust", "peach", "tangerine"}),
        "brown": frozenset({"brown", "tan", "chocolate", "coffee", "camel", "mocha"}),
        "beige": frozenset({"beige", "khaki", "cream", "sand", "nude", "taupe"}),
        "gold": frozenset({"gold", "golden", "champagne"}),
    }
)
# Plain colour words, which name a colour and nothing else ("Phantom" or "Jade" may also name a model).
BASIC_COLOUR_WORDS = frozenset(_FAMILY_WORDS) | {"navy", "multi", "multicolour", "multicolor"}

_FAMILY_OF_WORD: Mapping[str, str] = MappingProxyType(
    {word: family for family, words in _FAMILY_WORDS.items() for word in words}
)

# Phrases whose meaning is not their last word, rewritten before the name is split into parts.
_PHRASES: Mapping[str, str] = MappingProxyType(
    {"rose gold": "pink", "off white": "white", "off-white": "white"}
)

# "White/Black", "White & Red", "Black, Gold", "White-White": each part is one colour of a multi-colour item.
_PART_SEPARATORS = re.compile(r"\s*(?:/|-|&|,|\+|\band\b)\s*", re.IGNORECASE)


def colour_families(name: str) -> tuple[str, ...]:
    """The base colours a colour name is made of, sorted and without repeats.

    Order is ignored ("White/Black" equals "Black/White"). If any part is unrecognised the result is
    empty: an unknown colour is safer than a half-known one when colour decides a match.
    """
    text = name.lower()
    for phrase, replacement in _PHRASES.items():
        text = text.replace(phrase, replacement)

    families: set[str] = set()
    for part in filter(None, _PART_SEPARATORS.split(text.strip())):
        family = _family_of_part(part)
        if family is None:
            return ()
        families.add(family)
    return tuple(sorted(families))


def _family_of_part(part: str) -> str | None:
    # The head noun comes last ("Midnight Navy" is navy), so the last recognised word wins.
    for word in reversed(re.findall(r"[a-z]+", part)):
        if word in _FAMILY_OF_WORD:
            return _FAMILY_OF_WORD[word]
    return None
