"""Turn the fields of an Amazon page into a product fingerprint.

Structured spec rows are trusted first, then the selected variant, then the title.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from app.normalize.category import category_from_breadcrumbs, category_from_type_name
from app.normalize.facts import FASHION, ListingFacts, fingerprint_from_facts
from app.normalize.model import model_numbers_match, normalize_model_number

if TYPE_CHECKING:
    from app.domain.models import Category, Fingerprint
    from app.sources.amazon.page import AmazonPage

# Nike and Jordan style codes ("DH2987-100") name the exact colourway.
_STYLE_CODE = re.compile(r"\b[A-Z]{2}\d{4}-\d{3}\b")
_CODE_LIKE = re.compile(r"\b[A-Z0-9][A-Z0-9-]{5,}\b")
_SHORTEST_STYLE_CODE = 6  # adidas "GW9250", PUMA "687093", Nike "DH2987100"


def fingerprint_from(page: AmazonPage) -> Fingerprint:
    category = _category(page)
    return fingerprint_from_facts(
        ListingFacts(
            category=category,
            title=page.title,
            brand=page.spec("Brand", "Brand Name") or page.brand,
            # "Model Series" is deliberately not used: it can be coarser than the title ("Galaxy S").
            model_name=page.spec("Model Name"),
            model_number=_model_number(page, category),
            ram=page.spec("RAM Memory Installed Size", "RAM Memory Installed", "RAM", "RAM Size"),
            storage=page.spec("Memory Storage Capacity", "Internal Storage", "ROM", "Storage"),
            screen=page.spec("Screen Size", "Display Size Class", "Screen Size Unit of Measure", "Size"),
            variant=" ".join(page.variation.values()) or None,
            colour=page.variation.get("color_name") or page.spec("Colour", "Color"),
            gender=page.spec("Department") or " ".join(page.breadcrumbs),
        )
    )


def _category(page: AmazonPage) -> Category | None:
    return category_from_breadcrumbs(page.breadcrumbs) or category_from_type_name(
        page.spec("Item Type Name", "Generic Name", "Product Type") or ""
    )


def _model_number(page: AmazonPage, category: Category | None) -> str | None:
    texts = (page.description, page.document_title, page.title)
    if category in FASHION:
        style_code = next((match.group(0) for text in texts if (match := _STYLE_CODE.search(text))), None)
        if style_code:
            return style_code

    labels = ("Model Number", "Item model number", "Manufacturer Part Number", "Item Part Number", "Model")
    if category in FASHION:
        # A style code names one colourway; a short internal code ("LIT50") cannot, so the next one is tried.
        listed = next(
            (code for label in labels if (code := page.spec(label)) and _could_be_style_code(code)), None
        )
    else:
        listed = page.spec(*labels)
    if listed:
        # Prefer a longer code that extends it, e.g. PUMA's style "687093" -> "68709301" (style + colour).
        for text in texts:
            for match in _CODE_LIKE.finditer(text):
                code = match.group(0)
                if len(code) > len(listed) and model_numbers_match(listed, code):
                    return code
    return listed


def _could_be_style_code(code: str) -> bool:
    normalized = normalize_model_number(code)
    return len(normalized) >= _SHORTEST_STYLE_CODE and any(char.isdigit() for char in normalized)
