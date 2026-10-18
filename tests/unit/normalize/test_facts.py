import pytest

from app.domain.models import Category, Fingerprint, Gender
from app.normalize.facts import ListingFacts, fingerprint_from_facts, first_spec


def test_a_phone_reads_ram_and_storage_from_its_spec_text() -> None:
    facts = ListingFacts(
        category=Category.SMARTPHONE,
        title="Samsung Galaxy S24 FE 5G (Graphite, 128 GB)",
        brand="Samsung",
        model_name="Galaxy S24 FE 5G",
        ram="8 GB",
        storage="128 GB",
        colour="Graphite",
    )

    assert fingerprint_from_facts(facts) == Fingerprint(
        category=Category.SMARTPHONE,
        brand="samsung",
        model="galaxy s24 fe",
        ram_gb=8,
        storage_gb=128,
        colour="Graphite",
        colour_families=("grey",),
    )


def test_the_title_fills_in_missing_attributes() -> None:
    facts = ListingFacts(
        category=Category.SMARTPHONE, title="Apple iPhone 15 Plus (Black, 8GB RAM, 256 GB)", brand="Apple"
    )

    fingerprint = fingerprint_from_facts(facts)

    assert (fingerprint.model, fingerprint.ram_gb, fingerprint.storage_gb) == ("iphone 15 plus", 8, 256)


def test_a_model_name_that_is_really_a_model_number_is_used_as_one() -> None:
    facts = ListingFacts(
        category=Category.TELEVISION,
        title="LG 108 cm (43 inch) Ultra HD (4K) LED Smart WebOS TV 2026 Edition",
        brand="LG",
        model_name="43NU870BPLA",
        screen="108 cm (43 inch)",
    )

    fingerprint = fingerprint_from_facts(facts)

    assert fingerprint.model_number == "43NU870BPLA"
    assert fingerprint.model == "2026"
    assert fingerprint.screen_in == 43


def test_a_model_name_repeating_the_model_number_gives_way_to_the_title() -> None:
    facts = ListingFacts(
        category=Category.TELEVISION,
        title="LG NU87 Nano TV",
        brand="LG",
        model_name="43NU870BPLA",
        model_number="43NU870BPLA",
    )

    assert fingerprint_from_facts(facts).model == "nu87 nano"


def test_the_model_number_is_not_repeated_inside_the_model_name() -> None:
    facts = ListingFacts(
        category=Category.TELEVISION,
        title="LG NU87 Nano TV 43NU870BPLA",
        brand="LG",
        model_number="43NU870BPLA",
    )

    assert fingerprint_from_facts(facts).model == "nu87 nano"


def test_attributes_of_other_categories_are_ignored() -> None:
    facts = ListingFacts(
        category=Category.TELEVISION, title="LG TV", ram="1.5 GB", storage="8 GB", gender="Men"
    )

    fingerprint = fingerprint_from_facts(facts)

    assert (fingerprint.ram_gb, fingerprint.storage_gb, fingerprint.gender) == (None, None, None)


def test_fashion_reads_gender_from_the_hint_or_the_title() -> None:
    hinted = ListingFacts(category=Category.TSHIRT, title="PUMA Solid Polo", gender="Men")
    titled = ListingFacts(category=Category.SNEAKER, title="NIKE Court Vision Low Sneakers For Women")

    assert fingerprint_from_facts(hinted).gender is Gender.MEN
    assert fingerprint_from_facts(titled).gender is Gender.WOMEN


@pytest.mark.parametrize(
    ("labels", "value"),
    [(("RAM",), "8 GB"), (("ram",), "8 GB"), (("Memory", "Internal Storage"), "128 GB"), (("Colour",), None)],
)
def test_specs_are_looked_up_case_insensitively_in_label_order(
    labels: tuple[str, ...], value: str | None
) -> None:
    specs = {"RAM": "8 GB", "Internal Storage": "128 GB"}

    assert first_spec(specs, *labels) == value


def test_stray_punctuation_around_a_colour_is_dropped() -> None:
    facts = ListingFacts(category=Category.TSHIRT, title="PUMA Polo", colour=" Black. ")

    assert fingerprint_from_facts(facts).colour == "Black"


def test_a_fashion_title_ends_its_name_at_the_product_word_and_gives_up_its_colour() -> None:
    facts = ListingFacts(
        category=Category.SNEAKER,
        title="adidas Men Grand Court Base 2.0 Sportswear Shoes White 9",
        brand="adidas",
    )

    fingerprint = fingerprint_from_facts(facts)

    assert fingerprint.model == "grand court base 2.0"
    assert (fingerprint.colour, fingerprint.colour_families) == ("White", ("white",))


def test_a_stated_colour_wins_over_the_title() -> None:
    facts = ListingFacts(
        category=Category.SNEAKER, title="Nike Court Vision Low Sneakers Black", brand="Nike", colour="White"
    )

    assert fingerprint_from_facts(facts).colour == "White"


def test_colour_words_are_not_part_of_a_fashion_model() -> None:
    facts = ListingFacts(
        category=Category.SNEAKER, title="ADIDAS Men White Grand Court 2.0 Sneakers", brand="ADIDAS"
    )

    assert fingerprint_from_facts(facts).model == "grand court 2.0"


def test_phone_models_keep_every_word() -> None:
    # Only fashion titles end at a product word; a phone's title keeps what follows one.
    facts = ListingFacts(category=Category.SMARTPHONE, title="Apple iPhone 15 Pro Shoes Max", brand="Apple")

    assert fingerprint_from_facts(facts).model == "iphone 15 pro max"


def test_a_coded_colour_gives_way_to_a_plain_colour_in_the_title() -> None:
    # adidas states colours as codes: "FTWWHT/PRERUB/BETSCA" is Footwear White / Preloved Ruby / ...
    facts = ListingFacts(
        category=Category.SNEAKER,
        title="adidas Men Grand Court Base 2.0 Sportswear Shoes White 9",
        brand="adidas",
        colour="FTWWHT/PRERUB/BETSCA",
    )

    assert fingerprint_from_facts(facts).colour == "White"
