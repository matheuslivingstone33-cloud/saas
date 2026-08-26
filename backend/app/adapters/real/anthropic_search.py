"""AnthropicWebSearchAdapter — SearchPort real. FASE 7, implementado.

Usa a server tool `web_search` da Anthropic (mesma ANTHROPIC_API_KEY). Para
claude-opus-5 a variante corrente e `web_search_20260209` (filtragem dinamica).

CUSTO: ~US$10 por 1.000 buscas + os tokens da conversa. Isso e BALDE 2 e e caro
o suficiente para so rodar nos leads de maior valor — o PersonalizationService
ja aplica esse limiar e um teto por lote.
"""

from __future__ import annotations

from typing import Any

from app.core.config import Settings, get_settings
from app.core.errors import ProviderNotConfigured
from app.core.http_client import HttpClient
from app.core.logging import get_logger
from app.ports.dto import SearchResponse, SearchResult
from app.services.cost import CostRecorder, CostSpec

log = get_logger("anthropic_search")

VERSAO_WEB_SEARCH = "web_search_20260209"

SISTEMA = (
    "Voce pesquisa sinais publicos e recentes sobre uma empresa brasileira "
    "(expansao, obra, vaga aberta, mudanca de endereco, certificacao). "
    "Responda em portugues, uma linha por sinal, com a fonte entre parenteses. "
    "Se nao houver sinal relevante, responda exatamente: SEM SINAL."
)


class AnthropicWebSearchAdapter:
    provedor = "search"
    modo = "real"

    def __init__(
        self,
        http: HttpClient | None = None,
        cost: CostRecorder | None = None,
        settings: Settings | None = None,
        cliente: Any = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.http = http
        self.cost = cost
        if not self.settings.anthropic_api_key:
            raise ProviderNotConfigured(
                "ANTHROPIC_API_KEY vazia. Preencha o .env antes de SEARCH_MODE=real."
            )
        self._cliente = cliente

    @property
    def cliente(self):  # noqa: ANN201
        if self._cliente is None:
            import anthropic

            self._cliente = anthropic.Anthropic(api_key=self.settings.anthropic_api_key)
        return self._cliente

    def buscar(self, consulta: str, max_resultados: int = 5) -> SearchResponse:
        with self._guarda():
            resposta = self.cliente.messages.create(
                model=self.settings.llm_model,
                max_tokens=1024,
                system=SISTEMA,
                messages=[{"role": "user", "content": f"Sinais recentes sobre: {consulta}"}],
                thinking={"type": "adaptive"},
                output_config={"effort": "low"},
                tools=[
                    {
                        "type": VERSAO_WEB_SEARCH,
                        "name": "web_search",
                        "max_uses": 2,
                        "user_location": {"type": "approximate", "country": "BR"},
                    }
                ],
            )

        buscas = _contar_buscas(resposta)
        resultados = _resultados(resposta, max_resultados)
        self._registrar(consulta, buscas, resposta)
        log.info("web_search_real", consulta=consulta[:60], buscas=buscas, sinais=len(resultados))
        return SearchResponse(resultados=resultados, buscas_realizadas=buscas, modo=self.modo)

    # -- internos -------------------------------------------------------------
    def _guarda(self):  # noqa: ANN202
        from contextlib import nullcontext

        return self.http.guard("web_search") if self.http is not None else nullcontext()

    def _registrar(self, consulta: str, buscas: int, resposta: Any) -> None:
        if self.cost is None:
            return
        if buscas:
            self.cost.registrar(
                CostSpec(
                    provedor=self.provedor,
                    operacao="web_search",
                    chave_preco="search.web_search",
                    quantidade=buscas,
                    metadados={"consulta": consulta[:120]},
                ),
                modo=self.modo,
            )
        uso = getattr(resposta, "usage", None)
        if uso is not None:
            self.cost.registrar_llm(
                provedor=self.provedor,
                modelo=self.settings.llm_model,
                operacao="web_search.conversa",
                tokens_entrada=int(getattr(uso, "input_tokens", 0)),
                tokens_saida=int(getattr(uso, "output_tokens", 0)),
                modo=self.modo,
            )


def _contar_buscas(resposta: Any) -> int:
    """Quantas buscas a server tool realmente fez (e o que sera cobrado)."""
    uso = getattr(resposta, "usage", None)
    server = getattr(uso, "server_tool_use", None) if uso else None
    if server is not None:
        return int(getattr(server, "web_search_requests", 0) or 0)
    return sum(
        1
        for bloco in getattr(resposta, "content", [])
        if getattr(bloco, "type", None) == "web_search_tool_result"
    )


def _resultados(resposta: Any, maximo: int) -> list[SearchResult]:
    """Le os blocos de resultado; se vier erro, o content e objeto e nao lista."""
    saida: list[SearchResult] = []
    for bloco in getattr(resposta, "content", []):
        if getattr(bloco, "type", None) != "web_search_tool_result":
            continue
        conteudo = getattr(bloco, "content", None)
        if not isinstance(conteudo, list):
            log.warning("web_search_erro", detalhe=str(conteudo)[:200])
            continue
        for item in conteudo:
            saida.append(
                SearchResult(
                    titulo=str(getattr(item, "title", "") or "")[:300],
                    url=str(getattr(item, "url", "") or ""),
                    trecho=str(getattr(item, "encrypted_content", "") or "")[:300],
                )
            )
    if not saida:
        # Sem blocos estruturados, aproveitamos o texto que o modelo resumiu.
        texto = "".join(
            b.text for b in getattr(resposta, "content", []) if getattr(b, "type", None) == "text"
        ).strip()
        if texto and texto != "SEM SINAL":
            saida = [
                SearchResult(titulo=linha.strip(), url="", trecho=linha.strip())
                for linha in texto.splitlines()
                if linha.strip()
            ]
    return saida[:maximo]
