# syntax=docker/dockerfile:1.7
# ---- DecOps API (FastAPI + WeasyPrint) -------------------------------------
FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
# WeasyPrint runtime libraries + a font so PDFs render text.
RUN apt-get update && apt-get install -y --no-install-recommends \
      libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b libffi8 fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /usr/local/bin/uv
WORKDIR /srv/backend

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app
COPY docker-entrypoint.sh ./
RUN chmod +x docker-entrypoint.sh \
 && useradd --system --uid 10001 --home /srv/backend decops \
 && mkdir -p /data && chown -R decops:decops /data /srv/backend

ENV PATH="/srv/backend/.venv/bin:$PATH" \
    DECOPS_ENVIRONMENT=production \
    DECOPS_DEBUG=false \
    DECOPS_SECURE_COOKIES=true \
    DECOPS_ATTACHMENT_STORAGE_DIR=/data/attachments \
    DECOPS_IMPORT_STORAGE_DIR=/data/imports \
    PORT=8000
USER decops
VOLUME ["/data"]
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD python -c "import os,urllib.request as u;u.urlopen('http://127.0.0.1:'+os.environ.get('PORT','8000')+'/api/v1/health',timeout=4)"
ENTRYPOINT ["./docker-entrypoint.sh"]
