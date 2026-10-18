"""Find the Amazon product on one shop and say whether it can be bought there.

For each search query, from most to least specific:
1. search the shop and drop sponsored tiles;
2. check every tile against the hard rules, using what the tile shows;
3. open the product pages of the few best survivors and check them again with the full details;
4. stop at the first query that confirms a match.

What the shop can show (`ShopProfile`) adjusts this: a shop that never shows style codes is not searched
by code, and its results are judged by name from the start rather than waiting for a code that won't come.

A shop that cannot be read raises (the caller reports "couldn't check"); "not listed" is only ever the
outcome of a search that worked.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.domain.models import Availability, Category, MatchStatus, PlatformResult
from app.matching.query import search_queries
from app.matching.rules import CATEGORY_NOUN, Assessment, assess, similarity
from app.normalize.facts import FASHION

if TYPE_CHECKING:
    from collections.abc import Sequence

    from app.domain.models import Fingerprint, Listing
    from app.domain.ports import PlatformAdapter, ShopProfile

_SPELLINGS = {"iphone": "iPhone", "ipad": "iPad", "oneplus": "OnePlus"}
_CONFIDENCE = {"model number": 0.95, "model name": 0.85}
_STATUS = {Availability.IN_STOCK: MatchStatus.IN_STOCK, Availability.OUT_OF_STOCK: MatchStatus.OUT_OF_STOCK}


@dataclass(frozen=True, slots=True)
class _Candidate:
    listing: Listing
    assessment: Assessment
    score: float


class Matcher:
    def __init__(self, *, pages_per_batch: int = 4, max_pages_per_query: int = 12) -> None:
        # Product pages are opened best-looking first, a batch at a time, until one confirms the match.
        # Several batches matter for fashion: dozens of tiles read "PUMA Solid Men Polo Neck Black
        # T-Shirt", and only their product pages show the style code that tells them apart.
        self._pages_per_batch = pages_per_batch
        self._max_pages_per_query = max_pages_per_query

    async def find(self, source: Listing, adapter: PlatformAdapter) -> PlatformResult:
        fingerprint = source.fingerprint
        if fingerprint.category is None:
            raise ValueError("the source product must have a category")
        profile = adapter.profile
        # When the shop never shows codes, the results page is as final as the product page for identity.
        tiles_are_final = not profile.shows_model_numbers

        seen: set[str] = set()
        rejected: list[_Candidate] = []
        unsettled: list[_Candidate] = []
        for query in search_queries(fingerprint, by_code=profile.shows_model_numbers):
            tiles = [
                tile
                for tile in await adapter.search(query, fingerprint.category)
                if not tile.sponsored and tile.listing_id not in seen
            ]
            seen.update(tile.listing_id for tile in tiles)

            shortlist: list[_Candidate] = []
            for tile in tiles:
                assessment = assess(fingerprint, tile, final=tiles_are_final)
                candidate = _Candidate(tile, assessment, similarity(source, tile))
                (shortlist if candidate.assessment.passed else rejected).append(candidate)
            shortlist.sort(key=lambda candidate: candidate.score, reverse=True)
            shortlist = shortlist[: self._max_pages_per_query]

            confirmed: list[_Candidate] = []
            for start in range(0, len(shortlist), self._pages_per_batch):
                batch = [c.listing for c in shortlist[start : start + self._pages_per_batch]]
                for listing in await _details(adapter, batch):
                    candidate = _Candidate(
                        listing, assess(fingerprint, listing, final=True), similarity(source, listing)
                    )
                    if candidate.assessment.confirmed:
                        confirmed.append(candidate)
                    else:
                        (unsettled if candidate.assessment.passed else rejected).append(candidate)
                if confirmed:
                    break

            if confirmed:
                # The closest listing wins; of equally close duplicates, the one that is in stock.
                best = max(
                    confirmed,
                    key=lambda c: (c.score, c.listing.availability is Availability.IN_STOCK),
                )
                return _matched(adapter, fingerprint, best)

        return _not_listed(adapter, fingerprint, unsettled, rejected)


async def _details(adapter: PlatformAdapter, tiles: Sequence[Listing]) -> list[Listing]:
    """Product pages for `tiles`; individual failures are skipped unless every page failed."""
    if not tiles:
        return []
    outcomes = await asyncio.gather(*(adapter.fetch_details(tile) for tile in tiles), return_exceptions=True)
    pages = [outcome for outcome in outcomes if not isinstance(outcome, BaseException)]
    if not pages:
        raise next(outcome for outcome in outcomes if isinstance(outcome, BaseException))
    return pages


def _matched(adapter: PlatformAdapter, source: Fingerprint, best: _Candidate) -> PlatformResult:
    platform = adapter.platform
    listing, identity = best.listing, best.assessment.identity or "model name"
    theirs = listing.fingerprint
    status = _STATUS.get(listing.availability)
    reason = f"{_identity_phrase(identity, theirs, source)}, {_attributes_phrase(source)}."
    if status is None:
        return PlatformResult(
            platform=platform,
            status=MatchStatus.ERROR,
            reason=f"{reason[:-1]}, but {platform.label} didn't say whether it's in stock.",
            listing=listing,
            confidence=_CONFIDENCE[identity],
        )

    return PlatformResult(
        platform=platform,
        status=status,
        reason=reason,
        listing=listing,
        confidence=_CONFIDENCE[identity],
        notes=_notes(adapter.profile, source, theirs, identity),
    )


def _notes(profile: ShopProfile, source: Fingerprint, theirs: Fingerprint, identity: str) -> tuple[str, ...]:
    notes: list[str] = []
    if source.category in FASHION:
        if source.model_number and identity == "model name":
            notes.append("Matched by name: the listing doesn't show a style code.")
    elif source.colour and theirs.colour and source.colour.casefold() != theirs.colour.casefold():
        notes.append(f"Listed in {theirs.colour}; the Amazon product is {source.colour}.")
    if profile.stock_note:
        notes.append(profile.stock_note)
    return tuple(notes)


def _not_listed(
    adapter: PlatformAdapter, source: Fingerprint, unsettled: list[_Candidate], rejected: list[_Candidate]
) -> PlatformResult:
    platform = adapter.platform
    # A listing with no model name at all ("Nike Men Sneakers") says nothing useful as the closest one.
    named = [candidate for candidate in unsettled if candidate.listing.fingerprint.model]
    unsettled = named or ([] if rejected else unsettled)
    if unsettled:
        closest = max(unsettled, key=lambda c: c.score)
        facts = " or ".join(closest.assessment.unconfirmed)
        reason = f"Found “{closest.listing.title}”, but couldn't confirm its {facts}."
    elif rejected:
        # Prefer a near miss of the right kind and brand ("the S24 FE, but 256 GB") over a stray accessory.
        closest = max(
            rejected,
            key=lambda c: (
                c.listing.fingerprint.category is source.category,
                c.listing.fingerprint.brand == source.brand,
                c.score,
            ),
        )
        mismatch = closest.assessment.mismatches[0]
        reason = f"The closest {platform.label} listing, “{closest.listing.title}”, {mismatch}."
    else:
        reason = f"Nothing in {platform.label}'s search results looks like the {product_name(source)}."
    return PlatformResult(platform=platform, status=MatchStatus.NOT_LISTED, reason=reason)


def _identity_phrase(identity: str, theirs: Fingerprint, source: Fingerprint) -> str:
    if identity == "model number":
        code = "style code" if source.category in FASHION else "model number"
        return f"Same {code} ({theirs.model_number})"
    return f"Same model ({product_name(source)})"


def _attributes_phrase(source: Fingerprint) -> str:
    match source.category:
        case Category.SMARTPHONE:
            sizes = [f"{source.ram_gb} GB RAM" if source.ram_gb else None]
            sizes.append(f"{source.storage_gb} GB storage" if source.storage_gb else None)
            return " and ".join(filter(None, sizes)) or "same variant"
        case Category.TELEVISION:
            return f"{source.screen_in:g}-inch screen"
        case _:
            who = f", {source.gender.value}'s" if source.gender and source.gender.value != "unisex" else ""
            return f"{source.colour or 'same colour'}{who}"


def product_name(fingerprint: Fingerprint) -> str:
    """A readable name from a fingerprint: "Samsung Galaxy S24 FE", "LG NU87 Nano 2026"."""
    words = " ".join(filter(None, (fingerprint.brand, fingerprint.model))).split()
    name = " ".join(_display_word(word) for word in words)
    noun = CATEGORY_NOUN.get(fingerprint.category) if fingerprint.category else None
    return name or (noun or "product")


def _display_word(word: str) -> str:
    """ "s24" -> "S24", "fe" -> "FE", "fold7" -> "Fold7", "iphone" -> "iPhone"."""
    if word in _SPELLINGS:
        return _SPELLINGS[word]
    letters = len(word) - len(word.lstrip("abcdefghijklmnopqrstuvwxyz"))
    # Short words and codes that start with a letter or two are written in capitals; longer words with a
    # number at the end ("Fold7") are names.
    if len(word) <= 2 or (letters <= 2 and any(char.isdigit() for char in word)):
        return word.upper()
    return word[0].upper() + word[1:]
