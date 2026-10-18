from collections.abc import Mapping, Sequence

import pytest

from app.domain.models import Availability, Category, Fingerprint, Gender, Listing, MatchStatus, Platform
from app.domain.ports import FetchError, ShopProfile
from app.matching.matcher import Matcher

SOURCE = Listing(
    platform=Platform.AMAZON,
    listing_id="B0DHL7YT5S",
    url="https://www.amazon.in/dp/B0DHL7YT5S",
    title="Samsung Galaxy S24 FE 5G AI Smartphone (Graphite, 8GB RAM, 128GB Storage)",
    fingerprint=Fingerprint(
        category=Category.SMARTPHONE,
        brand="samsung",
        model="galaxy s24 fe",
        ram_gb=8,
        storage_gb=128,
        colour="Graphite",
        colour_families=("grey",),
    ),
)


def _tile(
    listing_id: str, title: str, availability: Availability = Availability.UNKNOWN, **fingerprint: object
) -> Listing:
    return Listing(
        platform=Platform.FLIPKART,
        listing_id=listing_id,
        url=f"https://www.flipkart.com/p/itm?pid={listing_id}",
        title=title,
        fingerprint=Fingerprint.model_validate(fingerprint),
        availability=availability,
        price_inr=39999,
    )


def _phone_tile(
    listing_id: str,
    colour: str,
    storage: int,
    availability: Availability,
    ram: int = 8,
    model: str = "galaxy s24 fe",
) -> Listing:
    return _tile(
        listing_id,
        f"Samsung {model.title()} 5G ({colour}, {storage} GB)",
        availability,
        category=Category.SMARTPHONE,
        brand="samsung",
        model=model,
        ram_gb=ram,
        storage_gb=storage,
        colour=colour,
    )


DEFAULT_PROFILE = ShopProfile()


class FakeAdapter:
    """A shop whose search results and product pages are given up front."""

    def __init__(
        self,
        results: Mapping[str, Sequence[Listing]],
        details: Mapping[str, Listing | Exception] | None = None,
        profile: ShopProfile = DEFAULT_PROFILE,
    ) -> None:
        self._results = results
        self._details = details or {}
        self._profile = profile
        self.searched: list[str] = []
        self.detailed: list[str] = []

    @property
    def platform(self) -> Platform:
        return Platform.FLIPKART

    @property
    def profile(self) -> ShopProfile:
        return self._profile

    async def search(self, query: str, category: Category) -> Sequence[Listing]:
        self.searched.append(query)
        return self._results.get(query, ())

    async def fetch_details(self, listing: Listing) -> Listing:
        self.detailed.append(listing.listing_id)
        detail = self._details.get(listing.listing_id, listing)
        if isinstance(detail, Exception):
            raise detail
        return detail


def _available(*tiles: Listing) -> dict[str, Listing]:
    """Product pages that confirm each tile and report it in stock unless the tile says otherwise."""
    return {
        tile.listing_id: tile.model_copy(
            update={
                "availability": tile.availability
                if tile.availability is not Availability.UNKNOWN
                else Availability.IN_STOCK
            }
        )
        for tile in tiles
    }


async def test_the_same_variant_in_the_same_colour_is_matched_and_its_stock_reported() -> None:
    graphite = _phone_tile("G128", "Graphite", 128, Availability.IN_STOCK)
    adapter = FakeAdapter(
        {"samsung galaxy s24 fe": [_phone_tile("B256", "Blue", 256, Availability.IN_STOCK), graphite]},
        _available(graphite),
    )

    result = await Matcher().find(SOURCE, adapter)

    assert result.status is MatchStatus.IN_STOCK
    assert result.listing is not None
    assert result.listing.listing_id == "G128"
    assert result.platform is Platform.FLIPKART
    assert "8 GB RAM" in result.reason
    assert "B256" not in adapter.detailed  # a tile that already conflicts is never opened


async def test_an_out_of_stock_match_is_reported_with_its_link() -> None:
    graphite = _phone_tile("G128", "Graphite", 128, Availability.OUT_OF_STOCK)
    adapter = FakeAdapter({"samsung galaxy s24 fe": [graphite]}, _available(graphite))

    result = await Matcher().find(SOURCE, adapter)

    assert result.status is MatchStatus.OUT_OF_STOCK
    assert result.listing is not None


