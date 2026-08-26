"""Nivel de autonomia como TRANSICAO de estado da assinatura.

assistido  <-> automatico

Efeito pratico (aplicado pelo SendService na Fase 3):
  * assistido  -> mensagem nasce AGUARDANDO_APROVACAO; nada sai sem humano.
  * automatico -> mensagem nasce APROVADA e vai para a fila, respeitando
                  limites diarios, opt-out e guardrails de canal.

A troca de nivel sempre gera audit_log: e uma decisao com consequencia legal.
"""

from __future__ import annotations

from app.core.errors import TransicaoInvalida
from app.models.enums import NivelAutonomia, StatusAssinatura, StatusMensagem

TRANSICOES_AUTONOMIA: dict[NivelAutonomia, frozenset[NivelAutonomia]] = {
    NivelAutonomia.ASSISTIDO: frozenset({NivelAutonomia.AUTOMATICO}),
    NivelAutonomia.AUTOMATICO: frozenset({NivelAutonomia.ASSISTIDO}),
}

TRANSICOES_STATUS: dict[StatusAssinatura, frozenset[StatusAssinatura]] = {
    StatusAssinatura.ATIVA: frozenset(
        {StatusAssinatura.INADIMPLENTE, StatusAssinatura.PAUSADA, StatusAssinatura.CANCELADA}
    ),
    StatusAssinatura.INADIMPLENTE: frozenset(
        {StatusAssinatura.ATIVA, StatusAssinatura.CANCELADA}
    ),
    StatusAssinatura.PAUSADA: frozenset({StatusAssinatura.ATIVA, StatusAssinatura.CANCELADA}),
    StatusAssinatura.CANCELADA: frozenset({StatusAssinatura.ATIVA}),
}


def validar_autonomia(de: NivelAutonomia, para: NivelAutonomia) -> None:
    if de == para or para not in TRANSICOES_AUTONOMIA.get(de, frozenset()):
        raise TransicaoInvalida("assinatura.autonomia", de.value, para.value)


def validar_status(de: StatusAssinatura, para: StatusAssinatura) -> None:
    if de == para or para not in TRANSICOES_STATUS.get(de, frozenset()):
        raise TransicaoInvalida("assinatura.status", de.value, para.value)


def status_inicial_mensagem(nivel: NivelAutonomia) -> StatusMensagem:
    """Onde a mensagem nasce, dado o nivel de autonomia."""
    if nivel is NivelAutonomia.AUTOMATICO:
        return StatusMensagem.APROVADA
    return StatusMensagem.AGUARDANDO_APROVACAO
