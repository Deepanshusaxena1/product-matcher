"""Model names ("galaxy s24 fe") and model numbers ("SM-S721B", "43NU870BPLA", "DH2987-100")."""

from __future__ import annotations

import re
from types import MappingProxyType
from typing import TYPE_CHECKING

from app.normalize.brand import brand_words

if TYPE_CHECKING:
    from collections.abc import Mapping

_PARENTHESISED = re.compile(r"\([^)]*\)|\[[^\]]*\]")
# Everything after these is variant or marketing text: "iPhone 15 - Black", "Sneakers For Men", "X | Y".
_TAIL = re.compile(r"\s[-–|]\s|[,|]|\sfor\s|\swith\s", re.IGNORECASE)
_NOISE_PHRASES = re.compile(r"t-?\s?shirts?|ultra\s+hd|full\s+hd|next\s+gen", re.IGNORECASE)
# Sizes are attributes of their own (screen, RAM, storage), not part of the model's name.
_SIZES = re.compile(r"\b\d+(?:\.\d+)?\s*(?:cms?|inch(?:es)?|gb|tb)\b", re.IGNORECASE)
_WORD = re.compile(r"[a-z0-9]+(?:\.\d+)?")  # "2.0" stays one version number
_PLUS_SUFFIX = re.compile(r"(?<=[a-z0-9])\+(?![a-z0-9])")

# Variant words glued to a number by some shops: "S24FE" is "S24 FE".
_VARIANT_WORDS = frozenset(
    {
        "pro",
        "max",
        "plus",
        "ultra",
        "lite",
        "fe",
        "neo",
        "mini",
        "prime",
        "edge",
        "fold",
        "flip",
        "note",
        "se",
    }
)
_GLUED_VARIANT = re.compile(rf"^([a-z]*\d+)({'|'.join(sorted(_VARIANT_WORDS, key=len, reverse=True))})$")

# Abbreviations brands use in some listings but not others.
_ABBREVIATIONS: Mapping[str, tuple[str, ...]] = MappingProxyType(
    {"lo": ("low",), "hi": ("high",), "nn": ("next", "nature")}
)

# Words that describe the kind of product or its marketing, never which model it is.
_NOISE_WORDS = frozenset(
    {
        # connectivity and marketing
        "5g", "4g", "lte", "ai", "new", "latest", "dual", "sim", "the", "and", "series", "edition",
        # product kinds
        "smartphone", "smartphones", "mobile", "phone", "tv", "television", "smart", "led", "4k", "uhd",
        "hd", "fhd", "webos", "android", "google",
        "sneakers", "sneaker", "shoes", "shoe", "running", "casual", "sports", "sport", "trainers",
        "polo", "polos", "tee", "tees", "jersey", "tshirt", "tshirts",
        # how a shoe or shirt looks or is worn, never which model it is
        "solid", "colourblocked", "colorblocked", "tennis", "sportswear", "lifestyle", "round", "toe", "lace",
        "ups",
        # who it is for
        "men", "mens", "women", "womens", "boys", "girls", "kids", "unisex", "adult",
    }
)  # fmt: skip

_SHORTEST_TRUSTED_PREFIX = 6  # "SMS721B" may extend to "SMS721BZKBINS"; "A15" must not extend to "A155"


def normalize_model(title: str, brand: str | None = None) -> str:
    """The model family a title names: "Samsung Galaxy S24 FE 5G AI Smartphone (...)" -> "galaxy s24 fe".

    The name is the first part of the title (before " - ", "|", ", " or "for") that says more than the brand:
    in "Puma | Smashic Comfort Casual Sneakers" the model follows the bar.
    """
    skip = _NOISE_WORDS | (brand_words(brand) if brand else frozenset())
    for part in _TAIL.split(_PARENTHESISED.sub(" ", title)):
        text = _NOISE_PHRASES.sub(" ", part.replace("'", "").replace("’", ""))
        model = " ".join(token for token in _tokens(_SIZES.sub(" ", text)) if token not in skip)
        if model:
            return model
    return ""


def same_model(a: str, b: str, *, allow_missing_words: bool = True) -> bool:
    """Whether two model names name the same model.

    Every distinguishing token (numbers, and variant words such as "plus" or "fe") must agree, so
    "iphone 15" is not "iphone 15 plus". Other words may be missing on one side ("s24 fe" is
    "galaxy s24 fe") but may not conflict; with `allow_missing_words=False` every word must agree.
    """
    tokens_a, tokens_b = set(_tokens(a)), set(_tokens(b))
    if not tokens_a or not tokens_b:
        return False
    if _distinguishing(tokens_a) != _distinguishing(tokens_b):
        return False
    if not allow_missing_words:
        return tokens_a == tokens_b
    return tokens_a <= tokens_b or tokens_b <= tokens_a


def normalize_model_number(raw: str) -> str:
    """Upper-case letters and digits only, without a regional suffix: "SM-S721B/DS" -> "SMS721B"."""
    return re.sub(r"[^A-Z0-9]", "", raw.split("/", 1)[0].upper())


def model_numbers_match(a: str, b: str) -> bool:
    """Equal, or one extends the other by a regional or colour suffix ("687093" -> "68709301")."""
    na, nb = normalize_model_number(a), normalize_model_number(b)
    if not na or not nb:
        return False
    shorter, longer = sorted((na, nb), key=len)
    return shorter == longer or (len(shorter) >= _SHORTEST_TRUSTED_PREFIX and longer.startswith(shorter))


def _tokens(text: str) -> list[str]:
    tokens: list[str] = []
    # "S24+" is the S24 Plus; "8GB+128GB" (a plus between numbers) is not.
    for word in _WORD.findall(_PLUS_SUFFIX.sub(" plus ", text.lower())):
        glued = _GLUED_VARIANT.match(word)
        if glued:
            tokens.extend(glued.groups())
        else:
            tokens.extend(_ABBREVIATIONS.get(word, (word,)))
    return tokens


def _distinguishing(tokens: set[str]) -> set[str]:
    return {token for token in tokens if token in _VARIANT_WORDS or any(char.isdigit() for char in token)}
