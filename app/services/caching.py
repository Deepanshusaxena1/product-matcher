"""Caching decorators for the two slow steps: reading the Amazon product and checking one shop.

Both wrap the real implementation behind the same port, so the comparer doesn't know caching exists.
Failures are never cached: a shop that couldn't be checked is asked again next time.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.domain.models import MatchStatus

if TYPE_CHECKING:
    from collections.abc import Callable

    from app.domain.models import Listing, PlatformResult
    from app.domain.ports import Cache, PlatformAdapter, ProductSource
    from app.services.comparer import PlatformFinder


class CachedProductSource:
    """A `ProductSource` that remembers products by `key(url)`, e.g. the canonical Amazon link."""

    def __init__(
        self, source: ProductSource, cache: Cache[Listing], *, ttl_seconds: float, key: Callable[[str], str]
    ) -> None:
        self._source = source
        self._cache = cache
        self._ttl_seconds = ttl_seconds
        self._key = key

    async def read(self, product_url: str) -> Listing:
        key = self._key(product_url)
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        listing = await self._source.read(product_url)
        self._cache.set(key, listing, self._ttl_seconds)
        return listing


class CachedFinder:
    """A `PlatformFinder` that reuses a shop's answer about a product, stamped with when it was found."""

    def __init__(
        self,
        finder: PlatformFinder,
        cache: Cache[PlatformResult],
        *,
        ttl_seconds: float,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._finder = finder
        self._cache = cache
        self._ttl_seconds = ttl_seconds
        self._clock = clock

    async def find(self, source: Listing, adapter: PlatformAdapter) -> PlatformResult:
        key = f"{adapter.platform}:{source.platform}:{source.listing_id}"
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        result = await self._finder.find(source, adapter)
        result = result.model_copy(update={"checked_at": result.checked_at or self._clock()})
        if result.status is not MatchStatus.ERROR:
            self._cache.set(key, result, self._ttl_seconds)
        return result
