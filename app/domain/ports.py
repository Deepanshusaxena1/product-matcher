"""Ports: the seams between the matching domain and the outside world.

Every protocol here is deliberately small (one job), so a shop, the AI helper or the cache can be replaced by
another implementation, or by a fake in tests, without touching the code that depends on it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Mapping, Sequence

    from app.domain.models import (
        Category,
        ComparisonEvent,
        ComparisonReport,
        Fingerprint,
        Listing,
        Platform,
    )


class ProductComparer(Protocol):
    """The use case: find the product behind an Amazon link on the other platforms."""

    def stream(self, product_url: str) -> AsyncGenerator[ComparisonEvent, None]:
        """`SourceRead` first, then one `PlatformChecked` per platform in the order they finish.

        Raises a `MatcherError` subclass, before the first event, when the link itself cannot be handled.
        """
        ...

    async def compare(self, product_url: str) -> ComparisonReport:
        """The whole stream as one report (see `app.services.report.collect_report`)."""
        ...


@dataclass(frozen=True, slots=True)
class FetchedPage:
    status_code: int
    url: str  # final URL, after any redirects that were followed
    text: str
    headers: Mapping[str, str] = field(default_factory=dict)  # lower-case names

    def json(self) -> Any:
        return json.loads(self.text)

    @property
    def redirect_location(self) -> str | None:
        """Where a redirect response points, when redirects were not followed."""
        return self.headers.get("location") if 300 <= self.status_code < 400 else None


class FetchError(Exception):
    """A page could not be fetched: network failure, timeout, or the site refused the request."""


class UnexpectedPageError(Exception):
    """A shop answered, but not with the page we asked for (a changed layout, an error or robot page)."""


class PageFetcher(Protocol):
    """Fetches web pages and JSON APIs.

    Implementations own retries and browser impersonation. They return any page the site answered with
    (including 404s and, when not following redirects, 3xx) and raise `FetchError` when there is no usable
    answer: the network failed, or the site blocked or throttled the request.
    """

    async def get(
        self,
        url: str,
        *,
        params: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
        follow_redirects: bool = True,
    ) -> FetchedPage: ...

    async def post_json(
        self, url: str, payload: Any, *, headers: Mapping[str, str] | None = None
    ) -> FetchedPage: ...


class ProductSource(Protocol):
    """Reads the product the user starts from (the Amazon page)."""

    async def read(self, product_url: str) -> Listing: ...


@dataclass(frozen=True, slots=True)
class ShopProfile:
    """What a shop can tell about its products: it shapes how the shop is searched and listings are judged."""

    shows_model_numbers: bool = True  # whether its pages state model numbers and style codes at all
    stock_note: str | None = None  # how its stock was checked, shown with every stock answer


class PlatformAdapter(Protocol):
    """Everything that is specific to one shop: how to search it and how to read its product pages."""

    @property
    def platform(self) -> Platform: ...

    @property
    def profile(self) -> ShopProfile: ...

    async def search(self, query: str, category: Category) -> Sequence[Listing]:
        """Organic results for `query`, each with whatever fingerprint the results page reveals."""
        ...

    async def fetch_details(self, listing: Listing) -> Listing:
        """The same listing completed from its product page: full fingerprint and current availability."""
        ...


@dataclass(frozen=True, slots=True)
class ProductEvidence:
    """Raw text from a product page, for the AI helper to read when deterministic parsing leaves gaps."""

    title: str
    specs: Mapping[str, str] = field(default_factory=dict)
    bullets: Sequence[str] = ()
    breadcrumbs: Sequence[str] = ()


class FingerprintEnricher(Protocol):
    """Fills gaps in a fingerprint (never overrides what deterministic parsing found)."""

    async def enrich(self, fingerprint: Fingerprint, evidence: ProductEvidence) -> Fingerprint: ...


@dataclass(frozen=True, slots=True)
class JudgeVerdict:
    same_product: bool
    reason: str


class MatchJudge(Protocol):
    """Second opinion on a borderline candidate. It only ever sees candidates that passed every hard rule."""

    async def judge(self, source: Listing, candidate: Listing) -> JudgeVerdict | None:
        """`None` means the judge abstained (unavailable, refused or timed out)."""
        ...


class Cache[V](Protocol):
    def get(self, key: str) -> V | None: ...

    def set(self, key: str, value: V, ttl_seconds: float) -> None: ...
