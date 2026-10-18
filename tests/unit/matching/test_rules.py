import pytest

from app.domain.models import Category, Fingerprint, Gender, Listing, Platform
from app.matching.rules import assess

PHONE = Fingerprint(
    category=Category.SMARTPHONE,
    brand="samsung",
    model="galaxy s24 fe",
    ram_gb=8,
    storage_gb=128,
    colour="Graphite",
)


def _candidate(title: str = "Samsung Galaxy S24 FE 5G", **fingerprint: object) -> Listing:
    return Listing(
        platform=Platform.FLIPKART,
        listing_id="X1",
        url="https://www.flipkart.com/p/x?pid=X1",
        title=title,
        fingerprint=Fingerprint.model_validate(fingerprint),
    )


def _phone(**changes: object) -> Listing:
    return _candidate(**{**PHONE.model_dump(), **changes})


def test_a_candidate_agreeing_on_every_must_match_attribute_is_confirmed_by_model_name() -> None:
    assessment = assess(PHONE, _phone(colour="Blue"), final=True)

    assert assessment.confirmed
    assert assessment.identity == "model name"


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"storage_gb": 256}, "256 GB storage, not 128 GB"),
        ({"ram_gb": 12}, "12 GB RAM, not 8 GB"),
        ({"model": "galaxy s24 plus"}, "galaxy s24 plus"),
        ({"brand": "oneplus"}, "oneplus"),
        ({"category": Category.TELEVISION}, "not a smartphone"),
        ({"category": None}, "not a smartphone"),
    ],
)
def test_a_conflicting_attribute_rejects_the_candidate_with_a_reason(
    changes: dict[str, object], reason: str
) -> None:
    assessment = assess(PHONE, _phone(**changes), final=False)

    assert not assessment.passed
    assert reason in assessment.mismatches[0]


def test_attributes_the_tile_does_not_show_yet_are_unconfirmed_not_matched() -> None:
    tile = _candidate(category=Category.SMARTPHONE, brand="samsung", model="galaxy s24 fe", ram_gb=8)

    assessment = assess(PHONE, tile, final=False)

    assert assessment.passed
    assert not assessment.confirmed
    assert assessment.unconfirmed == ("storage",)


@pytest.mark.parametrize(
    "title", ["Samsung Galaxy S24 FE (Refurbished)", "Samsung Galaxy S24 FE Renewed", "Combo pack of 2"]
)
def test_refurbished_and_multi_pack_listings_are_excluded(title: str) -> None:
    assert not assess(PHONE, _candidate(title, **PHONE.model_dump()), final=False).passed


TV = Fingerprint(
    category=Category.TELEVISION, brand="lg", model="nu87 nano 2026", model_number="43NU870BPLA", screen_in=43
)


def test_for_tvs_the_model_number_decides_even_when_titles_differ() -> None:
    same = assess(
        TV,
        _candidate(
            category=Category.TELEVISION, brand="lg", model="2026", model_number="43NU870BPLA", screen_in=43
        ),
        final=True,
    )
    other = assess(
        TV,
        _candidate(
            category=Category.TELEVISION,
            brand="lg",
            model="nu87 nano 2026",
            model_number="43NU875BPLA",
            screen_in=43,
        ),
        final=True,
    )

    assert same.confirmed
    assert same.identity == "model number"
    assert not other.passed
    assert "43NU875BPLA" in other.mismatches[0]


@pytest.mark.parametrize(("inches", "passes"), [(42.5, True), (43.3, True), (50, False)])
def test_screen_sizes_match_within_half_an_inch(inches: float, passes: bool) -> None:
    candidate = _candidate(
        category=Category.TELEVISION, brand="lg", model_number="43NU870BPLA", screen_in=inches
    )

    assert assess(TV, candidate, final=True).passed is passes


SNEAKER = Fingerprint(
    category=Category.SNEAKER,
    brand="nike",
    model="court vision low next nature",
    model_number="DH2987-100",
    colour="White",
    colour_families=("white",),
    gender=Gender.MEN,
)


def _shoe(**changes: object) -> Listing:
    return _candidate("NIKE COURT VISION LO NN Sneakers For Men", **{**SNEAKER.model_dump(), **changes})


