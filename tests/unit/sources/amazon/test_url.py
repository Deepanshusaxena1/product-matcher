import pytest

from app.domain.errors import InvalidProductUrlError
from app.sources.amazon.url import parse_amazon_link

ASIN = "B0DHL7YT5S"
CANONICAL = f"https://www.amazon.in/dp/{ASIN}"


@pytest.mark.parametrize(
    "pasted",
    [
        f"https://www.amazon.in/dp/{ASIN}",
        f"https://www.amazon.in/Samsung-Galaxy-Smartphone-Graphite-Storage/dp/{ASIN}/ref=sr_1_3?crid=2X&keywords=s24",
        f"https://www.amazon.in/gp/product/{ASIN}?th=1",
        f"https://m.amazon.in/gp/aw/d/{ASIN}",
        f"https://amazon.in/dp/{ASIN.lower()}",
        f"HTTPS://WWW.AMAZON.IN/DP/{ASIN}",
        f"www.amazon.in/dp/{ASIN}",
        f"  https://www.amazon.in/dp/{ASIN}  ",
        f"Check out this phone on Amazon: https://www.amazon.in/dp/{ASIN}?ref=share.",
    ],
)
def test_product_links_resolve_to_the_canonical_product_page(pasted: str) -> None:
    link = parse_amazon_link(pasted)

    assert link.asin == ASIN
    assert link.fetch_url == CANONICAL
    assert not link.is_short_link


@pytest.mark.parametrize(
    ("pasted", "fetch_url"),
    [
        ("https://amzn.in/d/5xYz123", "https://amzn.in/d/5xYz123"),
        ("https://amzn.to/3AbCdEf", "https://amzn.to/3AbCdEf"),
        ("https://a.co/d/abc123", "https://a.co/d/abc123"),
        ("Samsung Galaxy S24 FE https://amzn.in/d/5xYz123", "https://amzn.in/d/5xYz123"),
        ("https://user:secret@amzn.in:8443/d/5xYz123", "https://amzn.in/d/5xYz123"),
    ],
)
def test_short_links_are_accepted_and_sanitised_for_resolution(pasted: str, fetch_url: str) -> None:
    link = parse_amazon_link(pasted)

    assert link.is_short_link
    assert link.asin is None
    assert link.fetch_url == fetch_url


@pytest.mark.parametrize(
    "pasted",
    [
        "",
        "   ",
        "not a link",
        "https://www.flipkart.com/samsung-galaxy-s24-fe/p/itm123?pid=MOBH4ZG3Z5NCBW2H",
        f"https://www.amazon.com/dp/{ASIN}",
        f"https://www.amazon.in.evil.example/dp/{ASIN}",
        f"https://evilamazon.in/dp/{ASIN}",
        f"ftp://www.amazon.in/dp/{ASIN}",
        "javascript:alert(1)//amazon.in/dp/B0DHL7YT5S",
        "https://amzn.in/",
    ],
)
def test_anything_that_is_not_an_amazon_in_link_is_rejected(pasted: str) -> None:
    with pytest.raises(InvalidProductUrlError, match=r"Amazon\.in"):
        parse_amazon_link(pasted)


def test_an_amazon_page_that_is_not_a_product_is_rejected_with_a_specific_message() -> None:
    with pytest.raises(InvalidProductUrlError, match="product page"):
        parse_amazon_link("https://www.amazon.in/s?k=samsung+galaxy+s24+fe")
