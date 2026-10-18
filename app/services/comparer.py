"""The live use case: read the Amazon product, then look for it on each of its category's platforms."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Protocol

from app.domain.models import MatchStatus, Platform, PlatformChecked, PlatformResult, SourceRead
from app.services.report import collect_report

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Callable, Iterable

    from app.domain.models import ComparisonEvent, ComparisonReport, Listing
    from app.domain.ports import PlatformAdapter, ProductSource

logger = logging.getLogger(__name__)


class PlatformFinder(Protocol):
    """Finds one product on one shop (implemented by `app.matching.matcher.Matcher`)."""

    async def find(self, source: Listing, adapter: PlatformAdapter) -> PlatformResult: ...


class LiveProductComparer:
    """Implements `ProductComparer`. Shops are searched concurrently, and one shop failing never fails the
    request: it is reported as "couldn't check" while the others still answer."""

    def __init__(
        self,
        source: ProductSource,
        adapters: Iterable[PlatformAdapter],
        finder: PlatformFinder,
        *,
        platform_timeout_s: float = 45.0,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._source = source
        self._adapters = {adapter.platform: adapter for adapter in adapters}
        self._finder = finder
        self._platform_timeout_s = platform_timeout_s
        self._clock = clock

    @property
    def connected_platforms(self) -> tuple[Platform, ...]:
        """The platforms this comparer has an adapter for, in the order of `Platform`."""
        return tuple(platform for platform in Platform if platform in self._adapters)

    async def compare(self, product_url: str) -> ComparisonReport:
        return await collect_report(self.stream(product_url))

    async def stream(self, product_url: str) -> AsyncGenerator[ComparisonEvent, None]:
        product = await self._source.read(product_url)
        category = product.fingerprint.category
        assert category is not None  # the source refuses products outside the four categories
        yield SourceRead(source=product, platforms=category.platforms)

        checks = [
            asyncio.create_task(self._timed_check(product, platform)) for platform in category.platforms
        ]
        try:
            for next_finished in asyncio.as_completed(checks):
                yield PlatformChecked(result=await next_finished)
        finally:  # the listener left early (a closed browser tab): stop searching for it
            for check in checks:
                check.cancel()

    async def _timed_check(self, product: Listing, platform: Platform) -> PlatformResult:
        result = await self._check(product, platform)
        # A cached answer arrives already stamped with the time it was found.
        return result if result.checked_at else result.model_copy(update={"checked_at": self._clock()})

    async def _check(self, product: Listing, platform: Platform) -> PlatformResult:
        adapter = self._adapters.get(platform)
        if adapter is None:
            return _could_not_check(platform, f"{platform.label} isn't connected yet.")
        try:
            async with asyncio.timeout(self._platform_timeout_s):
                return await self._finder.find(product, adapter)
        except TimeoutError:
            logger.warning("%s timed out for %s", platform, product.listing_id)
            return _could_not_check(platform, f"{platform.label} took too long to answer. Try again.")
        except Exception:  # one shop's failure must never fail the whole comparison
            logger.exception("%s could not be checked for %s", platform, product.listing_id)
            return _could_not_check(platform, f"Couldn't check {platform.label} just now. Try again.")


def _could_not_check(platform: Platform, reason: str) -> PlatformResult:
    return PlatformResult(platform=platform, status=MatchStatus.ERROR, reason=reason)
