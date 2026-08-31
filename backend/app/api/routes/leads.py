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
from app.services.revelacao import ServicoDeRevelacao, mascarar

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
        # A mascara e aplicada AQUI, na saida — nunca no banco. O motor
        # precisa do e-mail para trabalhar antes de o usuario pagar por
        # ve-lo; quem nao pode ver e a pessoa, nao o sistema.
        "itens": [mascarar(lead) for lead in resultado.itens],
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
) -> dict:
    lead = LeadRepository(session).get(lead_id, user_id=user.id)
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead nao encontrado")
    return mascarar(lead)


@router.post("/{lead_id}/revelar", response_model=LeadOut)
def revelar(
    lead_id: uuid.UUID,
    session: Session = Depends(db),
    user: User = Depends(usuario_atual),
) -> dict:
    """Libera o contato deste lead — e cobra por isso.

    Idempotente: revelar de novo devolve o lead sem debitar outra vez.
    Um duplo clique nao pode custar dois creditos.
    """
    lead = LeadRepository(session).get(lead_id, user_id=user.id)
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead nao encontrado")
    ServicoDeRevelacao(session).revelar(lead)
    return mascarar(lead)


@router.get("/{lead_id}/cota")
def cota_do_lead(
    lead_id: uuid.UUID,
    session: Session = Depends(db),
    user: User = Depends(usuario_atual),
) -> dict:
    """Quanto ainda da para revelar na busca deste lead."""
    lead = LeadRepository(session).get(lead_id, user_id=user.id)
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead nao encontrado")
    return ServicoDeRevelacao(session).cota(user.id, lead.campaign_id).to_dict()


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
        servico.transicionar(
            lead, payload.status, motivo=payload.motivo, ator=Ator.USUARIO
        )
    except TransicaoInvalida as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return mascarar(lead)
