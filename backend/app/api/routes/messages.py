"""Rotas de mensagens: listar, aprovar (modo assistido), rejeitar e despachar.

Todo envio passa pelo SendService — a rota nao fala com a porta de e-mail
diretamente. E o que garante que opt-out, limites diarios e guardrail de canal
valem igual pela API, pelo worker e pelo pipeline.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.adapters.registry import ProviderRegistry
from app.api.deps import db, registry, usuario_atual
from app.api.schemas import MensagemOut, PaginaOut
from app.core.errors import BloqueadoPorCompliance
from app.models.enums import Ator, StatusMensagem, TipoEvento
from app.models.message import Message
from app.models.user import User
from app.repositories.misc import MessageRepository
from app.services.audit import AuditService
from app.services.envio import SendService

router = APIRouter(prefix="/messages", tags=["mensagens"])


@router.get("", response_model=PaginaOut[MensagemOut])
def listar(
    session: Session = Depends(db),
    user: User = Depends(usuario_atual),
    campaign_id: uuid.UUID | None = Query(default=None),
    status_filtro: StatusMensagem | None = Query(default=None, alias="status"),
    pagina: int = Query(default=1, ge=1),
    por_pagina: int = Query(default=25, ge=1, le=200),
) -> dict:
    resultado = MessageRepository(session).listar(
        user.id,
        campaign_id=campaign_id,
        status=status_filtro,
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


@router.post("/{message_id}/aprovar", response_model=MensagemOut)
def aprovar(
    message_id: uuid.UUID,
    session: Session = Depends(db),
    user: User = Depends(usuario_atual),
    portas: ProviderRegistry = Depends(registry),
) -> Message:
    """Modo ASSISTIDO: o humano aprova e o envio acontece na sequencia."""
    mensagem = MessageRepository(session).get(message_id, user_id=user.id)
    if mensagem is None:
        raise HTTPException(status_code=404, detail="Mensagem nao encontrada")
    try:
        SendService(session, portas).aprovar(mensagem, user)
    except BloqueadoPorCompliance as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    session.flush()
    return mensagem


@router.post("/{message_id}/rejeitar", response_model=MensagemOut)
def rejeitar(
    message_id: uuid.UUID,
    session: Session = Depends(db),
    user: User = Depends(usuario_atual),
) -> Message:
    mensagem = MessageRepository(session).get(message_id, user_id=user.id)
    if mensagem is None:
        raise HTTPException(status_code=404, detail="Mensagem nao encontrada")
    mensagem.status = StatusMensagem.REJEITADA
    session.flush()
    AuditService(session).registrar(
        evento=TipoEvento.MENSAGEM_BLOQUEADA,
        entidade_tipo="mensagem",
        entidade_id=mensagem.id,
        dados={"motivo": "rejeitada_pelo_usuario"},
        ator=Ator.USUARIO,
        user_id=user.id,
    )
    return mensagem


@router.post("/despachar-pendentes")
def despachar_pendentes(
    session: Session = Depends(db),
    user: User = Depends(usuario_atual),
    portas: ProviderRegistry = Depends(registry),
    limite: int = Query(default=50, ge=1, le=200),
) -> dict:
    """Despacha o que ja esta aprovado (modo automatico ou pos-aprovacao)."""
    lote = SendService(session, portas).processar_pendentes(user.id, limite=limite)
    return lote.to_dict()
