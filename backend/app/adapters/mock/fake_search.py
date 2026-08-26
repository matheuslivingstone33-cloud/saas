"""FakeSearch — mock do SearchPort (sinais de intencao).

Devolve resultados deterministicos derivados da consulta. O adaptador real
(Fase 7) usa a server tool `web_search` da Anthropic, que roda nos servidores
deles e custa a parte (balde 2).
"""

from __future__ import annotations

from app.adapters.mock._text import slug, tokenizar
from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.ports.dto import SearchResponse, SearchResult
from app.services.cost import CostRecorder, CostSpec

log = get_logger("fake_search")

MODELOS_DE_SINAL = [
    ("{alvo} anuncia expansao de unidade", "noticia de expansao"),
    ("{alvo} abre vaga para manutencao predial", "vaga aberta na area"),
    ("{alvo} investe em eficiencia energetica", "investimento declarado"),
    ("{alvo} reclamacoes sobre climatizacao", "sinal de dor operacional"),
    ("{alvo} certificacao de qualidade renovada", "sinal de maturidade"),
]


class FakeSearch:
    provedor = "search"
    modo = "mock"

    def __init__(self, cost: CostRecorder | None = None, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.cost = cost

    def buscar(self, consulta: str, max_resultados: int = 5) -> SearchResponse:
        alvo = " ".join(tokenizar(consulta)[:4]).title() or "Empresa"
        resultados = [
            SearchResult(
                titulo=modelo.format(alvo=alvo),
                url=f"https://exemplo.com.br/{slug(modelo.format(alvo=alvo))}",
                trecho=f"({motivo}) Conteudo simulado para {alvo}.",
            )
            for modelo, motivo in MODELOS_DE_SINAL[:max_resultados]
        ]
        if self.cost is not None:
            self.cost.registrar(
                CostSpec(
                    provedor=self.provedor,
                    operacao="web_search",
                    chave_preco="search.web_search",
                    quantidade=1,
                    metadados={"consulta": consulta},
                ),
                modo=self.modo,
            )
        log.info("search_mock", consulta=consulta, resultados=len(resultados))
        return SearchResponse(resultados=resultados, buscas_realizadas=1, modo=self.modo)
