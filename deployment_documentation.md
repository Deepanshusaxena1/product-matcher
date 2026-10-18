# Deploying the Product Matcher

The Product Matcher is a single web service: one Docker image serves both the API and the web page. It needs
no database, no secrets and no paid APIs. This guide covers running it locally, running it in Docker, and
putting it on the internet for free.

Free-tier terms below were current in October 2026. Providers change them, so check the provider's pricing
page before relying on them.

## Contents

1. [What the service needs](#1-what-the-service-needs)
2. [Settings](#2-settings)
3. [Run it locally](#3-run-it-locally)
4. [Run it in Docker](#4-run-it-in-docker)
5. [Put the code on GitHub](#5-put-the-code-on-github)
6. [Choose a free host](#6-choose-a-free-host)
7. [Deploy on Render (recommended)](#7-deploy-on-render-recommended)
8. [Deploy on Hugging Face Spaces](#8-deploy-on-hugging-face-spaces)
9. [Deploy on Koyeb](#9-deploy-on-koyeb)
10. [Share your own machine with Cloudflare Tunnel](#10-share-your-own-machine-with-cloudflare-tunnel)
11. [Check a deployment](#11-check-a-deployment)
12. [Troubleshooting](#12-troubleshooting)
13. [Security and limits](#13-security-and-limits)

## 1. What the service needs

| Need | Detail |
|---|---|
| Runtime | Python 3.12, or Docker (the image installs everything) |
| Memory | About 90 MB at peak during a search (measured); any free tier with 512 MB is enough |
| Port | Listens on `$PORT`, default `8000` |
| Outbound internet | HTTPS to amazon.in, flipkart.com, croma.com, api.croma.com and myntra.com |
| Health check | `GET /api/health` returns `{"status": "ok"}` |
| Storage | None. The cache lives in memory and empties on restart |
| Secrets | None |

**The one real risk is being blocked.** Amazon.in and the shops sometimes refuse requests from data-centre
addresses, which is where every cloud host runs. When that happens the app never guesses: the page shows
"Amazon.in couldn't be read just now" or a shop's card says "Couldn't check". If a cloud host is blocked,
[Cloudflare Tunnel](#10-share-your-own-machine-with-cloudflare-tunnel) serves the app from your own
connection instead.

## 2. Settings

Every setting is an environment variable starting with `MATCHER_`. All are optional.

| Variable | Default | What it does |
|---|---|---|
| `MATCHER_DEMO` | `false` | `true` serves bundled sample results instead of searching the shops (offline, instant) |
| `MATCHER_CROMA_PINCODE` | `400001` (Mumbai) | Where Croma's stock is checked for; the result card names it |
| `MATCHER_CROMA_INVENTORY_KEY` | unset | Pins Croma's public stock-check key; unset, it is read from Croma's own script |
| `MATCHER_FETCH_TIMEOUT_S` | `15` | Time limit for one request to a shop, in seconds |
| `MATCHER_PLATFORM_TIMEOUT_S` | `45` | Time limit for everything done for one shop, in seconds |
| `MATCHER_PRODUCT_CACHE_TTL_S` | `86400` (24 h) | How long an Amazon product is remembered |
| `MATCHER_RESULT_CACHE_TTL_S` | `1800` (30 min) | How long a shop's answer is reused; "Couldn't check" is never cached |
| `MATCHER_CACHE_MAX_ENTRIES` | `1000` | Size of each in-memory cache |
| `PORT` | `8000` | The port the server listens on (set automatically by most hosts) |

## 3. Run it locally

Needs [uv](https://docs.astral.sh/uv/), which also installs Python 3.12 if it is missing.

```bash
cd scruge-assignment
uv sync
uv run uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000.

Open the page from the server's address, not with an IDE's HTML preview (PyCharm's preview runs on port
63342). A preview has no search behind it, so every search there fails.

## 4. Run it in Docker

Needs [Docker Desktop](https://www.docker.com/products/docker-desktop/) running.

```bash
docker compose up --build          # build the image and serve http://localhost:8000
docker compose up --build -d       # the same, in the background
docker compose down                # stop it
```

Without compose:

```bash
docker build -t product-matcher .
docker run -p 8000:8000 product-matcher
docker run -p 8000:8000 -e MATCHER_CROMA_PINCODE=560001 product-matcher   # with a setting
```

The first build takes a few minutes; later builds reuse the dependency layer. If port 8000 is already in use
(for example by a `uvicorn` you started by hand), stop that first: `lsof -ti tcp:8000 | xargs kill`.

What the image does:

- It starts from `python:3.12-slim` and installs the locked dependencies with uv (no development tools).
- It runs as an unprivileged user.
- It checks `/api/health` every 30 seconds.
- It starts `uvicorn app.main:app` on `$PORT`.

## 5. Put the code on GitHub

Render, Hugging Face and Koyeb all deploy from a Git repository.

1. Create an empty repository on https://github.com/new. A private repository works with all three hosts.
2. Decide what to leave out. The assignment brief (`$cruge - Founding Backend Engineer Assignment.pdf`) and
   the `.claude/` folder are not needed to run the app. To exclude them, add them to `.gitignore`:

   ```bash
   printf '%s\n' '*.pdf' '.claude/' >> .gitignore
   ```

3. Commit and push:

   ```bash
   git init
   git add .
   git commit -m "Product Matcher"
   git branch -M main
   git remote add origin https://github.com/<your-user>/<your-repo>.git
   git push -u origin main
   ```

GitHub Pages cannot host this app: it serves only static files, and the app needs a running server for every
search.

## 6. Choose a free host

| Host | Free terms | Card needed | Notes |
|---|---|---|---|
| **Render** | Free web service; sleeps after 15 min without visitors, about a minute to wake | No | Builds the `Dockerfile`; `render.yaml` is ready; Singapore region, closest to the shops |
| **Hugging Face Spaces** | Free CPU (2 vCPU, 16 GB); sleeps after 48 h without visitors | No | Builds the `Dockerfile`; US/EU servers |
| **Koyeb** | One small free web service; sleeps when unused | No | Builds the `Dockerfile`; US/EU servers |
| **Cloudflare Tunnel** | Free quick tunnel to a server on your own machine | No | Uses your home connection, which the shops accept; your machine must stay on |

For a one- or two-day demo: try Render first, and keep Cloudflare Tunnel as the fallback.

## 7. Deploy on Render (recommended)

The repository includes `render.yaml` (a Render "Blueprint"): one free Docker web service in Singapore with a
health check on `/api/health`.

1. Push the code to GitHub ([section 5](#5-put-the-code-on-github)).
2. Sign up at https://render.com with your GitHub account.
3. Choose **New → Blueprint**, pick the repository, and approve. Render reads `render.yaml`.
4. Wait for the first build (5–10 minutes). The log ends with `Uvicorn running on http://0.0.0.0:…`.
5. Open the address Render shows, such as `https://product-matcher.onrender.com`.

Every push to `main` deploys again automatically. To change a setting, open the service's **Environment**
tab, add a `MATCHER_…` variable, and save; Render restarts the service.

On the free plan, the first visit after 15 idle minutes waits about a minute while the service wakes, and
the cache starts empty each time.

## 8. Deploy on Hugging Face Spaces

1. Sign up at https://huggingface.co and choose **New Space**.
2. Pick the **Docker** SDK, the free **CPU basic** hardware, and public or private visibility.
3. The Space's `README.md` must start with this settings block, which tells Hugging Face the app's port:

   ```yaml
   ---
   title: Product Matcher
   sdk: docker
   app_port: 8000
   ---
   ```

   Add it to the top of the `README.md` you push to the Space. Only the Space's copy needs it, not GitHub's.

4. Push the code to the Space's Git repository:

   ```bash
   git remote add space https://huggingface.co/spaces/<your-user>/<your-space>
   git push space main
   ```

5. The Space builds the `Dockerfile` and shows the app on its page, at
   `https://<your-user>-<your-space>.hf.space`.

Settings go under the Space's **Settings → Variables**.

## 9. Deploy on Koyeb

1. Push the code to GitHub ([section 5](#5-put-the-code-on-github)).
2. Sign up at https://www.koyeb.com and choose **Create Web Service → GitHub**, then pick the repository.
3. Choose the **Dockerfile** builder and the free instance.
4. Set the exposed port to `8000` and the health check path to `/api/health`.
5. Deploy, then open the `https://….koyeb.app` address Koyeb shows.

## 10. Share your own machine with Cloudflare Tunnel

This gives the server running on your Mac a temporary public HTTPS address. Requests to the shops then come
from your own connection, which they already accept.

1. Start the app locally ([section 3](#3-run-it-locally) or [section 4](#4-run-it-in-docker)).
2. Install and start a quick tunnel:

   ```bash
   brew install cloudflared
   cloudflared tunnel --url http://localhost:8000
   ```

3. Share the `https://….trycloudflare.com` address it prints.

The address works while both the app and `cloudflared` are running, and changes each time the tunnel
restarts. Keep the Mac awake for the length of the demo (macOS: `caffeinate -d` in another terminal).

## 11. Check a deployment

Replace `$URL` with the deployment's address.

```bash
curl -s $URL/api/health
# {"status":"ok"}

curl -sN -X POST $URL/api/compare/stream \
  -H 'Content-Type: application/json' \
  -d '{"url":"https://www.amazon.in/dp/B0GTZ9TSDJ"}'
# event: source … then one "event: result" per shop … then "event: done"
```

Then open `$URL` in a browser and click each sample button. Every shop should give an answer: in stock, out
of stock or not listed. A "Couldn't check" means that shop refused the server ([section 12](#12-troubleshooting)).

Before deploying a change, run the checks locally:

```bash
uv run pytest                                          # 434 offline tests
uv run pytest -m live tests/live/test_golden_set.py    # 22 hand-checked products against the live shops
```

## 12. Troubleshooting

| What you see | Why | What to do |
|---|---|---|
| Every search says "Amazon.in couldn't be read just now" | Amazon is refusing or throttling the host's address | Wait a few minutes and retry; if it persists, the host is blocked, so use Cloudflare Tunnel |
| One shop always says "Couldn't check" | That shop blocks the host's address | As above; the other shops still answer |
| "The search isn't available right now" | The page can't reach the API: an IDE preview, or the server is down | Open the page from the server's own address; check `/api/health` |
| The first visit takes about a minute | The free instance was asleep | Normal on free tiers; later visits are fast |
| A repeated search answers instantly with "Checked N min ago" | The answer came from the 30-minute cache | Normal; restart the service or lower `MATCHER_RESULT_CACHE_TTL_S` to force fresh checks |
| Croma's stock differs from the Croma site | Croma's stock depends on the delivery pincode | Set `MATCHER_CROMA_PINCODE` |
| `docker compose up` fails with "port is already allocated" | Something else uses port 8000 | `lsof -ti tcp:8000 \| xargs kill`, or map another port: `-p 8080:8000` |
| The build fails at `uv sync --frozen` | `uv.lock` is out of date with `pyproject.toml` | Run `uv lock` locally, commit `uv.lock`, push again |

## 13. Security and limits

- **No secrets anywhere.** The Croma key is public: Croma ships it to every visitor's browser.
- **No login.** Anyone with the address can run searches, and each search makes requests to the shops in
  the server's name. Share the address only with the people who need it, and stop the service after the demo.
- **Only Amazon.in is ever fetched from a pasted link.** Any other link is refused before a request is made.
- **One instance only.** The cache is in memory, so several instances wouldn't share answers. One instance is
  plenty for a demo.
