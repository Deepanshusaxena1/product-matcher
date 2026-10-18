import pytest

from app.normalize.units import parse_gb, parse_inr, parse_ram_storage, parse_screen_inches


@pytest.mark.parametrize(
    ("text", "gb"),
    [
        ("8 GB", 8),
        ("128GB", 128),
        ("256 gb", 256),
        ("1 TB", 1024),
        ("1TB", 1024),
        ("12 GB RAM", 12),
    ],
)
def test_memory_sizes_are_read_in_gigabytes(text: str, gb: int) -> None:
    assert parse_gb(text) == gb


@pytest.mark.parametrize("text", ["", "Others", "512 MB", "3.1 GHz", "4700 mAh"])
def test_anything_that_is_not_a_whole_gigabyte_size_is_unknown(text: str) -> None:
    assert parse_gb(text) is None


@pytest.mark.parametrize(
    ("text", "ram_storage"),
    [
        ("Samsung Galaxy S24 FE 5G AI Smartphone (Graphite, 8GB RAM, 128GB Storage)", (8, 128)),
        ("8 GB RAM | 128 GB ROM", (8, 128)),
        ("8GB+128GB", (8, 128)),
        ("8 GB + 256 GB", (8, 256)),
        ("(12GB RAM + 1TB Storage)", (12, 1024)),
        ("OnePlus 13R (Astral Trail, 12/256 GB)", (12, 256)),
        ("Apple iPhone 15 (128 GB) - Black", (None, 128)),
        ("Apple iPhone 15 Plus (Black, 8GB RAM, 256 GB)", (8, 256)),
        ("Galaxy S24 FE", (None, None)),
    ],
)
def test_ram_and_storage_are_read_from_titles_and_spec_lines(
    text: str, ram_storage: tuple[int | None, int | None]
) -> None:
    assert parse_ram_storage(text) == ram_storage


@pytest.mark.parametrize(
    ("text", "inches"),
    [
        ("43 Inches", 43),
        ("43 inch", 43),
        ('55"', 55),
        ("108 cm (43 inch)", 43),
        ("LG 108 cms (43 inches) NU87 AI Series Nano 4K Ultra HD", 43),
        ("139 cm (55 inches)", 55),
        ("6.7 Inches", 6.7),
    ],
)
def test_screen_sizes_prefer_the_stated_inches(text: str, inches: float) -> None:
    assert parse_screen_inches(text) == inches


@pytest.mark.parametrize(
    ("text", "inches"),
    [
        ("108 cm", 42.5),
        ("80 cm", 31.5),
        ("164 cms", 64.6),
    ],
)
def test_screen_sizes_given_only_in_centimetres_are_converted(text: str, inches: float) -> None:
    # Not rounded to a whole inch here: "80 cm" is sold as a 32" TV, so the matcher compares with a tolerance.
    assert parse_screen_inches(text) == inches


@pytest.mark.parametrize("text", ["", "4K Ultra HD", "3840 x 2160", "60 Hz"])
def test_text_without_a_screen_size_is_unknown(text: str) -> None:
    assert parse_screen_inches(text) is None


@pytest.mark.parametrize(
    ("text", "rupees"),
    [
        ("₹39,999.00", 39999.0),
        ("₹ 759", 759.0),
        ("Rs. 1,23,456", 123456.0),
        ("39999", 39999.0),
    ],
)
def test_prices_are_read_in_rupees(text: str, rupees: float) -> None:
    assert parse_inr(text) == rupees


@pytest.mark.parametrize("text", ["", "Currently unavailable", "₹"])
def test_text_without_a_price_is_unknown(text: str) -> None:
    assert parse_inr(text) is None
