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

# Os DOIS arquivos. `requirements-prod.txt` traz os SDKs dos adaptadores reais
# (anthropic, boto3, stripe), que so sao importados DENTRO da primeira chamada
# real — nao no arranque. Sem eles a imagem sobe healthy em mock e quebra no
# dia da virada: LLM_MODE/SEARCH_MODE=real dao ModuleNotFoundError na primeira
# pergunta, BILLING_MODE=real na primeira compra, e com EMAIL_MODE=real todo
# e-mail vira FALHOU "transitorio", em silencio, sem pausar nada. Os testes
# nao pegam: injetam cliente falso e nunca executam o `import`.
COPY requirements.txt requirements-prod.txt ./
RUN python -m venv /opt/venv \
 && /opt/venv/bin/pip install --upgrade pip \
 && /opt/venv/bin/pip install -r requirements.txt -r requirements-prod.txt

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

# Trava de build: se alguem tirar um SDK dos requirements, a imagem nao nasce.
# Melhor falhar aqui, no servidor, do que na primeira chamada paga.
RUN python -c "import anthropic, boto3, stripe"

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
