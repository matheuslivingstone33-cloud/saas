"""Rotas de leads (listagem paginada e transicao de estado)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import db, usuario_atual
from app.api.schemas import LeadOut, PaginaOut, TransicaoLeadIn
from app.core.errors import TransicaoInvalida
from app.domain.lead_state import proximos
from app.models.enums import Ator, StatusLead
from app.models.lead import Lead
from app.models.user import User
from app.repositories.leads import LeadRepository
from app.services.audit import AuditService
from app.services.leads import LeadService

router = APIRouter(prefix="/leads", tags=["leads"])


@router.get("", response_model=PaginaOut[LeadOut])
def listar(
    session: Session = Depends(db),
    user: User = Depends(usuario_atual),
    campaign_id: uuid.UUID | None = Query(default=None),
    status_filtro: StatusLead | None = Query(default=None, alias="status"),
    score_minimo: float | None = Query(default=None, ge=0, le=100),
    pagina: int = Query(default=1, ge=1),
    por_pagina: int = Query(default=25, ge=1, le=200),
) -> dict:
    resultado = LeadRepository(session).listar(
        user.id,
        campaign_id=campaign_id,
        status=status_filtro,
        score_minimo=score_minimo,
        pagina=pagina,
        por_pagina=por_pagina,
    )
    return {
        "itens": resultado.itens,
        "total": resultado.total,
        "pagina": resultado.pagina,
        "por_pagina": resultado.por_pagina,
        "paginas": resultado.paginas,
    }


@router.get("/{lead_id}", response_model=LeadOut)
def obter(
    lead_id: uuid.UUID,
    session: Session = Depends(db),
    user: User = Depends(usuario_atual),
) -> Lead:
    lead = LeadRepository(session).get(lead_id, user_id=user.id)
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead nao encontrado")
    return lead


@router.get("/{lead_id}/transicoes")
def transicoes_possiveis(
    lead_id: uuid.UUID,
    session: Session = Depends(db),
    user: User = Depends(usuario_atual),
) -> dict:
    lead = LeadRepository(session).get(lead_id, user_id=user.id)
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead nao encontrado")
    return {
        "atual": lead.status.value,
        "permitidas": [s.value for s in proximos(lead.status)],
    }


@router.post("/{lead_id}/transicao", response_model=LeadOut)
def transicionar(
    lead_id: uuid.UUID,
    payload: TransicaoLeadIn,
    session: Session = Depends(db),
    user: User = Depends(usuario_atual),
) -> Lead:
    lead = LeadRepository(session).get(lead_id, user_id=user.id)
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead nao encontrado")
    servico = LeadService(session, AuditService(session))
    try:
        return servico.transicionar(
            lead, payload.status, motivo=payload.motivo, ator=Ator.USUARIO
        )
    except TransicaoInvalida as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
