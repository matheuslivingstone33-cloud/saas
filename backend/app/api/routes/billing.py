"""FASE 5 — Rotas de creditos, planos e pacotes de tokens."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.adapters.registry import ProviderRegistry
from app.api.deps import db, registry, usuario_atual
from app.models.enums import Plano, TipoCredito
from app.models.user import User
from app.services.creditos import CATALOGO, PACOTES, CreditService

router = APIRouter(prefix="/billing", tags=["creditos e planos"])


@router.get("/saldo")
def saldo(
    session: Session = Depends(db),
    user: User = Depends(usuario_atual),
) -> dict:
    """Saldo, teto do plano e se o consumo esta bloqueado."""
    return CreditService(session).saldo(user.id).to_dict()


@router.get("/vitrine")
def vitrine(
    session: Session = Depends(db),
    user: User = Depends(usuario_atual),
) -> dict:
    """Planos e pacotes com a equivalencia em tokens medida no consumo real."""
    return CreditService(session).vitrine(user.id)


@router.get("/extrato")
def extrato(
    session: Session = Depends(db),
    user: User = Depends(usuario_atual),
    pagina: int = Query(default=1, ge=1),
    por_pagina: int = Query(default=25, ge=1, le=200),
) -> dict:
    resultado = CreditService(session).ledger.extrato(user.id, pagina, por_pagina)
    return {
        "itens": [
            {
                "id": str(i.id),
                "tipo": i.tipo.value,
                "quantidade": i.quantidade,
                "saldo_apos": i.saldo_apos,
                "descricao": i.descricao,
                "created_at": i.created_at.isoformat(),
            }
            for i in resultado.itens
        ],
        "total": resultado.total,
        "pagina": resultado.pagina,
        "por_pagina": resultado.por_pagina,
        "paginas": resultado.paginas,
    }


class CompraIn(BaseModel):
    pacote: str = Field(min_length=3, max_length=50)


@router.post("/comprar")
def comprar(
    payload: CompraIn,
    session: Session = Depends(db),
    user: User = Depends(usuario_atual),
    portas: ProviderRegistry = Depends(registry),
) -> dict:
    """Cria o checkout do pacote avulso (mock ate o BillingPort real)."""
    pacote = PACOTES.get(payload.pacote)
    if pacote is None:
        raise HTTPException(status_code=404, detail=f"Pacote desconhecido: {payload.pacote}")
    checkout = portas.billing.criar_checkout(str(user.id), pacote.codigo, pacote.preco_centavos)
    return {"checkout": checkout.model_dump(), "pacote": pacote.to_dict()}


class ConfirmacaoIn(BaseModel):
    checkout_id: str
    pacote: str


@router.post("/confirmar")
def confirmar(
    payload: ConfirmacaoIn,
    session: Session = Depends(db),
    user: User = Depends(usuario_atual),
    portas: ProviderRegistry = Depends(registry),
) -> dict:
    """Confirma o pagamento e credita. Em producao vira webhook assinado."""
    pacote = PACOTES.get(payload.pacote)
    if pacote is None:
        raise HTTPException(status_code=404, detail="Pacote desconhecido")
    if not portas.billing.confirmar(payload.checkout_id):
        raise HTTPException(status_code=402, detail="Pagamento nao confirmado")

    servico = CreditService(session)
    saldo_novo = servico.creditar(
        user.id,
        pacote.creditos,
        tipo=TipoCredito.COMPRA_PACOTE,
        descricao=f"compra do pacote {pacote.nome}",
    )
    return {"creditado": pacote.creditos, "saldo": saldo_novo}


class PlanoIn(BaseModel):
    plano: Plano


@router.post("/plano")
def trocar_plano(
    payload: PlanoIn,
    session: Session = Depends(db),
    user: User = Depends(usuario_atual),
) -> dict:
    """Troca de plano: aplica o novo teto e recarrega os creditos do ciclo."""
    servico = CreditService(session)
    assinatura = servico.assinatura(user.id)
    if assinatura is None:
        raise HTTPException(status_code=409, detail="Usuario sem assinatura")

    catalogo = CATALOGO[payload.plano]
    anterior = assinatura.plano
    assinatura.plano = payload.plano
    assinatura.teto_leads_mes = catalogo.teto_leads_mes
    session.flush()
    saldo_novo = servico.renovar_ciclo(user.id)
    return {
        "de": anterior.value,
        "para": payload.plano.value,
        "creditos_creditados": catalogo.creditos_mes,
        "saldo": saldo_novo,
    }


class OverageIn(BaseModel):
    habilitado: bool


@router.post("/overage")
def overage(
    payload: OverageIn,
    session: Session = Depends(db),
    user: User = Depends(usuario_atual),
) -> dict:
    """Liga/desliga o consumo acima do teto (cobrado por credito extra)."""
    assinatura = CreditService(session).assinatura(user.id)
    if assinatura is None:
        raise HTTPException(status_code=409, detail="Usuario sem assinatura")
    assinatura.overage_habilitado = payload.habilitado
    session.flush()
    return {
        "overage_habilitado": assinatura.overage_habilitado,
        "centavos_por_credito": CATALOGO[assinatura.plano].overage_centavos_por_credito,
    }
