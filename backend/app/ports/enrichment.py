"""Porta de enriquecimento por CNPJ.

A base da Receita Federal e DADO ABERTO: nao usa chave. O mesmo adaptador
atende dev e producao; muda apenas o tamanho do dataset importado.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.ports.dto import CompanyRecord


@runtime_checkable
class EnrichmentPort(Protocol):
    provedor: str
    modo: str

    def por_cnpj(self, cnpj: str) -> CompanyRecord | None:
        ...

    def buscar(
        self, nome: str, uf: str | None = None, municipio: str | None = None
    ) -> list[CompanyRecord]:
        ...
