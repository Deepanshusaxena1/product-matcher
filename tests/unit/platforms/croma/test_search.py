import json
from collections.abc import Callable

from app.domain.models import Availability, Category, Platform
from app.platforms.croma.search import parse_search_results


def test_every_product_in_the_results_becomes_a_listing(croma_file: Callable[[str], str]) -> None:
    results = parse_search_results(json.loads(croma_file("search_samsung_s24.json")))

    assert results is not None
    assert len(results) == 16
    onyx = next(listing for listing in results if listing.listing_id == "303849")
    assert onyx.platform is Platform.CROMA
    assert onyx.url == "https://www.croma.com/samsung-galaxy-s24-5g-8gb-ram-256gb-onyx-black-/p/303849"
    assert onyx.title == "SAMSUNG Galaxy S24 5G (8GB RAM, 256GB, Onyx Black)"
    assert onyx.price_inr == 49994
    assert (onyx.image_url or "").startswith("https://media.tatacroma.com/")
    assert onyx.availability is Availability.UNKNOWN  # stock needs the delivery check
    assert not onyx.sponsored


def test_a_phone_tile_reveals_its_model_memory_and_colour(croma_file: Callable[[str], str]) -> None:
    results = parse_search_results(json.loads(croma_file("search_samsung_s24.json"))) or []

    onyx = next(listing for listing in results if listing.listing_id == "303849").fingerprint
    assert onyx.category is Category.SMARTPHONE
    assert (onyx.brand, onyx.model) == ("samsung", "galaxy s24")
    assert (onyx.ram_gb, onyx.storage_gb) == (8, 256)
    assert onyx.colour == "Onyx Black"
    plus = next(listing for listing in results if listing.listing_id == "303847").fingerprint
    assert plus.model == "galaxy s24 plus"


def test_a_tv_tile_reveals_its_screen_size(croma_file: Callable[[str], str]) -> None:
    results = parse_search_results(json.loads(croma_file("search_lg_43_inch.json"))) or []

    nu870 = next(listing for listing in results if listing.listing_id == "323496").fingerprint
    assert nu870.category is Category.TELEVISION
    assert nu870.brand == "lg"
    assert nu870.screen_in == 43
    assert nu870.model_number is None  # only the product page states it


def test_a_product_from_a_category_outside_the_four_has_no_category() -> None:
    data = {
        "products": [
            {
                "code": "300001",
                "name": "SPIGEN Back Cover for Galaxy S24 (Black)",
                "manufacturer": "Spigen",
                "url": "/spigen-back-cover/p/300001",
                "categoryL2": "180",
            }
        ],
        "facets": [{"code": "lower_categories", "values": [{"code": "180", "name": "Mobile Covers"}]}],
    }

    [cover] = parse_search_results(data) or []

    assert cover.fingerprint.category is None


def test_a_response_without_products_is_not_search_results() -> None:
    assert parse_search_results({"errors": [{"message": "bad query"}]}) is None
    assert parse_search_results({"products": []}) == []