async def test_of_two_listings_of_the_same_variant_the_one_in_stock_is_reported() -> None:
    sold_out = _phone_tile("G128-OLD", "Graphite", 128, Availability.OUT_OF_STOCK)
    in_stock = _phone_tile("G128-NEW", "Graphite", 128, Availability.IN_STOCK)
    adapter = FakeAdapter({"samsung galaxy s24 fe": [sold_out, in_stock]}, _available(sold_out, in_stock))

    result = await Matcher().find(SOURCE, adapter)

    assert result.listing is not None
    assert result.listing.listing_id == "G128-NEW"


async def test_another_colour_of_the_same_variant_still_matches_with_a_note() -> None:
    blue = _phone_tile("B128", "Blue", 128, Availability.IN_STOCK)
    adapter = FakeAdapter({"samsung galaxy s24 fe": [blue]}, _available(blue))

    result = await Matcher().find(SOURCE, adapter)

    assert result.status is MatchStatus.IN_STOCK
    assert any("Blue" in note for note in result.notes)


async def test_only_other_variants_means_not_listed_with_the_nearest_miss_explained() -> None:
    adapter = FakeAdapter(
        {
            "samsung galaxy s24 fe": [
                _phone_tile("B256", "Blue", 256, Availability.IN_STOCK),
                _phone_tile("P256", "Graphite", 256, Availability.IN_STOCK, ram=8, model="galaxy s24 plus"),
            ]
        }
    )

    result = await Matcher().find(SOURCE, adapter)

    assert result.status is MatchStatus.NOT_LISTED
    assert result.listing is None
    assert "256 GB storage, not 128 GB" in result.reason
    assert adapter.detailed == []


async def test_nothing_from_the_brand_means_not_listed() -> None:
    result = await Matcher().find(SOURCE, FakeAdapter({}))

    assert result.status is MatchStatus.NOT_LISTED
    assert "samsung galaxy s24 fe" in result.reason.lower()


async def test_sponsored_results_are_never_matched() -> None:
    ad = _phone_tile("AD1", "Graphite", 128, Availability.IN_STOCK).model_copy(update={"sponsored": True})
    adapter = FakeAdapter({"samsung galaxy s24 fe": [ad]}, _available(ad))

    result = await Matcher().find(SOURCE, adapter)

    assert result.status is MatchStatus.NOT_LISTED
    assert adapter.detailed == []


async def test_a_match_the_product_page_contradicts_is_rejected() -> None:
    tile = _phone_tile("G128", "Graphite", 128, Availability.IN_STOCK)
    page = tile.model_copy(update={"fingerprint": tile.fingerprint.model_copy(update={"storage_gb": 256})})
    adapter = FakeAdapter({"samsung galaxy s24 fe": [tile]}, {"G128": page})

    result = await Matcher().find(SOURCE, adapter)

    assert result.status is MatchStatus.NOT_LISTED


async def test_a_match_whose_must_match_attributes_stay_unknown_is_not_claimed() -> None:
    tile = _phone_tile("G128", "Graphite", 128, Availability.IN_STOCK)
    vague = tile.model_copy(update={"fingerprint": tile.fingerprint.model_copy(update={"storage_gb": None})})
    adapter = FakeAdapter({"samsung galaxy s24 fe": [vague]}, {"G128": vague})

    result = await Matcher().find(SOURCE, adapter)

    assert result.status is MatchStatus.NOT_LISTED
    assert "couldn't confirm" in result.reason


async def test_one_failed_product_page_does_not_hide_a_match_on_another() -> None:
    first = _phone_tile("G1", "Graphite", 128, Availability.IN_STOCK)
    second = _phone_tile("G2", "Graphite", 128, Availability.IN_STOCK)
    adapter = FakeAdapter(
        {"samsung galaxy s24 fe": [first, second]}, {"G1": FetchError("timeout"), **_available(second)}
    )

    result = await Matcher().find(SOURCE, adapter)

    assert result.listing is not None
    assert result.listing.listing_id == "G2"


async def test_when_every_product_page_fails_the_shop_could_not_be_checked() -> None:
    tile = _phone_tile("G1", "Graphite", 128, Availability.IN_STOCK)
    adapter = FakeAdapter({"samsung galaxy s24 fe": [tile]}, {"G1": FetchError("timeout")})

    with pytest.raises(FetchError):
        await Matcher().find(SOURCE, adapter)


