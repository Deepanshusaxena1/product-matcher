"""A `ProductComparer` that answers with bundled sample results instead of searching live.

It stands in for the live pipeline while that is being built, and stays useful afterwards as an offline mode
for demos. The bundled scenarios are real listings observed on 17 Oct 2026, chosen so that together they show
every result state.
"""

from __future__ import annotations

import hashlib
from importlib import resources
from typing import TYPE_CHECKING

from pydantic import TypeAdapter

from app.domain.models import ComparisonReport, PlatformChecked, SourceRead
from app.sources.amazon.url import parse_amazon_link

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Sequence

    from app.domain.models import ComparisonEvent

_SCENARIOS = TypeAdapter(tuple[ComparisonReport, ...])


class DemoProductComparer:
    def __init__(self, scenarios: Sequence[ComparisonReport]) -> None:
        if not scenarios:
            raise ValueError("at least one demo scenario is required")
        for scenario in scenarios:
            _check_covers_its_platforms(scenario)
        self._scenarios = tuple(scenarios)
        self._by_asin = {scenario.source.listing_id: scenario for scenario in scenarios}

    @classmethod
    def bundled(cls) -> DemoProductComparer:
        raw = resources.files(__package__).joinpath("demo_scenarios.json").read_text(encoding="utf-8")
        return cls(_SCENARIOS.validate_json(raw))

    @property
    def scenarios(self) -> tuple[ComparisonReport, ...]:
        return self._scenarios

    async def compare(self, product_url: str) -> ComparisonReport:
        return self._scenario_for(product_url).model_copy(update={"demo": True})

    async def stream(self, product_url: str) -> AsyncGenerator[ComparisonEvent, None]:
        scenario = self._scenario_for(product_url)
        yield SourceRead(
            source=scenario.source, platforms=tuple(r.platform for r in scenario.results), demo=True
        )
        for result in scenario.results:
            yield PlatformChecked(result=result)

    def _scenario_for(self, product_url: str) -> ComparisonReport:
        link = parse_amazon_link(product_url)  # same validation as live mode
        scenario = self._by_asin.get(link.asin) if link.asin else None
        if scenario is None:
            scenario = self._scenarios[_stable_index(link.fetch_url, len(self._scenarios))]
        return scenario


def _check_covers_its_platforms(scenario: ComparisonReport) -> None:
    category = scenario.source.fingerprint.category
    answered = tuple(result.platform for result in scenario.results)
    if category is None or answered != category.platforms:
        raise ValueError(
            f"demo scenario {scenario.source.listing_id} must answer {category and category.platforms}, "
            f"got {answered}"
        )


def _stable_index(key: str, size: int) -> int:
    # hash() is salted per process; a digest keeps "same link, same sample" across restarts.
    return int.from_bytes(hashlib.sha256(key.encode()).digest()[:8], "big") % size
