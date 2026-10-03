# syntax=docker/dockerfile:1
# Multi-stage image for Railway API + worker (Linux). Gunicorn serves HTTP.
# Local Windows hosting can keep using Waitress outside this image.

FROM python:3.12-slim AS builder

WORKDIR /build
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt gunicorn


FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PDF_STORAGE_DIR=/data/pdfs \
    PORT=5000

RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 finpilot \
    && mkdir -p /data/pdfs \
    && chown -R finpilot:finpilot /data

COPY --from=builder /install /usr/local
WORKDIR /app

COPY app.py config.py extensions.py schemas.py ./
COPY database ./database
COPY routes ./routes
COPY services ./services
COPY scripts ./scripts

RUN chown -R finpilot:finpilot /app
USER finpilot

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD curl -fsS "http://127.0.0.1:${PORT:-5000}/api/health" || exit 1

# Default = API. Set FINPILOT_PROCESS=worker on the Railway worker service.
ENV FINPILOT_PROCESS=api
CMD ["sh", "-c", "if [ \"$FINPILOT_PROCESS\" = \"worker\" ]; then exec python -m services.jobs.worker; else exec gunicorn --workers 2 --timeout 120 --bind 0.0.0.0:${PORT:-5000} \"app:create_app()\"; fi"]
