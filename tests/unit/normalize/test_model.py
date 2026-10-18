import pytest

from app.normalize.model import model_numbers_match, normalize_model, normalize_model_number, same_model


@pytest.mark.parametrize(
    ("title", "brand", "model"),
    [
        (
            "Samsung Galaxy S24 FE 5G AI Smartphone (Graphite, 8GB RAM, 128GB Storage)",
            "samsung",
            "galaxy s24 fe",
        ),
        ("Samsung Galaxy S24FE", "samsung", "galaxy s24 fe"),
        ("Apple iPhone 15 Plus (128 GB) - Black", "apple", "iphone 15 plus"),
        ("Nike Mens Court Vision Lo NN Sneakers", "nike", "court vision low next nature"),
        ("NIKE Court Vision Low Next Nature Sneakers For Men", "nike", "court vision low next nature"),
        ("LG Electronics NU87 Series 2026", "lg", "nu87 2026"),
        ("LG 108 cms (43 inches) NU87 AI Series Nano 4K Ultra HD Smart webOS LED TV", "lg", "nu87 nano"),
        ("Samsung Galaxy S24 8GB 256GB", "samsung", "galaxy s24"),
        ("Samsung Galaxy S24+ 5G (Cobalt Violet, 256 GB)", "samsung", "galaxy s24 plus"),
        ("Redmi Note 13 5G (Arctic White, 8GB RAM, 256GB Storage)", "xiaomi", "redmi note 13"),
    ],
)
def test_model_names_drop_the_brand_the_variant_and_marketing_words(
    title: str, brand: str, model: str
) -> None:
    assert normalize_model(title, brand) == model


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("galaxy s24 fe", "galaxy s24 fe"),
        ("galaxy s24 fe", "s24 fe"),
        ("galaxy s24 fe", "galaxy s24fe"),
        ("court vision lo nn", "court vision low next nature"),  # Nike's own abbreviations
    ],
)
def test_the_same_model_written_differently_matches(a: str, b: str) -> None:
    assert same_model(a, b)


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("iphone 15", "iphone 15 plus"),
        ("iphone 15 pro", "iphone 15 pro max"),
        ("galaxy s24", "galaxy s24 fe"),
        ("galaxy s24", "galaxy s24+"),
        ("galaxy s24 fe", "galaxy s23 fe"),
        ("redmi note 13", "redmi note 13 pro"),
        ("galaxy s24", "galaxy a24"),
        ("", "galaxy s24"),
    ],
)
def test_models_that_differ_in_a_distinguishing_word_or_number_do_not_match(a: str, b: str) -> None:
    assert not same_model(a, b)


@pytest.mark.parametrize(
    ("raw", "normalised"),
    [
        ("43NU870BPLA", "43NU870BPLA"),
        ("dh2987-100", "DH2987100"),
        ("SM-S721B/DS", "SMS721B"),
        (" 687093 ", "687093"),
    ],
)
def test_model_numbers_keep_only_letters_and_digits(raw: str, normalised: str) -> None:
    assert normalize_model_number(raw) == normalised


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("43NU870BPLA", "43nu870bpla"),
        ("DH2987-100", "DH2987 100"),
        ("SM-S721B", "SM-S721BZKBINS"),  # regional SKU suffix
        ("687093", "68709301"),  # PUMA style code plus colour code
    ],
)
def test_model_numbers_match_when_equal_or_one_extends_the_other(a: str, b: str) -> None:
    assert model_numbers_match(a, b)


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("43NU870BPLA", "50NU870BPLA"),
        ("DH2987-100", "DH2987-101"),
        ("68709301", "68709302"),
        ("A15", "A155"),  # too short to trust a prefix
    ],
)
def test_different_model_numbers_do_not_match(a: str, b: str) -> None:
    assert not model_numbers_match(a, b)


def test_same_model_can_require_every_word_to_agree() -> None:
    assert same_model("court vision low", "court vision low next nature")
    assert not same_model("court vision low", "court vision low next nature", allow_missing_words=False)
    assert same_model("court vision lo nn", "court vision low next nature", allow_missing_words=False)


def test_a_title_that_names_only_the_brand_before_a_bar_takes_the_model_from_after_it() -> None:
    assert normalize_model("Puma | Smashic Comfort Casual Sneakers", "puma") == "smashic comfort"


def test_descriptions_of_a_shoe_are_not_part_of_its_model() -> None:
    assert normalize_model("ADIDAS Men Solid Grand Court 2.0 Tennis Sneakers", "adidas") == "grand court 2.0"
    assert (
        normalize_model("adidas Men Grand Court Base 2.0 Sportswear Shoes", "adidas")
        == "grand court base 2.0"
    )


def test_version_numbers_keep_their_decimal_point() -> None:
    assert normalize_model("ADIDAS Grand Court Base 2.0 Sneakers", "adidas") == "grand court base 2.0"
    assert not same_model("grand court 2.0", "grand court 3.0")
