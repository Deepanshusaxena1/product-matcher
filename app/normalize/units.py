"""Sizes and prices: memory in GB, screen diagonals in inches, prices in rupees."""

from __future__ import annotations

import re

_GB_PER_TB = 1024
_CM_PER_INCH = 2.54
_SMALLEST_STORAGE_GB = 32  # a lone size this big in a phone title is its storage, never its RAM

_SIZE = re.compile(r"(\d+(?:\.\d+)?)\s*(gb|tb)\b", re.IGNORECASE)
_RAM = re.compile(r"(\d{1,2})\s*(gb)\s*ram\b", re.IGNORECASE)
_STORAGE = re.compile(r"(\d{1,4})\s*(gb|tb)\s*(?:rom|storage|internal)\b", re.IGNORECASE)
# "8GB+128GB", "8 GB + 256 GB", "12/256 GB": RAM first, then storage.
_RAM_STORAGE_PAIR = re.compile(r"\b(\d{1,2})\s*(?:gb)?\s*[+/]\s*(\d{1,4})\s*(gb|tb)\b", re.IGNORECASE)

_INCHES = re.compile(r"(\d{1,3}(?:\.\d+)?)\s*(?:-\s*)?(?:inch(?:es)?\b|\"|”|″)", re.IGNORECASE)
_CENTIMETRES = re.compile(r"(\d{2,3}(?:\.\d+)?)\s*cms?\b", re.IGNORECASE)

_RUPEES = re.compile(r"\d[\d,]*(?:\.\d+)?")


def parse_gb(text: str) -> int | None:
    """The first memory size in `text`, in whole gigabytes ("1 TB" is 1024)."""
    return _gigabytes(_SIZE.search(text))


def parse_ram_storage(text: str) -> tuple[int | None, int | None]:
    """RAM and storage in GB, from a title or spec line such as "(Graphite, 8GB RAM, 128GB Storage)"."""
    ram = _gigabytes(_RAM.search(text))
    storage = _gigabytes(_STORAGE.search(text))

    if ram is None or storage is None:
        pair = _RAM_STORAGE_PAIR.search(text)
        if pair:
            ram = ram if ram is not None else int(pair.group(1))
            storage = storage if storage is not None else _to_gb(pair.group(2), pair.group(3))

    if storage is None:
        # One unlabelled size besides the RAM, as in "(Black, 8GB RAM, 256 GB)" or "(128 GB)".
        sizes = [_gigabytes(match) for match in _SIZE.finditer(_RAM.sub(" ", text))]
        if len(sizes) == 1 and sizes[0] is not None and sizes[0] >= _SMALLEST_STORAGE_GB:
            storage = sizes[0]
    return ram, storage


def parse_screen_inches(text: str) -> float | None:
    """The screen diagonal in inches.

    Stated inches win ("108 cm (43 inch)" is 43). A size given only in centimetres is converted but not
    rounded to a marketing size: "80 cm" TVs are sold as 32", so comparisons need a tolerance.
    """
    inches = _INCHES.search(text)
    if inches:
        return float(inches.group(1))
    centimetres = _CENTIMETRES.search(text)
    if centimetres:
        return round(float(centimetres.group(1)) / _CM_PER_INCH, 1)
    return None


def parse_inr(text: str) -> float | None:
    """A rupee amount such as "₹39,999.00" or "Rs. 1,23,456" (Indian digit grouping)."""
    match = _RUPEES.search(text)
    return float(match.group(0).replace(",", "")) if match else None


def _gigabytes(match: re.Match[str] | None) -> int | None:
    return _to_gb(match.group(1), match.group(2)) if match else None


def _to_gb(amount: str, unit: str) -> int | None:
    value = float(amount) * (_GB_PER_TB if unit.lower() == "tb" else 1)
    return int(value) if value > 0 and value.is_integer() else None
