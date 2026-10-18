"""The vocabulary every layer speaks.

A product offered by any shop is a `Listing`. What makes two listings "the same product" is captured by
their `Fingerprint` (brand, model and the category's must-match attributes). Looking for the Amazon
product on one platform yields a `PlatformResult`; the answer to a whole request is a
`ComparisonReport`. While a comparison runs it can be followed as `ComparisonEvent`s: the Amazon product
once read, then each platform's result as soon as it is known.

All models are immutable: they are passed between concurrently running platform searches.
"""

from __future__ import annotations

from datetime import datetime  # noqa: TC003 (pydantic needs it at runtime)
from enum import StrEnum
from types import MappingProxyType
from typing import TYPE_CHECKING, Annotated, Literal, Self
from urllib.parse import urlsplit

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

if TYPE_CHECKING:
    from collections.abc import Mapping


class Platform(StrEnum):
    AMAZON = "amazon"
    FLIPKART = "flipkart"
    CROMA = "croma"
    MYNTRA = "myntra"

    @property
    def label(self) -> str:
        """The shop's name as shoppers write it."""
        return self.value.capitalize()


class Category(StrEnum):
    SMARTPHONE = "smartphone"
    TELEVISION = "television"
    SNEAKER = "sneaker"
    TSHIRT = "tshirt"  # T-shirts, polos and jerseys

    @property
    def platforms(self) -> tuple[Platform, ...]:
        """The platforms this category is searched on (the assignment's "Search on" column)."""
        return _CATEGORY_PLATFORMS[self]


_CATEGORY_PLATFORMS: Mapping[Category, tuple[Platform, ...]] = MappingProxyType(
    {
        Category.SMARTPHONE: (Platform.FLIPKART, Platform.CROMA),
        Category.TELEVISION: (Platform.FLIPKART, Platform.CROMA),
        Category.SNEAKER: (Platform.FLIPKART, Platform.MYNTRA),
        Category.TSHIRT: (Platform.FLIPKART, Platform.MYNTRA),
    }
)


class Gender(StrEnum):
    MEN = "men"
    WOMEN = "women"
    UNISEX = "unisex"
    KIDS = "kids"


class Availability(StrEnum):
    """Whether a single listing can be bought right now."""

    IN_STOCK = "in_stock"
    OUT_OF_STOCK = "out_of_stock"
    UNKNOWN = "unknown"


class MatchStatus(StrEnum):
    """The answer for one platform. `ERROR` means "couldn't check" and is never shown as "not listed"."""

    IN_STOCK = "in_stock"
    OUT_OF_STOCK = "out_of_stock"
    NOT_LISTED = "not_listed"
    ERROR = "error"


_STATUSES_THAT_SHOW_A_LINK = frozenset({MatchStatus.IN_STOCK, MatchStatus.OUT_OF_STOCK})


def _require_web_url(value: str) -> str:
    # Listing URLs end up as clickable links in the UI, so anything but absolute http(s) is refused.
    parts = urlsplit(value)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise ValueError("must be an absolute http(s) URL")
    return value


WebUrl = Annotated[str, AfterValidator(_require_web_url)]


class _Immutable(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Fingerprint(_Immutable):
    """The normalised identity of a product. `None` means "unknown", never "doesn't apply"."""

    category: Category | None = None
    brand: str | None = None
    model: str | None = None
    model_number: str | None = None
    ram_gb: int | None = Field(default=None, gt=0)
    storage_gb: int | None = Field(default=None, gt=0)
    screen_in: float | None = Field(default=None, gt=0)
    colour: str | None = None
    colour_families: tuple[str, ...] = ()
    gender: Gender | None = None

    def completed_with(self, other: Fingerprint) -> Fingerprint:
        """This fingerprint with its unknown attributes taken from `other`; known ones are kept."""
        gaps = {
            name: getattr(other, name)
            for name in type(self).model_fields
            if getattr(self, name) in (None, ()) and getattr(other, name) not in (None, ())
        }
        return self.model_copy(update=gaps)


class Listing(_Immutable):
    """One product page on one platform."""

    platform: Platform
    listing_id: str = Field(min_length=1)
    url: WebUrl
    title: str = Field(min_length=1)
    fingerprint: Fingerprint = Fingerprint()
    availability: Availability = Availability.UNKNOWN
    price_inr: float | None = Field(default=None, ge=0)
    image_url: WebUrl | None = None
    sponsored: bool = False


class PlatformResult(_Immutable):
    platform: Platform
    status: MatchStatus
    reason: str
    listing: Listing | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    notes: tuple[str, ...] = ()
    checked_at: datetime | None = None  # when the shop was checked; older than now when the answer was cached

    @model_validator(mode="after")
    def _listing_agrees_with_status(self) -> Self:
        if self.status in _STATUSES_THAT_SHOW_A_LINK and self.listing is None:
            raise ValueError(f"a {self.status} result must include the matched listing")
        if self.status is MatchStatus.NOT_LISTED and self.listing is not None:
            raise ValueError("a not_listed result cannot include a listing")
        if self.listing is not None and self.listing.platform is not self.platform:
            raise ValueError(
                f"a {self.platform} result cannot include a listing from {self.listing.platform}"
            )
        return self


class ComparisonReport(_Immutable):
    source: Listing
    results: tuple[PlatformResult, ...]
    demo: bool = False  # True when the results are bundled sample data rather than live searches

    @model_validator(mode="after")
    def _is_well_formed(self) -> Self:
        if self.source.fingerprint.category is None:
            raise ValueError("the source product must have a known category")
        platforms = [result.platform for result in self.results]
        if len(platforms) != len(set(platforms)):
            raise ValueError("each platform may appear only once")
        return self


class SourceRead(_Immutable):
    """The Amazon product has been read; `platforms` are about to be checked."""

    kind: Literal["source"] = "source"
    source: Listing
    platforms: tuple[Platform, ...]
    demo: bool = False


class PlatformChecked(_Immutable):
    """One platform has been checked."""

    kind: Literal["result"] = "result"
    result: PlatformResult


ComparisonEvent = SourceRead | PlatformChecked
