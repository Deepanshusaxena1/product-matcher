# Product Matcher

Paste an Amazon.in product link and find the same product on Flipkart, Croma or Myntra, with whether you can
buy it there. Built for the $cruge Founding Backend Engineer assignment; the design is in
[SOLUTIONING.md](SOLUTIONING.md).

## Status

All six milestones are done:
- **Milestone 1:** the domain model, the interfaces every part plugs into, the API and the web page.
- **Milestone 2:** reading a live Amazon.in product page into a fingerprint, and the normalisers every shop
  shares (sizes, brands, colours, model names, categories).
- **Milestone 3:** live matching on Flipkart: search, hard rules, product-page checks and stock.
- **Milestone 4:** live matching on Croma (stock is checked for delivery to one pincode) and Myntra (no
  style codes, so fashion must match by name word for word, plus colour and who it's for).
- **Milestone 5 (without AI, by choice):** answers stream to the page shop by shop; Amazon products are
  cached for a day and shop answers for 30 minutes (never "couldn't check"), and each answer says when it
  was checked; sharper reading of fashion titles and adidas/PUMA style codes. T-shirts are only ever
  matched by style code, since names like "Cotton Slim Fit Polo" fit a hundred shirts.
- **Milestone 6:** a golden set of 20 hand-checked products, a web page redesigned to Apple's Human
  Interface Guidelines, a Docker image with a Render blueprint, and
  [How the Product Matcher Works — Explained for a 5-Year-Old](https://claude.ai/code/artifact/2e19d10a-64cd-410b-8d79-f2467b1296b4).

The app searches all three shops live. Set `MATCHER_DEMO=true` to serve the bundled sample results instead
(offline, instant). `MATCHER_CROMA_PINCODE` (default `400001`, Mumbai) sets where Croma's stock is checked
for; `MATCHER_CROMA_INVENTORY_KEY` pins Croma's stock-check key, which is otherwise read from Croma's own
script. `MATCHER_PRODUCT_CACHE_TTL_S` and `MATCHER_RESULT_CACHE_TTL_S` set how long products and answers are
reused.

To see what the matcher will search for, read any Amazon.in link from the command line:

```bash
uv run python -m app.sources.amazon "https://www.amazon.in/dp/B0DHL7YT5S"
```

## Run

Needs [uv](https://docs.astral.sh/uv/), which also installs Python 3.12 if it is missing.

```bash
uv sync
uv run uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000 and paste a link, or click one of the samples.

| Endpoint | Purpose |
|---|---|
| `POST /api/compare` with `{"url": "<Amazon.in link>"}` | The comparison report: the Amazon product and one result per platform |
| `POST /api/compare/stream`, same body | The same as server-sent events: `source`, one `result` per platform as each finishes, then `done` (or `error`) |
| `GET /api/health` | Liveness check |
| `GET /docs` | Interactive API documentation |

Errors come back as `{"code": "...", "detail": "<message fit to show the user>"}` with status 422 (not an
Amazon.in product link, or an unsupported category), 404 (no product at that link) or 502 (Amazon unreadable).
The stream reports these the same way, before it starts.

## Test

```bash
uv run pytest                 # unit tests, offline
uv run pytest -m live tests/live/test_golden_set.py   # 20 hand-checked products against the live shops
uv run pytest -m live tests/live   # all live tests, Amazon reading included
uv run ruff check app tests
uv run mypy
```

## Deploy

[![Deploy to DO](https://www.deploytodo.com/do-btn-blue.svg)](https://cloud.digitalocean.com/apps/new?repo=https://github.com/Deepanshusaxena1/product-matcher/tree/main)

The button deploys to DigitalOcean App Platform in Bangalore, as described by `.do/deploy.template.yaml`. The
full guide, covering Docker, App Platform and a DigitalOcean Droplet, is
[deployment_documentation.md](deployment_documentation.md).

The `Dockerfile` builds one image that serves the API and the page on `$PORT` (default 8000):

```bash
docker compose up --build        # builds the image and serves http://localhost:8000
# or, without compose:
docker build -t product-matcher .
docker run -p 8000:8000 product-matcher
```

On Render, create a Blueprint from this repository: `render.yaml` describes the service (Singapore region,
health check on `/api/health`). Any `MATCHER_*` setting can be added as an environment variable. The shops
may treat a data-centre address more warily than a home connection; when one refuses, its card says
"Couldn't check" rather than guessing.

## Layout

| Path | What lives there |
|---|---|
| `app/domain/` | Models, errors and ports (the small interfaces each shop, the AI helper and the cache implement) |
| `app/normalize/` | Shared normalisers: sizes and prices, brands, colours, model names and numbers, categories |
| `app/sources/amazon/` | The pasted link (also the guard against fetching other hosts), page parser, fingerprint, reader |
| `app/infra/` | The HTTP fetcher (curl_cffi impersonating Chrome, with retries) and the in-memory cache |
| `app/platforms/` | One adapter per shop (Flipkart, Croma, Myntra), reading the JSON shops embed or serve |
| `app/matching/` | Search queries, the hard rules (what must agree, per category) and the matcher |
| `app/services/comparer.py` | The live use case: Amazon first, then every shop concurrently, streamed as each answers |
| `app/services/caching.py` | Caching wrappers for reading Amazon and for checking a shop |
| `app/config.py` | Settings from `MATCHER_*` environment variables |
| `app/services/demo.py` | The demo comparer that serves the bundled samples |
| `app/api/` | HTTP routes, request schemas and the error-to-status mapping |
| `app/main.py` | App factory and composition root: the one place that picks implementations |
| `static/index.html` | The web page |
| `tests/fixtures/` | Trimmed real pages from Amazon, Flipkart, Croma and Myntra, used by the parser tests |
| `tests/live/` | Opt-in tests against the real sites; `golden_set.json` holds the hand-checked answers |