def test_a_fashion_tile_without_a_style_code_waits_for_its_product_page() -> None:
    assessment = assess(SNEAKER, _shoe(model_number=None, model="court vision low"), final=False)

    assert assessment.passed
    assert assessment.unconfirmed == ("style code",)


def test_a_different_style_code_rejects_a_fashion_candidate() -> None:
    assessment = assess(SNEAKER, _shoe(model_number="DH2987-001"), final=True)

    assert assessment.mismatches == ("has style code DH2987-001, not DH2987-100",)


@pytest.mark.parametrize(
    ("changes", "passes"),
    [
        ({"colour": "Black", "colour_families": ("black",)}, False),
        ({"colour": "White/Blue", "colour_families": ("blue", "white")}, False),
        ({"gender": Gender.WOMEN}, False),
        ({"gender": Gender.UNISEX}, True),
        ({"colour": "White/White-White"}, True),
    ],
)
def test_without_a_style_code_fashion_must_agree_on_colour_and_who_it_is_for(
    changes: dict[str, object], passes: bool
) -> None:
    assert assess(SNEAKER, _shoe(model_number=None, **changes), final=True).confirmed is passes


def test_without_style_codes_a_fashion_name_must_match_word_for_word() -> None:
    assessment = assess(SNEAKER, _shoe(model_number=None, model="court vision low next nature"), final=True)

    assert assessment.confirmed
    assert assessment.identity == "model name"


@pytest.mark.parametrize("model", ["court vision low", "court vision low next nature premium"])
def test_without_style_codes_a_shorter_or_longer_fashion_name_is_unconfirmed(model: str) -> None:
    # "Air Force 1" may or may not be the "Air Force 1 Shadow": only a style code could tell.
    assessment = assess(SNEAKER, _shoe(model_number=None, model=model), final=True)

    assert assessment.passed
    assert not assessment.confirmed
    assert assessment.unconfirmed == (f"model (it's named “{model}”, not “court vision low next nature”)",)


def test_without_style_codes_a_different_fashion_name_is_a_mismatch() -> None:
    assessment = assess(SNEAKER, _shoe(model_number=None, model="court vision low perforations"), final=True)

    assert assessment.mismatches == (
        "is the court vision low perforations, not the court vision low next nature",
    )


def test_phone_names_may_leave_out_words_that_do_not_distinguish_models() -> None:
    assert assess(PHONE, _phone(model="s24 fe"), final=True).confirmed


def test_a_shop_naming_fewer_colours_leaves_the_colour_unconfirmed() -> None:
    # Flipkart calls PUMA's "White-Matte Silver" just "White".
    source = SNEAKER.model_copy(
        update={"colour": "White-Matte Silver", "colour_families": ("silver", "white")}
    )

    assessment = assess(source, _shoe(model_number=None), final=False)

    assert assessment.passed
    assert "colour" in assessment.unconfirmed


def test_an_identical_style_code_settles_the_colour() -> None:
    source = SNEAKER.model_copy(
        update={"colour": "White-Matte Silver", "colour_families": ("silver", "white")}
    )

    assert assess(source, _shoe(), final=True).confirmed


def test_a_style_code_without_its_colour_suffix_still_needs_the_colour_to_agree() -> None:
    polo = Fingerprint(
        category=Category.TSHIRT,
        brand="puma",
        model_number="687093",
        colour="Black",
        colour_families=("black",),
    )
    navy = _candidate(
        "PUMA Polo", category=Category.TSHIRT, brand="puma", model_number="68709302", colour="Navy",
        colour_families=("blue",),
    )  # fmt: skip

    assert not assess(polo, navy, final=True).passed


def test_a_t_shirt_is_never_identified_by_name_alone() -> None:
    # "Puma Cotton Polo Slim Fit T-shirt" names a hundred shirts; only a style code tells them apart.
    polo = Fingerprint(
        category=Category.TSHIRT, brand="puma", model="cotton slim fit", model_number="687093",
        colour="Black", colour_families=("black",), gender=Gender.MEN,
    )  # fmt: skip
    lookalike = _candidate("Puma Cotton Polo Slim Fit T-shirt", **{**polo.model_dump(), "model_number": None})

    assessment = assess(polo, lookalike, final=True)

    assert assessment.passed
    assert assessment.unconfirmed == ("style code",)
