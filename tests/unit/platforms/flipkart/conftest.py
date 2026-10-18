from collections.abc import Callable
from pathlib import Path

import pytest

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures" / "flipkart"


@pytest.fixture(scope="session")
def flipkart_page() -> Callable[[str], str]:
    """Reads a saved Flipkart page by file name."""
    return lambda name: (FIXTURES / name).read_text(encoding="utf-8")
