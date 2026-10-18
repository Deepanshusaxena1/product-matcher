# Solutioning Doc: Cross-Platform Product Matcher ($cruge assignment)

## Context
The $cruge Founding Backend Engineer assignment: given **one Amazon.in product link**, find the **same product** on other Indian platforms and report, per platform, one of three visually distinct states: **In stock** (link), **Out of stock** (link), **Not listed**.

| Category | Platforms | Must match (besides brand + model) |
|---|---|---|
| Smartphones | Flipkart, Croma | RAM + storage |
| Televisions | Flipkart, Croma | Screen size |
| Sneakers | Flipkart, Myntra | Colour |
| T-shirts / polos / jerseys | Flipkart, Myntra | Colour |

Deliverables: (1) a "explain it to a 5-year-old" document on how matching works, (2) a vibe-coded website where you paste an Amazon link and see results. AI use is allowed.

The repo is currently empty (only a PyCharm stub `main.py`), so this is a greenfield build. Recommended stack: **Python + FastAPI backend, Playwright/httpx for fetching, Claude for fuzzy extraction/judging, a single-page frontend served by FastAPI.**

---

## 1. Core idea (one sentence)
Turn every listing — Amazon's and each candidate's — into the **same structured "product fingerprint"** (`brand, model, category, key attributes`), then a product "matches" only if the fingerprints agree on the **hard attributes** the spec lists; everything fuzzy (titles, colour names, model spellings) is normalised first.

```
Amazon URL ─► Extract ─► Fingerprint ─► per-platform: Search ─► Candidates ─► Fingerprint each
                                                                       │
                                     Hard-attribute filter ─► Score/rank ─► (LLM tie-break)
                                                                       │
                                     Best match? ── no ──► NOT LISTED
                                          │ yes
                                     Read stock on product page ─► IN STOCK / OUT OF STOCK (+ link)
```

## 2. Data model
```python
class Category(Enum): SMARTPHONE, TV, SNEAKER, TSHIRT

class Fingerprint:
    category: Category
    brand: str              # normalised: "samsung", "xiaomi", "nike"
    model: str              # normalised family: "galaxy s24 fe", "air force 1 07"
    model_number: str|None  # strongest signal when present: "SM-S721B", "43UR7500PSC", "CW2288-111"
    ram_gb: int|None        # phones
    storage_gb: int|None    # phones
    screen_in: float|None   # TVs (inches)
    colour: str|None        # raw colour name, e.g. "Midnight Navy"
    colour_family: str|None # normalised base: "blue"
    title: str; url: str; price: float|None

class PlatformResult:
    platform: str           # flipkart | croma | myntra
    status: IN_STOCK | OUT_OF_STOCK | NOT_LISTED | ERROR
    url: str|None; title: str|None; price: float|None
    confidence: float; reason: str   # human-readable "why we matched / didn't"
```
`ERROR` ("couldn't check") is an internal 4th state shown subtly — we never disguise a scraping failure as "Not listed".

## 3. Step 1 — Read the Amazon product
1. **Resolve URL**: follow `amzn.in/...` / `amzn.to` short links; extract **ASIN** from `/dp/<ASIN>`, `/gp/product/<ASIN>`; rebuild canonical `https://www.amazon.in/dp/<ASIN>` (drops tracking params; also the cache key).
2. **Fetch**: httpx with real browser headers; fall back to Playwright if a captcha/robot page is detected.
3. **Parse** (selectors, all optional): `#productTitle`, `#bylineInfo` (brand), breadcrumbs `#wayfinding-breadcrumbs_feature_div` (category), `#productDetails_techSpec_section_1`, `#prodDetails`, `#detailBullets_feature_div`, `#poExpander` table (Brand / Model Name / Model Number / RAM / Storage / Screen Size / Colour), selected variation `#variation_color_name .selection`, `#variation_size_name`.
4. **Category detection**: breadcrumb keyword map (`Smartphones`, `Televisions`, `Shoes › Sneakers/Sports Shoes`, `T-Shirts`, `Polos`, `Jerseys`) → fallback LLM classification on title. Reject anything outside the 4 categories with a clear message.
5. **LLM normaliser** (Claude, structured JSON output): give it title + spec table + bullets, ask it to fill the Fingerprint. Deterministic parsers run first; the LLM only fills gaps and canonicalises the model name. Its output is validated (e.g. RAM in {2..24}, screen in {24..100}).

