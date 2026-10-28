# JobPilot AI - API and worker image (same image, different command).
# Build context: repository root.
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /srv/api

# Dependencies first for layer caching (versions are pinned in pyproject.toml).
COPY apps/api/pyproject.toml ./
RUN mkdir app && touch app/__init__.py \
    && pip install . \
    && pip uninstall -y jobpilot-api \
    && rm -rf app

COPY apps/api/app ./app
COPY apps/api/alembic ./alembic
COPY apps/api/alembic.ini ./
COPY apps/api/scripts ./scripts

# Unprivileged runtime user; uploads live outside the code tree on a volume.
RUN useradd --system --uid 10001 --home-dir /srv/api jobpilot \
    && mkdir -p /data/uploads \
    && chown -R jobpilot /data
USER jobpilot

ENV UPLOAD_DIR=/data/uploads
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --retries=5 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=4).status == 200 else 1)"

CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*'"]
