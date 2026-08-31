"""Rotas de entregabilidade — o retorno do provedor.

Mesmo desenho das rotas do Motor 4, e pelo mesmo motivo:

  * `POST /inbound/retorno` — o webhook. Quem chama e o provedor (SNS do SES,
    webhook do BSP), entao nao ha usuario autenticado. Devolve 202 mesmo sem
    casar com nada: 404 aqui contaria a quem perguntasse quais enderecos estao
    na base, e faria o provedor reenviar para sempre.

  * `POST /leads/{id}/simular-retorno` — SO EM MODO MOCK. Sem ela, a supressao
    por bounce so seria testavel depois de ligar provedor pago e conseguir um
    endereco morto de verdade.

  * `GET /campanhas/{id}/reputacao` — a taxa que decide se a campanha continua.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import config, db, usuario_atual, webhook_autenticado
from app.core.config import Provider, Settings
from app.core.logging import get_logger
from app.models.user import User
from app.repositories.leads import LeadRepository
from app.repositories.misc import CampaignRepository
from app.services.entregabilidade import ServicoDeEntregabilidade, TipoRetorno

log = get_logger("api_entregabilidade")

router = APIRouter(tags=["entregabilidade"])
publico = APIRouter(tags=["entregabilidade"])


class RetornoRecebido(BaseModel):
    """Payload do webhook. Formato proprio: cada provedor tem o seu, e o
    adaptador da Fase 7 traduz para este."""

    contato: str = Field(min_length=3, max_length=320)
    tipo: TipoRetorno
    provider_message_id: str | None = Field(default=None, max_length=255)
    diagnostico: str | None = Field(default=None, max_length=500)


class SimulacaoRetorno(BaseModel):
    tipo: TipoRetorno = TipoRetorno.PERMANENTE
    diagnostico: str | None = Field(default=None, max_length=500)


@publico.post("/inbound/retorno", status_code=status.HTTP_202_ACCEPTED)
def receber_retorno(
    payload: RetornoRecebido,
    session: Session = Depends(db),
    _assinatura: bytes = Depends(webhook_autenticado),
) -> dict:
    """Webhook de bounce, reclamacao de spam e falha temporaria.

    Exige assinatura HMAC: um bounce forjado SUPRIME um contato e descarta o
    lead — daria para apagar a base de um concorrente com um laco de `curl`.
    """
    resultado = ServicoDeEntregabilidade(session).registrar(
        contato=payload.contato,
        tipo=payload.tipo,
        provider_message_id=payload.provider_message_id,
        diagnostico=payload.diagnostico,
    )
    return {"aceito": True, **resultado.to_dict()}


@router.post("/leads/{lead_id}/simular-retorno")
def simular_retorno(
    lead_id: uuid.UUID,
    payload: SimulacaoRetorno,
    session: Session = Depends(db),
    user: User = Depends(usuario_atual),
    settings: Settings = Depends(config),
) -> dict:
    """Simula o provedor devolvendo a mensagem. Existe apenas em modo mock."""
    if settings.mode_for(Provider.EMAIL) == "real":
        raise HTTPException(
            status_code=409,
            detail=(
                "Simulacao indisponivel com EMAIL_MODE=real. Com provedor real o "
                "retorno chega pelo webhook /inbound/retorno."
            ),
        )

    lead = LeadRepository(session).get(lead_id, user_id=user.id)
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead nao encontrado")

    resultado = ServicoDeEntregabilidade(session, settings=settings).registrar(
        contato=lead.email or "",
        tipo=payload.tipo,
        diagnostico=payload.diagnostico,
    )
    return resultado.to_dict()


@router.get("/campanhas/{campaign_id}/reputacao")
def reputacao(
    campaign_id: uuid.UUID,
    session: Session = Depends(db),
    user: User = Depends(usuario_atual),
    settings: Settings = Depends(config),
) -> dict:
    """Taxa de retorno da campanha — o freio que pausa o envio sozinho."""
    campanha = CampaignRepository(session).get(campaign_id, user_id=user.id)
    if campanha is None:
        raise HTTPException(status_code=404, detail="Campanha nao encontrada")

    rep = ServicoDeEntregabilidade(session, settings=settings).reputacao(campanha.id)
    return {
        "campanha_id": str(campanha.id),
        "status": campanha.status.value,
        "teto": settings.bounce_taxa_maxima,
        "amostra_minima": settings.bounce_amostra_minima,
        **rep.to_dict(),
    }
