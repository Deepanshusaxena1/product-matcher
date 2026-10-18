from pathlib import Path

import pytest

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures" / "amazon"


def read_fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture
def phone_html() -> str:
    return read_fixture("phone_samsung_s24fe.html")


@pytest.fixture
def tv_html() -> str:
    return read_fixture("tv_lg_43nu870bpla.html")


@pytest.fixture
def sneaker_html() -> str:
    return read_fixture("sneaker_nike_court_vision.html")


@pytest.fixture
def polo_html() -> str:
    return read_fixture("polo_puma_687093.html")
