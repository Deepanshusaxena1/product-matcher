import json
from collections.abc import Callable

import pytest

from app.domain.models import Availability
from app.domain.ports import FetchError, UnexpectedPageError
from app.platforms.croma.inventory import CromaStockChecker, InventoryKey, availability_from_promise
from support.fakes import FakeFetcher, page

HOME = "https://www.croma.com/"
BUNDLE = "https://www.croma.com/static/js/main.e09bbe36.chunk.js"
INVENTORY = "POST https://api.croma.com/inventory/oms/v2/details-pwa"
HOME_PAGE = '<html><head><script src="/static/js/main.e09bbe36.chunk.js"></script></head></html>'
BUNDLE_JS = 'const c={PROGRAM_ID:"01ea",OMS_APIM_SUBSCRIPTION_KEY:"1131858141634e2abe2efb2b3a2a2a5d",X:1};'


@pytest.mark.parametrize(
    ("fixture", "availability"),
    [
        ("inventory_in_stock.json", Availability.IN_STOCK),
        ("inventory_out_of_stock.json", Availability.OUT_OF_STOCK),
    ],
)
def test_stock_is_read_from_the_delivery_promise(
    croma_file: Callable[[str], str], fixture: str, availability: Availability
) -> None:
    assert availability_from_promise(json.loads(croma_file(fixture))) is availability


def test_an_unrecognised_promise_is_unknown() -> None:
    assert availability_from_promise({"error": "upstream timeout"}) is Availability.UNKNOWN


async def test_the_key_is_found_in_cromas_own_script_and_remembered() -> None:
    fetcher = FakeFetcher({HOME: page(HOME_PAGE), BUNDLE: page(BUNDLE_JS)})
    key = InventoryKey(fetcher)

    assert await key.get() == "1131858141634e2abe2efb2b3a2a2a5d"
    assert await key.get() == "1131858141634e2abe2efb2b3a2a2a5d"
    assert [url for url, _ in fetcher.requests] == [HOME, BUNDLE]


async def test_a_configured_key_is_used_without_looking_it_up() -> None:
    fetcher = FakeFetcher({})

    assert await InventoryKey(fetcher, configured="abc123").get() == "abc123"
    assert fetcher.requests == []


async def test_a_script_without_the_key_is_unexpected() -> None:
    fetcher = FakeFetcher({HOME: page(HOME_PAGE), BUNDLE: page("const c={};")})

    with pytest.raises(UnexpectedPageError):
        await InventoryKey(fetcher).get()


async def test_the_stock_check_asks_for_delivery_to_the_pincode(croma_file: Callable[[str], str]) -> None:
    fetcher = FakeFetcher({INVENTORY: page(croma_file("inventory_in_stock.json"))})
    checker = CromaStockChecker(fetcher, InventoryKey(fetcher, configured="k1"), pincode="400001")

    assert await checker.availability("323496") is Availability.IN_STOCK

    [(_, payload)] = fetcher.posted
    lines = payload["promise"]["promiseLines"]["promiseLine"]
    assert {line["itemID"] for line in lines} == {"323496"}
    assert {line["shipToAddress"]["zipCode"] for line in lines} == {"400001"}
    assert fetcher.headers[INVENTORY]["oms-apim-subscription-key"] == "k1"


async def test_a_refused_stock_check_forgets_the_key_so_the_next_one_looks_it_up_again(
    croma_file: Callable[[str], str],
) -> None:
    responses: dict[str, object] = {
        HOME: page(HOME_PAGE),
        BUNDLE: page(BUNDLE_JS),
        INVENTORY: FetchError("refused with HTTP 401"),
    }
    fetcher = FakeFetcher(responses)  # type: ignore[arg-type]
    checker = CromaStockChecker(fetcher, InventoryKey(fetcher), pincode="400001")

    with pytest.raises(FetchError):
        await checker.availability("323496")
    responses[INVENTORY] = page(croma_file("inventory_out_of_stock.json"))

    assert await checker.availability("303849") is Availability.OUT_OF_STOCK
    assert [url for url, _ in fetcher.requests].count(HOME) == 2


async def test_a_stock_check_that_fails_on_the_server_is_unexpected() -> None:
    fetcher = FakeFetcher({INVENTORY: page("{}", status=400)})
    checker = CromaStockChecker(fetcher, InventoryKey(fetcher, configured="k1"), pincode="400001")

    with pytest.raises(UnexpectedPageError):
        await checker.availability("323496")
