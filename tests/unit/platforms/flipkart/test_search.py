from collections.abc import Callable

import pytest

from app.domain.models import Availability, Category, Gender, Listing, Platform
from app.platforms.flipkart.search import parse_search_results


def _results(html: str) -> dict[str, Listing]:
    results = parse_search_results(html)
    assert results is not None
    return {listing.listing_id: listing for listing in results}


@pytest.fixture
def phones(flipkart_page: Callable[[str], str]) -> dict[str, Listing]:
    return _results(flipkart_page("search_samsung_s24fe.html"))


def test_a_phone_result_carries_its_variant_price_and_stock(phones: dict[str, Listing]) -> None:
    listing = phones["MOBH4ZG3Z5NCBW2H"]

    assert listing.platform is Platform.FLIPKART
    assert listing.title == "Samsung Galaxy S24 FE 5G (Blue, 128 GB)"
    assert listing.url == (
        "https://www.flipkart.com/samsung-galaxy-s24-fe-5g-blue-128-gb/p/itme960199e26f23?pid=MOBH4ZG3Z5NCBW2H"
    )
    assert listing.price_inr == 39999
    assert listing.availability is Availability.IN_STOCK
    assert listing.image_url is not None
    assert listing.image_url.startswith("https://rukmini1.flixcart.com/image/416/416/")
    fingerprint = listing.fingerprint
    assert fingerprint.category is Category.SMARTPHONE
    assert (fingerprint.brand, fingerprint.model) == ("samsung", "galaxy s24 fe")
    assert (fingerprint.ram_gb, fingerprint.storage_gb) == (8, 128)
    assert (fingerprint.colour, fingerprint.colour_families) == ("Blue", ("blue",))


def test_results_keep_page_order_and_flag_out_of_stock_and_ads(phones: dict[str, Listing]) -> None:
    assert next(iter(phones)) == "MOBH4ZG3Z5NCBW2H"
    assert phones["MOBH92ADUFBMDXZX"].availability is Availability.OUT_OF_STOCK
    assert phones["MOBHQCH6FPTX5FZ2"].sponsored
    assert not phones["MOBH4ZG33EBNZKS7"].sponsored


def test_a_plus_model_is_not_the_base_model(phones: dict[str, Listing]) -> None:
    assert phones["MOBGX2F3GDX7QYFT"].fingerprint.model == "galaxy s24 plus"


def test_accessories_in_phone_results_are_not_phones(phones: dict[str, Listing]) -> None:
    assert phones["MSAHNZWCZFRFEMZV"].fingerprint.category is None  # camera lens glass
    assert phones["MBPHH52D444XNBWY"].fingerprint.category is None  # back panel


def test_a_tv_result_carries_its_model_number_and_screen_size(flipkart_page: Callable[[str], str]) -> None:
    tvs = _results(flipkart_page("search_lg_43nu870bpla.html"))

    fingerprint = tvs["TVSHMYS2GZCZEZH4"].fingerprint
    assert fingerprint.category is Category.TELEVISION
    assert fingerprint.brand == "lg"
    assert fingerprint.model_number == "43NU870BPLA"
    assert fingerprint.screen_in == 43
    assert tvs["RFRHK762H3GG9TD9"].fingerprint.category is None  # a refrigerator


def test_sneaker_results_carry_colour_and_gender(flipkart_page: Callable[[str], str]) -> None:
    shoes = _results(flipkart_page("search_nike_court_vision.html"))

    mens = shoes["SHOGRVJPSM9MFYYE"].fingerprint
    assert mens.category is Category.SNEAKER
    assert (mens.brand, mens.model) == ("nike", "court vision low next nature")
    assert (mens.colour, mens.colour_families, mens.gender) == ("White", ("white",), Gender.MEN)
    assert shoes["SHOGUZ9QA3JNHQH3"].fingerprint.gender is Gender.WOMEN
    assert shoes["SHOHQDGJBSWAYWZG"].fingerprint.colour_families == ("blue", "white")


def test_clothing_results_without_a_stock_flag_have_unknown_availability(
    flipkart_page: Callable[[str], str],
) -> None:
    shirts = _results(flipkart_page("search_puma_polo.html"))

    listing = shirts["TSHH4D2FPT6NEYZZ"]
    assert listing.fingerprint.category is Category.TSHIRT
    assert listing.fingerprint.brand == "puma"
    assert listing.fingerprint.gender is Gender.MEN
    assert listing.availability is Availability.UNKNOWN
    assert listing.price_inr == 469


def test_a_page_without_search_state_is_not_a_results_page() -> None:
    assert parse_search_results("<html><body>Are you a human?</body></html>") is None