SNEAKER_SOURCE = Listing(
    platform=Platform.AMAZON,
    listing_id="B0983NTYZ5",
    url="https://www.amazon.in/dp/B0983NTYZ5",
    title="Nike Mens Court Vision Lo NN Sneakers",
    fingerprint=Fingerprint(
        category=Category.SNEAKER,
        brand="nike",
        model="court vision low next nature",
        model_number="DH2987-100",
        colour="White",
        colour_families=("white",),
        gender=Gender.MEN,
    ),
)


def _shoe_tile(listing_id: str, title: str, **changes: object) -> Listing:
    fingerprint = {**SNEAKER_SOURCE.fingerprint.model_dump(), "model_number": None, **changes}
    return _tile(listing_id, title, **fingerprint)


async def test_fashion_is_decided_by_the_style_code_on_the_product_page() -> None:
    lookalike = _shoe_tile("LOW", "NIKE Court Vision Low Sneakers For Men", model="court vision low")
    exact = _shoe_tile("NN", "NIKE COURT VISION LO NN Sneakers For Men")
    adapter = FakeAdapter(
        {"nike court vision low next nature white men sneakers": [lookalike, exact]},
        {
            "LOW": lookalike.model_copy(
                update={
                    "fingerprint": lookalike.fingerprint.model_copy(update={"model_number": "FQ8075-133"})
                }
            ),
            "NN": exact.model_copy(
                update={
                    "availability": Availability.IN_STOCK,
                    "fingerprint": exact.fingerprint.model_copy(update={"model_number": "DH2987-100"}),
                }
            ),
        },
    )

    result = await Matcher().find(SNEAKER_SOURCE, adapter)

    assert adapter.searched == ["nike DH2987-100", "nike court vision low next nature white men sneakers"]
    assert result.status is MatchStatus.IN_STOCK
    assert result.listing is not None
    assert result.listing.listing_id == "NN"
    assert "DH2987-100" in result.reason


async def test_a_confirmed_match_from_the_first_query_skips_the_rest() -> None:
    exact = _shoe_tile("NN", "NIKE COURT VISION LO NN Sneakers For Men", model_number="DH2987-100")
    adapter = FakeAdapter({"nike DH2987-100": [exact]}, _available(exact))

    await Matcher().find(SNEAKER_SOURCE, adapter)

    assert adapter.searched == ["nike DH2987-100"]


async def test_the_reason_mentions_only_attributes_the_amazon_product_states() -> None:
    source = SOURCE.model_copy(update={"fingerprint": SOURCE.fingerprint.model_copy(update={"ram_gb": None})})
    graphite = _phone_tile("G128", "Graphite", 128, Availability.IN_STOCK)
    adapter = FakeAdapter({"samsung galaxy s24 fe": [graphite]}, _available(graphite))

    result = await Matcher().find(source, adapter)

    assert result.reason == "Same model (Samsung Galaxy S24 FE), 128 GB storage."


async def test_product_pages_are_opened_in_batches_until_one_confirms_the_match() -> None:
    # Many lookalike tiles; only the product pages show style codes, and the match ranks last.
    tiles = [_shoe_tile(f"S{i}", "NIKE COURT VISION LO NN Sneakers For Men") for i in range(5)]
    pages = {
        tile.listing_id: tile.model_copy(
            update={
                "availability": Availability.IN_STOCK,
                "fingerprint": tile.fingerprint.model_copy(
                    update={
                        "model_number": "DH2987-100"
                        if tile.listing_id == "S4"
                        else f"XX0000-00{tile.listing_id[1]}"
                    }
                ),
            }
        )
        for tile in tiles
    }
    adapter = FakeAdapter({"nike court vision low next nature white men sneakers": tiles}, pages)

    result = await Matcher(pages_per_batch=2, max_pages_per_query=6).find(SNEAKER_SOURCE, adapter)

    assert result.listing is not None
    assert result.listing.listing_id == "S4"
    assert len(adapter.detailed) == 5


async def test_no_more_product_pages_than_the_limit_are_opened_per_query() -> None:
    tiles = [_shoe_tile(f"S{i}", "NIKE COURT VISION LO NN Sneakers For Men") for i in range(5)]
    pages = {
        tile.listing_id: tile.model_copy(
            update={"fingerprint": tile.fingerprint.model_copy(update={"model_number": "XX0000-000"})}
        )
        for tile in tiles
    }
    adapter = FakeAdapter({"nike court vision low next nature white men sneakers": tiles}, pages)

    result = await Matcher(pages_per_batch=2, max_pages_per_query=3).find(SNEAKER_SOURCE, adapter)

    assert result.status is MatchStatus.NOT_LISTED
    assert len(adapter.detailed) == 3


