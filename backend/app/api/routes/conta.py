"""Conta do cliente: perfil, nivel de autonomia e painel de KPIs.

O nivel de autonomia e uma TRANSICAO de estado da assinatura — por isso passa
por validacao e vira audit_log, e nao um simples UPDATE de coluna.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import db, usuario_atual
from app.core.errors import TransicaoInvalida
from app.domain.subscription_state import validar_autonomia
from app.models.campaign import Campaign
from app.models.enums import (
    Ator,
    NivelAutonomia,
    StatusLead,
    StatusMensagem,
    TipoEvento,
)
from app.models.lead import Lead
from app.models.message import Message
from app.models.user import User
from app.repositories.misc import CostEventRepository, UserRepository
from app.services.audit import AuditService
from app.services.creditos import CATALOGO, CreditService

router = APIRouter(tags=["conta"])


@router.get("/me")
def perfil(
    session: Session = Depends(db),
    user: User = Depends(usuario_atual),
) -> dict:
    assinatura = UserRepository(session).assinatura(user.id)
    saldo = CreditService(session).saldo(user.id)
    return {
        "id": str(user.id),
        "email": user.email,
        "nome": user.nome,
        "empresa": user.empresa,
        "cnpj": user.cnpj,
        "servico_padrao": user.servico_padrao,
        "regiao_padrao": user.regiao_padrao,
        "tom_de_voz": user.tom_de_voz,
        "diferenciais": user.diferenciais,
        "provas": user.provas,
        "evitar": user.evitar,
        "onboarding_completo": bool(user.empresa and user.servico_padrao),
        "assinatura": {
            "plano": assinatura.plano.value if assinatura else None,
            "status": assinatura.status.value if assinatura else None,
            "autonomy_level": assinatura.autonomy_level.value if assinatura else None,
            "teto_leads_mes": assinatura.teto_leads_mes if assinatura else 0,
            "leads_consumidos_mes": assinatura.leads_consumidos_mes if assinatura else 0,
            "overage_habilitado": assinatura.overage_habilitado if assinatura else False,
            "plano_catalogo": (
                CATALOGO[assinatura.plano].to_dict() if assinatura else None
            ),
        },
        "saldo": saldo.to_dict(),
    }


class PerfilIn(BaseModel):
    nome: str | None = Field(default=None, max_length=200)
    empresa: str | None = Field(default=None, max_length=200)
    cnpj: str | None = Field(default=None, max_length=18)
    servico_padrao: str | None = Field(default=None, max_length=500)
    regiao_padrao: str | None = Field(default=None, max_length=200)
    #: A voz do cliente. Chegam vazias para LIMPAR (o dono apagou o que tinha
    #: escrito), e por isso sao tratadas com `is not None`, nao com truthy.
    tom_de_voz: str | None = Field(default=None, max_length=120)
    diferenciais: str | None = Field(default=None, max_length=2000)
    provas: str | None = Field(default=None, max_length=2000)
    evitar: str | None = Field(default=None, max_length=2000)


@router.patch("/me")
def atualizar_perfil(
    payload: PerfilIn,
    session: Session = Depends(db),
    user: User = Depends(usuario_atual),
) -> dict:
    if payload.nome:
        user.nome = payload.nome
    if payload.empresa:
        user.empresa = payload.empresa
    if payload.cnpj is not None:
        user.cnpj = "".join(c for c in payload.cnpj if c.isdigit()) or None
    if payload.servico_padrao:
        user.servico_padrao = payload.servico_padrao
    if payload.regiao_padrao:
        user.regiao_padrao = payload.regiao_padrao
    for campo in ("tom_de_voz", "diferenciais", "provas", "evitar"):
        valor = getattr(payload, campo)
        if valor is not None:
            setattr(user, campo, valor.strip() or None)
    session.flush()
    return perfil(session=session, user=user)


class AutonomiaIn(BaseModel):
    autonomy_level: NivelAutonomia


@router.post("/me/autonomia")
def trocar_autonomia(
    payload: AutonomiaIn,
    session: Session = Depends(db),
    user: User = Depends(usuario_atual),
) -> dict:
    assinatura = UserRepository(session).assinatura(user.id)
    if assinatura is None:
        raise HTTPException(status_code=409, detail="Usuario sem assinatura")

    atual = assinatura.autonomy_level
    if atual is payload.autonomy_level:
        return {"de": atual.value, "para": atual.value, "alterado": False}

    try:
        validar_autonomia(atual, payload.autonomy_level)
    except TransicaoInvalida as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    assinatura.autonomy_level = payload.autonomy_level
    session.flush()
    AuditService(session).registrar(
        evento=TipoEvento.ASSINATURA_TRANSICAO,
        entidade_tipo="assinatura",
        entidade_id=assinatura.id,
        dados={"campo": "autonomy_level", "de": atual.value, "para": payload.autonomy_level.value},
        ator=Ator.USUARIO,
        user_id=user.id,
    )
    return {"de": atual.value, "para": payload.autonomy_level.value, "alterado": True}


@router.get("/dashboard")
def dashboard(
    session: Session = Depends(db),
    user: User = Depends(usuario_atual),
) -> dict:
    """KPIs do painel: funil, entregas, custo por balde e saldo."""
    leads_por_status = dict(
        session.execute(
            select(Lead.status, func.count(Lead.id))
            .where(Lead.user_id == user.id, Lead.deleted_at.is_(None))
            .group_by(Lead.status)
        ).all()
    )
    msgs_por_status = dict(
        session.execute(
            select(Message.status, func.count(Message.id))
            .where(Message.user_id == user.id)
            .group_by(Message.status)
        ).all()
    )
    campanhas = int(
        session.execute(
            select(func.count(Campaign.id)).where(
                Campaign.user_id == user.id, Campaign.deleted_at.is_(None)
            )
        ).scalar_one()
    )

    def leads(status: StatusLead) -> int:
        return int(leads_por_status.get(status, 0))

    def msgs(status: StatusMensagem) -> int:
        return int(msgs_por_status.get(status, 0))

    total_leads = sum(int(v) for v in leads_por_status.values())
    abordados = leads(StatusLead.ABORDADO) + leads(StatusLead.RESPONDIDO) + leads(
        StatusLead.CONVERTIDO
    )
    respondidos = leads(StatusLead.RESPONDIDO) + leads(StatusLead.CONVERTIDO)
    custo = CostEventRepository(session).resumo_por_balde(user_id=user.id)
    saldo = CreditService(session).saldo(user.id)
    por_lead, base, amostra, custo_medio = CreditService(session).tokens_por_lead(user.id)

    return {
        "campanhas": campanhas,
        "funil": {
            "descobertos": total_leads,
            "qualificados": leads(StatusLead.QUALIFICADO)
            + leads(StatusLead.ENFILEIRADO)
            + abordados,
            "abordados": abordados,
            "respondidos": respondidos,
            "convertidos": leads(StatusLead.CONVERTIDO),
            "opt_outs": leads(StatusLead.OPT_OUT),
            "descartados": leads(StatusLead.DESCARTADO),
        },
        "leads_por_status": {
            str(getattr(s, "value", s)): int(n) for s, n in leads_por_status.items()
        },
        "mensagens": {
            "aguardando_aprovacao": msgs(StatusMensagem.AGUARDANDO_APROVACAO),
            "enviadas": msgs(StatusMensagem.ENVIADA),
            "bloqueadas": msgs(StatusMensagem.BLOQUEADA),
            "falhas": msgs(StatusMensagem.FALHOU),
        },
        "taxas": {
            "qualificacao": _taxa(abordados + leads(StatusLead.QUALIFICADO), total_leads),
            "resposta": _taxa(respondidos, abordados),
            "conversao": _taxa(leads(StatusLead.CONVERTIDO), abordados),
        },
        "custo": {**custo, "total_usd": round(
            custo["balde_1_dados"]["usd"] + custo["balde_2_ia"]["usd"], 6
        )},
        "consumo": {
            "tokens_por_lead": por_lead,
            "base": base,
            "amostra_leads": amostra,
            "custo_medio_lead_micros": custo_medio,
        },
        "saldo": saldo.to_dict(),
    }


def _taxa(numerador: int, denominador: int) -> float:
    if not denominador:
        return 0.0
    return round(100 * numerador / denominador, 1)
