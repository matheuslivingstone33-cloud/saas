"""Aplicacao FastAPI.

Sobe sem nenhuma chave: todos os provedores partem em modo mock.
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from app.api import estatico
from app.api.routes import (
    billing,
    cadencia,
    campaigns,
    cerebro,
    compliance,
    conta,
    conversas,
    entregabilidade,
    leads,
    messages,
    stream,
    system,
)
from app.core.config import get_settings
from app.core.errors import (
    BloqueadoPorCompliance,
    DomainError,
    NetworkDisabledInMockMode,
    ProviderNotConfigured,
    SaldoInsuficiente,
    TransicaoInvalida,
)
from app.core.ids import request_id as gen_request_id
from app.core.logging import configure_logging, get_logger

settings = get_settings()
configure_logging("DEBUG" if settings.debug else "INFO")
log = get_logger("api")

DESCRICAO = """
Prospector AI — descobre, qualifica e inicia conversa com clientes ideais (B2B).

**Fases 0-6 rodam 100% em mock**: nenhuma chave de API, nenhuma requisicao de
rede, nenhum e-mail real (tudo vai para `outbox/`).
Consulte `GET /v1/providers` para ver o modo de cada porta.
"""

@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    log.info(
        "app_iniciada",
        ambiente=settings.app_env,
        banco="sqlite" if settings.is_sqlite else "postgres",
        modos=settings.modes(),
        tudo_mock=settings.is_all_mock(),
    )
    yield
    log.info("app_encerrada")


app = FastAPI(
    lifespan=lifespan,
    title=settings.app_name,
    version="0.1.0",
    description=DESCRICAO,
    docs_url="/docs",
    openapi_url="/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requisicoes(request: Request, call_next):  # noqa: ANN001, ANN201
    rid = request.headers.get("X-Request-Id") or gen_request_id()
    inicio = time.monotonic()
    resposta = await call_next(request)
    duracao = int((time.monotonic() - inicio) * 1000)
    resposta.headers["X-Request-Id"] = rid
    log.info(
        "requisicao",
        metodo=request.method,
        rota=request.url.path,
        status=resposta.status_code,
        latencia_ms=duracao,
        request_id=rid,
    )
    return resposta


# --- Tratadores de erro ------------------------------------------------------
@app.exception_handler(TransicaoInvalida)
async def _transicao(_: Request, exc: TransicaoInvalida) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": str(exc), "tipo": "transicao_invalida"})


@app.exception_handler(BloqueadoPorCompliance)
async def _compliance(_: Request, exc: BloqueadoPorCompliance) -> JSONResponse:
    return JSONResponse(status_code=451, content={"detail": str(exc), "tipo": "compliance"})


@app.exception_handler(SaldoInsuficiente)
async def _saldo(_: Request, exc: SaldoInsuficiente) -> JSONResponse:
    return JSONResponse(status_code=402, content={"detail": str(exc), "tipo": "saldo"})


@app.exception_handler(DomainError)
async def _dominio(_: Request, exc: DomainError) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": str(exc), "tipo": "dominio"})


@app.exception_handler(NetworkDisabledInMockMode)
async def _rede_mock(_: Request, exc: NetworkDisabledInMockMode) -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": str(exc), "tipo": "modo_mock"})


@app.exception_handler(ProviderNotConfigured)
async def _provedor(_: Request, exc: ProviderNotConfigured) -> JSONResponse:
    return JSONResponse(
        status_code=503, content={"detail": str(exc), "tipo": "provedor_nao_configurado"}
    )


# --- Rotas -------------------------------------------------------------------
@app.get("/", tags=["sistema"], include_in_schema=False)
def raiz():  # noqa: ANN201
    """Raiz: a interface, se estiver compilada; senao, a recepcao da API.

    Com `frontend/dist` presente, o app inteiro roda neste unico processo —
    sem Vite, sem esbuild, sem CORS. Sem o build, quem abre localhost:8000
    receberia {"detail":"Not Found"}, que parece defeito e nao e; entao
    devolvemos um mapa do que existe aqui.
    """
    dist = estatico.diretorio_da_interface()
    if dist is not None:
        return FileResponse(dist / "index.html", headers={"Cache-Control": "no-store"})
    return {
        "app": settings.app_name,
        "versao": "0.1.0",
        "descricao": "API do Prospector AI. A interface roda separada, na porta 5173.",
        "documentacao": "/docs",
        "saude": "/health",
        "provedores": f"{settings.api_prefix}/providers",
        "tudo_mock": settings.is_all_mock(),
    }


@app.get("/health", tags=["sistema"])
def health_raiz() -> dict:
    """Liveness na raiz — usado pelo HEALTHCHECK do container."""
    return {"status": "ok", "app": settings.app_name, "ambiente": settings.app_env}


app.include_router(system.router, prefix=settings.api_prefix)
app.include_router(conta.router, prefix=settings.api_prefix)
app.include_router(billing.router, prefix=settings.api_prefix)
app.include_router(campaigns.router, prefix=settings.api_prefix)
app.include_router(cerebro.router, prefix=settings.api_prefix)
app.include_router(compliance.router, prefix=settings.api_prefix)
# Rotas publicas: quem recebeu a mensagem nao tem conta no sistema.
app.include_router(compliance.publico)
app.include_router(leads.router, prefix=settings.api_prefix)
app.include_router(messages.router, prefix=settings.api_prefix)
app.include_router(stream.router, prefix=settings.api_prefix)
app.include_router(conversas.router, prefix=settings.api_prefix)
app.include_router(cadencia.router, prefix=settings.api_prefix)
app.include_router(entregabilidade.router, prefix=settings.api_prefix)
# Webhook do provedor: sem prefixo de usuario, quem chama e o provedor.
app.include_router(conversas.publico, prefix=settings.api_prefix)
app.include_router(entregabilidade.publico, prefix=settings.api_prefix)

# Por ULTIMO: o coringa de SPA so pode ver o que nenhuma rota de API pegou.
estatico.montar(app)