async def test_a_shop_without_style_codes_is_searched_and_judged_by_name() -> None:
    lookalike = _shoe_tile("LOW", "Nike Men Court Vision Low Sneakers", model="court vision low")
    other = _shoe_tile("PEG", "Nike Men Pegasus 40 Running Shoes", model="pegasus 40")
    exact = _shoe_tile("NN", "Nike Men Court Vision Low Next Nature Sneakers")
    adapter = FakeAdapter(
        {"nike court vision low next nature white men sneakers": [other, lookalike, exact]},
        {"NN": exact.model_copy(update={"availability": Availability.IN_STOCK})},
        profile=ShopProfile(shows_model_numbers=False),
    )

    result = await Matcher().find(SNEAKER_SOURCE, adapter)

    assert adapter.searched == ["nike court vision low next nature white men sneakers"]
    assert "PEG" not in adapter.detailed  # a different name is rejected from the results page
    assert result.status is MatchStatus.IN_STOCK
    assert result.listing is not None
    assert result.listing.listing_id == "NN"
    assert result.reason == "Same model (Nike Court Vision Low Next Nature), White, men's."
    assert result.notes == ("Matched by name: the listing doesn't show a style code.",)


async def test_a_lookalike_name_without_a_style_code_is_not_claimed() -> None:
    lookalike = _shoe_tile("LOW", "Nike Men Court Vision Low Sneakers", model="court vision low")
    adapter = FakeAdapter(
        {"nike court vision low next nature white men sneakers": [lookalike]},
        _available(lookalike),
        profile=ShopProfile(shows_model_numbers=False),
    )

    result = await Matcher().find(SNEAKER_SOURCE, adapter)

    assert result.status is MatchStatus.NOT_LISTED
    assert result.reason == (
        "Found “Nike Men Court Vision Low Sneakers”, but couldn't confirm its model "
        "(it's named “court vision low”, not “court vision low next nature”)."
    )


async def test_the_shop_explains_how_its_stock_was_checked() -> None:
    graphite = _phone_tile("G128", "Graphite", 128, Availability.OUT_OF_STOCK)
    adapter = FakeAdapter(
        {"samsung galaxy s24 fe": [graphite]},
        profile=ShopProfile(stock_note="Stock is for delivery to pincode 400001."),
    )

    result = await Matcher().find(SOURCE, adapter)

    assert result.status is MatchStatus.OUT_OF_STOCK
    assert result.notes == ("Stock is for delivery to pincode 400001.",)


async def test_a_listing_without_any_model_name_is_not_offered_as_the_closest() -> None:
    nameless = _shoe_tile("ANY", "Nike Mens Sneakers", model=None)
    other = _shoe_tile("PEG", "Nike Men Pegasus 40 Sneakers", model="pegasus 40")
    adapter = FakeAdapter(
        {"nike court vision low next nature white men sneakers": [nameless, other]},
        _available(nameless, other),
        profile=ShopProfile(shows_model_numbers=False),
    )

    result = await Matcher().find(SNEAKER_SOURCE, adapter)

    assert result.reason == (
        "The closest Flipkart listing, “Nike Men Pegasus 40 Sneakers”, "
        "is the pegasus 40, not the court vision low next nature."
    )


async def test_the_same_colour_written_in_another_case_gets_no_colour_note() -> None:
    graphite = _phone_tile("G128", "graphite", 128, Availability.IN_STOCK)
    adapter = FakeAdapter({"samsung galaxy s24 fe": [graphite]}, _available(graphite))

    result = await Matcher().find(SOURCE, adapter)

    assert result.notes == ()


@pytest.mark.parametrize(
    ("model", "name"),
    [
        ("galaxy s24 fe", "Samsung Galaxy S24 FE"),
        ("galaxy z fold7", "Samsung Galaxy Z Fold7"),
        ("galaxy a36", "Samsung Galaxy A36"),
    ],
)
def test_product_names_read_as_the_maker_writes_them(model: str, name: str) -> None:
    from app.matching.matcher import product_name

    assert product_name(Fingerprint(category=Category.SMARTPHONE, brand="samsung", model=model)) == name
