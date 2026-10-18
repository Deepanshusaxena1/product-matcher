import json
import re
from collections.abc import AsyncGenerator

import pytest
from fastapi.testclient import TestClient

from app.domain.errors import (
    InvalidProductUrlError,
    MatcherError,
    ProductNotFoundError,
    SourceUnavailableError,
    UnsupportedCategoryError,
)
from app.domain.models import (
    Availability,
    Category,
    ComparisonEvent,
    ComparisonReport,
    Fingerprint,
    Listing,
    MatchStatus,
    Platform,
    PlatformChecked,
    PlatformResult,
    SourceRead,
)
from app.main import create_app
from app.services.demo import DemoProductComparer

PRODUCT_URL = "https://www.amazon.in/dp/B0DHL7YT5S"


class StubComparer:
    def __init__(self, report: ComparisonReport | None = None, error: MatcherError | None = None) -> None:
        self._report = report
        self._error = error
        self.received: list[str] = []
        self.fail_after_source = False

    async def compare(self, product_url: str) -> ComparisonReport:
        self.received.append(product_url)
        if self._error is not None:
            raise self._error
        assert self._report is not None
        return self._report

    async def stream(self, product_url: str) -> AsyncGenerator[ComparisonEvent, None]:
        report = await self.compare(product_url)
        yield SourceRead(source=report.source, platforms=tuple(r.platform for r in report.results))
        for result in report.results:
            if self.fail_after_source:
                raise RuntimeError("a bug")
            yield PlatformChecked(result=result)


def a_report() -> ComparisonReport:
    phone = Fingerprint(
        category=Category.SMARTPHONE, brand="samsung", model="galaxy s24 fe", ram_gb=8, storage_gb=128
    )
    return ComparisonReport(
        source=Listing(
            platform=Platform.AMAZON,
            listing_id="B0DHL7YT5S",
            url=PRODUCT_URL,
            title="Samsung Galaxy S24 FE 5G AI Smartphone (Graphite, 8GB RAM, 128GB Storage)",
            fingerprint=phone,
        ),
        results=(
            PlatformResult(
                platform=Platform.FLIPKART,
                status=MatchStatus.IN_STOCK,
                reason="Same model with 8 GB RAM and 128 GB storage.",
                listing=Listing(
                    platform=Platform.FLIPKART,
                    listing_id="MOBH4ZG33EBNZKS7",
                    url="https://www.flipkart.com/samsung-galaxy-s24-fe/p/itme960199e26f23?pid=MOBH4ZG33EBNZKS7",
                    title="Samsung Galaxy S24 FE 5G (Graphite, 128 GB)",
                    fingerprint=phone,
                    availability=Availability.IN_STOCK,
                ),
            ),
            PlatformResult(platform=Platform.CROMA, status=MatchStatus.NOT_LISTED, reason="Not sold here."),
        ),
    )


def client_for(comparer: StubComparer) -> TestClient:
    return TestClient(create_app(comparer=comparer))


def test_compare_returns_the_report_for_the_pasted_link() -> None:
    comparer = StubComparer(report=a_report())

    response = client_for(comparer).post("/api/compare", json={"url": PRODUCT_URL})

    assert response.status_code == 200
    body = response.json()
    assert body["source"]["listing_id"] == "B0DHL7YT5S"
    assert [(r["platform"], r["status"]) for r in body["results"]] == [
        ("flipkart", "in_stock"),
        ("croma", "not_listed"),
    ]
    assert comparer.received == [PRODUCT_URL]


@pytest.mark.parametrize(
    ("error", "http_status"),
    [
        (InvalidProductUrlError("Please paste an Amazon.in product link."), 422),
        (UnsupportedCategoryError("Only phones, TVs, sneakers and T-shirts are supported."), 422),
        (ProductNotFoundError("Amazon has no product at that link."), 404),
        (SourceUnavailableError("Amazon isn't responding right now."), 502),
    ],
)
def test_matcher_errors_become_http_errors_with_a_readable_message(
    error: MatcherError, http_status: int
) -> None:
    response = client_for(StubComparer(error=error)).post("/api/compare", json={"url": PRODUCT_URL})

    assert response.status_code == http_status
    assert response.json() == {"code": error.code, "detail": error.message}


def test_a_request_without_a_url_is_rejected() -> None:
    response = client_for(StubComparer(report=a_report())).post("/api/compare", json={})

    assert response.status_code == 422


def test_health_check_reports_ok() -> None:
    response = client_for(StubComparer(report=a_report())).get("/api/health")

    assert response.json() == {"status": "ok"}


def test_the_web_page_is_served_at_the_root() -> None:
    response = client_for(StubComparer(report=a_report())).get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")


def test_every_sample_link_on_the_page_has_a_bundled_demo_scenario() -> None:
    page = client_for(StubComparer(report=a_report())).get("/").text
    sample_asins = set(re.findall(r"amazon\.in/dp/([A-Z0-9]{10})", page))
    bundled_asins = {scenario.source.listing_id for scenario in DemoProductComparer.bundled().scenarios}

    assert sample_asins, "the page should offer one-click sample links"
    assert sample_asins <= bundled_asins


def test_demo_mode_serves_the_bundled_samples() -> None:
    from app.config import Settings

    client = TestClient(create_app(settings=Settings(demo=True)))

    response = client.post("/api/compare", json={"url": PRODUCT_URL})

    assert response.status_code == 200
    assert response.json()["demo"] is True


def test_live_mode_builds_the_live_comparer_at_startup() -> None:
    from app.config import Settings
    from app.services.comparer import LiveProductComparer

    app = create_app(settings=Settings(demo=False))
    with TestClient(app):  # runs startup and shutdown
        assert isinstance(app.state.comparer, LiveProductComparer)
        assert app.state.comparer.connected_platforms == (Platform.FLIPKART, Platform.CROMA, Platform.MYNTRA)


def _events(text: str) -> list[tuple[str, dict[str, object]]]:
    """Parse a server-sent-events body into (event name, JSON data) pairs."""
    events = []
    for frame in text.strip().split("\n\n"):
        fields = dict(line.split(": ", 1) for line in frame.splitlines())
        events.append((fields["event"], json.loads(fields["data"])))
    return events


def test_the_stream_sends_the_source_then_each_result_then_done() -> None:
    response = client_for(StubComparer(report=a_report())).post(
        "/api/compare/stream", json={"url": PRODUCT_URL}
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = _events(response.text)
    assert [name for name, _ in events] == ["source", "result", "result", "done"]
    assert events[0][1]["source"]["listing_id"] == "B0DHL7YT5S"  # type: ignore[index]
    assert events[1][1]["result"]["platform"] == "flipkart"  # type: ignore[index]


def test_a_bad_link_is_an_http_error_before_any_streaming() -> None:
    comparer = StubComparer(error=InvalidProductUrlError("Please paste an Amazon.in product link."))

    response = client_for(comparer).post("/api/compare/stream", json={"url": "https://example.com"})

    assert response.status_code == 422
    assert response.json()["code"] == "invalid_product_url"


def test_a_failure_after_the_stream_started_ends_it_with_an_error_event() -> None:
    comparer = StubComparer(report=a_report())
    comparer.fail_after_source = True

    response = client_for(comparer).post("/api/compare/stream", json={"url": PRODUCT_URL})

    events = _events(response.text)
    assert [name for name, _ in events] == ["source", "error"]
    assert events[-1][1]["detail"] == "Something went wrong while checking. Try again."
