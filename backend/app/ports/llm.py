"""Porta de raciocinio e redacao."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.ports.dto import DiscoveryPlan, EmbeddingResponse, LLMRequest, LLMResponse


@runtime_checkable
class LLMPort(Protocol):
    provedor: str
    modo: str
    modelo: str

    def completar(self, req: LLMRequest) -> LLMResponse:
        """Uma chamada de texto."""
        ...

    def embutir(self, textos: list[str]) -> EmbeddingResponse:
        """Embeddings de dimensao fixa (settings.embedding_dim)."""
        ...

    def orquestrar_descoberta(self, servico: str, regiao: str, contexto: dict) -> DiscoveryPlan:
        """Loop de tool use: transforma servico livre em plano de busca.

        No adaptador real (Fase 7) isso roda o loop com a tool `buscar_empresas`
        (PlacesPort) e a server tool `web_search`. No FakeLLM, devolve um plano
        deterministico equivalente.
        """
        ...
