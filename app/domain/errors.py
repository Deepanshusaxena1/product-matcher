"""Failures a user should hear about, in plain words.

Each error carries a stable machine-readable `code`; how it maps to a transport (HTTP status, SSE event)
is decided by the API layer, not here.
"""

from typing import ClassVar


class MatcherError(Exception):
    code: ClassVar[str] = "matcher_error"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class InvalidProductUrlError(MatcherError):
    """The input is not an Amazon.in product link."""

    code = "invalid_product_url"


class UnsupportedCategoryError(MatcherError):
    """The Amazon product is outside the four supported categories."""

    code = "unsupported_category"


class ProductNotFoundError(MatcherError):
    """Amazon has no product page behind the link."""

    code = "product_not_found"


class SourceUnavailableError(MatcherError):
    """Amazon could not be read (blocked, timed out, or returned an unexpected page)."""

    code = "source_unavailable"
