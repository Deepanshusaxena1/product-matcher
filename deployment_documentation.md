# Deploying the Product Matcher

The Product Matcher is a single web service: one Docker image serves both the API and the web page. It needs
no database. This guide covers running it in Docker, then putting it on the internet on
[Render](https://render.com), with Flipkart and Myntra reached through a proxy in India.

Prices below were current in October 2026. Render and ZenRows change them, so check
https://render.com/pricing and https://www.zenrows.com/pricing before relying on them.

## Contents

1. [What the service needs](#1-what-the-service-needs)
2. [Settings](#2-settings)
3. [Run it in Docker](#3-run-it-in-docker)
4. [Why Render, and why a proxy for Flipkart and Myntra](#4-why-render-and-why-a-proxy-for-flipkart-and-myntra)
5. [Set up the proxy](#5-set-up-the-proxy)
6. [Deploy on Render](#6-deploy-on-render)
7. [Update and operate](#7-update-and-operate)
8. [Check a deployment](#8-check-a-deployment)
9. [Troubleshooting](#9-troubleshooting)
10. [Security and limits](#10-security-and-limits)

## 1. What the service needs

| Need | Detail |
|---|---|
| Runtime | Docker (the image installs everything) |
| Memory | About 90 MB at peak during a search (measured); Render's free 512 MB instance is plenty |
| Port | Listens on `$PORT`, default `8000` |
| Outbound internet | HTTPS to amazon.in, flipkart.com, croma.com, api.croma.com and myntra.com |
| Health check | `GET /api/health` returns `{"status": "ok"}` |
| Storage | None. The cache lives in memory and empties on restart |
| Secrets | One, optional: the proxy address, which contains its key or password |

## 2. Settings

Every setting is an environment variable starting with `MATCHER_`. All are optional. In Docker, pass them
with `-e`, or add them under `environment:` in a compose file. On Render, add them under the service's
**Environment**.

| Variable | Default | What it does |
|---|---|---|
| `MATCHER_DEMO` | `false` | `true` serves bundled sample results instead of searching the shops (offline, instant) |
| `MATCHER_CROMA_PINCODE` | `400001` (Mumbai) | Where Croma's stock is checked for; the result card names it |
| `MATCHER_CROMA_INVENTORY_KEY` | unset | Pins Croma's public stock-check key; unset, it is read from Croma's own script |
| `MATCHER_PROXY_URL` | unset | Proxy that the proxied shops' requests, and only theirs, go through ([section 5](#5-set-up-the-proxy)). Unset, every shop is fetched directly. `MATCHER_FLIPKART_PROXY_URL` is read too, as its older name |
| `MATCHER_PROXIED_SHOPS` | `flipkart,myntra` | Which shops go through the proxy, comma-separated (`flipkart`, `croma`, `myntra`) |
| `MATCHER_PROXY_CA_PATH` | unset | The proxy's CA certificate file. Unset, the proxy's certificate isn't checked |
| `MATCHER_PROXY_TIMEOUT_S` | `30` | Time limit for one request through the proxy, in seconds (the proxy retries for us, so it can be slow) |
| `MATCHER_FETCH_TIMEOUT_S` | `15` | Time limit for one direct request to a shop, in seconds |
| `MATCHER_PLATFORM_TIMEOUT_S` | `45` | Time limit for everything done for one shop, in seconds |
| `MATCHER_PRODUCT_CACHE_TTL_S` | `86400` (24 h) | How long an Amazon product is remembered |
| `MATCHER_RESULT_CACHE_TTL_S` | `1800` (30 min) | How long a shop's answer is reused; "Couldn't check" is never cached |
| `MATCHER_CACHE_MAX_ENTRIES` | `1000` | Size of each in-memory cache |
| `PORT` | `8000` | The port the server listens on inside the container |

## 3. Run it in Docker

Needs Docker: [Docker Desktop](https://www.docker.com/products/docker-desktop/) on a Mac or PC, or Docker
Engine on Linux.

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

From a home connection in India every shop answers directly, so no proxy is needed locally. The first build
takes a few minutes; later builds reuse the dependency layer. If port 8000 is already in use, stop whatever
holds it (`lsof -ti tcp:8000 | xargs kill`) or map another port: `-p 8080:8000`.

What the image does:

- It starts from `python:3.12-slim` and installs the locked dependencies with uv (no development tools).
- It runs as an unprivileged user.
- It checks `/api/health` every 30 seconds.
- It starts `uvicorn app.main:app` on `$PORT`, trusting proxy headers so it works behind Render's router.

## 4. Why Render, and why a proxy for Flipkart and Myntra

The shops decide whom they answer, and no single host suits all of them. Measured on 2026-10-18:

| Where the app ran | Amazon | Flipkart | Croma | Myntra |
|---|---|---|---|---|
| Home connection in India (Airtel) | Answers | Answers | Answers | Answers |
| Render, Singapore | Answers | Throttles every request (HTTP 429) | Answers | Serves a page with no results |
| DigitalOcean App Platform, Bangalore | Answers | Answers, but rate-limits (HTTP 429) | Refuses all of DigitalOcean's addresses (HTTP 403) | Not measured |

Render suits Amazon and Croma, and Flipkart and Myntra turn away servers outside India whichever host runs
them. So the app runs on Render, and Flipkart's and Myntra's requests alone go through
[ZenRows](https://www.zenrows.com), which fetches each page from an Indian home connection. Amazon and Croma
are still fetched directly, so the proxy carries only those two shops' requests.

When a shop refuses anyway, the app never guesses: that shop's card says "Couldn't check" and the others
still answer.

`.do/deploy.template.yaml` describes the DigitalOcean App Platform setup that was tried; it isn't used here,
because Croma refuses DigitalOcean.

## 5. Set up the proxy

Skip this section to deploy without it: Flipkart's and Myntra's cards will then say "Couldn't check".

### 5.1 Get a ZenRows key

1. Sign up at https://app.zenrows.com/register. The free plan is 5,000 credits a month with no card.
2. Copy the **API key** from the **Fetch** playground.

A request through ZenRows' Indian home connections ("premium proxies") costs about 10 credits. A search makes
roughly 5–15 requests to each proxied shop, and the 30-minute cache saves repeats, so the free plan covers
a few dozen searches a month. ZenRows' dashboard shows the credits used.

### 5.2 Build the proxy address

```
http://<API key>:premium_proxy=true&proxy_country=in@api.zenrows.com:8001
```

- `premium_proxy=true&proxy_country=in` asks for an Indian home connection, which Flipkart and Myntra require.
- This address contains the API key. Treat it as a secret: put it only in Render's environment, never in the
  repository.

To try it from your own machine before deploying (the count should be `1`: Flipkart's real results page):

```bash
P='http://<API key>:premium_proxy=true&proxy_country=in@api.zenrows.com:8001'
curl -sk -x "$P" 'https://www.flipkart.com/search?q=samsung+galaxy+s24+fe' | grep -c __INITIAL_STATE__
```

ZenRows refuses IP-lookup sites such as ipinfo.io (error `REQS001`), so test with a shop's page.

**Bright Data instead of ZenRows.** Any proxy that gives Indian addresses works. With Bright Data, create a
**Web Unlocker API** zone (under **Web Access → Add API**; not Browser API, whose addresses start with
`wss://`) and use `http://brd-customer-<customer id>-zone-<zone name>-country-in:<zone password>@<host>:<port>`
with the host and port the zone shows.

### 5.3 Optional: verify the proxy's certificate

ZenRows and Bright Data re-sign the pages they fetch with their own certificate. Without that certificate, the
app accepts whatever certificate the proxy presents. That is acceptable here (the pages are public and no user
data passes through), but to check it:

1. Download the provider's CA certificate (Bright Data: the zone's **SSL certificate** page).
2. On Render, open the service's **Environment → Secret Files**, add a file named `proxy-ca.crt` and paste the
   certificate in. Render mounts it at `/etc/secrets/proxy-ca.crt`.
3. Set `MATCHER_PROXY_CA_PATH=/etc/secrets/proxy-ca.crt`.

## 6. Deploy on Render

`render.yaml` in this repository describes the service: Docker, Singapore region, free plan, the health check
on `/api/health`, the Croma pincode, and a prompt for the proxy.

1. Sign up at https://render.com and connect your GitHub account.
2. Click the **Deploy to Render** button in the README, or open **New → Blueprint** and pick this repository.
3. When Render asks for `MATCHER_PROXY_URL`, paste the address from
   [step 5.2](#52-build-the-proxy-address). Leave it empty to deploy without the proxy.
4. Click **Apply**. The first build takes a few minutes; the service's page then shows its
   `https://….onrender.com` address.

**Already deployed from this blueprint before the proxy existed?** Render only asks for secrets when a
blueprint is first created. Open the service's **Environment**, add `MATCHER_PROXY_URL` with the
address, and save; Render redeploys.

**The free plan sleeps.** A free service stops after 15 minutes without visitors, and the next visitor waits
about a minute while it starts. For a demo, open the address a minute before showing it, or move to the
Starter plan (about $7 a month), which stays awake.

## 7. Update and operate

| Task | Where |
|---|---|
| Deploy the latest code | Automatic on every push to `main`; or **Manual Deploy → Deploy latest commit** |
| Follow the app's log | The service's **Logs** tab |
| Restart (also empties the cache) | **Manual Deploy → Restart service** |
| Change a setting | **Environment**: add or edit any `MATCHER_*` variable; saving redeploys |
| See what the proxy costs | ZenRows' dashboard (credits used) |
| Stop the proxy | Remove `MATCHER_PROXY_URL`; Flipkart's and Myntra's cards go back to "Couldn't check" |
| Stop everything | **Settings → Suspend service**, or **Delete service** |

## 8. Check a deployment

Replace `$URL` with the deployment's address (`https://….onrender.com`, or `http://localhost:8000` for local
Docker).

```bash
curl -s $URL/api/health
# {"status":"ok"}

curl -sN -X POST $URL/api/compare/stream \
  -H 'Content-Type: application/json' \
  -d '{"url":"https://www.amazon.in/dp/B0GTZ9TSDJ"}'
# event: source … then one "event: result" per shop … then "event: done"
```

Then open `$URL` in a browser and click each sample button. Every shop should give an answer: in stock, out
of stock or not listed. A "Couldn't check" means that shop refused the server ([section 9](#9-troubleshooting)).

## 9. Troubleshooting

The service's **Logs** tab names the reason for every "Couldn't check": search it for
`could not be checked`. The line under it says what the shop or the proxy answered.

| What you see | Why | What to do |
|---|---|---|
| The first page load takes about a minute | The free plan was asleep | Normal on the free plan ([section 6](#6-deploy-on-render)) |
| Flipkart says "Couldn't check" with `HTTP 429`, or Myntra with "returned a page without results" | No proxy is set, so the shop sees a server outside India | Set `MATCHER_PROXY_URL` ([section 5](#5-set-up-the-proxy)) |
| The log shows `CONNECT tunnel failed, response 407` | Bright Data rejected the proxy's user name or password | Rebuild the address from the zone's access details ([5.2](#52-build-the-proxy-address)) |
| The log shows `over proxy` with `Could not connect` or a timeout | Wrong proxy host or port, or the zone is disabled | Check the zone in Bright Data and the host and port in the address |
| The log shows a certificate error for flipkart.com or myntra.com | `MATCHER_PROXY_CA_PATH` points at a missing or wrong file | Re-add the secret file ([5.3](#53-optional-verify-the-proxys-certificate)), or remove the setting |
| Flipkart works, then stops working at the start of a month or after a burst of searches | The free tier's 5,000 requests are used up, or the spending limit was hit | Check the zone's statistics and billing in Bright Data |
| Croma or Amazon says "Couldn't check" | That shop is refusing or throttling Render's address | Wait a few minutes and retry; Amazon throttles bursts of searches |
| A repeated search answers instantly with "Checked N min ago" | The answer came from the 30-minute cache | Normal; restart the service or lower `MATCHER_RESULT_CACHE_TTL_S` to force fresh checks |
| Croma's stock differs from the Croma site | Croma's stock depends on the delivery pincode | Set `MATCHER_CROMA_PINCODE` |
| The build fails at `uv sync --frozen` | `uv.lock` is out of date with `pyproject.toml` | Run `uv lock` on your own machine, commit `uv.lock` and push |

## 10. Security and limits

- **One secret.** The proxy address contains its key or password: keep it in Render's environment only.
  The app keeps it out of its own logs and settings output. The Croma key is not a secret: Croma ships it to
  every visitor's browser.
- **No login.** Anyone with the address can run searches, and each search makes requests to the shops in the
  server's name, and through the proxy at your cost. Share the address only with the people who need it, set
  a spending limit on the Bright Data zone, and suspend the service when it isn't needed.
- **Only Amazon.in is ever fetched from a pasted link.** Any other link is refused before a request is made.
- **HTTPS only.** Render serves the app over HTTPS and redirects HTTP to it.
- **One instance only.** The cache is in memory, so several instances wouldn't share answers. One instance is
  plenty for a demo.
