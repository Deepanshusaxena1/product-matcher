import pytest
from pydantic import ValidationError

from app.domain.models import (
    Availability,
    Category,
    ComparisonReport,
    Fingerprint,
    Listing,
    MatchStatus,
    Platform,
    PlatformResult,
)


def make_listing(platform: Platform = Platform.FLIPKART, **overrides: object) -> Listing:
    fields: dict[str, object] = {
        "platform": platform,
        "listing_id": "ID1",
        "url": "https://www.example.com/p/ID1",
        "title": "Samsung Galaxy S24 FE 5G (Graphite, 128 GB)",
        "fingerprint": Fingerprint(category=Category.SMARTPHONE, brand="samsung"),
    }
    fields.update(overrides)
    return Listing.model_validate(fields)


@pytest.mark.parametrize(
    ("category", "platforms"),
    [
        (Category.SMARTPHONE, (Platform.FLIPKART, Platform.CROMA)),
        (Category.TELEVISION, (Platform.FLIPKART, Platform.CROMA)),
        (Category.SNEAKER, (Platform.FLIPKART, Platform.MYNTRA)),
        (Category.TSHIRT, (Platform.FLIPKART, Platform.MYNTRA)),
    ],
)
def test_each_category_is_searched_on_the_platforms_named_in_the_assignment(
    category: Category, platforms: tuple[Platform, ...]
) -> None:
    assert category.platforms == platforms


@pytest.mark.parametrize("status", [MatchStatus.IN_STOCK, MatchStatus.OUT_OF_STOCK])
def test_a_found_result_must_carry_the_matched_listing(status: MatchStatus) -> None:
    with pytest.raises(ValidationError, match="must include the matched listing"):
        PlatformResult(platform=Platform.FLIPKART, status=status, reason="Same model")


def test_a_not_listed_result_cannot_carry_a_listing() -> None:
    with pytest.raises(ValidationError, match="cannot include a listing"):
        PlatformResult(
            platform=Platform.FLIPKART,
            status=MatchStatus.NOT_LISTED,
            reason="No match",
            listing=make_listing(),
        )


def test_an_error_result_may_carry_what_was_found_before_the_check_failed() -> None:
    result = PlatformResult(
        platform=Platform.CROMA,
        status=MatchStatus.ERROR,
        reason="Found the product but couldn't confirm stock",
        listing=make_listing(Platform.CROMA),
    )

    assert result.listing is not None


def test_a_result_listing_must_come_from_the_same_platform() -> None:
    with pytest.raises(ValidationError, match="listing from croma"):
        PlatformResult(
            platform=Platform.FLIPKART,
            status=MatchStatus.IN_STOCK,
            reason="Same model",
            listing=make_listing(Platform.CROMA),
        )


@pytest.mark.parametrize(
    "url",
    ["javascript:alert(1)", "ftp://www.example.com/p/1", "/relative/path", "https://", ""],
)
def test_listing_links_must_be_absolute_web_urls(url: str) -> None:
    with pytest.raises(ValidationError, match="http"):
        make_listing(url=url)


def test_confidence_is_a_probability() -> None:
    with pytest.raises(ValidationError):
        PlatformResult(
            platform=Platform.FLIPKART,
            status=MatchStatus.IN_STOCK,
            reason="Same model",
            listing=make_listing(),
            confidence=1.5,
        )


def test_a_report_needs_a_source_product_with_a_known_category() -> None:
    with pytest.raises(ValidationError, match="category"):
        ComparisonReport(source=make_listing(Platform.AMAZON, fingerprint=Fingerprint()), results=())


def test_a_report_has_at_most_one_result_per_platform() -> None:
    not_listed = PlatformResult(platform=Platform.CROMA, status=MatchStatus.NOT_LISTED, reason="No match")

    with pytest.raises(ValidationError, match="once"):
        ComparisonReport(source=make_listing(Platform.AMAZON), results=(not_listed, not_listed))


def test_reports_serialise_enums_as_stable_lowercase_strings() -> None:
    report = ComparisonReport(
        source=make_listing(Platform.AMAZON),
        results=(
            PlatformResult(
                platform=Platform.FLIPKART,
                status=MatchStatus.IN_STOCK,
                reason="Same model",
                listing=make_listing(availability=Availability.IN_STOCK),
            ),
        ),
    )

    payload = report.model_dump(mode="json")

    assert payload["source"]["platform"] == "amazon"
    assert payload["source"]["fingerprint"]["category"] == "smartphone"
    assert payload["results"][0]["status"] == "in_stock"
    assert payload["results"][0]["listing"]["availability"] == "in_stock"


def test_a_fingerprint_is_completed_from_another_without_overriding_what_it_knows() -> None:
    from_search = Fingerprint(category=Category.SMARTPHONE, brand="samsung", model="galaxy s24 fe", ram_gb=8)
    from_page = Fingerprint(brand="samsung", model="galaxy s24 fe 5g", storage_gb=128, colour="Graphite")

    completed = from_page.completed_with(from_search)

    assert completed == Fingerprint(
        category=Category.SMARTPHONE,
        brand="samsung",
        model="galaxy s24 fe 5g",
        ram_gb=8,
        storage_gb=128,
        colour="Graphite",
    )


@pytest.mark.parametrize(
    ("platform", "label"),
    [
        (Platform.AMAZON, "Amazon"),
        (Platform.FLIPKART, "Flipkart"),
        (Platform.CROMA, "Croma"),
        (Platform.MYNTRA, "Myntra"),
    ],
)
def test_platforms_have_a_display_name(platform: Platform, label: str) -> None:
    assert platform.label == label
