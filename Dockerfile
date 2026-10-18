# syntax=docker/dockerfile:1
# One image serves the API and the web page. Build: docker build -t product-matcher .
# Run:   docker run -p 8000:8000 product-matcher      (MATCHER_* variables configure it; see app/config.py)
FROM python:3.12-slim

# The same uv version that wrote uv.lock, so the lock file always reads.
COPY --from=ghcr.io/astral-sh/uv:0.12.19 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Dependencies first, so code changes reuse this layer.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY app ./app
COPY static ./static
RUN uv sync --frozen --no-dev

RUN useradd --create-home --uid 10001 matcher
USER matcher

ENV PATH="/app/.venv/bin:$PATH" \
    PORT=8000
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ[\"PORT\"]}/api/health', timeout=4)"

# PORT is set by hosts such as Render; the proxy headers keep client addresses right behind their router.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port \"$PORT\" --proxy-headers --forwarded-allow-ips='*'"]
