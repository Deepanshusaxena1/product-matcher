"""Whether Croma can deliver a product to a pincode, from the delivery-promise API its own product pages use.

Croma's stock is regional, so the answer is always for one pincode. The API wants a subscription key that
Croma ships to every browser in its JavaScript bundle; it is read from there (once per process) unless one
is configured.
"""

from __future__ import annotations

import asyncio
import re
from typing import TYPE_CHECKING, Any

from app.domain.models import Availability
from app.domain.ports import FetchError, UnexpectedPageError
from app.platforms.croma.common import API_URL, BASE_URL, SITE_HEADERS
from app.platforms.embedded_json import dig

if TYPE_CHECKING:
    from app.domain.ports import PageFetcher

_PROMISE_URL = f"{API_URL}/inventory/oms/v2/details-pwa"
_BUNDLE = re.compile(r'<script[^>]+src="(/static/js/main\.[0-9a-f]+\.chunk\.js)"')
_KEY = re.compile(r'OMS_APIM_SUBSCRIPTION_KEY:"([0-9a-f]{16,64})"')
_NO_DELIVERY_DATE = "2500-01-01"  # "any date": the question is whether it can be delivered at all


class InventoryKey:
    """The subscription key for Croma's delivery-promise API."""

    def __init__(self, fetcher: PageFetcher, *, configured: str | None = None) -> None:
        self._fetcher = fetcher
        self._configured = configured
        self._discovered: str | None = None
        self._lock = asyncio.Lock()

    async def get(self) -> str:
        if self._configured:
            return self._configured
        async with self._lock:  # concurrent stock checks share one lookup
            if self._discovered is None:
                self._discovered = await self._discover()
            return self._discovered

    def forget(self) -> None:
        """Drop a discovered key (Croma may have rotated it); the next `get` looks it up again."""
        self._discovered = None

    async def _discover(self) -> str:
        home = await self._fetcher.get(f"{BASE_URL}/")
        bundle = _BUNDLE.search(home.text) if home.status_code == 200 else None
        if bundle is None:
            raise UnexpectedPageError("Croma's home page no longer links its main script")
        script = await self._fetcher.get(BASE_URL + bundle.group(1))
        key = _KEY.search(script.text) if script.status_code == 200 else None
        if key is None:
            raise UnexpectedPageError("Croma's main script no longer contains the stock-check key")
        return key.group(1)


class CromaStockChecker:
    def __init__(self, fetcher: PageFetcher, key: InventoryKey, *, pincode: str) -> None:
        self._fetcher = fetcher
        self._key = key
        self._pincode = pincode

    async def availability(self, item_id: str) -> Availability:
        headers = {**SITE_HEADERS, "oms-apim-subscription-key": await self._key.get()}
        try:
            response = await self._fetcher.post_json(
                _PROMISE_URL, promise_request(item_id, self._pincode), headers=headers
            )
        except FetchError:
            self._key.forget()
            raise
        if response.status_code != 200:
            raise UnexpectedPageError(
                f"Croma's stock check answered HTTP {response.status_code} for {item_id}"
            )
        try:
            return availability_from_promise(response.json())
        except ValueError as error:
            raise UnexpectedPageError(f"Croma's stock check for {item_id} was not JSON") from error


def promise_request(item_id: str, pincode: str) -> dict[str, Any]:
    """Ask whether `item_id` can reach `pincode` by home delivery (HDEL) or same-day delivery (SDEL)."""

    def line(line_id: str, fulfilment: str) -> dict[str, Any]:
        return {
            "fulfillmentType": fulfilment,
            "itemID": item_id,
            "lineId": line_id,
            "requiredQty": "1",
            "shipToAddress": {"zipCode": pincode},
            "extn": {"widerStoreFlag": "N"},
        }

    return {
        "promise": {
            "allocationRuleID": "SYSTEM",
            "checkInventory": "Y",
            "organizationCode": "CROMA",
            "sourcingClassification": "EC",
            "promiseLines": {
                "promiseLine": [{**line("1", "HDEL"), "reqEndDate": _NO_DELIVERY_DATE}, line("3", "SDEL")]
            },
        }
    }


def availability_from_promise(data: Any) -> Availability:
    """In stock when Croma promises any delivery; out of stock when it lists every line as unavailable."""
    option = dig(data, "promise", "suggestedOption")
    promised = dig(option, "option", "promiseLines", "promiseLine")
    if isinstance(promised, list) and promised:
        return Availability.IN_STOCK
    if isinstance(promised, list) and dig(option, "unavailableLines", "unavailableLine"):
        return Availability.OUT_OF_STOCK
    return Availability.UNKNOWN
