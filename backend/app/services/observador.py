"""Observador de execucao — deixa o pipeline contar o que esta fazendo.

Sem isto, "rodar campanha" e uma caixa-preta: o usuario clica, espera e recebe
leads prontos. O raciocinio (que ramos o Cerebro escolheu, que termo buscou,
que empresa casou com a Receita, por que o score deu 44) fica invisivel — e e
justamente a parte que da confianca no produto.

O pipeline emite eventos; quem consome decide o que fazer. A rota SSE
transmite ao vivo para a interface; os testes coletam em lista; quem nao passa
observador nenhum nao paga nada por isso.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

#: Assinatura de quem escuta: recebe a etapa e os dados daquele momento.
Observador = Callable[[str, dict[str, Any]], None]


@dataclass(slots=True)
class Evento:
    etapa: str
    dados: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"etapa": self.etapa, **self.dados}


class ColetorDeEventos:
    """Observador de teste: guarda tudo em memoria."""

    def __init__(self) -> None:
        self.eventos: list[Evento] = []

    def __call__(self, etapa: str, dados: dict[str, Any]) -> None:
        self.eventos.append(Evento(etapa, dados))

    @property
    def etapas(self) -> list[str]:
        return [e.etapa for e in self.eventos]

    def de(self, etapa: str) -> list[Evento]:
        return [e for e in self.eventos if e.etapa == etapa]

    def primeiro(self, etapa: str) -> Evento | None:
        achados = self.de(etapa)
        return achados[0] if achados else None


def emitir(observador: Observador | None, etapa: str, **dados: Any) -> None:
    """Chama o observador se houver um. Nunca deixa o pipeline quebrar por causa
    de quem esta assistindo."""
    if observador is None:
        return
    try:
        observador(etapa, dados)
    except Exception:  # pragma: no cover - observador quebrado nao para a campanha
        pass
