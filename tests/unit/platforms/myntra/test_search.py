import json
from collections.abc import Callable

from app.domain.models import Availability, Category, Gender, Platform
from app.platforms.myntra.search import parse_search_results


def _page(*products: dict[str, object]) -> str:
    state = {"searchData": {"results": {"products": list(products)}}}
    return f"<script>window.__myx_deviceType__ = 'desktop'; window.__myx = {json.dumps(state)}</script>"


def test_every_product_tile_becomes_a_listing(myntra_page: Callable[[str], str]) -> None:
    results = parse_search_results(myntra_page("search_nike_court_vision.html"))

    assert results is not None
    assert len(results) == 14
    low = next(listing for listing in results if listing.listing_id == "27306858")
    assert low.platform is Platform.MYNTRA
    assert (
        low.url == "https://www.myntra.com/casual-shoes/nike/nike-men-court-vision-low-sneakers/27306858/buy"
    )
    assert low.title == "Nike Men Court Vision Low Sneakers"
    assert low.price_inr == 4271
    assert (low.image_url or "").startswith("https://assets.myntassets.com/")
    assert low.availability is Availability.UNKNOWN  # the tile only summarises one size


def test_a_tile_reveals_category_brand_model_colour_and_gender(myntra_page: Callable[[str], str]) -> None:
    results = parse_search_results(myntra_page("search_nike_court_vision.html")) or []

    low = next(listing for listing in results if listing.listing_id == "27306858").fingerprint
    assert low.category is Category.SNEAKER
    assert (low.brand, low.model) == ("nike", "court vision low")
    assert (low.colour, low.colour_families) == ("White", ("white",))
    assert low.gender is Gender.MEN
    assert low.model_number is None


def test_polo_tiles_are_t_shirts(myntra_page: Callable[[str], str]) -> None:
    results = parse_search_results(myntra_page("search_puma_polo.html")) or []

    assert {listing.fingerprint.category for listing in results} == {Category.TSHIRT}


def test_advertised_tiles_are_marked_sponsored() -> None:
    tile = {
        "productId": 1,
        "landingPageUrl": "tshirts/puma/x/1/buy",
        "productName": "Puma Men Polo T-shirt",
        "brand": "Puma",
        "category": "Tshirts",
        "isPLA": True,
    }

    [listing] = parse_search_results(_page(tile)) or []

    assert listing.sponsored


def test_a_page_without_search_data_is_not_search_results() -> None:
    assert parse_search_results("<html>Oops! Something went wrong</html>") is None
