"""Vocabulary shared by Croma's search results and product pages."""

from __future__ import annotations

import re
from typing import Any

from app.domain.models import Category

BASE_URL = "https://www.croma.com"
API_URL = "https://api.croma.com"
# Croma's API answers only requests that look like they come from its own site.
SITE_HEADERS = {"origin": BASE_URL, "referer": f"{BASE_URL}/", "accept": "application/json"}

# Croma's leaf category names: "Android Phones", "iPhones", "Flip and Fold Mobile Phones", "4K Ultra HD TVs".
_CATEGORY_NAMES: tuple[tuple[Category, re.Pattern[str]], ...] = (
    (Category.SMARTPHONE, re.compile(r"phones?$", re.IGNORECASE)),
    (Category.TELEVISION, re.compile(r"\btvs?$|televisions?$", re.IGNORECASE)),
)
_NOT_SMART = re.compile(r"\b(?:keypad|feature|basic|landline|cordless)\b", re.IGNORECASE)


def category_from_name(name: Any) -> Category | None:
    if not isinstance(name, str) or _NOT_SMART.search(name):
        return None
    return next((category for category, pattern in _CATEGORY_NAMES if pattern.search(name.strip())), None)


def absolute_url(path: Any) -> str | None:
    return BASE_URL + path if isinstance(path, str) and path.startswith("/") else None
