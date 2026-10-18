import pytest

from app.normalize.colour import colour_families


@pytest.mark.parametrize(
    ("name", "families"),
    [
        ("Black", ("black",)),
        ("Phantom Black", ("black",)),
        ("Onyx Black", ("black",)),
        ("Midnight Navy", ("blue",)),
        ("Navy", ("blue",)),
        ("Sky Blue", ("blue",)),
        ("Graphite", ("grey",)),
        ("Titanium Gray", ("grey",)),
        ("Ivory", ("white",)),
        ("Triple White", ("white",)),
        ("Rose Gold", ("pink",)),
        ("Mint", ("green",)),
        ("Maroon", ("red",)),
        ("Olive Green", ("green",)),
    ],
)
def test_colour_names_map_to_a_base_colour(name: str, families: tuple[str, ...]) -> None:
    assert colour_families(name) == families


@pytest.mark.parametrize(
    ("name", "families"),
    [
        ("White/White-White", ("white",)),
        ("White/Black", ("black", "white")),
        ("Black/White", ("black", "white")),
        ("White & Red", ("red", "white")),
        ("Black, Gold", ("black", "gold")),
    ],
)
def test_multi_colour_names_become_the_set_of_their_base_colours(
    name: str, families: tuple[str, ...]
) -> None:
    # Order-free, so "White/Black" and "Black/White" agree while "White/Red" does not.
    assert colour_families(name) == families


@pytest.mark.parametrize("name", ["", "Astral Trail", "White/Astral Trail", "Multicolour"])
def test_names_with_any_unrecognised_part_are_unknown_rather_than_guessed(name: str) -> None:
    assert colour_families(name) == ()
