# =============================================================================
# Backend + Worker — imagem multi-stage, usuario nao-root, SEM segredo embutido.
# =============================================================================

# ---------- stage 1: builder -------------------------------------------------
FROM python:3.12-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN python -m venv /opt/venv \
 && /opt/venv/bin/pip install --upgrade pip \
 && /opt/venv/bin/pip install -r requirements.txt

# ---------- stage 2: runtime -------------------------------------------------
FROM python:3.12-slim AS runtime

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN apt-get update \
 && apt-get install -y --no-install-recommends curl \
 && rm -rf /var/lib/apt/lists/* \
 && groupadd --gid 10001 app \
 && useradd --uid 10001 --gid app --create-home app

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
COPY --chown=app:app . /app
RUN chmod +x /app/scripts/*.sh \
 && mkdir -p /app/outbox \
 && chown -R app:app /app/outbox

USER app

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=5s --start-period=25s --retries=6 \
  CMD curl -fsS http://localhost:8000/health || exit 1

CMD ["/app/scripts/start-api.sh"]
