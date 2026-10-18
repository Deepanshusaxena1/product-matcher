from app.domain.models import Category, Fingerprint, Gender
from app.sources.amazon.fingerprint import fingerprint_from
from app.sources.amazon.page import AmazonPage, parse_amazon_page


def _fingerprint(html: str) -> Fingerprint:
    page = parse_amazon_page(html)
    assert page is not None
    return fingerprint_from(page)


def test_a_smartphone_is_identified_by_model_ram_and_storage(phone_html: str) -> None:
    assert _fingerprint(phone_html) == Fingerprint(
        category=Category.SMARTPHONE,
        brand="samsung",
        model="galaxy s24 fe",
        ram_gb=8,
        storage_gb=128,
        colour="Graphite",
        colour_families=("grey",),
    )


def test_a_television_is_identified_by_model_number_and_screen_size(tv_html: str) -> None:
    fingerprint = _fingerprint(tv_html)

    assert fingerprint.category is Category.TELEVISION
    assert fingerprint.brand == "lg"
    assert fingerprint.model_number == "43NU870BPLA"
    # From the title, as "Model Name" only repeats the model number; sizes and the number are dropped.
    assert fingerprint.model == "nu87 nano 2026"
    assert fingerprint.screen_in == 43
    # The TV's 8 GB of app storage is not a phone's storage: attributes are read per category.
    assert fingerprint.ram_gb is None
    assert fingerprint.storage_gb is None


def test_a_sneaker_is_identified_by_style_code_colour_and_gender(sneaker_html: str) -> None:
    assert _fingerprint(sneaker_html) == Fingerprint(
        category=Category.SNEAKER,
        brand="nike",
        model="court vision low next nature",
        model_number="DH2987-100",
        colour="White",
        colour_families=("white",),
        gender=Gender.MEN,
    )


def test_a_style_code_that_extends_the_item_model_number_is_preferred(polo_html: str) -> None:
    # PUMA's "687093" is the style; "68709301" is that style in Black, which is what must match.
    fingerprint = _fingerprint(polo_html)

    assert fingerprint.category is Category.TSHIRT
    assert fingerprint.brand == "puma"
    assert fingerprint.model_number == "68709301"
    assert fingerprint.colour == "Black"
    assert fingerprint.colour_families == ("black",)
    assert fingerprint.gender is Gender.MEN


def test_the_product_type_is_the_fallback_when_breadcrumbs_are_missing() -> None:
    page = AmazonPage(title="Samsung Galaxy S24 FE 5G", specs={"Item Type Name": "Smartphones"})

    assert fingerprint_from(page).category is Category.SMARTPHONE


def test_title_attributes_fill_in_for_a_sparse_spec_table() -> None:
    page = AmazonPage(
        title="Apple iPhone 15 Plus (Black, 256 GB)",
        breadcrumbs=("Electronics", "Smartphones"),
        specs={"Brand": "Apple"},
    )

    fingerprint = fingerprint_from(page)

    assert fingerprint.model == "iphone 15 plus"
    assert fingerprint.storage_gb == 256
    assert fingerprint.ram_gb is None


def test_a_coarse_model_series_does_not_replace_the_model_named_in_the_title() -> None:
    # Live page B0CS69QQTG lists "Model Series: Galaxy S", which would make every Galaxy S phone match.
    page = AmazonPage(
        title="Samsung Galaxy S24 5G AI Smartphone (Onyx Black, 8GB, 256GB Storage)",
        breadcrumbs=("Electronics", "Smartphones"),
        specs={"Brand": "Samsung", "Model Series": "Galaxy S"},
    )

    assert fingerprint_from(page).model == "galaxy s24"


def test_a_product_outside_the_four_categories_has_no_category() -> None:
    page = AmazonPage(title="Epson projector", breadcrumbs=("Electronics", "Projectors"))

    assert fingerprint_from(page).category is None


def test_a_listed_code_too_short_to_be_a_style_code_gives_way_to_the_part_number() -> None:
    # Live page B09VSZNT7Z: "Model number: LIT50", "Manufacturer part number: GW9250" (the real style code).
    page = AmazonPage(
        title="adidas Men Grand Court Base 2.0 Sportswear Shoes White 9",
        breadcrumbs=("Shoes", "Men's Shoes", "Sneakers"),
        specs={"Brand": "adidas", "Model number": "LIT50", "Manufacturer part number": "GW9250"},
    )

    assert fingerprint_from(page).model_number == "GW9250"


def test_a_phone_page_without_breadcrumbs_is_recognised_by_its_generic_name() -> None:
    # Live page B0HJB7MQ97 has no category trail at all.
    page = AmazonPage(
        title="iPhone 18 Pro (256 GB) - Black",
        specs={"Brand": "Apple", "Model Name": "iPhone 18 Pro", "Item model number": "MJRP4HN/A",
               "Memory Storage Capacity": "256 GB", "Generic Name": "iPhone"},
        variation={"color_name": "Black", "size_name": "256 GB"},
    )  # fmt: skip

    fingerprint = fingerprint_from(page)

    assert fingerprint.category is Category.SMARTPHONE
    assert (fingerprint.brand, fingerprint.model) == ("apple", "iphone 18 pro")
    assert fingerprint.storage_gb == 256
