"""Parse whatever the user pasted into an Amazon.in product link.

This is also the server's guard against being pointed at arbitrary hosts: only Amazon.in product pages and
Amazon's own short-link hosts are ever fetched, and URLs are rebuilt from their parsed parts (dropping
credentials, ports and tracking parameters) rather than fetched as given.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlsplit

from app.domain.errors import InvalidProductUrlError

_PRODUCT_HOSTS = frozenset({"amazon.in", "www.amazon.in", "m.amazon.in"})
_SHORT_LINK_HOSTS = frozenset({"amzn.in", "amzn.to", "a.co"})

_ASIN_IN_PATH = re.compile(
    r"/(?:dp|gp/product|gp/aw/d|exec/obidos/asin)/([a-z0-9]{10})(?=[/?#]|$)", re.IGNORECASE
)
_ASIN = re.compile(r"[A-Z0-9]{10}")
_HTTP_URL_IN_TEXT = re.compile(r"https?://\S+", re.IGNORECASE)
_TRAILING_PUNCTUATION = ".,;:!)]}>'\""

_NOT_AMAZON = "Please paste an Amazon.in product link (amazon.in/... or an amzn.in short link)."
_NOT_A_PRODUCT = "That Amazon.in link doesn't point to a product page. Open the product and copy its link."


@dataclass(frozen=True, slots=True)
class AmazonLink:
    """A validated link: a product page (ASIN known) or a short link still to be resolved."""

    fetch_url: str  # the only URL the server will request for this link
    asin: str | None = None

    @classmethod
    def product(cls, asin: str) -> AmazonLink:
        return cls(fetch_url=f"https://www.amazon.in/dp/{asin}", asin=asin)

    @property
    def is_short_link(self) -> bool:
        return self.asin is None


def parse_amazon_link(pasted: str) -> AmazonLink:
    """Parse a pasted link (possibly surrounded by share text) or raise `InvalidProductUrlError`."""
    parts = urlsplit(_extract_url(pasted))
    host = (parts.hostname or "").lower()

    if parts.scheme.lower() not in {"http", "https"}:
        raise InvalidProductUrlError(_NOT_AMAZON)

    if host in _SHORT_LINK_HOSTS:
        if parts.path.strip("/") == "":
            raise InvalidProductUrlError(_NOT_AMAZON)
        return AmazonLink(fetch_url=f"https://{host}{parts.path}")

    if host not in _PRODUCT_HOSTS:
        raise InvalidProductUrlError(_NOT_AMAZON)

    asin = _asin_from(parts.path, parts.query)
    if asin is None:
        raise InvalidProductUrlError(_NOT_A_PRODUCT)
    return AmazonLink.product(asin)


def _extract_url(pasted: str) -> str:
    text = pasted.strip()
    match = _HTTP_URL_IN_TEXT.search(text)
    if match:
        candidate = match.group(0)
    else:
        # Links copied without a scheme, e.g. "www.amazon.in/dp/...", possibly inside share text.
        candidate = next((token for token in text.split() if "/" in token), text)
        if "://" not in candidate:
            candidate = f"https://{candidate}"
    return candidate.rstrip(_TRAILING_PUNCTUATION)


def _asin_from(path: str, query: str) -> str | None:
    match = _ASIN_IN_PATH.search(path)
    if match:
        return match.group(1).upper()
    for value in parse_qs(query).get("asin", []):
        if _ASIN.fullmatch(value.upper()):
            return value.upper()
    return None
