"""Maquina de estados do lead — transicoes VALIDADAS em codigo.

    descoberto -> qualificado -> enfileirado -> abordado -> respondido -> convertido
                          \\            \\            \\           \\
                           +---------- descartado / opt_out ----------+

Regras:
  * opt_out e descartado sao alcancaveis de quase todo estado (o titular pode
    pedir saida a qualquer momento);
  * opt_out e TERMINAL e irreversivel — nunca volta;
  * toda transicao gera audit_log (quem, de onde para onde, por que).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from app.core.errors import TransicaoInvalida
from app.models.enums import StatusLead

S = StatusLead

TRANSICOES: dict[StatusLead, frozenset[StatusLead]] = {
    S.DESCOBERTO: frozenset({S.QUALIFICADO, S.DESCARTADO, S.OPT_OUT}),
    S.QUALIFICADO: frozenset({S.ENFILEIRADO, S.DESCARTADO, S.OPT_OUT}),
    S.ENFILEIRADO: frozenset({S.ABORDADO, S.QUALIFICADO, S.DESCARTADO, S.OPT_OUT}),
    S.ABORDADO: frozenset({S.RESPONDIDO, S.ENFILEIRADO, S.DESCARTADO, S.OPT_OUT}),
    S.RESPONDIDO: frozenset({S.CONVERTIDO, S.DESCARTADO, S.OPT_OUT}),
    S.CONVERTIDO: frozenset({S.OPT_OUT}),
    S.OPT_OUT: frozenset(),  # terminal e irreversivel
    S.DESCARTADO: frozenset({S.QUALIFICADO}),  # reativacao manual e permitida
}

TERMINAIS = frozenset({S.OPT_OUT})

#: Estados em que o lead pode receber abordagem.
ABORDAVEIS = frozenset({S.QUALIFICADO, S.ENFILEIRADO})


@dataclass(frozen=True, slots=True)
class Transicao:
    lead_id: uuid.UUID | None
    de: StatusLead
    para: StatusLead
    motivo: str | None = None


def pode_transicionar(de: StatusLead, para: StatusLead) -> bool:
    if de == para:
        return False
    return para in TRANSICOES.get(de, frozenset())


def validar(de: StatusLead, para: StatusLead) -> None:
    if not pode_transicionar(de, para):
        raise TransicaoInvalida("lead", de.value, para.value)


def proximos(de: StatusLead) -> list[StatusLead]:
    return sorted(TRANSICOES.get(de, frozenset()), key=lambda s: s.value)


def eh_terminal(status: StatusLead) -> bool:
    return status in TERMINAIS
