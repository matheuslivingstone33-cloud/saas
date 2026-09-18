"""Rotas de sistema: saude, provedores, custo (margem) e auditoria."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.adapters.registry import ProviderRegistry
from app.api.deps import config, db, registry, usuario_admin, usuario_atual
from app.api.schemas import (
    AuditLogOut,
    CostEventOut,
    CustoResumoOut,
    IntegridadeOut,
    PaginaOut,
    SaudeOut,
)
from app.core.config import Settings
from app.models.user import User
from app.repositories.misc import AuditLogRepository, CostEventRepository
from app.services.audit import AuditService

router = APIRouter(tags=["sistema"])


@router.get("/health")
def health(settings: Settings = Depends(config)) -> dict:
    """Liveness: nao toca banco (usado pelo HEALTHCHECK do container)."""
    return {"status": "ok", "app": settings.app_name, "ambiente": settings.app_env}


@router.get("/health/ready", response_model=SaudeOut)
def ready(
    session: Session = Depends(db),
    settings: Settings = Depends(config),
) -> dict:
    try:
        session.execute(text("SELECT 1"))
        banco = "ok"
    except Exception as exc:  # pragma: no cover - caminho de falha
        banco = f"erro: {exc}"

    fila = "redis" if settings.redis_url else "inline (sem Redis)"
    portas = ProviderRegistry(settings=settings)
    diagnostico = portas.diagnostico()
    return {
        "status": "ok" if banco == "ok" else "degradado",
        "app": settings.app_name,
        "ambiente": settings.app_env,
        "banco": banco,
        "fila": fila,
        "tudo_mock": settings.is_all_mock(),
        "provedores": diagnostico,
    }


@router.get("/providers")
def provedores(portas: ProviderRegistry = Depends(registry)) -> dict:
    """Estado de cada porta. Guia da virada da Fase 7 (um flag por vez)."""
    return {
        "provedores": portas.diagnostico(),
        "observacao": (
            "Fases 0-6 rodam com tudo em mock. Na Fase 7, vire um *_MODE para "
            "real por vez e rode o smoke test daquele provedor."
        ),
    }


@router.get("/costs/summary", response_model=CustoResumoOut)
def resumo_custo(
    session: Session = Depends(db),
    user: User = Depends(usuario_atual),
    campaign_id: uuid.UUID | None = Query(default=None),
) -> dict:
    resumo = CostEventRepository(session).resumo_por_balde(
        user_id=user.id, campaign_id=campaign_id
    )
    total = resumo["balde_1_dados"]["usd"] + resumo["balde_2_ia"]["usd"]
    return {**resumo, "total_usd": round(total, 6)}


@router.get("/costs", response_model=PaginaOut[CostEventOut])
def listar_custos(
    session: Session = Depends(db),
    user: User = Depends(usuario_atual),
    campaign_id: uuid.UUID | None = Query(default=None),
    pagina: int = Query(default=1, ge=1),
    por_pagina: int = Query(default=50, ge=1, le=200),
) -> dict:
    resultado = CostEventRepository(session).listar(
        user.id, campaign_id=campaign_id, pagina=pagina, por_pagina=por_pagina
    )
    return {
        "itens": resultado.itens,
        "total": resultado.total,
        "pagina": resultado.pagina,
        "por_pagina": resultado.por_pagina,
        "paginas": resultado.paginas,
    }


@router.get("/margem")
def margem(
    session: Session = Depends(db),
    user: User = Depends(usuario_atual),
    campaign_id: uuid.UUID | None = Query(default=None),
) -> dict:
    """Painel de margem: receita reconhecida x custo dos dois baldes."""
    from app.services.margem import MargemService

    return MargemService(session).por_usuario(user.id, campaign_id).to_dict()


@router.get("/margem/consolidado")
def margem_consolidada(
    session: Session = Depends(db),
    user: User = Depends(usuario_admin),  # noqa: ARG001 — so quem opera o SaaS
) -> dict:
    """Visao do operador do SaaS: receita e custo de TODOS os clientes.

    Era aberta a qualquer conta logada. So `ADMIN_EMAILS` entra agora.
    """
    from app.services.margem import MargemService

    return MargemService(session).consolidado()


@router.get("/audit", response_model=PaginaOut[AuditLogOut])
def listar_auditoria(
    session: Session = Depends(db),
    user: User = Depends(usuario_atual),
    entidade_id: uuid.UUID | None = Query(default=None),
    pagina: int = Query(default=1, ge=1),
    por_pagina: int = Query(default=50, ge=1, le=200),
) -> dict:
    resultado = AuditLogRepository(session).listar(
        user.id, entidade_id=entidade_id, pagina=pagina, por_pagina=por_pagina
    )
    return {
        "itens": resultado.itens,
        "total": resultado.total,
        "pagina": resultado.pagina,
        "por_pagina": resultado.por_pagina,
        "paginas": resultado.paginas,
    }


@router.get("/audit/integridade", response_model=IntegridadeOut)
def integridade(
    session: Session = Depends(db),
    user: User = Depends(usuario_atual),  # noqa: ARG001 — o total e do sistema inteiro
) -> dict:
    servico = AuditService(session)
    integra, erro = servico.verificar_cadeia()
    return {"integra": integra, "registros": servico.total(), "primeiro_erro_seq": erro}