## 4. Step 2 — Normalisation rules (the heart of matching)
- **Brand**: lowercase, strip "Visit the … Store", alias table (`mi`/`redmi`/`xiaomi`, `oneplus`/`one plus`, `lg electronics`→`lg`, `u.s. polo assn.`/`us polo`).
- **Model**: lowercase, unify spaces/hyphens (`S24FE` ≈ `S24 FE`), remove brand, remove noise words (`5g`, `(…)` colour/storage suffixes, `smart`, `led`, `4k`, `men's`, `running shoes`). Compare by **token set**: all distinguishing tokens (`pro`, `max`, `plus`, `ultra`, `lite`, `fe`, `neo`, numbers) must be equal — `iPhone 15` ≠ `iPhone 15 Plus`.
- **Model number**: if both sides have one, it decides (normalised, ignoring region suffixes like `/DS`, `INS`). TVs: Amazon model number (e.g. `43UR7500PSC`) usually appears in Flipkart/Croma titles/specs → near-certain match.
- **RAM/storage**: parse `8 GB RAM | 128 GB ROM`, `8GB+128GB`, `1 TB` → integer GB. Must be exactly equal.
- **Screen size**: parse inches or cm (Flipkart writes `108 cm (43 inch)`); convert cm/2.54, round to nearest inch; must be equal (±0.5").
- **Colour**: match on **colour family** with a curated map (`midnight/jet/onyx/phantom/graphite black`→black, `navy/indigo/cobalt`→blue, `white/triple white/ivory`→white…). Multi-colour sneakers: compare the full ordered set (`White/Black` vs `Black/White` OK, `White/Red` ≠ `White/Black`). Exact name match → higher confidence; family-only match → accepted. For Nike/Adidas/Puma, the **style code** (`CW2288-111`) encodes colourway and is the strongest signal.
- **Exclusions** on candidates: refurbished/renewed/open-box, "pack of N"/combo (T-shirts), bundles (TV + soundbar), accessories (cases, covers, screen guards), sponsored/ad tiles.

## 5. Step 3 — Search each platform (adapter pattern)
```python
class PlatformAdapter(Protocol):
    name: str
    async def search(self, fp: Fingerprint) -> list[Candidate]     # top ~10
    async def fetch_details(self, c: Candidate) -> Fingerprint     # spec page
    async def stock_status(self, page) -> IN_STOCK | OUT_OF_STOCK
```
Query building: `brand + model [+ ram/storage | + screen size | + colour]`; if 0 results, retry with a looser query (drop attributes), then a search-engine fallback (`site:flipkart.com <query>`) via a SERP API.

| Platform | Search | Product details | Stock signal |
|---|---|---|---|
| **Flipkart** | `flipkart.com/search?q=` HTML (httpx often works; Playwright fallback) | Specifications table on PDP; variant-specific `pid` in URL | "Sold Out" / "Currently Unavailable" / "Coming Soon" text, or missing *Buy Now/Add to Cart* → out of stock |
| **Croma** | Croma's frontend search JSON endpoint (verify at build time), else HTML | PDP spec section / JSON-LD | Stock is pincode-dependent → fix a default pincode (e.g. Mumbai 400001) and say so in UI; JSON-LD `availability` or "Out of Stock"/"Notify me" button |
| **Myntra** | `myntra.com/<query-slug>` page; results in embedded `window.__myx` JSON | PDP `window.__myx.pdpData` (brand, name, baseColour, articleType) | `sizes[].available` — in stock if **any** size available; all unavailable → out of stock |

Variants: Flipkart phone pages expose RAM/storage/colour variants under one page — we must verify the *selected* variant's specs (and follow variant links if the listed one differs). Myntra/Flipkart fashion list each colour as a separate product, so colour check is per listing.

## 6. Step 4 — Decide the match
1. **Hard filter** (deterministic, cannot be overridden): brand equal; category equal; category-specific attribute equal (RAM+storage / screen / colour family); exclusion rules pass.
2. **Score** survivors: model-number exact (+0.5), model token-set equality (+0.3), title similarity (rapidfuzz token_set_ratio, up to +0.2), exact colour name (+0.05).
3. **Accept** if top score ≥ 0.75. **Borderline** (0.5–0.75) or several near-tied → LLM judge: "Are these the same product given these fingerprints? yes/no + reason". LLM may only *reject or confirm* among hard-filter survivors — never resurrect a hard mismatch.
4. No survivor → **Not listed** (with reason, e.g. "found Galaxy S24 FE but only 8/256, not 8/128").
5. Matched → read stock on the PDP → **In stock / Out of stock** + link.

## 7. Backend architecture
```
app/
  main.py               FastAPI app, routes, serves frontend
  models.py             Fingerprint, PlatformResult (pydantic)
  amazon.py             URL resolve + scrape + parse
  normalize.py          brand/model/units/colour normalisers + tables
  matcher.py            hard filter, scoring, decision
  llm.py                Claude extraction + judge (structured output)
  fetch.py              httpx client, Playwright pool, retries, UA rotation, captcha detect
  platforms/{flipkart,croma,myntra}.py   adapters
  cache.py              TTL cache (in-memory / SQLite) keyed by ASIN
static/index.html       frontend
tests/                  unit + golden-set tests
```
- `POST /api/compare {url}` → `{source: Fingerprint, results: [PlatformResult]}`; optional `GET /api/compare/stream` (SSE) so each platform card fills in as soon as it finishes.
- Platforms run **concurrently** (`asyncio.gather`), each with a timeout (~20 s) and 2 retries; per-platform failure → `ERROR`, never crashes the request.
- Cache Amazon fingerprints (24 h) and platform results (~30 min, stock changes).
- LLM: `claude-haiku-5-5` for extraction (cheap/fast), `claude-sonnet-5-5` for borderline judging; deterministic path works without LLM if the key is missing.
- Deploy: Docker image with Playwright browsers → Render/Railway/Fly; single service serves API + static page.

## 8. Frontend (vibe-coded)
Single page: URL input → "Checking…" → source product card (image, title, extracted brand/model/attributes, so the user sees *what* we searched for) → one card per platform:
- **In stock**: filled green dot, price, "Buy on Flipkart →" link.
- **Out of stock**: filled amber dot, greyed price, "View on Croma →" link.
- **Not listed**: hollow grey dot, "Not sold here", reason in small text.
- (Error: dashed outline, "Couldn't check — retry".)
Plus a few sample Amazon links (one per category) as one-click demo buttons.

## 9. The "explain to a 5-year-old" document (draft)
> Imagine you have a toy and you want to find the **exact same toy** in other shops.
> 1. First I look at your toy really carefully and write down its **name tag**: who made it (brand), what it's called (model), and the one special thing that makes it *this* toy — for phones how much it can remember (RAM and storage), for TVs how big the screen is, for shoes and T-shirts what colour it is.
> 2. Then I walk into each shop and ask, "Do you have toys called this?" The shop shows me a few.
> 3. For each one I write the same kind of name tag. Shops write things differently ("Midnight Black" vs "Black", "108 cm" vs "43 inch"), so I translate everything into the same simple words first.
> 4. If the name tags match on every important thing, it's the same toy! If even one important thing is different — like a red shoe instead of a white shoe — it's *not* the same toy, even if it looks close.
> 5. If I find it, I check: is it on the shelf (**in stock**) or is the shelf empty (**out of stock**)? If no toy in the shop matches, the shop **doesn't sell it**.
> When I'm not sure, I ask a smart helper (AI) to look at both name tags — but the helper is never allowed to say "same" if the colour or size is different.

Delivered as a 1–2 page doc (Markdown/PDF or Google Doc) with a small diagram.

## 10. Risks & mitigations
| Risk | Mitigation |
|---|---|
| Anti-bot blocks (Amazon captcha, Flipkart/Myntra 403) | Real headers, Playwright fallback, low concurrency, retries, optional residential proxy; `ERROR` state instead of false "Not listed" |
| Site HTML changes | Prefer embedded JSON/JSON-LD over CSS selectors; selectors isolated per adapter; golden tests catch breakage |
| Same model, different variant (8/128 vs 8/256, colourways) | Hard filter + variant-specific URLs |
| Colour naming chaos | Colour-family map + style codes + LLM fallback for unknown names |
| Croma stock depends on pincode | Fixed default pincode, shown in UI |
| Slow responses (~10–30 s with browsers) | Parallel adapters, SSE streaming, caching |

## 11. Build plan (milestones)
1. Skeleton: FastAPI, models, `/api/compare` returning mock data + frontend with the 3 states.
2. Amazon extractor + normalisers + unit tests (units, colours, brands, model tokens).
3. Flipkart adapter (covers all 4 categories) + matcher end-to-end.
4. Croma and Myntra adapters.
5. LLM extraction/judge, caching, SSE, error handling.
6. Golden set + polish UI, deploy, write the 5-year-old doc.

## 12. Verification
- **Unit tests** (`pytest`): normalisers — `"108 cm (43 inch)"`→43, `"8GB+128GB"`→(8,128), `"Phantom Black"`→black, `"iPhone 15"`≠`"iPhone 15 Plus"`.
- **Golden set**: ~20 real Amazon links (5 per category, incl. known-out-of-stock and known-not-listed items, plus tricky variant cases) with hand-verified expected status per platform; `pytest -m live` runs them against live sites and reports precision (no false matches is the priority) and recall.
- **Manual E2E**: `uvicorn app.main:app`, paste each golden link in the browser, confirm each state renders distinctly and links open the correct variant page.
