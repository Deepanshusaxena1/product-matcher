"""Build a fingerprint from the facts a shop shows, in the shop's own words.

Every shop reader collects the same handful of facts (title, brand, model name or number, sizes, colour,
who it is for) from wherever that shop keeps them, then calls `fingerprint_from_facts`. Only the
attributes that matter for the category are read: a TV's "8 GB" of app storage is not a phone's storage.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.domain.models import Category, Fingerprint
from app.normalize.brand import normalize_brand
from app.normalize.category import gender_from
from app.normalize.colour import BASIC_COLOUR_WORDS, colour_families
from app.normalize.model import model_numbers_match, normalize_model
from app.normalize.units import parse_gb, parse_ram_storage, parse_screen_inches

if TYPE_CHECKING:
    from collections.abc import Mapping

FASHION = frozenset({Category.SNEAKER, Category.TSHIRT})

# A single token mixing letters and digits, e.g. "43NU870BPLA": a model number, not a model name.
_CODE = re.compile(r"^(?=.*\d)(?=.*[A-Za-z])[A-Za-z0-9-]{6,}$")
# Fashion titles name the product, then the kind of product, then the variant: "... Base 2.0 Shoes White 9".
_FASHION_NOUN = re.compile(
    r"\b(?:sneakers?|shoes?|trainers?|t-?\s?shirts?|tees?|polos?|jerseys?)\b", re.IGNORECASE
)
_WORD = re.compile(r"[A-Za-z]+")


@dataclass(frozen=True, slots=True)
class ListingFacts:
    category: Category | None
    title: str
    brand: str | None = None
    model_name: str | None = None
    model_number: str | None = None
    ram: str | None = None
    storage: str | None = None
    screen: str | None = None
    variant: str | None = None  # the selected variant as shown, e.g. "8GB + 256GB"; read before the title
    colour: str | None = None
    gender: str | None = None


def fingerprint_from_facts(facts: ListingFacts) -> Fingerprint:
    brand = normalize_brand(facts.brand) if facts.brand else None
    model_name, model_number = facts.model_name, facts.model_number
    if model_name and _CODE.match(code := model_name.strip()):
        # A code in the name field ("43NU870BPLA") is a model number, never a model name.
        model_name, model_number = None, model_number or code
    fashion = facts.category in FASHION
    name, variant = _split_fashion_title(facts.title) if fashion else (facts.title, "")
    colour = _colour((facts.colour or "").strip(" .,;"), _colour_words(variant))
    ram_gb, storage_gb = _ram_storage(facts) if facts.category is Category.SMARTPHONE else (None, None)
    model = _model(model_name or name, brand, model_number)
    if fashion and model:  # a colour is its own attribute, not part of a shoe's or shirt's name
        model = " ".join(word for word in model.split() if word not in BASIC_COLOUR_WORDS) or None

    return Fingerprint(
        category=facts.category,
        brand=brand,
        model=model,
        model_number=model_number,
        ram_gb=ram_gb,
        storage_gb=storage_gb,
        screen_in=_screen(facts) if facts.category is Category.TELEVISION else None,
        colour=colour,
        colour_families=colour_families(colour) if colour else (),
        gender=gender_from(facts.gender or "", facts.title) if facts.category in FASHION else None,
    )


def first_spec(specs: Mapping[str, str], *labels: str) -> str | None:
    """The value of the first of `labels` present in `specs`, matching labels case-insensitively."""
    by_label = {label.casefold(): value for label, value in specs.items()}
    return next((by_label[label.casefold()] for label in labels if label.casefold() in by_label), None)


def _split_fashion_title(title: str) -> tuple[str, str]:
    """(name, variant): the title up to its last product word, and what follows it."""
    nouns = list(_FASHION_NOUN.finditer(title))
    if not nouns or not title[: nouns[0].start()].strip():
        return title, ""
    end = nouns[-1].end()
    return title[:end], title[end:]


def _colour(stated: str, in_title: str | None) -> str | None:
    """The stated colour, unless it is a code no one can read ("FTWWHT/PRERUB") and the title names one."""
    if stated and (colour_families(stated) or not in_title):
        return stated
    return in_title or stated or None


def _colour_words(text: str) -> str | None:
    """The colours named in a title's variant text: "White 9" -> "White"."""
    words = [word for word in _WORD.findall(text) if colour_families(word)]
    return "/".join(words) or None


def _model(source: str, brand: str | None, model_number: str | None) -> str | None:
    model = normalize_model(source, brand)
    if model_number:  # matched on its own; inside the name it would only add noise
        model = " ".join(word for word in model.split() if not model_numbers_match(word, model_number))
    return model or None


def _ram_storage(facts: ListingFacts) -> tuple[int | None, int | None]:
    ram = parse_gb(facts.ram) if facts.ram else None
    storage = parse_gb(facts.storage) if facts.storage else None
    if ram is None or storage is None:
        for text in filter(None, (facts.variant, facts.title)):
            found_ram, found_storage = parse_ram_storage(text)
            ram, storage = ram or found_ram, storage or found_storage
    return ram, storage


def _screen(facts: ListingFacts) -> float | None:
    texts = filter(None, (facts.screen, facts.variant, facts.title))
    return next((inches for text in texts if (inches := parse_screen_inches(text))), None)
