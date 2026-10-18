from datetime import UTC, datetime

from app.domain.models import Category, Fingerprint, Listing, MatchStatus, Platform, PlatformResult
from app.domain.ports import PlatformAdapter, ShopProfile
from app.infra.cache import TtlCache
from app.services.caching import CachedFinder, CachedProductSource

TV = Listing(
    platform=Platform.AMAZON,
    listing_id="B0GTZ9TSDJ",
    url="https://www.amazon.in/dp/B0GTZ9TSDJ",
    title="LG 43 inch TV",
    fingerprint=Fingerprint(category=Category.TELEVISION, brand="lg"),
)
NOW = datetime(2026, 10, 18, 12, 0, tzinfo=UTC)


class CountingSource:
    def __init__(self) -> None:
        self.reads = 0

    async def read(self, product_url: str) -> Listing:
        self.reads += 1
        return TV


class Shop:
    def __init__(self, platform: Platform) -> None:
        self._platform = platform

    @property
    def platform(self) -> Platform:
        return self._platform

    @property
    def profile(self) -> ShopProfile:
        return ShopProfile()

    async def search(self, query: str, category: Category) -> list[Listing]:
        raise AssertionError("never searched")

    async def fetch_details(self, listing: Listing) -> Listing:
        raise AssertionError("never opened")


class CountingFinder:
    def __init__(self, status: MatchStatus) -> None:
        self.status = status
        self.finds = 0

    async def find(self, source: Listing, adapter: PlatformAdapter) -> PlatformResult:
        self.finds += 1
        return PlatformResult(platform=adapter.platform, status=self.status, reason="-")


async def test_the_same_product_is_read_from_amazon_once() -> None:
    inner = CountingSource()
    source = CachedProductSource(inner, TtlCache(), ttl_seconds=60, key=lambda url: url.split("?")[0])

    await source.read("https://www.amazon.in/dp/B0GTZ9TSDJ?ref=a")
    again = await source.read("https://www.amazon.in/dp/B0GTZ9TSDJ?ref=b")

    assert again == TV
    assert inner.reads == 1


async def test_a_shops_answer_is_reused_with_the_time_it_was_found() -> None:
    inner = CountingFinder(MatchStatus.NOT_LISTED)
    finder = CachedFinder(inner, TtlCache(), ttl_seconds=60, clock=lambda: NOW)

    first = await finder.find(TV, Shop(Platform.CROMA))
    again = await finder.find(TV, Shop(Platform.CROMA))

    assert inner.finds == 1
    assert again == first
    assert again.checked_at == NOW


async def test_each_shop_has_its_own_answer() -> None:
    inner = CountingFinder(MatchStatus.NOT_LISTED)
    finder = CachedFinder(inner, TtlCache(), ttl_seconds=60, clock=lambda: NOW)

    await finder.find(TV, Shop(Platform.CROMA))
    flipkart = await finder.find(TV, Shop(Platform.FLIPKART))

    assert inner.finds == 2
    assert flipkart.platform is Platform.FLIPKART


async def test_couldnt_check_is_never_reused() -> None:
    inner = CountingFinder(MatchStatus.ERROR)
    finder = CachedFinder(inner, TtlCache(), ttl_seconds=60, clock=lambda: NOW)

    await finder.find(TV, Shop(Platform.CROMA))
    await finder.find(TV, Shop(Platform.CROMA))

    assert inner.finds == 2
