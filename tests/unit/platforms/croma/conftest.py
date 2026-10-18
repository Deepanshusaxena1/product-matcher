from collections.abc import Callable
from pathlib import Path

import pytest

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures" / "croma"


@pytest.fixture(scope="session")
def croma_file() -> Callable[[str], str]:
    """Reads a saved Croma page or API response by file name."""
    return lambda name: (FIXTURES / name).read_text(encoding="utf-8")
