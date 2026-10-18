from app.domain.models import Category, Fingerprint, Gender
from app.matching.query import search_queries


def test_a_phone_is_searched_by_brand_and_model() -> None:
    fingerprint = Fingerprint(category=Category.SMARTPHONE, brand="samsung", model="galaxy s24 fe", ram_gb=8)

    assert search_queries(fingerprint) == ["samsung galaxy s24 fe"]


def test_a_tv_is_searched_by_model_number_first_then_by_model_and_size() -> None:
    fingerprint = Fingerprint(
        category=Category.TELEVISION,
        brand="lg",
        model="nu87 nano 2026",
        model_number="43NU870BPLA",
        screen_in=43,
    )

    assert search_queries(fingerprint) == ["lg 43NU870BPLA", "lg nu87 nano 2026 43 inch"]


def test_fashion_is_searched_by_style_code_first_then_by_description() -> None:
    fingerprint = Fingerprint(
        category=Category.SNEAKER,
        brand="nike",
        model="court vision low next nature",
        model_number="DH2987-100",
        colour="White",
        gender=Gender.MEN,
    )

    assert search_queries(fingerprint) == [
        "nike DH2987-100",
        "nike court vision low next nature white men sneakers",
        "nike court vision low next nature sneakers",  # shops' searches can trip over colour names
    ]


def test_unknown_parts_are_left_out_and_queries_are_not_repeated() -> None:
    fingerprint = Fingerprint(category=Category.TSHIRT, brand="puma")

    assert search_queries(fingerprint) == ["puma t-shirt"]


def test_a_shop_that_does_not_index_codes_is_searched_by_description_only() -> None:
    fingerprint = Fingerprint(
        category=Category.SNEAKER, brand="nike", model="court vision low", model_number="DH2987-100"
    )

    assert search_queries(fingerprint, by_code=False) == ["nike court vision low sneakers"]
