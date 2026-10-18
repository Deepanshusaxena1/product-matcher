import json
from collections.abc import Callable

import pytest

from app.domain.models import Availability, Category, Gender
from app.platforms.myntra.product import parse_product_page


def test_a_product_page_gives_the_fingerprint_price_and_stock(myntra_page: Callable[[str], str]) -> None:
    page = parse_product_page(myntra_page("pdp_nike_court_vision_low.html"))

    assert page is not None
    assert page.listing_id == "27306858"
    assert page.title == "Nike Men Court Vision Low Sneakers"
    assert page.fingerprint.category is Category.SNEAKER
    assert (page.fingerprint.brand, page.fingerprint.model) == ("nike", "court vision low")
    assert page.fingerprint.colour == "White"
    assert page.fingerprint.gender is Gender.MEN
    assert page.price_inr == 4271  # the discounted price, not the M.R.P.
    assert page.availability is Availability.IN_STOCK  # size 6 is available


def test_kids_shoes_are_for_kids(myntra_page: Callable[[str], str]) -> None:
    page = parse_product_page(myntra_page("pdp_nike_af1_kids.html"))

    assert page is not None
    assert page.fingerprint.gender is Gender.KIDS


def _pdp(flags: dict[str, object], sizes: list[dict[str, object]]) -> str:
    data = {
        "pdpData": {
            "id": 1,
            "name": "Puma Men Polo T-shirt",
            "brand": {"name": "Puma"},
            "baseColour": "Black",
            "analytics": {"articleType": "Tshirts", "gender": "Men"},
            "flags": flags,
            "sizes": sizes,
            "price": {"mrp": 1699, "discounted": 764},
        }
    }
    return f"<script>window.__myx = {json.dumps(data)}</script>"


@pytest.mark.parametrize(
    ("flags", "sizes", "availability"),
    [
        ({"outOfStock": True}, [{"label": "M", "available": True}], Availability.OUT_OF_STOCK),
        ({"outOfStock": False}, [{"label": "M", "available": False}], Availability.OUT_OF_STOCK),
        ({"outOfStock": False}, [{"label": "S", "available": False}, {"label": "M", "available": True}],
         Availability.IN_STOCK),
        ({"outOfStock": False}, [], Availability.IN_STOCK),
        ({}, [], Availability.UNKNOWN),
    ],
)  # fmt: skip
def test_in_stock_means_at_least_one_size_can_be_bought(
    flags: dict[str, object], sizes: list[dict[str, object]], availability: Availability
) -> None:
    page = parse_product_page(_pdp(flags, sizes))

    assert page is not None
    assert page.availability is availability


def test_a_page_without_product_data_is_not_a_product_page() -> None:
    assert parse_product_page("<html>Oops! Something went wrong</html>") is None
