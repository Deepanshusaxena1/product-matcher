"""Read an Amazon.in product page into plain fields, without interpreting them.

Amazon lays product pages out in several ways (standard, premium-brand and fashion layouts), so every
field has a list of places to look and every one of them is optional. Turning these fields into a
fingerprint is `fingerprint.py`'s job.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from selectolax.lexbor import LexborHTMLParser

from app.domain.models import Availability
from app.normalize.facts import first_spec
from app.normalize.units import parse_inr

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping

    from selectolax.lexbor import LexborNode

_BRAND_SELECTORS = (
    "#bylineInfo",
    "#productBrandLogo_feature_div .premium-brand-visit-store-link a",
    ".offer-display-feature-text-message a[href^='/premium/']",  # premium layout without a store link
)
# The price to pay, never the struck-through M.R.P. (`.a-text-price`). Its hidden text is sometimes empty,
# so the visible whole-rupee figure is the fallback.
_PRICE_SELECTORS = (
    ".apex-pricetopay-value .a-offscreen",
    ".priceToPay .a-offscreen",
    ".apex-pricetopay-value .a-price-whole",
    "#corePriceDisplay_desktop_feature_div .a-price:not(.a-text-price) .a-offscreen",
    "#corePrice_feature_div .a-price:not(.a-text-price) .a-offscreen",
)
_DESCRIPTION_SELECTORS = ("#trailProductDescription_feature_div", "#productDescription")
_TWISTER_VALUE = re.compile(r"^inline-twister-expanded-dimension-text-(\w+)$")
_DIRECTION_MARKS = str.maketrans("", "", "‎‏")

_IN_STOCK = re.compile(r"\bin stock\b", re.IGNORECASE)
_OUT_OF_STOCK = re.compile(r"currently unavailable|out of stock", re.IGNORECASE)
_ROBOT_CHECK = re.compile(r"/errors/validateCaptcha|Enter the characters you see below", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class AmazonPage:
    title: str
    brand: str | None = None  # as shown, e.g. "Visit the Samsung Store"
    breadcrumbs: tuple[str, ...] = ()
    specs: Mapping[str, str] = field(default_factory=dict)  # label -> value, first occurrence wins
    variation: Mapping[str, str] = field(default_factory=dict)  # selected variant, e.g. color_name -> White
    bullets: tuple[str, ...] = ()
    description: str = ""
    document_title: str = ""  # the <title>, which sometimes carries a style code the body omits
    price_inr: float | None = None
    availability: Availability = Availability.UNKNOWN
    image_url: str | None = None

    def spec(self, *labels: str) -> str | None:
        """The value of the first of `labels` present in the spec tables (case-insensitive)."""
        return first_spec(self.specs, *labels)


def is_robot_check(html: str) -> bool:
    """Amazon's captcha page, served with status 200 instead of the product."""
    return bool(_ROBOT_CHECK.search(html)) and "productTitle" not in html


def parse_amazon_page(html: str) -> AmazonPage | None:
    """The page's fields, or `None` when it is not a product page."""
    tree = LexborHTMLParser(html)
    title = _text(tree.css_first("#productTitle"))
    if not title:
        return None

    return AmazonPage(
        title=title,
        brand=_first_text(tree, _BRAND_SELECTORS),
        breadcrumbs=tuple(
            crumb for node in tree.css("#wayfinding-breadcrumbs_feature_div a") if (crumb := _text(node))
        ),
        specs=dict(_first_wins(_spec_rows(tree))),
        variation=_variation(tree),
        bullets=tuple(bullet for node in tree.css("#feature-bullets li") if (bullet := _text(node))),
        description=" ".join(filter(None, (_text(tree.css_first(s)) for s in _DESCRIPTION_SELECTORS))),
        document_title=_text(tree.css_first("title")),
        price_inr=_price(tree),
        availability=_availability(_text(tree.css_first("#availability"))),
        image_url=_image_url(tree.css_first("#landingImage")),
    )


def _spec_rows(tree: LexborHTMLParser) -> Iterator[tuple[str, str]]:
    # The "at a glance" table under the title: two cells per row.
    for row in tree.css("#productOverview_feature_div tr"):
        cells = row.css("td")
        if len(cells) >= 2:
            yield _text(cells[0]), _text(cells[1])
    # Technical details: label in <th>, value in <td>, spread over several tables (in a side sheet on the
    # newer layout).
    for row in tree.css("#prodDetails tr, #voyager-ns-desktop-side-sheet-main-section tr"):
        label, value = row.css_first("th"), row.css_first("td")
        if label is not None and value is not None:
            yield _text(label), _text(value)
    # Fashion layout: "Item model number : 687093" as a bold label and a value span.
    for item in tree.css("#detailBullets_feature_div li"):
        spans = item.css("span.a-list-item > span")
        if len(spans) >= 2:
            yield _text(spans[0]).rstrip(" :"), _text(spans[1])


def _first_wins(rows: Iterator[tuple[str, str]]) -> Iterator[tuple[str, str]]:
    seen: set[str] = set()
    for label, value in rows:
        if label and value and label.casefold() not in seen:
            seen.add(label.casefold())
            yield label, value


def _variation(tree: LexborHTMLParser) -> dict[str, str]:
    selected: dict[str, str] = {}
    for node in tree.css("[id^='inline-twister-expanded-dimension-text-']"):
        match = _TWISTER_VALUE.match(node.attributes.get("id") or "")
        if match and (value := _text(node)):
            selected[match.group(1)] = value
    return selected


def _price(tree: LexborHTMLParser) -> float | None:
    price = _first_text(tree, _PRICE_SELECTORS)
    return parse_inr(price) if price else None


def _availability(message: str) -> Availability:
    if _OUT_OF_STOCK.search(message):
        return Availability.OUT_OF_STOCK
    if _IN_STOCK.search(message):
        return Availability.IN_STOCK
    return Availability.UNKNOWN


def _image_url(node: LexborNode | None) -> str | None:
    if node is None:
        return None
    url = node.attributes.get("data-old-hires") or node.attributes.get("src")
    return url if url and url.startswith("https://") else None


def _first_text(tree: LexborHTMLParser, selectors: tuple[str, ...]) -> str | None:
    return next(
        (text for selector in selectors for node in tree.css(selector) if (text := _text(node))), None
    )


def _text(node: LexborNode | None) -> str:
    if node is None:
        return ""
    return " ".join(node.text(separator=" ").translate(_DIRECTION_MARKS).split())
