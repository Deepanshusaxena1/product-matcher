"""The hard rules: what must agree for a shop listing to be the Amazon product.

A rule only rejects on a conflict it can see. A fact the listing doesn't show yet is *unconfirmed*, which
keeps the candidate alive until its product page is read, but never counts as a match.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING

from rapidfuzz import fuzz, utils

from app.domain.models import Category, Gender
from app.normalize.facts import FASHION
from app.normalize.model import model_numbers_match, normalize_model_number, same_model

if TYPE_CHECKING:
    from collections.abc import Mapping

    from app.domain.models import Fingerprint, Listing

CATEGORY_NOUN: Mapping[Category, str] = MappingProxyType(
    {
        Category.SMARTPHONE: "smartphone",
        Category.TELEVISION: "TV",
        Category.SNEAKER: "sneaker",
        Category.TSHIRT: "T-shirt",
    }
)

# Phone model numbers are written differently by each shop ("SM-S721B" vs "S721B-SM"), so for phones the
# model name decides. For TVs and fashion the model number or style code does.
_NUMBER_DECIDES = frozenset({Category.TELEVISION, Category.SNEAKER, Category.TSHIRT})
_SCREEN_TOLERANCE_IN = 0.5  # "108 cm" is 42.5", sold as 43"
_EXCLUDED = re.compile(
    r"\b(?:refurbished|renewed|pre-?owned|open[- ]box|unboxed|combo|(?:pack|set) of \d+)\b", re.IGNORECASE
)


@dataclass(frozen=True, slots=True)
class Assessment:
    mismatches: tuple[str, ...] = ()  # completes "The listing ...": "has 256 GB storage, not 128 GB"
    unconfirmed: tuple[str, ...] = ()  # must-match facts the listing hasn't shown, e.g. "storage"
    identity: str | None = None  # how the model was confirmed: "model number" or "model name"

    @property
    def passed(self) -> bool:
        return not self.mismatches

    @property
    def confirmed(self) -> bool:
        return self.passed and not self.unconfirmed and self.identity is not None


def assess(source: Fingerprint, candidate: Listing, *, final: bool) -> Assessment:
    """Check `candidate` against the Amazon product's fingerprint.

    `final` is False while judging a search tile: a fashion tile without a style code is then kept for its
    product page to settle. When True, the model name is the last resort.
    """
    theirs = candidate.fingerprint
    mismatches: list[str] = []
    unconfirmed: list[str] = []

    if _EXCLUDED.search(candidate.title):
        mismatches.append("is a refurbished or multi-pack listing")
    if source.category is not None and theirs.category is not source.category:
        mismatches.append(f"is not a {CATEGORY_NOUN[source.category]}")
    if source.brand:
        if theirs.brand is None:
            unconfirmed.append("brand")
        elif theirs.brand != source.brand:
            mismatches.append(f"is by {theirs.brand}, not {source.brand}")

    identity, conflict, unknown = _identity(source, theirs, final=final)
    mismatches.extend(filter(None, [conflict]))
    unconfirmed.extend(filter(None, [unknown]))

    match source.category:
        case Category.SMARTPHONE:
            _compare_gb(source.ram_gb, theirs.ram_gb, "RAM", mismatches, unconfirmed)
            _compare_gb(source.storage_gb, theirs.storage_gb, "storage", mismatches, unconfirmed)
        case Category.TELEVISION:
            _compare_screen(source, theirs, mismatches, unconfirmed)
        case Category.SNEAKER | Category.TSHIRT:
            if not _same_style_code(source, theirs):  # a full style code names the colourway itself
                _compare_colour(source, theirs, mismatches, unconfirmed)
            _compare_gender(source, theirs, mismatches)

    return Assessment(tuple(mismatches), tuple(unconfirmed), identity if not mismatches else None)


def similarity(source: Listing, candidate: Listing) -> float:
    """How alike two listings look, for ranking candidates that pass the rules (0 to 1)."""
    ours, theirs = source.fingerprint, candidate.fingerprint
    score = 0.0
    if (
        ours.model_number
        and theirs.model_number
        and model_numbers_match(ours.model_number, theirs.model_number)
    ):
        score += 0.5
    if ours.model and theirs.model and same_model(ours.model, theirs.model):
        score += 0.25
    score += 0.15 * fuzz.token_set_ratio(source.title, candidate.title, processor=utils.default_process) / 100
    if ours.colour and theirs.colour and ours.colour.casefold() == theirs.colour.casefold():
        score += 0.1
    elif ours.colour_families and ours.colour_families == theirs.colour_families:
        score += 0.05
    return round(score, 4)


def _identity(
    source: Fingerprint, theirs: Fingerprint, *, final: bool
) -> tuple[str | None, str | None, str | None]:
    """(how the model was confirmed, a conflict, a fact still unknown): at most one is set."""
    number_decides = source.category in _NUMBER_DECIDES
    if source.model_number and theirs.model_number:
        if model_numbers_match(source.model_number, theirs.model_number):
            return "model number", None, None
        if number_decides:
            if source.category in FASHION:
                return None, f"has style code {theirs.model_number}, not {source.model_number}", None
            return None, f"is model {theirs.model_number}, not {source.model_number}", None
    elif number_decides and source.model_number and not final:
        return None, None, "style code" if source.category in FASHION else "model number"

    if source.model and theirs.model:
        # Fashion lines come in editions that differ by one word ("Air Force 1" and "Air Force 1 Shadow"),
        # so without a style code a fashion name must match word for word.
        if same_model(source.model, theirs.model, allow_missing_words=source.category not in FASHION):
            if source.category is Category.TSHIRT:
                # "Cotton Slim Fit Polo" names a hundred shirts: only a style code tells them apart.
                return None, None, "style code"
            return "model name", None, None
        if same_model(source.model, theirs.model):
            return None, None, f"model (it's named “{theirs.model}”, not “{source.model}”)"
        return None, f"is the {theirs.model}, not the {source.model}", None
    return None, None, "model"


def _compare_gb(
    ours: int | None, theirs: int | None, label: str, mismatches: list[str], unconfirmed: list[str]
) -> None:
    if ours is None:
        return
    if theirs is None:
        unconfirmed.append(label)
    elif theirs != ours:
        mismatches.append(f"has {theirs} GB {label}, not {ours} GB")


def _compare_screen(
    source: Fingerprint, theirs: Fingerprint, mismatches: list[str], unconfirmed: list[str]
) -> None:
    if source.screen_in is None:
        return
    if theirs.screen_in is None:
        unconfirmed.append("screen size")
    elif abs(theirs.screen_in - source.screen_in) > _SCREEN_TOLERANCE_IN + 1e-9:
        mismatches.append(f"has a {theirs.screen_in:g}-inch screen, not {source.screen_in:g}-inch")


def _compare_colour(
    source: Fingerprint, theirs: Fingerprint, mismatches: list[str], unconfirmed: list[str]
) -> None:
    if not source.colour_families:
        return
    ours, other = set(source.colour_families), set(theirs.colour_families)
    if not other or (ours != other and (ours < other or other < ours)):
        # Unknown, or one shop names fewer of the colours ("White" for "White-Matte Silver").
        unconfirmed.append("colour")
    elif ours != other:
        mismatches.append(f"is {theirs.colour or '/'.join(theirs.colour_families)}, not {source.colour}")


def _same_style_code(source: Fingerprint, theirs: Fingerprint) -> bool:
    """Identical codes, not merely one extending the other (PUMA's "687093" leaves the colour open)."""
    return bool(
        source.model_number
        and theirs.model_number
        and normalize_model_number(source.model_number) == normalize_model_number(theirs.model_number)
    )


def _compare_gender(source: Fingerprint, theirs: Fingerprint, mismatches: list[str]) -> None:
    if source.gender is None or theirs.gender is None or Gender.UNISEX in (source.gender, theirs.gender):
        return
    if theirs.gender is not source.gender:
        mismatches.append(f"is for {theirs.gender.value}, not {source.gender.value}")
