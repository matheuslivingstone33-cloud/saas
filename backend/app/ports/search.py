"""Porta de busca web (sinais de intencao)."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.ports.dto import SearchResponse


@runtime_checkable
class SearchPort(Protocol):
    provedor: str
    modo: str

    def buscar(self, consulta: str, max_resultados: int = 5) -> SearchResponse:
        ...
