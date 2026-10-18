import pytest

from app.domain.errors import (
    InvalidProductUrlError,
    ProductNotFoundError,
    SourceUnavailableError,
    UnsupportedCategoryError,
)
from app.domain.models import Availability, Category, Platform
from app.domain.ports import FetchedPage, FetchError
from app.sources.amazon.reader import AmazonProductSource
from support.fakes import FakeFetcher

ASIN = "B0DHL7YT5S"
PRODUCT_URL = f"https://www.amazon.in/dp/{ASIN}"


def _page(text: str, status: int = 200, url: str = PRODUCT_URL) -> FetchedPage:
    return FetchedPage(status_code=status, url=url, text=text)


def _redirect(location: str, url: str) -> FetchedPage:
    return FetchedPage(status_code=301, url=url, text="", headers={"location": location})


async def test_a_product_link_is_read_into_a_listing_with_a_fingerprint(phone_html: str) -> None:
    fetcher = FakeFetcher({PRODUCT_URL: _page(phone_html)})

    listing = await AmazonProductSource(fetcher).read(
        f"https://www.amazon.in/Samsung/dp/{ASIN}/ref=sr_1_3?k=s24"
    )

    assert fetcher.requests == [(PRODUCT_URL, True)]  # canonical URL, tracking dropped
    assert listing.platform is Platform.AMAZON
    assert listing.listing_id == ASIN
    assert str(listing.url) == PRODUCT_URL
    assert listing.title.startswith("Samsung Galaxy S24 FE")
    assert listing.fingerprint.category is Category.SMARTPHONE
    assert (listing.fingerprint.ram_gb, listing.fingerprint.storage_gb) == (8, 128)
    assert listing.price_inr == 39999.0
    assert listing.availability is Availability.IN_STOCK


async def test_a_short_link_is_followed_one_checked_hop_at_a_time(phone_html: str) -> None:
    fetcher = FakeFetcher(
        {
            "https://amzn.in/d/5xYz123": _redirect(
                f"https://www.amazon.in/Samsung-Galaxy/dp/{ASIN}?_encoding=UTF8&ref_=share",
                "https://amzn.in/d/5xYz123",
            ),
            PRODUCT_URL: _page(phone_html),
        }
    )

    listing = await AmazonProductSource(fetcher).read("https://amzn.in/d/5xYz123")

    assert listing.listing_id == ASIN
    assert fetcher.requests == [("https://amzn.in/d/5xYz123", False), (PRODUCT_URL, True)]


async def test_a_short_link_that_leads_off_amazon_is_refused_without_fetching_it() -> None:
    fetcher = FakeFetcher(
        {"https://amzn.to/3AbCdEf": _redirect("http://169.254.169.254/latest", "https://amzn.to/3AbCdEf")}
    )

    with pytest.raises(InvalidProductUrlError):
        await AmazonProductSource(fetcher).read("https://amzn.to/3AbCdEf")

    assert fetcher.requests == [("https://amzn.to/3AbCdEf", False)]


async def test_a_short_link_that_redirects_in_circles_gives_up() -> None:
    fetcher = FakeFetcher({"https://amzn.in/d/loop": _redirect("/d/loop", "https://amzn.in/d/loop")})

    with pytest.raises(SourceUnavailableError):
        await AmazonProductSource(fetcher, max_redirects=3).read("https://amzn.in/d/loop")

    assert len(fetcher.requests) == 3


async def test_a_short_link_that_does_not_redirect_is_not_a_product() -> None:
    fetcher = FakeFetcher(
        {"https://amzn.in/d/gone": _page("<html></html>", status=404, url="https://amzn.in/d/gone")}
    )

    with pytest.raises(ProductNotFoundError):
        await AmazonProductSource(fetcher).read("https://amzn.in/d/gone")


async def test_a_missing_product_is_reported_as_not_found() -> None:
    fetcher = FakeFetcher({PRODUCT_URL: _page("<html>Page Not Found</html>", status=404)})

    with pytest.raises(ProductNotFoundError):
        await AmazonProductSource(fetcher).read(PRODUCT_URL)


@pytest.mark.parametrize(
    "response",
    [
        FetchError("connection reset"),
        _page('<form action="/errors/validateCaptcha">Enter the characters you see below</form>'),
        _page("<html><body>Something unexpected</body></html>"),
        _page("<html></html>", status=500),
    ],
    ids=["network-failure", "robot-check", "unexpected-page", "server-error"],
)
async def test_an_unreadable_amazon_is_reported_as_unavailable(response: FetchedPage | Exception) -> None:
    fetcher = FakeFetcher({PRODUCT_URL: response})

    with pytest.raises(SourceUnavailableError):
        await AmazonProductSource(fetcher).read(PRODUCT_URL)


SUPPORTED = "You can compare phones, TVs, sneakers and T-shirts."


def _product(title: str, *crumbs: str) -> str:
    links = "".join(f"<a>{crumb}</a>" for crumb in crumbs)
    return f'<span id="productTitle">{title}</span><div id="wayfinding-breadcrumbs_feature_div">{links}</div>'


async def _refusal(html: str) -> str:
    fetcher = FakeFetcher({PRODUCT_URL: _page(html)})
    with pytest.raises(UnsupportedCategoryError) as refused:
        await AmazonProductSource(fetcher).read(PRODUCT_URL)
    return refused.value.message


async def test_a_product_outside_the_four_categories_is_refused_by_its_kind() -> None:
    message = await _refusal(_product("Epson EB-X51 Projector", "Electronics", "Projectors"))

    assert message == f"Projectors aren't supported. {SUPPORTED}"


async def test_a_laptop_is_refused_by_its_plain_category_name() -> None:
    # Live page B0GR177QCS: Computers & Accessories > Laptops > Traditional Laptops.
    html = _product(
        "Apple 2026 MacBook Neo 13″ Laptop with A18 Pro chip", "Computers & Accessories", "Laptops",
        "Traditional Laptops",
    )  # fmt: skip

    assert await _refusal(html) == f"Laptops aren't supported. {SUPPORTED}"


async def test_a_product_without_categories_is_refused_without_naming_one() -> None:
    message = await _refusal(_product("Mystery gadget"))

    assert message == f"This product isn't supported. {SUPPORTED}"


async def test_a_link_that_is_not_amazon_is_refused_before_any_request() -> None:
    fetcher = FakeFetcher({})

    with pytest.raises(InvalidProductUrlError):
        await AmazonProductSource(fetcher).read("https://www.flipkart.com/p/itm123")

    assert fetcher.requests == []
