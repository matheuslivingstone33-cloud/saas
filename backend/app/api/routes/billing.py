"""FASE 5 — Rotas de creditos, planos e pacotes de tokens.

Regra desta camada: credito so entra por pagamento que o PROVEDOR confirma.
Ate 18/09 havia tres jeitos de ganhar credito sem pagar — trocar de plano
(recarregava o ciclo a cada troca), confirmar um pacote diferente do pago, e
confirmar o mesmo pagamento varias vezes.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.registry import ProviderRegistry
from app.api.deps import config, db, registry, usuario_atual
from app.core.config import Settings
from app.models.credit_ledger import CreditLedger
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
    checkout_id: str = Field(min_length=3, max_length=300)
    #: Ignorado. Fica no contrato para nao quebrar o cliente antigo, mas o
    #: pacote creditado e o que o PROVEDOR diz que foi pago.
    pacote: str | None = None


def referencia_do_checkout(checkout_id: str) -> uuid.UUID:
    """Id estavel do pagamento no extrato: o mesmo checkout, o mesmo id."""
    return uuid.uuid5(uuid.NAMESPACE_URL, f"prospector:checkout:{checkout_id}")


@router.post("/confirmar")
def confirmar(
    payload: ConfirmacaoIn,
    session: Session = Depends(db),
    user: User = Depends(usuario_atual),
    portas: ProviderRegistry = Depends(registry),
) -> dict:
    """Confere o pagamento com o provedor e credita UMA vez.

    Em producao com Stripe real, o caminho principal vira o webhook assinado;
    esta rota continua como reconciliacao e segue as mesmas tres travas.
    """
    consulta = portas.billing.consultar(payload.checkout_id)
    if not consulta.pago:
        raise HTTPException(status_code=402, detail="Pagamento nao confirmado")
    if consulta.user_id != str(user.id):
        # Pagamento de outra conta: para este usuario, ele nao existe.
        raise HTTPException(status_code=404, detail="Pagamento nao encontrado")

    pacote = PACOTES.get(consulta.pacote or "")
    if pacote is None or consulta.valor_centavos != pacote.preco_centavos:
        raise HTTPException(status_code=409, detail="Pagamento nao confere com o pacote")

    servico = CreditService(session)
    referencia = referencia_do_checkout(payload.checkout_id)
    ja_creditado = session.execute(
        select(CreditLedger.id).where(
            CreditLedger.user_id == user.id,
            CreditLedger.referencia_tipo == "checkout",
            CreditLedger.referencia_id == referencia,
        )
    ).first()
    if ja_creditado is not None:
        return {"creditado": 0, "saldo": servico.saldo(user.id).creditos, "ja_creditado": True}

    saldo_novo = servico.creditar(
        user.id,
        pacote.creditos,
        tipo=TipoCredito.COMPRA_PACOTE,
        descricao=f"compra do pacote {pacote.nome}",
        referencia_id=referencia,
        referencia_tipo="checkout",
    )
    return {"creditado": pacote.creditos, "saldo": saldo_novo}


class PlanoIn(BaseModel):
    plano: Plano


def troca_livre_de_plano(settings: Settings) -> bool:
    """Trocar para plano pago sem pagar so existe em desenvolvimento.

    Em qualquer ambiente publicado — inclusive com o pagamento ainda simulado —
    subir de plano exige pagamento, que ainda nao tem fluxo proprio.
    """
    return not settings.em_producao and settings.mode_for("billing") == "mock"


@router.post("/plano")
def trocar_plano(
    payload: PlanoIn,
    session: Session = Depends(db),
    user: User = Depends(usuario_atual),
    settings: Settings = Depends(config),
) -> dict:
    """Troca de plano: aplica o novo teto; so plano pago recarrega o ciclo.

    Antes, qualquer conta logada ia para o Scale sem pagar, e cada troca
    recarregava os creditos — ir e voltar entre dois planos era credito
    infinito.
    """
    servico = CreditService(session)
    assinatura = servico.assinatura(user.id)
    if assinatura is None:
        raise HTTPException(status_code=409, detail="Usuario sem assinatura")
    if payload.plano == assinatura.plano:
        raise HTTPException(status_code=409, detail="Voce ja esta neste plano")

    catalogo = CATALOGO[payload.plano]
    pago = catalogo.preco_centavos > 0
    if pago and not troca_livre_de_plano(settings):
        raise HTTPException(
            status_code=402,
            detail="A troca para um plano pago passa pelo pagamento, que ainda nao "
            "esta disponivel. Fale com a gente para contratar.",
        )

    anterior = assinatura.plano
    assinatura.plano = payload.plano
    assinatura.teto_leads_mes = catalogo.teto_leads_mes
    session.flush()
    if pago:
        saldo_novo = servico.renovar_ciclo(user.id)
        creditados = catalogo.creditos_mes
    else:
        # Descer para o gratuito nao da credito: o saldo que existe continua.
        saldo_novo = servico.saldo(user.id).creditos
        creditados = 0
    return {
        "de": anterior.value,
        "para": payload.plano.value,
        "creditos_creditados": creditados,
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
    if payload.habilitado and CATALOGO[assinatura.plano].overage_centavos_por_credito <= 0:
        # Sem preco de overage, ligar a chave era revelar contato de graca.
        raise HTTPException(
            status_code=402,
            detail="O plano gratuito nao tem consumo alem do limite. Troque de plano.",
        )
    assinatura.overage_habilitado = payload.habilitado
    session.flush()
    return {
        "overage_habilitado": assinatura.overage_habilitado,
        "centavos_por_credito": CATALOGO[assinatura.plano].overage_centavos_por_credito,
    }
