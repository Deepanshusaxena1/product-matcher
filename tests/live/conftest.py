from collections.abc import AsyncIterator

import pytest

from app.config import Settings
from app.infra.http import CurlPageFetcher
from app.main import build_live_comparer
from app.services.comparer import LiveProductComparer


@pytest.fixture
async def comparer() -> AsyncIterator[LiveProductComparer]:
    """The live comparer exactly as the app builds it, talking to the real shops."""
    fetcher = CurlPageFetcher.impersonating_chrome()
    yield build_live_comparer(fetcher, Settings())
    await fetcher.aclose()
