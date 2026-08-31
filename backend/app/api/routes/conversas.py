"""Rotas do Motor 4 — a conversa de duas pontas.

Duas portas de entrada, de proposito:

  * `POST /inbound/email` — o webhook que o provedor real chama quando o lead
    responde. Sem autenticacao de usuario (quem chama e o provedor), mas o lead
    e resolvido pelo endereco: nao da para injetar resposta em conversa alheia
    sem conhecer um e-mail que ja esta na base daquele tenant.

  * `POST /leads/{id}/simular-resposta` — SO EM MODO MOCK. Sem isto, o Motor 4
    seria impossivel de testar antes de ligar provedor pago: o produto inteiro
    foi construido para rodar sem chave, e a conversa nao pode ser a excecao.
    A rota se recusa a funcionar quando o e-mail esta em modo real.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.adapters.registry import ProviderRegistry
from app.api.deps import config, db, registry, usuario_atual, webhook_autenticado
from app.core.config import Provider, Settings
from app.core.logging import get_logger
from app.models.enums import Canal
from app.models.lead import Lead
from app.models.user import User
from app.repositories.leads import LeadRepository
from app.services.conversa import Intencao, ServicoDeConversa

log = get_logger("api_conversas")

router = APIRouter(tags=["conversas"])
publico = APIRouter(tags=["conversas"])


class RespostaRecebida(BaseModel):
    """Payload do webhook. Formato proprio: cada provedor tem o seu, e o
    adaptador da Fase 7 traduz para este."""

    remetente: str = Field(min_length=3, max_length=320)
    corpo: str = Field(min_length=1, max_length=20000)
    assunto: str | None = Field(default=None, max_length=300)
    provider_message_id: str | None = Field(default=None, max_length=255)


class SimulacaoResposta(BaseModel):
    corpo: str = Field(min_length=1, max_length=20000)
    assunto: str | None = Field(default=None, max_length=300)


class RespostaManual(BaseModel):
    """O que a pessoa escreveu. Sai como escrito, sem passar por LLM."""

    corpo: str = Field(min_length=1, max_length=20000)
    assunto: str | None = Field(default=None, max_length=300)


def _lead_por_email(session: Session, endereco: str) -> Lead | None:
    """Acha o lead pelo endereco que respondeu.

    Comparacao em minusculas no BANCO (nao em Python): e-mail nao diferencia
    caixa, e o provedor devolve do jeito que o remetente digitou.

    Pega o mais recente quando ha mais de um: o mesmo contato pode aparecer em
    campanhas diferentes, e a conversa pertence a abordagem mais nova.
    """
    alvo = endereco.strip().lower()
    if not alvo:
        return None
    return session.execute(
        select(Lead)
        .where(Lead.deleted_at.is_(None), func.lower(Lead.email) == alvo)
        .order_by(Lead.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()


@publico.post("/inbound/email", status_code=status.HTTP_202_ACCEPTED)
def receber_email(
    payload: RespostaRecebida,
    session: Session = Depends(db),
    _assinatura: bytes = Depends(webhook_autenticado),
) -> dict:
    """Webhook de resposta por e-mail. Exige assinatura HMAC do provedor.

    "Publico" aqui quer dizer sem sessao de usuario, nao sem autenticacao: quem
    prova identidade e o segredo compartilhado com o provedor.
    """
    lead = _lead_por_email(session, payload.remetente)
    if lead is None:
        # 202 mesmo sem achar: o provedor nao deve reenviar indefinidamente, e
        # devolver 404 vazaria quais enderecos estao na base.
        log.info("inbound_sem_lead", remetente=payload.remetente[:80])
        return {"aceito": True, "casou_com_lead": False}

    portas = ProviderRegistry()
    try:
        resultado = ServicoDeConversa(session, portas).receber(
            lead=lead,
            corpo=payload.corpo,
            remetente=payload.remetente,
            assunto=payload.assunto,
            canal=Canal.EMAIL,
            provider_message_id=payload.provider_message_id,
        )
    finally:
        portas.fechar()

    return {"aceito": True, "casou_com_lead": True, **resultado.to_dict()}


@router.post("/leads/{lead_id}/simular-resposta")
def simular_resposta(
    lead_id: uuid.UUID,
    payload: SimulacaoResposta,
    session: Session = Depends(db),
    user: User = Depends(usuario_atual),
    portas: ProviderRegistry = Depends(registry),
    settings: Settings = Depends(config),
) -> dict:
    """Simula o lead respondendo. Existe apenas em modo mock."""
    if settings.mode_for(Provider.EMAIL) == "real":
        raise HTTPException(
            status_code=409,
            detail=(
                "Simulacao indisponivel com EMAIL_MODE=real. Com provedor real, a "
                "resposta chega pelo webhook /inbound/email."
            ),
        )

    lead = LeadRepository(session).get(lead_id, user_id=user.id)
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead nao encontrado")

    resultado = ServicoDeConversa(session, portas).receber(
        lead=lead,
        corpo=payload.corpo,
        remetente=lead.email,
        assunto=payload.assunto,
        canal=Canal.EMAIL,
    )
    return resultado.to_dict()


@router.post("/leads/{lead_id}/responder")
def responder(
    lead_id: uuid.UUID,
    payload: RespostaManual,
    session: Session = Depends(db),
    user: User = Depends(usuario_atual),
    portas: ProviderRegistry = Depends(registry),
) -> dict:
    """A pessoa escreve e o sistema envia — a conversa NAO sai do produto.

    Enviar por fora (um `mailto:`, por exemplo) parece equivalente e nao e: a
    resposta do lead voltaria para a caixa pessoal, fora do alcance do Motor 4,
    e a thread ficaria com um buraco exatamente no trecho que importa.
    """
    lead = LeadRepository(session).get(lead_id, user_id=user.id)
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead nao encontrado")

    resultado = ServicoDeConversa(session, portas).responder_manualmente(
        lead=lead, corpo=payload.corpo, autor=user, assunto=payload.assunto
    )
    return resultado.to_dict()


@router.post("/leads/{lead_id}/devolver-para-ia")
def devolver_para_ia(
    lead_id: uuid.UUID,
    session: Session = Depends(db),
    user: User = Depends(usuario_atual),
    portas: ProviderRegistry = Depends(registry),
) -> dict:
    """Devolve a conversa ao agente. Assumir nao pode ser porta sem volta."""
    lead = LeadRepository(session).get(lead_id, user_id=user.id)
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead nao encontrado")

    devolvida = ServicoDeConversa(session, portas).devolver_para_ia(lead, user)
    return {"lead_id": str(lead.id), "devolvida": devolvida, "assumida": False}


@router.get("/conversas/intencoes")
def listar_intencoes() -> dict:
    """As intencoes que o Motor 4 reconhece e o que cada uma dispara.

    Serve a interface e serve de documentacao viva: se alguem acrescentar uma
    intencao sem decidir o que ela faz, aparece aqui como buraco.
    """
    from app.services.conversa import QUENTES, SEM_RESPOSTA

    return {
        "intencoes": [
            {
                "valor": i.value,
                "gera_resposta": i not in SEM_RESPOSTA,
                "lead_quente": i in QUENTES,
            }
            for i in Intencao
        ]
    }
