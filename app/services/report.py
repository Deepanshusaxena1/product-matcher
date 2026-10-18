"""Turn a comparison's events into the single report the non-streaming API returns."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.domain.models import ComparisonReport, PlatformChecked, SourceRead

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from app.domain.models import ComparisonEvent


async def collect_report(events: AsyncIterator[ComparisonEvent]) -> ComparisonReport:
    """Wait for every result; they are reported in the category's platform order, not finishing order."""
    first = await anext(events, None)
    if not isinstance(first, SourceRead):
        raise ValueError("a comparison stream must start with the source product")
    results = {
        event.result.platform: event.result async for event in events if isinstance(event, PlatformChecked)
    }
    ordered = tuple(results[platform] for platform in first.platforms if platform in results)
    return ComparisonReport(source=first.source, results=ordered, demo=first.demo)
