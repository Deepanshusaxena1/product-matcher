from collections.abc import Callable

from app.domain.models import Availability, Category, Fingerprint, Gender
from app.platforms.flipkart.product import FlipkartProductPage, parse_product_page


def _page(html: str) -> FlipkartProductPage:
    page = parse_product_page(html)
    assert page is not None
    return page


def test_a_phone_page_gives_its_stock_price_and_full_fingerprint(flipkart_page: Callable[[str], str]) -> None:
    page = _page(flipkart_page("pdp_samsung_s24fe_graphite_oos.html"))

    assert page.listing_id == "MOBH92ADUFBMDXZX"
    assert page.title == "Samsung Galaxy S24 FE 5G (Graphite, 128 GB)"
    assert page.availability is Availability.OUT_OF_STOCK
    assert page.price_inr == 38998
    assert page.image_url is not None
    assert page.fingerprint == Fingerprint(
        category=Category.SMARTPHONE,
        brand="samsung",
        model="galaxy s24 fe",
        model_number="S721B-SM",
        ram_gb=8,
        storage_gb=128,
        colour="Graphite",
        colour_families=("grey",),
    )


def test_a_tv_page_whose_model_name_is_a_model_number_uses_it_as_one(
    flipkart_page: Callable[[str], str],
) -> None:
    page = _page(flipkart_page("pdp_lg_43nu870bpla.html"))

    assert page.availability is Availability.IN_STOCK
    assert page.price_inr == 30409
    assert page.fingerprint.category is Category.TELEVISION
    assert page.fingerprint.brand == "lg"
    assert page.fingerprint.model_number == "43NU870BPLA"
    assert page.fingerprint.screen_in == 43
    assert page.fingerprint.ram_gb is None  # the TV's "Ram Capacity" is not a phone attribute


def test_a_sneaker_page_gives_its_article_number_and_brand_colour(
    flipkart_page: Callable[[str], str],
) -> None:
    page = _page(flipkart_page("pdp_nike_court_vision_lo_nn.html"))

    assert page.availability is Availability.IN_STOCK
    assert page.fingerprint == Fingerprint(
        category=Category.SNEAKER,
        brand="nike",
        model="court vision low next nature",
        model_number="DH2987-100",
        colour="White/White-White",
        colour_families=("white",),
        gender=Gender.MEN,
    )


def test_a_tshirt_page_gives_its_style_code(flipkart_page: Callable[[str], str]) -> None:
    page = _page(flipkart_page("pdp_puma_polo_68709301.html"))

    assert page.availability is Availability.IN_STOCK
    assert page.price_inr == 469
    assert page.fingerprint.category is Category.TSHIRT
    assert page.fingerprint.model_number == "68709301"
    assert (page.fingerprint.colour, page.fingerprint.colour_families) == ("Black", ("black",))
    assert page.fingerprint.gender is Gender.MEN


def test_a_page_without_product_state_is_not_a_product_page() -> None:
    assert parse_product_page("<html><body>Something went wrong</body></html>") is None
