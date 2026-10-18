# Deploying the Product Matcher

The Product Matcher is a single web service: one Docker image serves both the API and the web page. It needs
no database, no secrets and no paid APIs. This guide covers running it in Docker, then putting it on the
internet with DigitalOcean in Bangalore:

- **[App Platform](#4-deploy-on-app-platform) (recommended):** one click from GitHub, with HTTPS included. No server
  to look after. About $5 a month.
- **[A Droplet](#5-alternative-a-droplet):** your own server running Docker and Caddy. More steps, more control,
  and a way out if Flipkart refuses App Platform's address.

Prices below were current in October 2026. DigitalOcean changes them, so check
https://www.digitalocean.com/pricing before relying on them.

## Contents

1. [What the service needs](#1-what-the-service-needs)
2. [Settings](#2-settings)
3. [Run it in Docker](#3-run-it-in-docker)
4. [Deploy on App Platform](#4-deploy-on-app-platform)
5. [Alternative: a Droplet](#5-alternative-a-droplet)
6. [Update and operate the Droplet](#6-update-and-operate-the-droplet)
7. [Check a deployment](#7-check-a-deployment)
8. [Troubleshooting](#8-troubleshooting)
9. [Security and limits](#9-security-and-limits)

## 1. What the service needs

| Need | Detail |
|---|---|
| Runtime | Docker (the image installs everything) |
| Memory | About 90 MB at peak during a search (measured); the 1 GB Droplet is plenty |
| Port | Listens on `$PORT`, default `8000` |
| Outbound internet | HTTPS to amazon.in, flipkart.com, croma.com, api.croma.com and myntra.com |
| Health check | `GET /api/health` returns `{"status": "ok"}` |
| Storage | None. The cache lives in memory and empties on restart |
| Secrets | None |

**The one real risk is being blocked.** Amazon.in and the shops sometimes refuse requests from data-centre
addresses. Flipkart in particular refuses servers outside India, which is why this guide uses DigitalOcean's
Bangalore region and checks Flipkart from the server
([step 4.2](#42-check-that-flipkart-answers-the-app)). When a shop refuses, the app never guesses: that
shop's card says "Couldn't check".

## 2. Settings

Every setting is an environment variable starting with `MATCHER_`. All are optional. In Docker, pass them
with `-e`, or add them under `environment:` in a compose file.

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
| `PORT` | `8000` | The port the server listens on inside the container |

## 3. Run it in Docker

Needs Docker: [Docker Desktop](https://www.docker.com/products/docker-desktop/) on a Mac or PC, or Docker
Engine on Linux ([step 5.6](#56-install-docker)).

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

The first build takes a few minutes; later builds reuse the dependency layer. If port 8000 is already in use,
stop whatever holds it (`lsof -ti tcp:8000 | xargs kill`) or map another port: `-p 8080:8000`.

What the image does:

- It starts from `python:3.12-slim` and installs the locked dependencies with uv (no development tools).
- It runs as an unprivileged user.
- It checks `/api/health` every 30 seconds.
- It starts `uvicorn app.main:app` on `$PORT`, trusting proxy headers so it works behind a reverse proxy.

## 4. Deploy on App Platform

App Platform builds the `Dockerfile` from GitHub and runs it with HTTPS. `.do/deploy.template.yaml` in this
repository already says everything it needs: Bangalore region (`blr`), port `8000`, the health check on
`/api/health`, the smallest instance (512 MB, $5 a month) and the Croma pincode.

### 4.1 Deploy

1. Sign up at https://cloud.digitalocean.com/registrations/new (a card or PayPal is required).
2. Open this link, which is also the **Deploy to DigitalOcean** button in the README:

   https://cloud.digitalocean.com/apps/new?repo=https://github.com/Deepanshusaxena1/product-matcher/tree/main

3. Check that the region shows **Bangalore**, then click **Create App**. The first build takes a few
   minutes.
4. When the deploy is live, the app's page shows its `https://….ondigitalocean.app` address.

The button only works while the repository is public. For a private repository, create the app by hand
instead: **Create → App Platform → GitHub**, pick the repository, and set the region, port and health check
to the values in `.do/deploy.template.yaml`. Connected that way, App Platform also redeploys on every push.

### 4.2 Check that Flipkart answers the app

Flipkart refuses servers outside India, and sometimes data-centre addresses inside it. On the app's page,
open the **Console** tab and run this (the image has no `curl`, so it uses Python):

```bash
python -c "import urllib.request as u; r = u.Request('https://www.flipkart.com/search?q=samsung+galaxy+s24+fe', headers={'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36'}); print(b'__INITIAL_STATE__' in u.urlopen(r, timeout=15).read())"
```

- `True` means Flipkart served its real results page: you're done. Check the whole app with
  [section 7](#7-check-a-deployment).
- `False` or an HTTP error means Flipkart refused the app's address. The app still runs, but Flipkart's card
  will always say "Couldn't check". App Platform reaches the internet from shared addresses, so either add a
  dedicated egress IP (app **Settings → Networking**, up to $25 a month, then check again) or move to a
  [Droplet](#5-alternative-a-droplet), whose address you can test before installing anything.

### 4.3 Update and operate

| Task | Where |
|---|---|
| Deploy the latest code | App page → **Actions → Force Rebuild and Deploy** (automatic on push if the app is connected through GitHub) |
| Follow the app's log | **Runtime Logs** tab |
| Restart (also empties the cache) | **Actions → Restart** |
| Change a setting | **Settings → web → Environment Variables**, add any `MATCHER_*` variable; saving redeploys |
| Stop paying | **Settings → Destroy App** |

## 5. Alternative: a Droplet

Use this instead of App Platform when Flipkart refuses App Platform's address, or when you want your own
server. The result is one Droplet (DigitalOcean's name for a virtual server) in Bangalore running two containers: the
app, and [Caddy](https://caddyserver.com) in front of it for HTTPS. The Droplet gets a free address of the
form `https://<ip-with-dashes>.sslip.io`, so no domain is needed.

### 5.1 Create an account

Sign up at https://cloud.digitalocean.com/registrations/new. DigitalOcean asks for a card or PayPal before it
lets you create anything. Droplets are billed by the hour up to a monthly cap, and keep billing while powered
off: only **Destroy** stops the charges.

### 5.2 Create the Droplet

In the control panel, open **Create → Droplets**.

| Field | Value |
|---|---|
| Region | **Bangalore** (datacenter **BLR1**) |
| Image | **Ubuntu 24.04 (LTS) x64** |
| Size | **Basic → Regular**, the **1 GB / 1 vCPU** plan (about $6 a month). The 512 MB plan also runs the app, but needs swap to build the image ([step 5.6](#56-install-docker)) |
| Authentication | **SSH Key → New SSH Key**, and paste the contents of your `~/.ssh/id_ed25519.pub` (macOS: `pbcopy < ~/.ssh/id_ed25519.pub` copies it). With no key yet, create one with `ssh-keygen -t ed25519` |
| Hostname | `product-matcher` |

Click **Create Droplet** and wait about a minute. Note the **ipv4** address on the Droplet's page; the rest of
this guide calls it `<IP>`.

### 5.3 Connect over SSH

```bash
ssh root@<IP>
```

DigitalOcean's Ubuntu images log in as `root`. Every command from here on runs on the Droplet.

### 5.4 Check that Flipkart answers the server

Do this before installing anything. It asks for the same search page the app reads:

```bash
curl -s -A "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36" \
  "https://www.flipkart.com/search?q=samsung+galaxy+s24+fe" | grep -c "__INITIAL_STATE__"
```

- `1` means Flipkart served its real results page: carry on.
- `0` means Flipkart refused this Droplet's address. The app would still run, but Flipkart's card would
  always say "Couldn't check". Destroy the Droplet (**Destroy → Destroy this Droplet**) and create a new one:
  it gets a different address, which Flipkart may accept.

### 5.5 Add a Cloud Firewall

A new Droplet accepts traffic on every port. A Cloud Firewall (free) closes all but the ones the app needs.
Use it rather than `ufw` on the server: ports Docker publishes skip `ufw`'s rules, but they can't skip a
Cloud Firewall.

1. Open **Networking → Firewalls → Create Firewall**. Name it `product-matcher`.
2. Under **Inbound Rules**, keep the **SSH** rule and add **HTTP** and **HTTPS**, each from
   **All IPv4** and **All IPv6**.
3. Leave the **Outbound Rules** as they are (all traffic allowed; the app needs it to reach the shops).
4. Under **Apply to Droplets**, choose `product-matcher`, then **Create Firewall**.

### 5.6 Install Docker

```bash
curl -fsSL https://get.docker.com | sh
docker version
docker compose version     # needs v2.24 or newer for the file in step 5.8
```

**On the 512 MB plan only**, add swap so the image build can't run out of memory:

```bash
fallocate -l 2G /swapfile && chmod 600 /swapfile
mkswap /swapfile && swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab
```

### 5.7 Get the code

The repository is public, so no credentials are needed:

```bash
git clone https://github.com/Deepanshusaxena1/product-matcher.git
cd product-matcher
```

### 5.8 Add HTTPS with Caddy

Create `compose.prod.yaml` next to `compose.yaml`. It adds Caddy and stops publishing the app's own port, so
the only way in is through HTTPS:

```bash
cat > compose.prod.yaml <<'EOF'
services:
  matcher:
    ports: !reset []        # reachable only through Caddy
  caddy:
    image: caddy:2
    restart: unless-stopped
    command: caddy reverse-proxy --from ${SITE_ADDRESS} --to matcher:8000
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - caddy-data:/data    # keeps the certificate across restarts
    depends_on:
      - matcher
volumes:
  caddy-data:
EOF
```

Then write a `.env` file that tells Docker Compose to use both files and sets the site address from the
Droplet's public IP:

```bash
cat > .env <<EOF
COMPOSE_FILE=compose.yaml:compose.prod.yaml
SITE_ADDRESS=$(curl -s https://ifconfig.me | tr . -).sslip.io
EOF
cat .env
```

`SITE_ADDRESS` should look like `139-59-10-20.sslip.io`: sslip.io answers any such name with the IP inside
it, which is enough for Caddy to get a free Let's Encrypt certificate. `.env` is ignored by Git and
`compose.prod.yaml` isn't in the repository, so `git pull` leaves both alone.

With a domain of your own, point an `A` record at `<IP>` and set `SITE_ADDRESS` to that name instead.

### 5.9 Start it

```bash
docker compose up -d --build
docker compose ps          # both services "running"; matcher becomes "healthy" within a minute
```

The first build takes a few minutes. Then open `https://<SITE_ADDRESS>` in a browser.

Both containers restart on their own after a crash or a Droplet reboot (`restart: unless-stopped`, and the
Docker service starts at boot).

## 6. Update and operate the Droplet

All from `~/product-matcher` on the Droplet. Because `.env` sets `COMPOSE_FILE`, plain `docker compose`
commands include Caddy.

| Task | Command |
|---|---|
| Deploy the latest code | `git pull && docker compose up -d --build` |
| Follow the app's log | `docker compose logs -f matcher` |
| Follow Caddy's log (certificates, requests) | `docker compose logs -f caddy` |
| Restart (also empties the cache) | `docker compose restart matcher` |
| Change a setting | Add it under `matcher: environment:` in `compose.prod.yaml`, then `docker compose up -d` |
| Stop everything | `docker compose down` |
| Free disk space from old builds | `docker image prune -f` |

A setting added to `compose.prod.yaml` survives `git pull`. Editing `compose.yaml` on the Droplet would make
the next `git pull` conflict.

To stop paying, destroy the Droplet from its page (**Destroy**). Powering it off does not stop billing.

## 7. Check a deployment

Replace `$URL` with the deployment's address (`https://<SITE_ADDRESS>`, the `ondigitalocean.app` address, or
`http://localhost:8000` for local Docker).

```bash
curl -s $URL/api/health
# {"status":"ok"}

curl -sN -X POST $URL/api/compare/stream \
  -H 'Content-Type: application/json' \
  -d '{"url":"https://www.amazon.in/dp/B0GTZ9TSDJ"}'
# event: source … then one "event: result" per shop … then "event: done"
```

Then open `$URL` in a browser and click each sample button. Every shop should give an answer: in stock, out
of stock or not listed. A "Couldn't check" means that shop refused the server ([section 8](#8-troubleshooting)).

## 8. Troubleshooting

| What you see | Why | What to do |
|---|---|---|
| `ssh` times out | Wrong IP, the Droplet is still booting, or the Cloud Firewall lacks the SSH rule | Check the Droplet's page and the firewall's inbound rules ([5.5](#55-add-a-cloud-firewall)) |
| `ssh` says "Permission denied (publickey)" | The Droplet doesn't have your key | Use the key you added at creation (`ssh -i ~/.ssh/id_ed25519 root@<IP>`), or reset access from the Droplet's **Access** page |
| The browser can't reach the site at all | HTTP/HTTPS is missing from the Cloud Firewall, or the firewall isn't applied to this Droplet | Check **Networking → Firewalls → product-matcher** ([5.5](#55-add-a-cloud-firewall)) |
| Caddy's log shows certificate errors | Let's Encrypt couldn't reach the Droplet on port 80, or `SITE_ADDRESS` doesn't contain this Droplet's IP | Fix the firewall; check `cat .env`; then `docker compose restart caddy` |
| `docker compose up` says `!reset` is unknown | Docker Compose is older than v2.24 | Reinstall Docker ([5.6](#56-install-docker)) to get a current version |
| One shop always says "Couldn't check" | That shop blocks the server's address | `docker compose logs matcher \| grep "could not be checked"` shows the refusal; the other shops still answer. On App Platform, read the app's **Runtime Logs**, and see [4.2](#42-check-that-flipkart-answers-the-app) for Flipkart |
| Every search says "Amazon.in couldn't be read just now" | Amazon is refusing or throttling the server's address | Wait a few minutes and retry; Amazon throttles bursts of searches |
| A repeated search answers instantly with "Checked N min ago" | The answer came from the 30-minute cache | Normal; `docker compose restart matcher` or lower `MATCHER_RESULT_CACHE_TTL_S` to force fresh checks |
| Croma's stock differs from the Croma site | Croma's stock depends on the delivery pincode | Set `MATCHER_CROMA_PINCODE` |
| `docker compose up` fails with "port is already allocated" | Something else uses that port | `lsof -i :80 -i :443` (Droplet) or `lsof -ti tcp:8000 \| xargs kill` (local) |
| The build fails at `uv sync --frozen` | `uv.lock` is out of date with `pyproject.toml` | Run `uv lock` on your own machine, commit `uv.lock`, push, then `git pull` on the Droplet |
| The build is killed partway on the 512 MB plan | The Droplet ran out of memory | Add swap ([5.6](#56-install-docker)) and build again |
| App Platform's deploy fails its health check | The HTTP port isn't `8000` or the path isn't `/api/health` | Fix both in the service's settings ([section 4](#4-deploy-on-app-platform)) and redeploy |

## 9. Security and limits

- **No secrets anywhere.** The Croma key is public: Croma ships it to every visitor's browser.
- **No login.** Anyone with the address can run searches, and each search makes requests to the shops in
  the server's name. Share the address only with the people who need it, and stop the service
  (**Destroy App**, or `docker compose down` on a Droplet) when it isn't needed.
- **Only Amazon.in is ever fetched from a pasted link.** Any other link is refused before a request is made.
- **HTTPS only.** App Platform serves the app over HTTPS itself. On a Droplet, the Cloud Firewall leaves only
  ports 22, 80 and 443 open, the app's port 8000 isn't published, and Caddy redirects HTTP to HTTPS.
- **One instance only.** The cache is in memory, so several instances wouldn't share answers. One instance is
  plenty for a demo.
- **Keep the Droplet patched**: `apt update && apt upgrade -y`, then `reboot` when asked.
