"""Maquina de estados da campanha."""

from __future__ import annotations

from app.core.errors import TransicaoInvalida
from app.models.enums import StatusCampanha

C = StatusCampanha

TRANSICOES: dict[StatusCampanha, frozenset[StatusCampanha]] = {
    # PAUSADA a partir do rascunho: e o estado de bloqueio por saldo/plano.
    C.RASCUNHO: frozenset({C.DESCOBRINDO, C.PAUSADA, C.CONCLUIDA}),
    C.DESCOBRINDO: frozenset({C.QUALIFICANDO, C.PAUSADA, C.FALHOU}),
    C.QUALIFICANDO: frozenset({C.PRONTA, C.PAUSADA, C.FALHOU}),
    # PRONTA volta para DESCOBRINDO quando o usuario pede uma nova rodada.
    C.PRONTA: frozenset({C.EXECUTANDO, C.DESCOBRINDO, C.PAUSADA, C.CONCLUIDA}),
    C.EXECUTANDO: frozenset({C.CONCLUIDA, C.PAUSADA, C.FALHOU}),
    C.PAUSADA: frozenset({C.DESCOBRINDO, C.QUALIFICANDO, C.PRONTA, C.EXECUTANDO, C.CONCLUIDA}),
    # CONCLUIDA -> PAUSADA: a rodada termina segundos depois do envio, e o
    # bounce/reclamacao chega DEPOIS. Sem esta saida a pausa por reputacao
    # nunca acontecia, e a cadencia seguia mandando o 2o e o 3o toque.
    C.CONCLUIDA: frozenset({C.PRONTA, C.DESCOBRINDO, C.PAUSADA}),
    C.FALHOU: frozenset({C.RASCUNHO, C.DESCOBRINDO}),
}


def pode_transicionar(de: StatusCampanha, para: StatusCampanha) -> bool:
    return de != para and para in TRANSICOES.get(de, frozenset())


def validar(de: StatusCampanha, para: StatusCampanha) -> None:
    if not pode_transicionar(de, para):
        raise TransicaoInvalida("campanha", de.value, para.value)
