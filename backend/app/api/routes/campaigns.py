"""Rotas de campanha, incluindo a execucao do pipeline (stub da Fase 0)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.adapters.registry import ProviderRegistry
from app.api.deps import db, registry, usuario_atual
from app.api.schemas import CampanhaIn, CampanhaOut, ExecucaoIn, PaginaOut
from app.core.errors import DomainError, SaldoInsuficiente
from app.models.campaign import Campaign
from app.models.enums import StatusCampanha
from app.models.user import User
from app.repositories.misc import CampaignRepository
from app.services.envio import SendService
from app.services.pipeline import PipelineStub
from app.workers.queue import enfileirar

router = APIRouter(prefix="/campaigns", tags=["campanhas"])


@router.post("", response_model=CampanhaOut, status_code=status.HTTP_201_CREATED)
def criar(
    payload: CampanhaIn,
    session: Session = Depends(db),
    user: User = Depends(usuario_atual),
) -> Campaign:
    repo = CampaignRepository(session)
    return repo.add(
        Campaign(
            user_id=user.id,
            nome=payload.nome,
            servico=payload.servico,
            regiao=payload.regiao,
            filtros=payload.filtros,
            canal_padrao=payload.canal_padrao,
            autonomy_override=payload.autonomy_override,
            meta_leads=payload.meta_leads,
            status=StatusCampanha.RASCUNHO,
        )
    )


@router.get("", response_model=PaginaOut[CampanhaOut])
def listar(
    session: Session = Depends(db),
    user: User = Depends(usuario_atual),
    status_filtro: StatusCampanha | None = Query(default=None, alias="status"),
    pagina: int = Query(default=1, ge=1),
    por_pagina: int = Query(default=25, ge=1, le=200),
) -> dict:
    pagina_res = CampaignRepository(session).listar(
        user.id, status=status_filtro, pagina=pagina, por_pagina=por_pagina
    )
    return {
        "itens": pagina_res.itens,
        "total": pagina_res.total,
        "pagina": pagina_res.pagina,
        "por_pagina": pagina_res.por_pagina,
        "paginas": pagina_res.paginas,
    }


@router.get("/{campaign_id}", response_model=CampanhaOut)
def obter(
    campaign_id: uuid.UUID,
    session: Session = Depends(db),
    user: User = Depends(usuario_atual),
) -> Campaign:
    campanha = CampaignRepository(session).get(campaign_id, user_id=user.id)
    if campanha is None:
        raise HTTPException(status_code=404, detail="Campanha nao encontrada")
    return campanha


@router.post("/{campaign_id}/run")
def executar(
    campaign_id: uuid.UUID,
    payload: ExecucaoIn,
    session: Session = Depends(db),
    user: User = Depends(usuario_atual),
    portas: ProviderRegistry = Depends(registry),
) -> dict:
    """Roda o pipeline ponta a ponta. Em modo mock, nada sai para a rede."""
    campanha = CampaignRepository(session).get(campaign_id, user_id=user.id)
    if campanha is None:
        raise HTTPException(status_code=404, detail="Campanha nao encontrada")

    if payload.assincrono:
        job = enfileirar(
            "app.workers.tasks.executar_campanha", str(campanha.id), payload.limite_leads
        )
        return {"enfileirado": True, "job_id": job.id, "modo_fila": job.modo}

    try:
        resultado = PipelineStub(session, portas).executar(
            campanha, limite_leads=payload.limite_leads
        )
    except SaldoInsuficiente:
        # Tratado pelo handler global como 402 (Payment Required).
        raise
    except DomainError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return resultado.to_dict()


@router.post("/{campaign_id}/reset", response_model=CampanhaOut)
def reabrir(
    campaign_id: uuid.UUID,
    session: Session = Depends(db),
    user: User = Depends(usuario_atual),
) -> Campaign:
    """Volta a campanha concluida para PRONTA (util na demo)."""
    campanha = CampaignRepository(session).get(campaign_id, user_id=user.id)
    if campanha is None:
        raise HTTPException(status_code=404, detail="Campanha nao encontrada")
    from app.domain import campaign_state

    try:
        campaign_state.validar(campanha.status, StatusCampanha.PRONTA)
    except DomainError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    campanha.status = StatusCampanha.PRONTA
    session.flush()
    return campanha


@router.get("/{campaign_id}/limites")
def limites(
    campaign_id: uuid.UUID,
    session: Session = Depends(db),
    user: User = Depends(usuario_atual),
    portas: ProviderRegistry = Depends(registry),
) -> dict:
    """Quanto ainda pode sair hoje, por usuario e por campanha."""
    campanha = CampaignRepository(session).get(campaign_id, user_id=user.id)
    if campanha is None:
        raise HTTPException(status_code=404, detail="Campanha nao encontrada")
    return SendService(session, portas).limites(user.id, campanha.id)


@router.post("/{campaign_id}/disparar")
def disparar(
    campaign_id: uuid.UUID,
    session: Session = Depends(db),
    user: User = Depends(usuario_atual),
    portas: ProviderRegistry = Depends(registry),
) -> dict:
    """Despacha as mensagens ja aprovadas desta campanha."""
    campanha = CampaignRepository(session).get(campaign_id, user_id=user.id)
    if campanha is None:
        raise HTTPException(status_code=404, detail="Campanha nao encontrada")
    envio = SendService(session, portas)
    lote = envio.processar_pendentes(user.id, limite=200)
    return {"campaign_id": str(campanha.id), **lote.to_dict()}
