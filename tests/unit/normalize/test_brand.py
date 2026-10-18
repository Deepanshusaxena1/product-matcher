import pytest

from app.normalize.brand import brand_words, normalize_brand


@pytest.mark.parametrize(
    ("raw", "brand"),
    [
        ("Samsung", "samsung"),
        ("Visit the Samsung Store", "samsung"),
        ("Visit the PUMA Store", "puma"),
        ("Brand: Nike", "nike"),
        ("LG Electronics", "lg"),
        ("One Plus", "oneplus"),
        ("ONEPLUS", "oneplus"),
        ("Redmi", "xiaomi"),
        ("Mi", "xiaomi"),
        ("U.S. POLO ASSN.", "us polo assn"),
        ("US Polo Assn", "us polo assn"),
        ("  Apple  ", "apple"),
    ],
)
def test_brands_are_reduced_to_one_canonical_name(raw: str, brand: str) -> None:
    assert normalize_brand(raw) == brand


@pytest.mark.parametrize("raw", ["", "   ", "Visit the  Store", "Generic"])
def test_missing_or_placeholder_brands_are_unknown(raw: str) -> None:
    assert normalize_brand(raw) is None


def test_brand_words_cover_every_spelling_that_names_the_brand_itself() -> None:
    assert {"lg", "electronics"} <= brand_words("lg")
    assert {"xiaomi", "mi"} <= brand_words("xiaomi")


def test_sub_brands_are_not_brand_words_because_they_name_a_product_line() -> None:
    # "Redmi Note 13" and "Poco X6" stay distinguishable even though both are made by Xiaomi.
    assert "redmi" not in brand_words("xiaomi")
    assert "poco" not in brand_words("xiaomi")
