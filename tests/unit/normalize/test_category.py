import pytest

from app.domain.models import Category, Gender
from app.normalize.category import category_from_breadcrumbs, category_from_type_name, gender_from


@pytest.mark.parametrize(
    ("crumbs", "category"),
    [
        (
            ["Electronics", "Mobiles & Accessories", "Smartphones & Basic Mobiles", "Smartphones"],
            Category.SMARTPHONE,
        ),
        (
            ["Electronics", "Home Theater, TV & Video", "Televisions", "Smart Televisions"],
            Category.TELEVISION,
        ),
        (["Shoes & Handbags", "Shoes", "Men's Shoes", "Casual Shoes", "Sneakers"], Category.SNEAKER),
        (["Shoes & Handbags", "Shoes", "Men's Shoes", "Sports Shoes", "Running Shoes"], Category.SNEAKER),
        (["Clothing & Accessories", "Men", "T-shirts, Polos & Shirts", "Polos"], Category.TSHIRT),
        (["Clothing & Accessories", "Men", "T-shirts, Polos & Shirts", "T-shirts"], Category.TSHIRT),
        (["Sports", "Cricket", "Clothing", "Jerseys"], Category.TSHIRT),
    ],
)
def test_the_deepest_breadcrumb_decides_the_category(crumbs: list[str], category: Category) -> None:
    assert category_from_breadcrumbs(crumbs) is category


@pytest.mark.parametrize(
    "crumbs",
    [
        [],
        ["Electronics", "Mobiles & Accessories", "Smartphones & Basic Mobiles", "Basic Mobiles"],
        ["Electronics", "Mobiles & Accessories", "Mobile Accessories", "Cases & Covers"],
        ["Clothing & Accessories", "Men", "T-shirts, Polos & Shirts", "Shirts"],
        ["Shoes & Handbags", "Shoes", "Men's Shoes", "Formal Shoes"],
        ["Electronics", "Home Theater, TV & Video", "Projectors"],
    ],
)
def test_products_outside_the_four_categories_have_none(crumbs: list[str]) -> None:
    # A parent crumb such as "T-shirts, Polos & Shirts" must not pull formal shirts into scope.
    assert category_from_breadcrumbs(crumbs) is None


@pytest.mark.parametrize(
    ("type_name", "category"),
    [
        ("Smartphones", Category.SMARTPHONE),
        ("Smartphone", Category.SMARTPHONE),
        ("NANO 4K UHD AI TV", Category.TELEVISION),
        ("T-Shirt", Category.TSHIRT),
        ("Sneakers", Category.SNEAKER),
        ("iPhone", Category.SMARTPHONE),  # Generic Name on live page B0HJB7MQ97, which has no breadcrumbs
        ("Mobile Phone", Category.SMARTPHONE),
        ("Cell Phone", Category.SMARTPHONE),
        ("Mobile Phone Case", None),
        ("iPhone Screen Protector", None),
        ("Shirt", None),
        ("", None),
    ],
)
def test_a_product_type_name_is_the_fallback(type_name: str, category: Category | None) -> None:
    assert category_from_type_name(type_name) is category


@pytest.mark.parametrize(
    ("texts", "gender"),
    [
        (["Men"], Gender.MEN),
        (["Shoes", "Men's Shoes"], Gender.MEN),
        (["Nike Mens Court Vision Lo NN Sneakers"], Gender.MEN),
        (["Women's Running Shoes"], Gender.WOMEN),
        (["Boys", "T-shirts"], Gender.KIDS),
        (["Unisex-Adult"], Gender.UNISEX),
        (["Galaxy S24 FE"], None),
    ],
)
def test_gender_is_read_from_the_first_text_that_names_one(texts: list[str], gender: Gender | None) -> None:
    assert gender_from(*texts) is gender


def test_womens_is_not_mistaken_for_mens() -> None:
    assert gender_from("Womens Polo T-Shirt") is Gender.WOMEN
