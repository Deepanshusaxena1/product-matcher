"""Application factory and composition root: the one place that decides which implementations are used."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.errors import install_error_handlers
from app.api.routes import router as api_router
from app.config import Settings
from app.infra.cache import TtlCache
from app.infra.http import CurlPageFetcher
from app.matching.matcher import Matcher
from app.platforms.croma.adapter import CromaAdapter
from app.platforms.croma.inventory import InventoryKey
from app.platforms.flipkart.adapter import FlipkartAdapter
from app.platforms.myntra.adapter import MyntraAdapter
from app.services.caching import CachedFinder, CachedProductSource
from app.services.comparer import LiveProductComparer
from app.services.demo import DemoProductComparer
from app.sources.amazon.reader import AmazonProductSource
from app.sources.amazon.url import parse_amazon_link

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from app.domain.models import Listing, PlatformResult
    from app.domain.ports import PageFetcher, ProductComparer

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


def build_live_comparer(fetcher: PageFetcher, settings: Settings) -> LiveProductComparer:
    croma_key = InventoryKey(fetcher, configured=settings.croma_inventory_key)
    products: TtlCache[Listing] = TtlCache(max_entries=settings.cache_max_entries)
    results: TtlCache[PlatformResult] = TtlCache(max_entries=settings.cache_max_entries)
    return LiveProductComparer(
        CachedProductSource(
            AmazonProductSource(fetcher),
            products,
            ttl_seconds=settings.product_cache_ttl_s,
            key=lambda url: parse_amazon_link(url).fetch_url,  # one entry however the link was pasted
        ),
        adapters=[
            FlipkartAdapter(fetcher),
            CromaAdapter(fetcher, pincode=settings.croma_pincode, key=croma_key),
            MyntraAdapter(fetcher),
        ],
        finder=CachedFinder(Matcher(), results, ttl_seconds=settings.result_cache_ttl_s),
        platform_timeout_s=settings.platform_timeout_s,
    )


def create_app(comparer: ProductComparer | None = None, settings: Settings | None = None) -> FastAPI:
    """`comparer` overrides everything (tests); otherwise `settings` choose demo or live."""
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if comparer is not None or settings.demo:
            yield
            return
        # The HTTP session belongs to the running event loop, so it is opened here rather than at import.
        fetcher = CurlPageFetcher.impersonating_chrome(timeout_s=settings.fetch_timeout_s)
        app.state.comparer = build_live_comparer(fetcher, settings)
        try:
            yield
        finally:
            await fetcher.aclose()

    app = FastAPI(
        title="Product Matcher",
        summary="Find an Amazon.in product on Flipkart, Croma and Myntra, and whether it is in stock.",
        version="0.5.0",
        lifespan=lifespan,
    )
    if comparer is not None:
        app.state.comparer = comparer
    elif settings.demo:
        app.state.comparer = DemoProductComparer.bundled()
    install_error_handlers(app)
    app.include_router(api_router)
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="web")  # last: API routes win
    return app


app = create_app()
