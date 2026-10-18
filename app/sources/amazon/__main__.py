"""Read one Amazon.in link and print what the matcher will search for.

uv run python -m app.sources.amazon "https://www.amazon.in/dp/B0DHL7YT5S"
"""

from __future__ import annotations

import asyncio
import sys

from app.domain.errors import MatcherError
from app.infra.http import CurlPageFetcher
from app.sources.amazon.reader import AmazonProductSource


async def _main(link: str) -> int:
    fetcher = CurlPageFetcher.impersonating_chrome()
    try:
        listing = await AmazonProductSource(fetcher).read(link)
    except MatcherError as error:
        print(f"{error.code}: {error.message}", file=sys.stderr)
        return 1
    finally:
        await fetcher.aclose()
    print(listing.model_dump_json(indent=2, exclude_none=True))
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    sys.exit(asyncio.run(_main(sys.argv[1])))
