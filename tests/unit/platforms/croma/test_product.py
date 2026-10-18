from collections.abc import Callable

from app.domain.models import Category
from app.platforms.croma.product import parse_product_page


def test_a_phone_page_gives_the_full_fingerprint(croma_file: Callable[[str], str]) -> None:
    page = parse_product_page(croma_file("pdp_samsung_s24_303849.html"))

    assert page is not None
    assert page.listing_id == "303849"
    assert page.title == "SAMSUNG Galaxy S24 5G (8GB RAM, 256GB, Onyx Black)"
    assert page.fingerprint.category is Category.SMARTPHONE
    assert (page.fingerprint.brand, page.fingerprint.model) == ("samsung", "galaxy s24")
    assert page.fingerprint.model_number == "SM-S921BZKCINS"
    assert (page.fingerprint.ram_gb, page.fingerprint.storage_gb) == (8, 256)
    assert page.fingerprint.colour == "Onyx Black"
    assert (page.image_url or "").startswith("https://media.tatacroma.com/")


def test_a_tv_page_gives_its_model_number_and_screen_size(croma_file: Callable[[str], str]) -> None:
    page = parse_product_page(croma_file("pdp_lg_43nu870bpla.html"))

    assert page is not None
    assert page.fingerprint.category is Category.TELEVISION
    assert page.fingerprint.brand == "lg"
    assert page.fingerprint.model_number == "43NU870BPLA"
    assert page.fingerprint.screen_in == 43
    assert page.fingerprint.colour == "Black"


def test_a_page_without_product_data_is_not_a_product_page() -> None:
    assert parse_product_page("<html><body>Something went wrong</body></html>") is None
